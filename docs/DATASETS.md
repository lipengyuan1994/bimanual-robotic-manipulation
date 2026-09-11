# Demonstration datasets

`src/bimanual/dataset_export.py` converts sealed raw demonstration runs into a
local LeRobot v3 dataset. This is data preparation, not ACT training or a claim
that a learned controller can manipulate objects. Raw collection and timestamp
semantics are described in [the interfaces](INTERFACES.md).

## Input checks

`preflight_sources(run_roots, comparison_run_roots=..., max_frames=100_000)` checks
all inputs before creating output or importing optional LeRobot dependencies:

- Verify each run's existing evidence seal, referenced files, RGB image decoding,
  episode/schema/transition alignment, and agreement with source provenance.
- Require selected episodes to have the train split, successful reported outcome,
  zero interventions and at least one confirmed action transition.
- Reject duplicate episode identities and seeds reused across supplied splits.
- Enforce the explicit maximum exported transition count.

Supply the complete known validation/test collection through
`comparison_run_roots`; those records are checked but never exported. A collection
cannot prove separation from sources it has not been given. Failures and
interventions remain in original evidence even though success-only training intake
rejects them. A reported success still depends on independent physical scoring.

## Export API

Use the verified native training environment with the repository's pinned
`lerobot==0.6.1`. The base simulation environment intentionally does not need to
import LeRobot for source validation. Missing or mismatched dependency versions
raise an explicit error before output is created.

```python
from pathlib import Path
from bimanual.dataset_export import export_lerobot_dataset

export_lerobot_dataset(
    (Path(".artifacts/runs/your-sealed-run"),),
    Path(".artifacts/datasets/your-new-dataset"),
    repo_id="local/your_dataset",
    comparison_run_roots=(),  # Include known held-out runs when they exist.
)
```

The identifier is local metadata; this function does not upload to Hugging Face,
request hosted compute, download model weights or resume an existing dataset.
Existing destinations are rejected. Output cannot be inside a sealed source run.
Export failures preserve partial output and an error record when the writer was
created; a missing `export_manifest.json` means the export did not complete.

## Stored features and timing

| Feature | Meaning and representation |
|---|---|
| `observation.state` | 12 joint positions, float32 radians |
| `observation.velocity` | 12 joint velocities, float32 radians/second |
| `action` | 12 absolute joint targets, float32 radians |
| `observation.images.overhead` | Original 270 × 480 × 3 RGB pixels |
| `observation.images.left_wrist` | Original left wrist RGB pixels |
| `observation.images.right_wrist` | Original right wrist RGB pixels |
| `task` | Episode instruction, converted to LeRobot task metadata |

Joint ordering is exactly [the versioned interface](INTERFACES.md). Image storage
uses image-backed features rather than lossy video, with no crop or resize. No
robot-state normalization is performed. LeRobot's reader returns image tensors
as channels × height × width with values in [0, 1]; this is decoding behavior,
not an exported model normalization specification.

Only nonterminal observations produce training rows: each pairs the captured
images/joints with the action actually applied immediately afterward. The final
observation has no action and remains in raw evidence. LeRobot supplies timestamps
at frame_index/20 automatically; the exporter validates the original 20 Hz cadence
and preserves each source's simulation start time in lineage. See the
[pinned writer API](https://raw.githubusercontent.com/huggingface/lerobot/v0.6.1/src/lerobot/datasets/dataset_writer.py).

## Provenance and read-back

The exporter uses `LeRobotDataset.create`, `add_frame`, `save_episode` and
`finalize`, then checks episode/frame counts and every decoded state, velocity,
action, image and timestamp against the source. These methods and finalization
requirements were checked against the
[pinned LeRobot API](https://raw.githubusercontent.com/huggingface/lerobot/v0.6.1/src/lerobot/datasets/lerobot_dataset.py).

`raw_sources/000000`, and subsequent numbered directories, contain complete copies
of the selected sealed runs, including source manifests, lineage, terminal frames
and scene assets. This makes the bundle portable and retains full scoring context,
but duplicates source images and meshes. Budget disk space before larger exports.
Source manifests and copied artifacts are rechecked during export.

`export_manifest.json` records source manifest/episode hashes, code and controller
lineage, split/seed, ordered camera feature names, exact library version,
transition counts and hashes of output files. Its canonical digest binds these
fields. Do not change a sealed export in place; create another directory after
changing data, preprocessing, or checkpoints. The general v3 format is documented
by [LeRobot](https://huggingface.co/docs/lerobot/lerobot-dataset-v3).

## Verification

The base-environment test checks preflight and frame mapping without substituting
a fake dataset writer:

```sh
.venv/bin/python -m pytest tests/test_dataset_export.py -q
```

Actual format integration requires the optional native training environment and an
explicit switch. A skipped test is not integration evidence:

```sh
HF_HOME="$PWD/.artifacts/huggingface" BIMANUAL_TEST_LEROBOT=1 \
  .artifacts/training-venv/bin/python -m pytest tests/test_dataset_export.py -q
```

The real integration test creates a small synthetic fixture, exports it through
the actual library and opens the resulting dataset again. It validates data-format
compatibility only. Physical source-run exports, measured ACT training and
held-out policy rollouts need their own experiment records.

Set `HF_HOME` to the project-local `.artifacts/huggingface` directory before
starting the Python process. The library uses a local Arrow cache during read-back
even for a fully local dataset; the default user cache can be outside the allowed
workspace. This cache is not a hidden model download or cloud inference service.

## September 10 validation checkpoint

The native optional environment passed all **11 exporter tests**, including the
real LeRobot v3 integration test. The base environment passed 10 lightweight tests
and explicitly skipped that integration test. Initial read-back failed at the
default user cache directory; setting project-local `HF_HOME` resolved that error.

The actual contact-placement recording `20260910T210237-50fcd0cc7d99` exported to
`.artifacts/datasets/placement-probe`: **one episode, 460 action-aligned rows**.
Every row's numeric features, three decoded images and timestamp matched the raw
source. All 1,418 generated/copied files passed SHA-256 verification, and the
original source seal remained valid. The export manifest digest is
`22d4f66520183efe630965e45f7ea4e63282772fd056330fefe16b50fc9e8bcc`.
The hashed files occupy 85,924,892 bytes. This is one recorded scripted skill;
it is not a diverse dataset or trained-policy performance evidence.

macOS printed duplicate AVFoundation receiver-class warnings while loading PyAV
and Homebrew FFmpeg libraries. Import, image-backed export and read-back completed,
but this does not validate native video or audio capture. No library files were
removed or renamed, and no architecture compatibility exception was introduced.

## Training ACT on real demonstrations

`src/bimanual/training.py` exposes:

```python
from pathlib import Path
from bimanual.evidence import EvidenceStore
from bimanual.training import ACTTrainingConfig, run_train

result = run_train(
    ACTTrainingConfig(
        dataset_path=Path(".artifacts/datasets/placement-probe"),
        device="cpu", architecture="small", steps=3,
        batch_size=1, chunk_size=10, seed=0,
    ),
    store=EvidenceStore(Path(".artifacts")),
    project_root=Path.cwd(),
)
```

Start the native training interpreter with project-local `HF_HOME`, as above.
MPS must be explicitly requested and available; set
`PYTORCH_ENABLE_MPS_FALLBACK=0` before launching the process. Device substitution
or an enabled MPS fallback is rejected. The trainer checks the pinned LeRobot
version and records the other runtime package versions. The CPU path has been
executed on real data; this trainer's MPS path needs its own recorded run.

The trainer verifies every exported file and source episode before training and
again before claiming completion. It refuses non-training sources, interventions,
failed episodes, schema/cadence mismatches, unsealed files and inconsistent frame
counts. Output goes into a newly generated evidence run outside the dataset.
Failures, including `KeyboardInterrupt`, preserve logs and seal a failed run.
Abrupt process death still requires a later interrupted-worker recovery mechanism;
a signal that kills Python immediately cannot run this cleanup handler.

The actual ACT model sees only joint positions, three RGB images and supervised
action chunks with LeRobot's end-of-episode padding mask. The stored velocity,
raw evaluator truth and task outcomes never enter the model. Instruction text
remains dataset metadata: this bounded ACT policy is not itself a language planner.
Images retain the complete 270 × 480 field of view, without resizing or cropping.
The small profile uses ResNet18 and a smaller transformer (dimension 128, four
attention heads, one encoder/decoder/VAE layer, latent dimension 16). The default
profile keeps ACT's normal transformer dimensions. Both initialize from random
weights and deliberately set pretrained backbone weights to `None`: no weights,
hosted API or compute are downloaded or purchased.

The official ACT preprocessing pipeline applies dataset mean/std normalization;
the corresponding saved postprocessor converts predicted actions back to absolute
joint radians. Numeric state/action statistics are recomputed over **training rows
only in float64**, with an explicit standard-deviation floor of `1e-4` radians
(configurable). This prevents a nearly constant parked joint from turning floating
point roundoff into a huge normalized target. Image statistics retain the dataset's
RGB statistics. Both the adjusted values and the original stats-file hash are
recorded; the original dataset stays untouched.

AdamW uses ACT's optimizer preset, weight decay `1e-4` and gradient norm clipping
at 10. Learning rate defaults to `1e-5` for both backbone and transformer. Each step
records sampled row indices, finite gradient checks, loss components and timing.
A seed initializes model, sampling and runtime RNGs, but deterministic algorithms
are not automatically enabled; no cross-device bitwise reproducibility is claimed.

Every completed run contains:

- `checkpoint/config.json`, `checkpoint/model.safetensors`: real trained parameters.
- `checkpoint/policy_preprocessor.json` and `checkpoint/policy_postprocessor.json`,
  plus their normalization-state safetensors files.
- `trainer_state.pt`: optimizer state, completed step count, sampler and runtime
  RNG states, and the dataset-manifest file digest. A resume command is not yet
  implemented; this file preserves the state needed for one.
- `training_config.json`, `normalization.json`, `dataset_manifest.json`,
  `steps.jsonl`, `metrics.json` and the ordinary immutable evidence manifest with
  code/source provenance and file hashes.

After saving, the trainer reloads the actual local policy and both processors and
checks that they reproduce the same denormalized action chunk. The postprocessor
must be loaded with LeRobot's action converters:

```python
from lerobot.processor import PolicyProcessorPipeline
from lerobot.processor.converters import (
    policy_action_to_transition, transition_to_policy_action,
)

pre = PolicyProcessorPipeline.from_pretrained(
    checkpoint, config_filename="policy_preprocessor.json", local_files_only=True,
)
post = PolicyProcessorPipeline.from_pretrained(
    checkpoint, config_filename="policy_postprocessor.json", local_files_only=True,
    to_transition=policy_action_to_transition,
    to_output=transition_to_policy_action,
)
```

An executor must still validate checkpoint lineage, reset policy queues, check
fresh observation identity and all action bounds, and independently score physical
outcomes. Finite model output and low training loss do not demonstrate a successful
grasp, release, hand-off or dinner-table task.

### Real-data pilot evidence

The initial three-step CPU pilot `20260910T211138-b4f6c242246c` completed but exposed
an issue in upstream float32 numeric statistics: a constant wrist target near 1.2
radians had a slightly displaced mean and zero reported standard deviation. That
amplified its normalized target. The original run is retained and is not the
recommended checkpoint.

The corrected pilot `20260910T211456-55d5d5db50cc` used the float64 statistics above:
**one CPU optimizer step** on an actual image/action chunk from the 460-transition
placement dataset. The small ACT had 11,908,460 parameters; its sampled step took
0.944 seconds and the complete run, including verification and checkpoint reload,
took 10.20 seconds. Total loss was 27.8736, comprising L1 loss 0.86979 and KL loss 2.70038
with ACT's KL weight 10. The checkpoint and both processors reloaded consistently.
These are training-execution measurements, not held-out learning improvement or
manipulation success. One episode cannot establish generalization.

Run the lightweight trainer checks with `.venv/bin/python -m pytest
tests/test_training.py -q`. The real optional integration check additionally needs
`BIMANUAL_TRAIN_TEST_DATASET` pointing to a verified export and the native training
interpreter; it performs one actual optimizer step and reloads the checkpoint.

The native trainer test run passed **14 tests**, including the actual one-step
training/checkpoint/processor integration. The base environment passed 13 lightweight
checks and explicitly skipped the real-training integration.

### Actual MPS training check

Run `20260910T211727-eaf518d3ec4c` completed three real-data training steps on
MPS with `PYTORCH_ENABLE_MPS_FALLBACK=0`, using the same corrected statistics,
full camera resolution and small ACT profile. Step times were 2.468, 0.301 and
0.382 seconds; total time including integrity checks and reload was 10.80 seconds.
Both checkpoint and processor reload checks passed. Losses across three different
sampled frames are not a learning curve or evidence of manipulation improvement.

LeRobot emits a weights-loading progress line; the CLI now sends library progress
to stderr so stdout remains a parseable JSON result. CPU CLI verification run
`20260910T212012-c722c7d4d0cb` completed one update and produced valid JSON. All
previous runs remain available, including the earlier output with mixed progress.

## Continuous dinner capture

The successful fixed-scene dinner teacher is connected to the same raw
recording contract through `dinner-teacher --record-demonstration`. Collection
captures all three original 480×270 RGB views and joint observations before every
20 Hz action, retaining only fully applied transitions and a terminal observation.
This is independent of the 2 Hz replay: `--no-render` suppresses the GIF, while
explicit demonstration collection still renders the training cameras.

The authored scene has one nominal training configuration, seed 0. Repeated
captures are not independent randomized scenes or held-out evaluation. Phase
annotations remain a separate training sidecar; they do not enter deployed
observations. Episode success must agree with the independent dinner scorer.
Failed or cancelled episodes remain evidence and are rejected by success-only
training intake. Runtime capture now passes in the recorded run below. Export verification remains
pending; the earlier replay cannot supply missing full-rate observations retroactively.

Fifteen focused actor/recording tests pass, including real PNG/episode-contract
checks with a short synthetic environment and failed-step boundaries. Those
tests do not establish physical dinner success; complete recorded reproduction now passes below; LeRobot export/read-back remains pending.

## Long-episode timestamp precision

LeRobot 0.6.1 generates frame timestamps as `frame_index / fps` and stores them
as float32. Export read-back now requires exact equality to that float32 value.
The previous fixed one-microsecond tolerance against a float64 division could
reject correct later rows in a 240-second dinner episode. This change does not
relax raw observation cadence or accept adjacent frame timestamps.

Twenty-three native LeRobot export tests pass, including a real 4,819-frame
numeric storage episode and rejection of one-ULP timestamp changes/nonfinite
values. Log: `.artifacts/dataset-long-timestamp-real-tests.log`. The long numeric
fixture validates timestamp storage, not image rendering or manipulation.

### First complete recorded dinner

Run `20260911T022644-a24a56ff004c` completes from clean `6c6c991` with a passing
independent physical score and valid demonstration. Audit
`20260911T023608-8896f729ffd5` verifies all 4,819 applied actions against their
pre-action observations/phase sidecar, 4,820 observations and 14,460 RGB files.
Source size is about 595 MiB. Actor/capture time is 445.07 seconds for 240.95
simulated seconds; scoring, replay encoding and final sealing are excluded from
that timer. Final three-camera preview was inspected. This is one nominal scripted
training episode, with no learned execution or generalization claim.
