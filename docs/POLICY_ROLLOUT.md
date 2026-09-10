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

## Why the 500-update policy failed

Offline diagnostic `20260910T213333-4b4e28f16c5e` compared the checkpoint against 16
fixed training frames: indices 0, 10, 20, 30, 60, 80, 100, 120, 130, 160, 190, 230,
290, 350, 380 and 420. It also compared the executed targets with the teacher's
trajectory. The script, raw comparisons, checkpoint/dataset identity and metrics
are sealed in that run; integrity was verified. No weights were updated and no
additional physical rollout was attempted.

**The model moves toward a closed carry pose too early. It is not stuck waiting
at the initial idle observation.** At time zero, the teacher commands
`[0, -1, 0.8, 1.2, 0, 0.8]` for the left arm; the learned rollout instead commands
approximately `[0.415, -0.716, 0.725, 1.539, -0.251, 0.165]`.
By three seconds, learned targets are approximately
`[0.745, -0.691, 0.738, 1.509, -0.514, -0.011]`: near the later carry configuration,
with an already closed gripper. They remain around that pose instead of following
the teacher's downward movement toward the block.

| Diagnostic | Observed result | Implication |
|---|---|---|
| Rollout PNG/joint preprocessing versus LeRobot dataset preprocessing | Exactly equal model-input tensors at all 16 frames | No camera-order, pixel-scaling or numeric-normalization mismatch was found |
| Prior inference versus posterior-mean diagnostic | Mean left-joint chunk error 0.184119 versus 0.184122 rad | The training posterior/inference prior difference does not explain this failure |
| Initial teacher frame, known in-distribution input | Prior left-joint chunk error 0.332 rad; gripper prediction 0.164 versus target 0.8 | The policy has not accurately fitted even the start of its training episode |
| Teacher frame 100, start of closing | Prior left-joint chunk error 0.270 rad; first gripper prediction −0.002 versus target 0.797 | Approach/closing distinctions remain poorly learned before closed-loop drift |
| Mean-normalized-image ablation | Mean left-action change about 0.22–0.33 rad across selected frames | Outputs are image-sensitive; this does not establish useful visual grounding or isolate the effect of missing pretrained features |

The posterior comparison is deliberately privileged **offline analysis**: it
supplies the real future demonstration actions to the VAE encoder, keeps dropout
disabled and sets reparameterization noise to zero. It never supplies those
future actions to the deployed rollout. The maximum prior/posterior-mean action
difference was only 0.0000263 rad across the selected frames. The measured error
therefore persists even when that latent pathway has access to the target chunk.

The evidence is consistent with underfitting of observation-conditioned motion
and confusion between parts of the trajectory. It does not isolate the precise
contribution of random visual initialization, transformer size or data scarcity.
The ten-step prediction horizon may still limit sequencing, but removing the
one-second leading dwell would not directly correct the observed premature
movement and closure.

**Recommended next single experiment:** keep the dataset, seed, small architecture,
normalization, ten-step chunk and optimizer unchanged; train a fresh, bounded
2,000-update checkpoint. Evaluate the same 16 prior-inference frames, reporting
initial/approach/closing errors separately, then attempt one physical rollout.
This changes training duration alone and tests whether the obvious training-set
underfit improves. It is a proposed experiment, not work performed by this
analysis. Do not add time, phase labels, object poses or teacher actions as model
inputs, and do not relax contact/placement checks.

If a subsequent experiment changes prediction horizon to 100, separate that
training horizon from the number of queued targets executed before observing
again. Consuming all 100 targets may exceed the present two-second freshness
budget. Prefer a declared short execution prefix and fresh replanning; do not
silently extend expiry to make a longer chunk run.

Two initial diagnostic-script failures were preserved as
`20260910T213224-157f3ddec11c` and `20260910T213308-a35d4f6a9845`: the first compared
processor metadata with tensors; the second omitted training-style action
batching. The successful diagnostic corrected both. These were analysis harness
errors, not further training or robot attempts.

## Controlled 2,000-update duration experiment

The proposed duration-only experiment was completed as training run
`20260910T213909-88c7e1c3a78b`. It used the same dataset, seed, batch size 1, small
architecture, ten-step chunk, optimizer and normalization. The relevant training
source files were byte-identical to the 500-update baseline, and the first 500
sample indices and losses matched exactly. The fresh 2,000-update run took 424.72
seconds on MPS; median/p95 update times were 0.204/0.234 seconds. Both checkpoint
and processor reload checks passed. Its final sampled loss was 0.4135; the last
50 sampled updates averaged total loss 0.6353 and L1 0.1575.

Exactly one physical rollout, `20260910T214631-6fd7bfd78a0c`, was attempted. It
**failed** at 11.5 simulated seconds with 0/400 airborne hold samples, no object
lift and zero forbidden contact samples. It executed 230 steps from 23 valid
chunks and took 22.58 wall-clock seconds. The block remained at its pickup
location. The checkpoint, physical run and diagnostic manifests were verified.

Fixed-frame diagnostic `20260910T214716-29f5dca0583e` repeated the same 16 teacher
frames on CPU, with no parameter updates. Input preprocessing still matched
exactly. Mean left-joint chunk MAE improved from **0.1841 to 0.04882 rad** (73.5%)
on those selected training frames. Initial-frame error improved from 0.3316 to
0.0520 rad; frame 100, at the start of closing, improved from 0.2703 to 0.0430 rad.
Prior and posterior-mean errors remained essentially equal (0.048817/0.048814).
These are training-frame improvements, not held-out or physical success rates.

The physical failure changed. The initial predicted gripper target was now 0.838,
close to the teacher's open target 0.8. However, initial shoulder-pan target
−0.011 rad drifted to −0.155 rad after one second and about −0.797 rad after three
seconds. The teacher's pickup approach instead requires positive pan near +0.684
rad. The policy therefore moved toward the later placement-side branch without
picking up the block. Initial joint values and all three camera images were
identical to the corresponding teacher observation; the failure cannot be
explained by a different initial scene.

This establishes that additional optimization improves fitting, while small
closed-loop errors can still lead into the wrong part of the trajectory. It
motivates a separate prediction-horizon experiment rather than claiming that
training loss is sufficient. A longer forecast will retain an explicit short
execution prefix and unchanged full-chunk/expiry checks. Replanning every ten
steps during a twenty-step initial dwell may still restart an idle prediction;
that limitation must remain visible when interpreting the next experiment.

## Prediction horizon and executed prefix

`PolicyRolloutConfig.execute_chunk_steps` now declares how many targets may be
executed from each forecast before capturing a fresh observation and replanning.
It defaults to ten. A 100-step forecast can therefore be assessed without queuing
five seconds of motion from one old observation. The raw and accepted records
retain the complete forecast, prediction length, executed-prefix length and
number of discarded forecast steps.

Every target in the full forecast is validated before any prefix enters the
queue. An invalid 100th target rejects the entire proposal even when only ten
steps would have been executed, and even when the invalid target belongs to the
supervisor-held right arm. Short-prefix execution does not extend the two-second
source-observation expiry. Cancellation and stale identities still clear all
pending actions. Tests cover these distinctions and verify that the next prefix
uses the new current observation identity before execution.

The next controlled experiment changes the ACT prediction horizon from ten to
100 while retaining a ten-step execution prefix and the existing guards. This
may improve the sequence the model learns, but it does not by itself guarantee
escape from a leading idle segment when every short replan restarts that segment.
The result must be measured; phase/time labels and teacher targets remain excluded.
