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
