# Learned ACT placement diagnostic

The rollout runs an actual saved ACT policy in the practice-block placement
scene. It uses the saved image/state preprocessor and inverse action processor.
Every active-arm target comes from the learned prediction. No inverse kinematics,
scripted motion target, object position or contact score enters the policy.

This is a **training-scene diagnostic**, not a held-out evaluation or a complete
dinner-table workflow. A successfully loaded model can still fail to grasp.

## Running locally

Use the verified native training environment:

```sh
HF_HOME="$PWD/.artifacts/huggingface" .artifacts/training-venv/bin/bimanual policy-rollout .artifacts/runs/20260910T211456-55d5d5db50cc --device cpu
```

The command returns a nonzero exit status when physical acceptance fails. The
Python API also supports an operator cancellation callback:

```python
from pathlib import Path
from bimanual.evidence import EvidenceStore
from bimanual.policy_rollout import PolicyRolloutConfig, run_policy_rollout

result = run_policy_rollout(
    PolicyRolloutConfig(
        training_run=Path(".artifacts/runs/20260910T211456-55d5d5db50cc"),
        device="cpu",
    ),
    store=EvidenceStore(Path(".artifacts")),
    project_root=Path.cwd(),
)
print(result.model_dump_json(indent=2))
```

Run with `.artifacts/training-venv/bin/python`, native ARM64, and
`HF_HOME="$PWD/.artifacts/huggingface"`. Rendering requires macOS graphics access.
MPS is an explicit alternative; start a fresh process with
`PYTORCH_ENABLE_MPS_FALLBACK=0`. CPU and MPS are separate requested devices;
unsupported MPS must fail visibly. Model loading is local only.

The checkpoint must come from a sealed, completed `act_training` run with verified
checkpoint and processor reloads. Its file digests are checked before loading,
and its checkpoint bundle is copied into the new evidence run. The training
manifest and dataset-manifest identity remain linked. The adapter checks every
source scene digest and source configuration against the declared placement:
left arm, 25 g block at `(-0.15, -0.08)`, destination `(-0.15, +0.08)`, no injected
faults. Keep the exported dataset available for those source-config checks.
Relative dataset paths resolve against `project_root`; when moving to another
host, migrate the referenced artifacts as well as the code.

## Control and observations

The policy receives exactly four fields: three channel-first RGB camera tensors
and the twelve measured joint positions. Images start as uint8 and are converted
to float32 `[0,1]` before the saved normalization pipeline. Camera order is
`overhead`, `left/wrist_cam`, `right/wrist_cam`. Velocities, contact forces, object
poses, phase labels and time are absent from model inputs.

ACT predicts an entire action chunk. The adapter first checks the shape and all
finite joint bounds in every raw target, including later targets and the inactive
arm. It does not clip a bad prediction. The supervisor then holds the right arm
at its reset targets; the six predicted left-arm targets stay unchanged. Both the
raw and accepted chunks and the explicit ownership mask are recorded.

Before each applied action, the queue rechecks episode identity, observation
sequence, source-observation age and wall-clock expiry. Default expiry is two
seconds from the observation capture; it does not extend when inference ends.
A stale target is rejected rather than executed. Cancellation clears queued
actions and resets ACT's internal queue. A callback passed as `cancelled=` can
connect an operator stop control; `KeyboardInterrupt` is also recorded.

Each accepted target advances ten 5 ms physics steps. Live contact/penetration
checks remain active. No object welding, teleporting or artificial force is added.
Observations and strict JSON action logs are recorded alongside camera images,
replay and privileged scoring truth. Scoring truth is kept separate from policy
inputs. A partially applied failed control step is marked `applied=false`; the
physics trace preserves what happened before the stop.

## Physical checks and limits

The maximum diagnostic duration is 23 simulated seconds. The independent
scorer uses the declared teacher experiment's phase clock: settle, approach,
descend, close, lift, hold, transport, lower, release, retreat and final settling.
These labels also control which contacts the existing experiment guard allows;
they are not model inputs or scripted joint targets. This timing constraint is
part of the diagnostic, not a general-purpose learned skill supervisor.

At 11.5 seconds the rollout stops if the two-second airborne bilateral hold did
not pass. Otherwise it continues toward transport and release, requiring the
same sustained-contact, stable-placement, collision and timestamp checks as the
teacher baseline. A shorter configured time limit cannot manufacture completion.
The adapter reports full-task `manipulation_success=null`; it only claims learned
practice-block placement if all physical placement checks pass.

## First attempted learned rollout

Run `20260910T212314-08d05dd65d98` used the three-step CPU checkpoint
`20260910T211456-55d5d5db50cc`. Its manifest integrity was verified.

- Outcome: **failed**, because the object never passed the airborne hold check.
- Executed 230 control steps from 23 accepted ACT chunks, reaching 11.5 simulated
  seconds in 24.71 wall-clock seconds including rendering and recording.
- Airborne bilateral hold: **0/400** samples; the block remained at pickup.
- Forbidden contact samples: **0**; maximum penetration approximately **0.39 mm**.
- Retained 690 RGB images, raw/accepted action chunks, physics truth and a replay.

This is useful evidence that the image-to-action execution path works and that
an unsuccessful learned policy is reported honestly. It does not prove a useful
manipulation policy. The later terminal-observation recording and CPU-thread
configuration additions are covered separately by tests; this original run is
preserved under its actual working-source digest.

## Exercise: read a failed learned run

Open its replay, then compare the first `raw_chunk` and `accepted_chunk` in
`action-chunks.jsonl`. Which values changed, and why can we still say the left arm
was learned control? Feedback: only the six right-arm targets were held at reset
by explicit ownership; the six left-arm targets were used unchanged. Explain why
23 accepted action chunks and zero collisions do not imply a successful grasp.
The missing evidence is sustained bilateral airborne contact and final release.

See [training](TRAINING.md), [interfaces](INTERFACES.md), and the
[contact experiment](CONTACT_GRASP.md) for the related model, contract and physics
boundaries. Keep learning exposure separate from demonstrated understanding.

## Bounded 500-update experiment

Training run `20260910T212647-8c539d28090b` performed exactly 500 updates on the same
single training episode (460 transitions), using the small ACT profile, MPS,
float32, four CPU threads and disabled MPS CPU fallback. It completed in 110.93
seconds, with median update time 0.200 s and p95 0.226 s. Checkpoint and both
processor reload checks passed; the manifest was verified.

The first sampled training loss was 32.678 and the final sampled loss 0.989;
the last 50 updates averaged 1.280. These batches contain different randomly
sampled training frames. This is neither a paired loss comparison nor validation
performance. The final loss components were L1 0.236 and KL 0.0754.

Exactly one subsequent physical diagnostic was attempted:
`20260910T212856-6da67f992681`, on MPS with the new checkpoint. It **failed** at
11.5 simulated seconds, again with 0/400 airborne bilateral hold samples. All 23
chunks passed the action guard and all 230 control steps executed, but the block
remained at pickup. There were zero forbidden contact samples. Total wall time
was 22.45 seconds; warm inference p50/p95 were 42.1/45.2 ms (22 samples, excluding
the first 591 ms inference). The manifest, terminal observation and replay were
verified. No further training was started after inspecting that outcome.

The lower training loss has not translated into contact-based pickup. The next
investigation must compare actual learned trajectories with the demonstrated
skill and improve data coverage or training accordingly; it must not substitute
scripted active-arm targets or weaken the physical success check. Both failed
rollouts remain available. They are separate training-scene diagnostics, not a
frozen release evaluation suite.
