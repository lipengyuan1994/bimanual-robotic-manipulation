# Local ACT training and inference runtime

The ACT runtime probe executes the actual LeRobot policy, including its ResNet18
image backbone, transformer, variational training objective, backward pass and
AdamW optimizer. It accepts three RGB cameras and twelve joint values, matching
the planned two-arm interface. This checks whether our local machine can run the
operations needed for training. **Synthetic probe results do not establish that
an arm can manipulate an object, or that a trained policy exists.**

## Environment and commands

Use the isolated, verified native environment at `.artifacts/training-venv`.
It contains the frozen `training` extra: Python 3.12, LeRobot 0.6.1, PyTorch 2.11.0
and torchvision 0.26.0. The ordinary `.venv` can continue running the simulator
without requiring LeRobot. Verify architecture before selecting an interpreter:

```sh
.artifacts/training-venv/bin/python -c 'import platform; assert platform.machine() == "arm64"; print(platform.python_version())'
HF_HOME="$PWD/.artifacts/huggingface" .artifacts/training-venv/bin/bimanual training-probe --device cpu --architecture default
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HOME="$PWD/.artifacts/huggingface" .artifacts/training-venv/bin/bimanual training-probe --device mps --architecture small --train-steps 2
.artifacts/training-venv/bin/python -m pytest -q tests/test_training_probe.py
```

MPS needs access to macOS Metal services. A sandboxed process can report MPS
unavailable even on this Mac; the probe records that as a failed requested-device
run. Start a fresh process with `PYTORCH_ENABLE_MPS_FALLBACK=0`. An unavailable MPS
device, LeRobot device substitution, or enabled CPU fallback is rejected. CPU is
an explicit separate profile. No model weights are downloaded and nothing is
uploaded to Hugging Face. The cache directory stays inside `.artifacts`.

## What the probe records

Every invocation creates an immutable `act_runtime_probe` evidence run, including
failures. The manifest binds the source revision and dirty-source digest, full
probe settings, exact library versions, requested/actual device, precision, seed,
input hash, initial and updated parameter hashes, finite gradient checks, loss
components, and output shape/hash. `act_config.json` contains the full resolved
LeRobot configuration. A small synthetic action array is an inspection artifact;
it must never be loaded as a trained policy or sent to the simulator.

The probe measures initialization including imports, individual training steps,
first inference latency, subsequent inference latencies and their p50/p95.
MPS timers synchronize the device, so GPU dispatch alone cannot masquerade as
completed work. Three warm samples are a smoke check, not a robust deployment
benchmark. Run manifests preserve all raw latency samples. Seeded inputs are
identical across devices; bitwise equality of device arithmetic, dropout or
sampling is not promised. Deterministic-algorithm settings are recorded.

Default inputs are batch size 1, three 270×480 RGB images in channel-first float32
`[0, 1]`, twelve synthetic state values in `[-1, 1]`, and ten synthetic target
steps of twelve values in `[-1, 1]`. The probe intentionally bypasses dataset
normalization: these are synthetic already-scaled tensors, not radians from a
recorded demonstration. A real trainer must persist and reuse fitted image,
state and action preprocessing and inverse action transforms.

| Profile | Transformer configuration | Intended use |
|---|---|---|
| `small` | width 128, four heads, feedforward 512, one main encoder/decoder layer, one VAE encoder layer, latent width 16 | Cheap operation compatibility check |
| `default` | LeRobot ACT defaults, full resolved settings saved in each run | More representative local resource probe |

Both retain the actual ResNet18 backbone and VAE. Both start randomly because
`pretrained_backbone_weights=None`. Chunk size defaults to ten instead of the
upstream hundred; this is a disclosed probe setting, not a final policy choice.
The optimizer and gradient clipping use ACT's optimizer preset. No runtime-only
model is published or offered as a deployable checkpoint.

## From runtime checks to a learned skill

1. Validate successful contact-based teacher demonstrations and preserve failures.
2. Keep training, validation and held-out test seeds separate before fitting.
3. Export camera/joint/action records to LeRobot and inspect synchronized samples.
4. Fit preprocessing only on training data, train ACT, and save dataset/checkpoint
   lineage and both forward/inverse processors.
5. Evaluate learned actions through the same joint limits, ownership, freshness
   and contact checks as other control paths. A loss reduction alone is not success.
6. Keep all attempted rollouts and report contact-based task outcomes separately
   from runtime, throughput and export checks.

The [interface contract](INTERFACES.md) defines camera ordering, units and
observation/action identity. The [roadmap](ROADMAP.md) retains the full workflow,
Intel and production requirements; passing this probe does not complete M2.

## Troubleshooting

The installed OpenCV and PyAV wheels both load an AVFoundation Objective-C class
on this Mac, which prints duplicate-class warnings during LeRobot import. The
runtime probes completed despite those warnings. This is an unresolved packaging
warning; it is not evidence that video capture/encoding combinations are safe.
Do not delete shared libraries or change the dependency lock to hide the warning.

A missing `lerobot` import means the simulator environment was selected instead
of the isolated training environment. The ordinary test suite skips the actual
ACT test when LeRobot is absent; that skip is not a training-runtime pass.

## Fifteen-minute learning exercise

An observation answers “what can the policy see now?” An action chunk answers
“which joint targets should it propose for the next few control steps?” With
20 Hz control, ten predicted steps cover half a second. Training compares those
proposals with the demonstrator's actions and updates model parameters; inference
predicts without updating parameters.

Inspect one probe manifest and find the camera resolution, chunk size, finite
gradient count and two different model-state hashes. Explain why these prove that
training operations ran but do not prove a successful grasp. Then calculate the
prediction horizon for chunk size 20 at 20 Hz. Feedback: it is one second, and a
synthetic loss has no physical contact or placement outcome to score. Completing
this reading is exposure; demonstrated understanding should be recorded only
after the learner responds.

References: [LeRobot ACT](https://huggingface.co/docs/lerobot/act) and the installed,
version-pinned `lerobot/policies/act/configuration_act.py` and `modeling_act.py`.

## Initial native runtime evidence (September 10, 2026)

These exploratory runs used the working tree, not a clean release checkpoint.
Both use three 270×480 images, batch size 1, chunk size 10 and float32. The two
profiles differ in architecture, so these numbers are not an apples-to-apples
CPU/GPU speed comparison. Timing samples are too few for a performance guarantee.

| Device/profile | Run | Parameters | Training step 1 / step 2 | Warm inference p50 / p95 |
|---|---|---:|---:|---:|
| CPU/default ACT | `20260910T210908-f0695741a656` | 51,563,404 | 0.952 / 0.832 s | 160.9 / 167.7 ms |
| MPS/small ACT | `20260910T210906-baf0b4ad24cb` | 11,908,460 | 3.007 / 0.206 s | 35.9 / 37.6 ms |

Both completed two actual optimizer steps with finite gradients, changed model
hashes, and finite `(1, 10, 12)` inference outputs. Their evidence manifests were
verified. MPS ran with CPU fallback disabled and all model parameters on `mps:0`.
The first MPS step includes compilation and startup costs; the second is useful
only as an early feasibility measurement.

Earlier preserved probes `20260910T210618-ae7316efc5ca` (CPU/small),
`20260910T210728-e71096c75a5f` (CPU/default), and
`20260910T210741-440a3ea5f49e` (MPS/small) also completed. Those exploratory versions
used AdamW's generic weight-decay default and a clipping threshold of one.
The later runs above use the ACT optimizer preset (weight decay 0.0001,
clipping threshold 10). Their results are not silently pooled together.

No real-data learning, grasp outcome, generalization, OpenVINO export or Intel
hardware compliance is claimed by these runs.

## Real-data duration measurements

The single-episode placement experiments use 460 confirmed training transitions,
three 270×480 RGB views, the small ACT model, batch size 1, chunk size 10 and MPS
with CPU fallback disabled. They start fresh from the same seed and use the same
optimizer and preprocessing.

| Training run | Updates | Total time | Median / p95 update time | Physical follow-up |
|---|---:|---:|---:|---|
| `20260910T212647-8c539d28090b` | 500 | 110.93 s | 0.200 / 0.226 s | Failed airborne hold |
| `20260910T213909-88c7e1c3a78b` | 2,000 | 424.72 s | 0.204 / 0.234 s | Failed airborne hold |

The first 500 sampled indices and losses matched exactly across these two runs;
this is observed reproducibility for this configuration, not a guarantee across
hardware or library versions. Both checkpoint/processor reload checks passed.
The longer run reduced left-joint MAE on 16 selected training observations from
0.1841 to 0.04882 radians, but its one physical rollout still failed. Read the
[trajectory diagnosis](POLICY_ROLLOUT.md) for why closer training predictions did
not establish a working grasp. These measurements support local compute planning;
they do not establish learned task quality, generalization or Intel compliance.

## Longer prediction horizon: measured regression

The controlled fresh 2,000-update MPS run
`20260910T215215-21d288d2ea95` increased the horizon from ten to 100. It kept the
same 460-transition dataset, sampling seed/order, batch size 1, small architecture
profile, learning rate and normalization; the larger positional-query table added
11,520 parameters. Native ARM64, actual MPS with fallback disabled, and saved
checkpoint/processor reloads were verified. Total training time was 1,201.87
seconds, median/p95 step time 0.583/0.674 seconds, and last-50 mean loss 0.6591.

The single rollout `20260910T221237-b592ded438b5` executed only ten targets per
fresh forecast while validating all 100, retaining the two-second expiry. It
failed at 11.5 simulated seconds with no lift and 0/400 airborne hold samples.
The same 16-frame diagnostic `20260910T221312-f2b4ee5ef961` used a matched first-ten
action comparison: mean left-joint MAE worsened from 0.04882 to 0.18713 rad.
Preprocessing was exact and weights stayed unchanged. All three evidence seals
were verified. The [rollout analysis](POLICY_ROLLOUT.md) records the nearly constant
initial forecast, additional offline bound failures, timings and proposed bounded
approach-skill dataset experiment. No further training increase is justified by
these results alone; neither checkpoint has demonstrated learned manipulation.

## Approach-only dataset and failed learned validation

The next bounded experiment used six physically verified teacher approach
recordings (480 transitions) and two excluded validation recordings. Dataset
`.artifacts/datasets/approach-corrections-v0` and validation summary
`20260910T222142-56fe43edcba9` preserve the source identities and split checks.
The teacher moves an open hand to pregrasp; no grasp or full-task label is assigned.

MPS training `20260910T222228-e72392685e90` completed 2,000 updates in 421.87 seconds
with chunk ten and the same small ACT/optimizer settings. Reload checks passed;
last-50 mean loss was 0.5893. The three predeclared physical attempts all failed
the unchanged 2 mm/100-sample pregrasp predicate. They retained safe open hands
and had no forbidden contacts or limit violations, but two stayed roughly 119 mm
from target and the third finished 3.77 mm away without settling.

Offline teacher-frame diagnostic `20260910T223207-d0e15ade206d` found mean selected
training/validation joint errors of 0.02275/0.02262 rad. Even settled teacher
observations predict a tool target 3.52 mm from pregrasp, outside the threshold;
closed-loop starting errors then compound. These results identify a fitting and
control problem, rather than proving that more varied data alone resolves it.
The [complete approach record](POLICY_ROLLOUT.md) lists every physical run,
protocol, predicate, dataset digest, launch/finalization recovery and limitation.
No further training or replacement validation attempts were made.

## Explicit temporal sampling experiment

Uniform sampling remains the default and preserves the original `torch.randint`
call and CPU-generator sequence exactly. A separate, opt-in
`ACTTrainingConfig.sampling_profile="approach_regions_v1"` changes only which
training frames are drawn. It does not add time, phase or task truth to the policy.

The new profile requires `sampling_protocol_run` to name the sealed approach
collection protocol. For the existing dataset, use
`.artifacts/runs/20260910T221849-29cbd0279045`. The loader verifies its seal, kind,
configuration and declared motion/settle counts, then matches each copied
training episode's skill, protocol identity, case, target and length. An unrelated
protocol, wrong task, missing/empty region or inconsistent episode is rejected.
The dataset and protocol must therefore travel together for remote reproduction.

Each training episode receives equal probability. Within an episode, probability
is allocated as follows; endpoints are exclusive:

| Region | Source frame indices in the current 80-transition episode | Probability within episode |
|---|---|---:|
| Start | `[0,10)` | 1/3 |
| Middle motion | `[10,60)` | 1/3 |
| Settled endpoint | `[60,80)` | 1/3 |

The first ten frames are fixed by the named profile; the motion boundary and
settling length come from the verified collection configuration. Frames within
each region have equal probability, and every training frame remains eligible.
For six episodes, each episode/region has total probability 1/18. Individual
start/middle/settled-frame probabilities are 1/180, 1/900 and 1/360 respectively,
versus the uniform baseline's 1/480. Draws use replacement and a seeded CPU
`torch.multinomial` with float64 probabilities. Validation outcomes, evaluator
truth and held-out frame labels do not influence these probabilities.

`sampling-plan.json` records every global dataset index, episode identity,
original source-frame index, source episode hash, region and probability, plus
the sealed collection protocol. The same plan is copied into the checkpoint as
`training_sampling.json`; its digest and the sampler RNG state are preserved in
`trainer_state.pt`. Each update records the selected source-frame identities.
After saving, training reloads that state and verifies the next batch matches,
without advancing the persisted RNG state. This is RNG continuation evidence;
a general interrupted-training resume command is not implemented.

Focused tests verify exact default sampling compatibility, per-episode/region
probability mass, complete source-index coverage, deterministic RNG restoration,
and incompatible or corrupted protocol rejection. The real ACT reload test also
checks sampler/checkpoint lineage when explicitly enabled. The planned controlled
comparison keeps the approach dataset, model, seed and 2,000-update count fixed;
per-region teacher-frame errors must be assessed before deciding on further
physical attempts. The new profile has not yet demonstrated an improvement.

## Temporal-sampling result: better fit, no completed learned skill

The declared weighted run `20260910T225506-3f5e98132b20` completed 2,000 native MPS
updates in 413.30 seconds from clean commit `781556df04e6bb6eebe5e1e94320146838904b4f`.
Its initial parameter hash matched the uniform baseline; dataset, architecture,
seed, optimizer and normalization were unchanged. Realized start/middle/settled
anchor draws were 684/655/661. Checkpoint, processor and sampler-RNG reloads passed.
Regions classify observation anchors; future action chunks may cross regions or
include normal episode-end padding. Sampled loss is not a common evaluation metric
when the sampling distribution changes.

Frozen teacher-frame comparison `20260910T230229-4797222025f2` shows start FK error
reductions of 32.7% on training observations and 26.2% on validation observations.
Settled target error fell about 66.3%, from 3.50 mm to 1.18 mm. This justified the
same three guarded physical checks, but **all three still failed**: final errors
were 18.62, 6.70 and 1.27 mm, with 0/100, 0/100 and 24/100 final passing samples.
The last case's longest continuous passing stretch was only seven samples, so
its final position accuracy does not establish a stable pregrasp.

The [full weighted comparison](POLICY_ROLLOUT.md) retains every protocol, run,
physical outcome and trace diagnosis. It proposes a separate bounded time-budget
experiment with unchanged weights and physical thresholds to distinguish delayed
convergence from persistent forecast-boundary motion. That experiment has not
been run, and no additional training or retries were performed.

## Nominal stall after per-step replanning: training-only diagnosis

The [cadence comparison](POLICY_ROLLOUT.md) fixes terminal motion on two development
validation starts, while nominal training case 1000 still stalls about 123 mm
from pregrasp. Analysis `20260911T012244-b6feaf688748` compares only that nominal
policy trajectory against the six training recordings and retained training-frame
predictions. No model load, training or physical run was required.

Residual fitting error is the clearest initiating defect. At reset, every measured
joint and all three camera-image hashes exactly match nominal training frame 0,
yet the policy predicts pan −0.036375 rad against teacher +0.000564 rad. Retained
teacher-frame inference has 6.615 mm FK target error there and backward targets
at frames 1 and 5 too. Frame 0 received only six sampled updates. Missing reset
coverage cannot account for an error at this exact recorded input.

The policy subsequently enters a region without matching correction examples.
After one control step, its minimum distance to the continuous training teacher
paths is 0.02935 rad across the five active arm joints. At the final stalled
observation it is 0.03770 rad from the closest path, case 1002 near frame 6.
That neighboring teacher example advances pan by +0.007408 rad; the stalled
policy's raw first forecast instead requests −0.010304 rad, and temporal averaging
holds it almost stationary. These distances describe joint-space coverage, not
a calibrated novelty threshold or image-feature coverage. They support a
sustaining coverage gap, but do not override the directly observed fitting defect
that starts the failure. A numerical causal allocation is not established.

The proposed next single experiment retains all 480 training transitions and the
same model, seed, optimizer and 2,000-update budget. Allocate one third of draws
to nominal training frames `[0,10)`, one third to all training settled frames
`[60,80)`, and one third to all remaining training frames. This changes sampling
alone, retains endpoint probability mass and keeps every training frame eligible;
it intentionally changes episode balance. First assess nominal launch direction,
per-region teacher/FK errors and endpoint accuracy before new physical trials.
The reduced attention to other training starts is an explicit tradeoff to measure.
All masks must derive from verified training configs, and all probability/RNG
lineage must be saved. No validation states were used to choose this design.
The proposal and detailed limits are preserved locally in
`.artifacts/nominal-launch-proposal.md`; implementation and measured results follow.


The follow-up is now preregistered as protocol `20260911T013418-850e2f3250df`.
Before any new physical run, compare the same retained training observations:
the nominal first pan increment must be positive, mean first-target joint/FK
errors at nominal frames 0/1/5 must each improve by at least 25%, settled mean
FK error may increase at most 0.5 mm, and other training starts' mean joint error
may increase at most 20%. All selected frames are reported. These are internal
development gates, not event requirements or manipulation success. Only a passing
offline comparison advances to the unchanged eight-second physical suite.
The `approach_nominal_launch_v1` sampler is implemented and verified against the
actual 480-frame dataset: groups 10/120/350 each receive one third of total mass.
It derives a unique nominal episode from the verified zero-offset training config,
retains all frames and ordering, and records truthful conditional probabilities.
Focused tests: 32 passed, one real-ACT check explicitly skipped. The completed
training experiment is recorded below.


## Nominal launch experiment result

Clean sampler checkpoint `497e23a366d512554f22cc21c745ad54c338ba81` trained run
`20260911T014325-bad8e53b82db`: 2,000 updates on native MPS in 415.15 seconds,
11,908,460 parameters, unchanged 480-frame dataset. Checkpoint, processors and
sampler reload checks pass. Training and evidence seals verify.

Training-only offline run `20260911T015030-96f6a94b5887` leaves weights unchanged.
Comparison `20260911T015050-0e94cba7b117` applies the preregistered gates:

| Measure | Previous model | Nominal-launch sampler |
|---|---:|---:|
| Nominal launch mean first-joint error | 0.013894 rad | 0.008822 rad |
| Nominal launch mean tool-target error | 6.960 mm | 2.828 mm |
| Settled mean tool-target error | 1.180 mm | 1.918 mm |
| Other training starts mean first-joint error | 0.020952 rad | 0.031087 rad |

The launch error reductions pass, but the nominal first pan target is still
negative, settled error exceeds the allowed 0.5 mm increase, and other starts
exceed the allowed 20% regression. The offline gate **fails**. No physical test
was attempted with this checkpoint, and it is not promoted. The result demonstrates
a sampling tradeoff, not reliable learned control. Investigate fitting capacity,
initialization and training duration before another preregistered intervention;
keep the validation scenes excluded from training design.


## Matched no-VAE ACT experiment

Analysis `20260911T015525-e3f5eb07e758` identifies a testable training/inference
difference in installed LeRobot: the standard action-conditioned VAE samples a
latent vector during training, while inference uses zero. The latest run sampled
nominal frame zero 71 times but still predicted backward. Every update clipped
the aggregate gradient; final weighted KL was about 3.6 times reconstruction loss.
This does not prove KL caused clipping or caused the failed movement.

Protocol `20260911T015715-5ef000508650` changes only to ACT's supported `use_vae=False`
mode at the same 2,000 updates, data, nominal-launch sampler, optimizer and dropout.
The optional encoder/KL objective is removed and the latent is zero during both
training and inference. Standard ACT remains the default; `train --no-vae` selects
this experimental mode. No teacher action enters deployed inference in either mode.

To avoid an initialization confound, the trainer first constructs the standard
seeded model, copies every shared parameter and buffer to the ablated model, and
restores the CPU RNG after that extra construction. It records hashes and all
removed state keys. Verification `20260911T015639-f799b069df61` reproduces the actual
baseline initial-state hash exactly; the ablated policy has 11,702,604 parameters.
Training stochastic draws differ because the VAE no longer samples latents; they
are not claimed identical. Four real LeRobot tests pass, including one CPU update,
checkpoint/processor/sampler reload and rejection of a mismatched declared initial
reference hash before any optimizer update. The ablation is not yet quality evidence.

The offline gates remain tied to the original balanced-sampling baseline,
`20260910T230212-7b5dbe7d1c2b`, rather than accepting the later degraded endpoints
as the new standard. No physical run follows a failed offline gate.

### No-VAE result: not promoted

Run `20260911T020002-4ce2f8fd061b` completed 2,000 native MPS updates in 383.62
seconds from clean `1ae01ae`, with the declared common initialization verified.
Checkpoint, processor and sampler reloads pass. Offline assessment
`20260911T021007-6e147d54a964` preserves checkpoint bytes. Frozen comparison
`20260911T021025-e0da5ef47834` fails four of six gates:

| Measure | Original baseline | No-VAE candidate |
|---|---:|---:|
| Nominal launch mean first-joint error | 0.013894 rad | 0.017548 rad |
| Nominal launch mean tool-target error | 6.960 mm | 7.635 mm |
| Settled mean tool-target error | 1.180 mm | 1.601 mm |
| Other training starts mean first-joint error | 0.020952 rad | 0.033530 rad |

The first pan command remains backward. Endpoint retention and unchanged weights
pass, but launch and other-start gates fail. No physical run follows this result.
Removing the VAE alone at this budget does not solve the fitting problem; this
experiment does not establish that the standard VAE is generally better.

### Deterministic fitting follow-up

Training-only audit `20260911T021301-8ac3000fe6d8` compares retained loss windows
and per-joint errors for all three candidates. The no-VAE run still clips every
update; its final 250-update mean L1 is 0.12217 and median gradient norm 29.62
against a clip threshold of 10. Lower aggregate training loss did not improve
launch inference. Saved action normalization remains consistent with inference.

Protocol `20260911T021430-2b8791b001be` tests dropout 0 instead of 0.1 on the
no-VAE configuration, keeping the same data, initialization, sampling, learning
rate and 2,000-update budget. It preserves the existing offline gates and only
permits physical validation after all gates pass. The earlier unexecuted record
`20260911T021411-d998adb7e673` retained a contradictory copied intervention string
and is superseded before training. No earlier record was edited.

`train --dropout 0` selects this configuration; the default remains 0.1. The value
is saved in both training and checkpoint configuration. One actual native CPU
update with no VAE/dropout, checkpoint reload and processor/sampler checks passes
(`.artifacts/no-dropout-checkpoint-test.log`). This is a controlled fitting
experiment, not a claim that dropout should be removed from the released policy.

### Dropout-zero result: improved nominal fit, gate still failed

Run `20260911T021733-b67e2a69d96e` completed 2,000 native MPS updates from clean
`6f878db`, with verified initialization and checkpoint/processor/sampler reloads.
Reported training time is 374.88 seconds; brief overlap with CPU checks means this
is not an isolated device benchmark. Offline assessment
`20260911T022407-3ae87ae922f8` preserves weights. Frozen comparison
`20260911T022426-bc9a525f85c4` fails the direction and other-start retention gates.

Nominal launch mean joint error improves 0.013894→0.003573 rad and tool error
6.960→1.470 mm. Settled tool error improves 1.180→1.022 mm. Other training starts'
mean joint error worsens 0.020952→0.031807 rad, beyond the allowed 20% increase;
the first nominal pan target is still negative. Four of six gates pass, but the
candidate is not promoted and receives no physical rollout. Better average fit
is insufficient to establish reliable learned control.

### Fixed-duration follow-up

Protocol `20260911T023056-6649c0803bb0` declares 20,000 updates from the same
initialization, changing only duration from the dropout-zero run. An audit of
actual sampled indices found 52/480 training observation anchors unseen at 2,000
updates. Mean L1 over the final 250 updates was 0.04490 versus 0.05128 in the
preceding 250, so fitting was still improving. These are training observations,
not evidence of validation success.

Use the final fixed-budget checkpoint, no intermediate quality-based selection,
and retain the original offline gates. Estimated native MPS time is about 62.5
minutes by linear extrapolation; this is not a guaranteed benchmark. Start only
after the active dinner capture ends, avoiding competing GPU jobs. Spend remains
zero. The protocol is not a completed training result.
