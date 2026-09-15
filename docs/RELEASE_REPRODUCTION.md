# Release reproduction runbook

This is the command sequence for a future M3 candidate. It is deliberately a
runbook, not evidence that the current candidate qualifies: [STATUS](STATUS.md)
records the live gates and exact artifact identities. Do not substitute a failed
seed, rerun a sealed one-attempt evaluation, or use a placeholder as an input.

All paths below are examples. Before each command, replace every uppercase token
with an existing, sealed artifact. Keep the resulting command, revision, inputs,
device, and output in the experiment record.

## 1. Install and prove the local runtime

On Apple Silicon, use the native setup first. `doctor --require-device mps` is
appropriate only when the launch environment can expose MPS; CPU is the supported
fallback for local diagnostic work.

```sh
scripts/bootstrap.sh
sh scripts/bootstrap-training.sh
sh scripts/bootstrap-reasoning.sh
.venv/bin/bimanual doctor --require-device cpu --record
.venv/bin/bimanual sim --seconds 4
scripts/check.sh --render
```

For a single environment that can run the complete workflow, set
`BIMANUAL_PYTHON` to the verified native Python 3.12 executable and create the
dedicated environment described in [workflow execution](WORKFLOW_EXECUTION.md).

## 2. Capture, export, and train a skill

Record a contact-only teacher episode before exporting it. The dataset exporter
accepts **run directories**, not bare run IDs. Include every known held-out run
with `--comparison-run`; the exporter does not infer a split from a directory
name.

```sh
.venv/bin/bimanual dinner-teacher --recipe v2 --record-demonstration
HF_HOME="$PWD/.artifacts/huggingface" \
  .artifacts/training-venv/bin/bimanual dataset-export \
  "$TEACHER_RUN_ROOT" \
  --comparison-run "$VALIDATION_RUN_ROOT" \
  --comparison-run "$TEST_RUN_ROOT" \
  --destination .artifacts/datasets/CANDIDATE_DATASET \
  --repo-id local/CANDIDATE_DATASET
.venv/bin/bimanual dataset-skill-views \
  --dataset .artifacts/datasets/CANDIDATE_DATASET \
  --destination .artifacts/CANDIDATE-skill-views.json
```

Use the frozen cohort declaration for the selected skill when one exists. An
ad-hoc `train` command is useful only for a new, separately declared experiment.
The complete argument list below includes the source-bound sampling inputs needed
by the current corrective bar profile; another profile has its own sealed values.

```sh
HF_HUB_OFFLINE=1 PYTORCH_ENABLE_MPS_FALLBACK=0 \
  .artifacts/training-venv/bin/bimanual train \
  --dataset .artifacts/datasets/CANDIDATE_DATASET \
  --corrective-dataset .artifacts/datasets/CORRECTIVE_DATASET \
  --skill-views .artifacts/CANDIDATE-skill-views.json \
  --skill-id bar_place_and_return \
  --sampling-profile bar_late_workbench_overlap_sampling_v7 \
  --sampling-protocol-run .artifacts/experiments/SAMPLING.json \
  --device mps --architecture small --steps 20000 --batch-size 4 --chunk-size 10 \
  --seed 0 --no-vae --dropout 0 --learning-rate-schedule terminal_linear \
  --temporal-loss-profile first_action_half_v1 --checkpoint-interval 500
```

If that opted-in candidate fails after a snapshot, resume only from the snapshot
owned by its sealed failed parent and repeat its original arguments. The trainer
rejects a changed device, dataset, sampling declaration, package set, or initial
state.

```sh
.artifacts/training-venv/bin/bimanual train \
  --dataset .artifacts/datasets/CANDIDATE_DATASET \
  --device mps --architecture small --steps 20000 --batch-size 4 --chunk-size 10 \
  --seed 0 --checkpoint-interval 500 \
  --resume-from .artifacts/runs/FAILED_RUN/snapshots/checkpoint-00000500
```

Validate the completed checkpoint and then run its frozen physical protocol. A
completed optimizer run is not a successful physical component.

```sh
.venv/bin/bimanual skill-checkpoint "$TRAINING_RUN_ROOT" \
  --skill-id bar_place_and_return \
  --dataset .artifacts/datasets/CANDIDATE_DATASET
.artifacts/training-venv/bin/bimanual skill-physical-protocol-run \
  docs/experiments/PHYSICAL_PROTOCOL.json \
  --skill bar_place_and_return --training-attempt "$COHORT_ATTEMPT"
```

## 3. Freeze scenes and visual decisions before the workflow

The release suite uses its already frozen scene protocol. Preparing a scene only
checks the allocated XML; it does not evaluate a policy.

```sh
.venv/bin/bimanual scene-variant-protocol-check \
  docs/experiments/dinner-perturbation-protocol-v1.json
.venv/bin/bimanual scene-variant-suite-prepare \
  docs/experiments/dinner-perturbation-protocol-v1.json
```

Use a locally sealed Qwen snapshot. A planner suite must be frozen before its
model run, and it remains visual-decision evidence rather than robot execution.

```sh
.artifacts/reasoning-venv/bin/bimanual planner-preflight \
  --model-root .artifacts/models/qwen3-vl-4b-instruct
.venv/bin/bimanual planner-suite-create \
  --spec .artifacts/PLANNER_CASES.json \
  --model-root .artifacts/models/qwen3-vl-4b-instruct \
  --destination .artifacts/experiments/PLANNER_PROTOCOL.json
.venv/bin/bimanual planner-suite-check .artifacts/experiments/PLANNER_PROTOCOL.json
PYTORCH_ENABLE_MPS_FALLBACK=0 .artifacts/reasoning-venv/bin/bimanual \
  planner-suite-run .artifacts/experiments/PLANNER_PROTOCOL.json --device mps
```

## 4. Assemble, activate, and evaluate the full workflow

Use the workflow environment for all commands that load or verify model-related
artifacts. Supply exactly seven `--training-run` values in this fixed order:
hand-off, bar, cup, plate, drawer, spoon, fork. The final release declaration
requires a *sealed scene-suite index run*, not an individual prepared scene.

```sh
.artifacts/workflow-venv/bin/bimanual workflow-create \
  --dataset .artifacts/datasets/CANDIDATE_DATASET \
  --skill-views .artifacts/CANDIDATE-skill-views.json \
  --destination .artifacts/workflows/CANDIDATE.json \
  --training-run "$HANDOFF_RUN" --training-run "$BAR_RUN" \
  --training-run "$CUP_RUN" --training-run "$PLATE_RUN" \
  --training-run "$DRAWER_RUN" --training-run "$SPOON_RUN" \
  --training-run "$FORK_RUN"
.artifacts/workflow-venv/bin/bimanual workflow-check .artifacts/workflows/CANDIDATE.json
.artifacts/workflow-venv/bin/bimanual workflow-activate .artifacts/workflows/CANDIDATE.json
```

For a hand-off checkpoint trained with a verified corrective archive, add
`--handoff-corrective-dataset PATH` to `workflow-create`; it must be the archive
bound by that training record. Do not supply the option for a non-corrective
hand-off run.

```sh
.artifacts/workflow-venv/bin/bimanual workflow-release-create \
  --workflow-manifest .artifacts/workflows/CANDIDATE.json \
  --planner-model .artifacts/models/qwen3-vl-4b-instruct \
  --scene-suite-run "$SCENE_SUITE_RUN_ROOT" \
  --perturbation-protocol docs/experiments/dinner-perturbation-protocol-v1.json \
  --instruction "Set the dinner table with the plate, cup, spoon and fork, including the hand-off" \
  --destination .artifacts/releases/CANDIDATE.json
.artifacts/workflow-venv/bin/bimanual workflow-release-check .artifacts/releases/CANDIDATE.json
.artifacts/workflow-venv/bin/bimanual workflow-release-run \
  .artifacts/releases/CANDIDATE.json combined-30001
.artifacts/workflow-venv/bin/bimanual workflow-release-suite .artifacts/releases/CANDIDATE.json
```

The release runner consumes each allocated case once. Run every declared case in
the order recorded by the protocol before the suite aggregation; never replace a
failed or consumed case with a different seed.

## 5. Intel and OpenVINO evidence

The repository currently provides an evidence **validator**, not an OpenVINO
conversion or benchmark runner. On an actual eligible Core Ultra Series 2/3 host,
run MuJoCo and the converted model together using a separately recorded target-host
procedure. Record every requested and actual device, precision, raw warm samples,
model-only and end-to-end timing, memory, simulation time, and fallback. Then
validate the record:

```sh
.venv/bin/bimanual intel-benchmark-check \
  path/to/intel-openvino-benchmark.json
```

A passing validator only proves record shape. It does not import OpenVINO, convert
a model, execute inference, discover hardware, or establish Intel compliance.

## 6. Serve and package

The portal is read-only unless its owner supplies a validated
`WorkflowProcessConfig` JSON file. The browser never supplies model paths or
runtime limits. Use the activated workflow only after its deployment status
reverifies.

```sh
.artifacts/workflow-venv/bin/bimanual workflow-deployment-status
.artifacts/workflow-venv/bin/bimanual serve \
  --operator-config /absolute/path/operator-config.json --port 8767
```

After the release suite, video, slides, cover, and HTTPS application URL exist,
inspect the submission inputs at the exact clean `HEAD`. Replace `GIT_HEAD` with
the output of `git rev-parse HEAD`; it is not a literal accepted revision.

```sh
.venv/bin/bimanual submission-check \
  --revision "$(git rev-parse HEAD)" \
  --release-protocol .artifacts/releases/CANDIDATE.json \
  --release-suite "$RELEASE_SUITE_RUN_ROOT" \
  --interactive-url https://YOUR_HOST/app \
  --video demo.mp4 --slides slides.pdf --cover cover.png
.venv/bin/bimanual submission-create \
  --revision "$(git rev-parse HEAD)" \
  --release-protocol .artifacts/releases/CANDIDATE.json \
  --release-suite "$RELEASE_SUITE_RUN_ROOT" \
  --interactive-url https://YOUR_HOST/app \
  --video demo.mp4 --slides slides.pdf --cover cover.png \
  --destination .artifacts/submission/CANDIDATE
.venv/bin/bimanual submission-verify .artifacts/submission/CANDIDATE
```

The package is an immutable local artifact. It does not upload to the hackathon
platform or turn failed local/Intel gates into success.
