# Execute a local development workflow

`workflow-run` connects a verified seven-skill checkpoint manifest, local Qwen
planner and the guarded continuous simulation runner. It loads models before
capturing execution images and keeps simulation operations on one owning thread.
There is currently **no validated seven-model cohort**. This command is an
execution interface, not evidence that learned dinner setup works.

## Environment

Both `training` and `reasoning` extras are required in the same native environment.
Keep this separate from an active training environment. Follow the architecture
checks in [setup](SETUP.md) before selecting the interpreter. With
`BIMANUAL_PYTHON` set to the verified native Python 3.12 executable:

```sh
UV_PYTHON_INSTALL_DIR="$HOME/.local/share/uv/python-arm64" \
UV_PROJECT_ENVIRONMENT="$PWD/.artifacts/workflow-venv" \
/opt/homebrew/bin/uv sync --frozen --python "$BIMANUAL_PYTHON" \
  --extra training --extra reasoning
```

All weights stay local. No hosted model service or automatic model download is
part of execution. Native MPS is optional; CPU remains a selectable device for
each model. Do not share the GPU with a training or benchmark job.

## Inputs and command

Create and verify the [explicit checkpoint manifest](WORKFLOW_MANIFEST.md) and
prepare a [sealed local Qwen model](PLANNER.md). The paths below are examples;
they must refer to actual verified artifacts, not empty placeholder directories.

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 \
HF_HOME="$PWD/.artifacts/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.artifacts/workflow-venv/bin/bimanual workflow-run \
  .artifacts/workflows/candidate-v1.json \
  --planner-model .artifacts/models/qwen3-vl-4b-instruct \
  --instruction "Set the dinner table with the plate, cup, spoon and fork, including the hand-off" \
  --policy-device cpu --planner-device cpu \
  --wall-timeout-seconds 1800 --step-timeout-seconds 300 \
  --max-actions-per-skill 2000
```

The command uses the canonical seven-skill sequence and its prerequisite chain.
An instruction does not grant arbitrary motions: each camera-grounded proposal
must match the next registered step, stop, or request clarification. Each attempt
has its own action budget and step timeout; the supervisor retains its two-retry
limit. [Recovery eligibility](WORKFLOW_RUNNER.md) is unchanged.

## Evidence and limits

The run records configuration, model provenance, planning decisions, physical
observations/actions, workflow events and terminal status in the evidence store.
It retains failures during setup or execution. A completed executor sequence is
reported separately from `independent_task_success`, which remains unknown here;
it must not be counted as an independently scored full-task success.

Cancellation revokes execution authority and closes the worker. The overall
wall timeout is cooperative: it is checked between setup and execution calls.
It cannot forcibly interrupt a blocked native model load or a single blocked
inference call. A cancelled model thread can finish computing copied inputs,
but cannot resume the simulation or write worker artifacts after closure. Hard
process isolation and a live operator UI remain separate work.
