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
## Controlled 100-step prediction-horizon experiment

Training run `20260910T215215-21d288d2ea95` completed a fresh 2,000 MPS updates
with a 100-step horizon. The dataset, sampling seed/order, batch size, small
architecture profile, optimizer and normalization matched the preceding 2,000-step
experiment; the positional-query table grew with the horizon (11,919,980 versus
11,908,460 parameters). Native ARM64 and MPS were verified, CPU fallback was
disabled, and saved checkpoint/processor reloads passed. The run took 1,201.87
seconds, with median/p95 update times of 0.583/0.674 seconds. Its final sampled
loss was 0.4861; the last 50 updates averaged total loss 0.6591 and L1 0.2575.
These are observed development-machine timings, not isolated hardware benchmarks.

Exactly one physical rollout, `20260910T221237-b592ded438b5`, used a ten-action
execution prefix and the unchanged two-second freshness limit. All 23 complete
100-target forecasts passed the guards; 230 targets were executed. The run
**failed** its airborne hold at 11.5 simulated seconds: 0/400 hold samples, no
object lift and zero forbidden contact samples. It took 25.66 wall-clock seconds;
warm inference median/p95 was 44.2/50.4 ms. The failed replay and every raw
forecast are retained. No target clipping, teacher assistance or relaxed scoring
was used.

Diagnostic `20260910T221312-f2b4ee5ef961` compared the same 16 teacher observations
on CPU, scoring only the first ten forecast targets for a matched comparison.
Preprocessing matched exactly and no weights changed. Mean left-joint MAE
**regressed from 0.04882 to 0.18713 rad**. Initial-frame error was 0.2342 rad;
closing-start frame 100 was 0.2612 rad. Prior/posterior-mean errors were again
almost equal (0.187127/0.187128), so this evidence does not implicate inference
latent sampling as the principal cause.

The longer forecast did not learn the initial motion sequence: its first
100-target shoulder-pan range was only 0.0203 rad, versus 0.6839 rad in the
teacher targets. Its first target jumped to +0.548 rad rather than remaining at
home, and the physical trajectory subsequently oscillated between approach-like
poses and gripper openings. Six selected teacher observations (indices 100,
120, 130, 160, 190 and 230) also produced out-of-range gripper targets in offline
forecasts. Those observations were not reached by the physical run; these are
additional offline model defects, not unrecorded physical attempts.

This controlled horizon increase did not improve the baseline. Retain horizon ten
for further development, while keeping the independently tested execution-prefix
interface. The next proposed data experiment is an approach-only bounded skill:
collect collision-checked teacher corrections from a small declared set of
perturbed starting joint positions, train from images and joints, and test whether
it reaches the pregrasp pose from those states before adding closure and transport.
This directly targets the observed closed-loop drift and follows the planned
skill supervisor architecture. It requires explicit dataset/skill lineage and
separate success checks; it has not been implemented by this experiment. Do not
repeat or enlarge training simply because loss falls, and do not add time, phase,
object truth or teacher targets to deployed policy inputs.
## Bounded approach-skill experiment

The next experiment separates open-hand approach from grasping and transport.
This is an experimental local prototype, not a replacement for the dinner-table
workflow. The future supervisor would permit descent and closure only after a
verified pregrasp outcome; a timeout or unsafe hand condition must stop that
transition. No such learned multi-skill supervisor was deployed in this experiment.

Collection protocol `20260910T221849-29cbd0279045` declares six training start-joint
offsets and two separate validation offsets. Only the first five left-arm joints
are changed at simulation reset, before time advances; object poses are unchanged.
Case numbers identify the listed offsets, rather than implying random sampling.
The local collector is `.artifacts/approach-correction-prototype.py`.

| Cases | Split | Left-arm offsets from home, radians |
|---|---|---|
| 1000 | Training | `[0, 0, 0, 0, 0]` |
| 1001 | Training | `[0.08, 0, 0, 0, -0.04]` |
| 1002 | Training | `[-0.08, 0, 0, 0, 0.04]` |
| 1003 | Training | `[0, 0.05, -0.04, 0.03, 0]` |
| 1004 | Training | `[0, -0.05, 0.04, -0.03, 0]` |
| 1005 | Training | `[-0.15, 0.10, 0, 0.09, 0.06]` |
| 2000 | Validation | `[0.04, 0.03, -0.02, 0.02, -0.03]` |
| 2001 | Validation | `[-0.10, 0.06, 0.02, 0.05, 0.02]` |

Each teacher recording has three seconds of bounded, collision-checked motion
followed by one second of settling: 80 confirmed 20 Hz transitions and a terminal
observation, with all three cameras. Success requires 800 contiguous 200 Hz
samples, no robot contacts, no measured joint-limit violation, an open gripper
throughout, and the last 100 samples simultaneously within 2 mm of the pregrasp
point `[-0.15, -0.08, 0.46]` metres, downward-axis error at most 0.02, gripper error
at most 0.03 rad and maximum joint speed at most 0.05 rad/s. The stationary
block's workbench support contact is permitted.

All eight teacher attempts passed. The first collection completed its physics and
recording but hit a NumPy-integer metrics serialization error. Its original trace,
script and recording were retained, rescored and sealed with an explicit recovery
record; it was not physically repeated. Dataset-validation evidence
`20260910T222142-56fe43edcba9` records all eight source run identities. Predicate
negative controls reject duplicated/missing samples, a missed target, closed hand,
moving terminal state and robot contact.

The actual LeRobot dataset `.artifacts/datasets/approach-corrections-v0` contains
only the six training episodes: 480 transitions. The two validation episodes
(160 transitions) were checked for split leakage but excluded from export.
Export-manifest SHA-256:
`f419f580bc986beaff354fdc8e59b511752d61c6b067faa84c6d03d6ce3ef802`.
The dataset seal/read-back and all source evidence were verified.

Training run `20260910T222228-e72392685e90` completed a fresh 2,000 updates with the
small ACT profile, chunk ten, batch one, seed zero, learning rate `1e-5` and the
existing normalization floor. Native MPS ran with fallback disabled. Training
took 421.87 seconds; last-50 mean total loss was 0.5893 and L1 0.1420. Checkpoint
and processor reloads passed. The first launcher stopped on an incorrect function
import before creating a training run; the corrected launcher is retained locally.

Validation protocol `20260910T222439-7d1f591c7b40` froze exactly three physical
attempts before training finished. The local adapter
`.artifacts/approach-policy-validation.py` reuses the existing full-forecast guard
queue, saved ACT processors, two-second freshness limit and explicit inactive-arm
ownership. Images and measured joints are the only policy inputs. IK, teacher
targets, object truth, time and phase labels never enter its inference loop.
The existing full-placement command and its success definition are unchanged.

| Case | Physical run | Final position error | Outcome |
|---|---|---:|---|
| 1000, training start | `20260910T222947-caa04d2ce60e` | 119.32 mm | Failed, 0/100 stable pregrasp samples |
| 2000, validation start | `20260910T222958-f3a92ce97b8d` | 119.32 mm | Failed, 0/100 stable pregrasp samples |
| 2001, validation start | `20260910T223006-e1ce834df9c8` | 3.77 mm | Failed, 0/100 stable pregrasp samples |

All three executed 80 guarded targets over four simulated seconds. No forbidden
contacts, measured limit violations or closed-hand samples occurred. Every run,
proposal, observation and replay is retained. This is **zero learned successes
in three attempts**, including zero in the two validation cases; it is not a
reliability estimate for the complete task. The 2 mm and stability limits were
not relaxed when one case approached the target.

Offline diagnostic `20260910T223207-d0e15ade206d` evaluated ten selected teacher
frames from each of the eight recordings on CPU without changing weights.
Selected training/validation left-joint chunk MAE was 0.02275/0.02262 rad.
Scratch forward kinematics shows that every settled teacher observation predicts
a first target about 3.52 mm from pregrasp, already outside the 2 mm predicate.
At the nominal initial teacher frame, predicted pan is −0.0327 rad versus the
teacher's +0.0006 rad; predicted-versus-teacher tool-target error is 7.83 mm.
Initial target errors across the eight cases range from 5.72 to 31.69 mm.
These are errors on teacher observations, before off-trajectory observations can
be blamed.

The recorded execution then compounds this error. Cases 1000 and 2000 repeatedly
return to a small backward offset near home, approximately 119 mm from pregrasp.
Case 2001 advances toward the goal but remains inaccurate and unsettled. Its final
half-second maximum joint speed is 0.558 rad/s; the other two cases reach about
1.67 rad/s during repeated within-chunk target variations. Initial measured joints
and all three image hashes match the corresponding teacher recording exactly
for all three cases.

Both imperfect supervised fitting and accumulated control error therefore matter.
The next useful change must address measured start/endpoint errors and target
variation, with explicit evaluation of those regions, before expanding the task
or increasing a training budget. No further training is authorized by these
results themselves. Fixed object placement, one scene and eight chosen robot
starts do not establish visual localization or generalization to dinner objects.
Prototype scripts and data remain local artifacts pending reviewed integration;
this experiment is not a reproducible production release.

## Controlled temporal-sampling comparison

Weighted training run `20260910T225506-3f5e98132b20` completed exactly 2,000 MPS
updates in 413.30 seconds from clean commit
`781556df04e6bb6eebe5e1e94320146838904b4f` (`git_dirty=false`). It used the same
480-transition approach dataset, model architecture, initial weights, seed,
optimizer and normalization as the uniform baseline. Initial parameter hashes
match exactly. Only the explicit `approach_regions_v1` sampling profile changed.
Checkpoint, normalization-processor and sampler-RNG reloads all passed.

Realized draws were 684 start, 655 middle and 661 settled observations; the six
episodes received 336, 323, 338, 329, 349 and 325 draws. These regions classify
observation anchors: the normal ten-action training chunk may cross a region
boundary or include episode-end padding. The full probability/source-frame plan
is sealed with the checkpoint. Last-50 mean sampled loss was 0.5586; sampled loss
is not directly comparable across different observation distributions.

Comparison protocol `20260910T225601-e6e5c115c729` retained the same eight teacher
cases and ten frame indices per case. CPU diagnosis
`20260910T230212-7b5dbe7d1c2b` and verified comparison
`20260910T230229-4797222025f2` found the following:

| Selected teacher observations | Uniform mean FK target error | Weighted mean FK target error | Reduction |
|---|---:|---:|---:|
| Training starts | 14.12 mm | 9.50 mm | 32.7% |
| Validation starts | 19.35 mm | 14.28 mm | 26.2% |
| Training settled endpoints | 3.50 mm | 1.18 mm | 66.3% |
| Validation settled endpoints | 3.51 mm | 1.18 mm | 66.3% |

No selected forecast exceeded action bounds. Settled first-target error was now
below the unchanged 2 mm position threshold, and start errors materially improved.
This justified a bounded physical comparison; it did not establish physical
success. Protocol `20260910T230315-a0d0a0ef081f` reused the same three starts, full
forecast guards, two-second freshness, four-second deadline and 100-sample
pregrasp predicate.

| Case | Weighted physical run | Final position error | Final 100 samples passing | Outcome |
|---|---|---:|---:|---|
| 1000, training start | `20260910T230320-5ac4edc886e6` | 18.62 mm | 0/100 | Failed |
| 2000, validation start | `20260910T230331-fc2ae284cf4b` | 6.70 mm | 0/100 | Failed |
| 2001, validation start | `20260910T230339-1566b39a015c` | 1.27 mm | 24/100 | Failed |

All three have 80 confirmed control steps, 800 checked physics samples and zero
forbidden contacts, measured joint-limit violations or closed-hand samples. All
seals verify, and all preceding uniform failures remain retained. The weighted
checkpoint therefore still has **zero successful pregrasp trials in three
attempts**, including zero in the two validation cases.

Trace diagnosis `20260910T230619-9a1f1f4fea4d` explains the partial tolerance result.
Case 2001 first entered the position tolerance at 3.535 seconds but repeatedly
left the combined stable state. Among its last 100 samples, position failed 42
and speed failed 69; orientation and open-hand checks passed throughout. Its
longest uninterrupted passing stretch was only seven samples (35 ms), and only
three passing samples ended the run. Thus 24/100 is a nonconsecutive count and
cannot be read as a successful hold. The new forecast at 3.5 seconds changed its
pan target by 0.0285 rad; the following trajectory was still moving toward the
goal. Cases 1000 and 2000 never entered position tolerance before the deadline,
and also failed orientation/speed checks while approaching.

The weighted nominal first pan target still points backward (−0.0364 rad versus
the teacher's +0.0006), although later forecasts now advance. Case 2000 starts
forward and also progresses. During the final half-second, position error fell
from about 26.3 to 18.6 mm, 8.7 to 6.7 mm and 2.1 to 1.3 mm respectively. The
recorded evidence therefore shows remaining start bias, delayed convergence and
forecast-boundary motion; it does not establish that the policy will settle if
allowed to continue.

**Proposed next single experiment, not yet run:** use this unchanged checkpoint
and the same three starts, with a separately declared eight-second maximum and
success only after 100 consecutive samples satisfy the original physical
predicate. Change no model, sampler, action cadence, bounds, camera expiry or
pose/velocity thresholds. Preserve the four-second failures as failures. This
isolates whether the deadline cuts off converging motion or repeated forecast
changes prevent sustained settling. It must be recorded as a new time-budget
experiment, not a reinterpretation of these results. No further training is
indicated before that distinction is measured.

### Fixed eight-second follow-up

Protocol `20260911T005034-081e3e8a71ed` keeps the weighted checkpoint, three
starts, 20 Hz action cadence, ten-action prefix, full-forecast validation,
two-second freshness and physical tolerances unchanged. It changes the fixed
horizon to eight seconds and still requires all final 100 consecutive physics
samples to satisfy the original predicate. The earlier unexecuted protocol
`20260911T004954-6c7c20f63818` accidentally retained `max_steps=80` alongside
`max_control_steps=160`; it was superseded before any rollout. Neither protocol
changes the outcomes of the four-second experiment.

| Case | Run | Final position error | Passing final samples | Outcome |
|---|---|---|---|---|
| 1000 | `20260911T005034-834068f8f4d3` | 1.448 mm | 37/100 | Failed |
| 2000 | `20260911T005053-4f6648ff4391` | 1.430 mm | 37/100 | Failed |
| 2001 | `20260911T005108-8843a3403dc6` | 1.484 mm | 37/100 | Failed |

All three seals verify; each applied 160 controls and checked 1,600 contiguous,
finite physics samples with no contacts, joint-limit violations or hand closure.
Terminal peak joint speeds were 1.110, 1.110 and 0.974 rad/s against the unchanged
0.05 rad/s stable-hold threshold. Extra time brings all three starts near the
target but does not produce stable convergence. The next experiment should test
replanning cadence and ACT temporal ensembling separately, using unchanged weights
and preserving whole-forecast checks before averaging. No further training is
justified by position error alone.

The new records also retain the original four-second prefix score. Its nested
`teacher_only: true` is an inherited field from the shared teacher scoring helper,
not evidence of teacher execution; the outer record correctly states
`teacher_assistance: false`, and the retained raw ACT chunks/actions establish
learned control. Do not use that inherited field to classify the controller.
Future reuse of this helper must remove that metadata from both score levels.

### Replanning cadence and official ACT temporal ensembling

Protocol `20260911T005658-6ada62ed651f` fixes six diagnostic runs before execution:
three original starts with one-action execution prefixes, then the same three
with LeRobot 0.6.1's `ACTTemporalEnsembler` coefficient 0.01. Both modes infer at
every 20 Hz simulation observation. Neither changes the weighted checkpoint,
images/joint inputs, eight-second horizon, final 100-sample predicate or two-second
freshness. All ten raw forecast actions pass the original guard before any
averaging; the averaged action is separately validated before application. The
ensemble resets on termination/cancellation. No simulator target enters inference.

| Mode | Case | Run | Final error | Final peak speed | Result |
|---|---|---|---|---|---|
| One-step, no ensemble | 1000 | `20260911T005751-61b95aa61391` | 125.734 mm | 0.00364 rad/s | Failed, stalls away from target |
| One-step, no ensemble | 2000 | `20260911T005814-fc678568c304` | 1.157 mm | 0.01865 rad/s | 100/100, pregrasp passed |
| One-step, no ensemble | 2001 | `20260911T005833-83da9f26958d` | 1.142 mm | 0.03586 rad/s | 100/100, pregrasp passed |
| One-step, ensemble 0.01 | 1000 | `20260911T005851-d67583653934` | 122.860 mm | 0.00020 rad/s | Failed, stalls away from target |
| One-step, ensemble 0.01 | 2000 | `20260911T005910-1b05f68e6327` | 0.976 mm | 0.00034 rad/s | 100/100, pregrasp passed |
| One-step, ensemble 0.01 | 2001 | `20260911T005928-f367a4ab5181` | 0.976 mm | 0.00040 rad/s | 100/100, pregrasp passed |

Comparison `20260911T010051-7d76cac619de` verifies all six manifests, identical
checkpoint hashes, declared starts, 160 applied controls, 1,600 physics samples
and 160 fully validated ten-action predictions per episode. Both modes pass two
of three starts; the repeated validation cases are not four independent successful
scenes. The nominal training start remains a failure, so neither is a reliable
pregrasp policy. These open-hand movements are not grasps or full dinner tasks.

Per-step replanning resolves the terminal motion on the two validation starts;
temporal averaging reduces it further. It does not fix the nominal initial-motion
bias. Next inspect that failed trajectory against training coverage and collect
teacher corrections from training-only policy-visited states if warranted. Do not
add the validation starts to training, silently substitute them for nominal, or
claim release generalization from this development comparison. The optional runtime adapter is now integrated and independently tested below;
the nominal policy failure still blocks adoption as a reliable skill.

### Guarded temporal runtime

`policy-rollout --execute-chunk-steps 1 --temporal-ensemble-coefficient 0.01`
enables the optional adapter for compatible rollout checkpoints. Default execution
is unchanged. The coefficient is bounded to 0–1; positive values favor older
forecasts in the pinned LeRobot 0.6.1 implementation. This command still targets
the supported placement interface, not the experimental approach driver.

Every raw forecast is checked before averaging. The averaged action is checked
again before the right-arm ownership mask. The queue requires one consumed action
per advancing observation and clears all history on task changes, cancellation,
stale observations, sequence gaps and invalid targets. Run records retain both
raw and averaged forecasts. One synchronous caller owns the queue.

Thirty base tests and all 33 native training-environment tests pass, including
float32 CPU parity with official ACTTemporalEnsembler for coefficients 0, 0.01
and 1 across overlapping forecasts and reset. These verify runtime behavior,
not manipulation quality. No new physical rollout is claimed by these tests.

### Explicit arm ownership

The shared action queues now accept fixed `controlled_arms` permissions: left,
right, or ordered left/right. The standalone placement command still uses its
existing left-only mode. Permissions do not come from the action model.

All twelve predicted joints are checked before masking, including unowned joints
and later forecast targets. Unowned joints then retain the caller's fixed hold
setpoints for the queue lifetime. Public hold snapshots cannot alter the stored
setpoints. Ownership changes require a new queue, with old action/ensemble history
cleared. Temporal averaging uses the same permissions before final application.

Ownership evidence is now a versioned object containing controlled/held arms,
fixed hold targets and their scope. Historical records with the earlier textual
mask description remain unchanged. ActionChunk schema and target/freshness guards
are unchanged. Thirty-five temporal tests pass in the native LeRobot environment,
including actual official averaging parity; `.artifacts/owned-temporal-real-tests.log`.
