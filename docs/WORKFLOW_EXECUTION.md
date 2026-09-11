# Execute a local development workflow

`workflow-run` connects a verified seven-skill checkpoint manifest, local Qwen
planner and the guarded continuous simulation runner. By default the CLI uses
a spawned worker process, loading models before capturing execution images and
keeping simulation operations on one owning thread within that process.
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
  --wall-timeout-seconds 1800 --step-timeout-seconds 300
```

The command uses the canonical seven-skill sequence, prerequisite chain, and the
per-skill action budgets and execution prefix sealed inside the workflow manifest.
The operator cannot replace those settings with one global command-line budget.
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

The default process supervisor handles cancellation and the overall wall deadline
outside the model process. It first requests cooperative cancellation, waits up to
two seconds, then terminates and, if necessary, kills the child with one-second
grace per escalation. It reaps the child before sealing parent evidence. A forced
interruption never becomes successful execution, even if a child completion
manifest already exists. Partial worker files remain preserved. Evidence hashing
and sealing happen afterward and are not included in the stop grace.

The parent emits a `dinner_workflow_process` record with child PID, exit status,
stop events and verified child manifest identity. The child evidence store is
`RUN_DIRECTORY/child-evidence`; its run ID is recorded as `child_run_id`.
Only a verified completed `dinner_workflow_execution` child with matching config
can establish execution completion. This still does not establish physical task
success. Each child that reaches worker creation also seals `step-report.json`,
which joins planner, camera, supervisor, ACT-inference and action evidence for
every attempt. Any ambiguous or contradictory join downgrades the child run to
failed. See [workflow step evidence](WORKFLOW_STEP_REPORT.md). One spawned worker
owns the simulation, supervised by a separate guardian.
The guardian monitors the original parent's process handle and can terminate a
worker stuck in a native call after parent loss. A common filesystem lease prevents
another supported worker from starting in the same evidence store until cleanup.
Guardian failure triggers dedicated process-group cleanup while its PID is pinned
against automatic reaping; unconfirmed cleanup leaves evidence unsealed.

This path is validated on POSIX with Python3.12 and supports one worker with threads.
It does not reconstruct an interrupted parent's run record or manage independently
launched subprocess trees. Original-parent loss therefore does not fabricate a
sealed parent outcome. The operator UI uses this same worker path.

For direct debugging, `--in-process` preserves the original cooperative runner.
That mode checks cancellation between blocking operations and cannot forcibly
interrupt a model load or inference kernel. A cancelled planner thread may finish
computing copied inputs, but cannot resume simulation or modify sealed evidence.

After a child execution record is sealed, evaluate its run ID in its own store:

```sh
.venv/bin/bimanual --artifacts RUN_DIRECTORY/child-evidence dinner-evaluate CHILD_RUN_ID
```

For `--in-process`, use the usual artifact store and returned run ID. The parent
process record is a lifecycle record, not a physical trace. See
[independent outcomes](DINNER_OUTCOMES.md).
Missing instrumentation declarations remain an explicit failed condition until a
source-bound audit is supplied. The execution command itself continues to report
`independent_task_success: null`; it does not silently equate step completion with
the separate scorer's result.


Current combined validation:57 native CPU process, guardian, lease and operator
tests pass. These include cooperative stop, ignored termination followed by
kill/reap, corrupt/missing child results, completed child evidence with a hung
thread, guardian crash and original-parent death during a GIL-held native call.
The parent-death case also verifies restart on the same evidence store without
inventing a seal for the interrupted parent. Log:
`.artifacts/checks-guardian-process-final.log`.
Actual CLI run `20260911T061251-260718b9a590` with an absent cohort fails as expected,
verifies its failed child manifest and reaps the child without loading models.
This verifies the failure path, not full learned execution or GPU interruption.

## Optional local operator controls

`bimanual serve --operator-config /absolute/path/operator.json` enables the
portal's instruction form and job-specific stop button. The JSON must validate
as `WorkflowProcessConfig`; model/cohort paths and runtime limits are configured
by the server owner, never supplied by browser requests. Without this option the
portal remains read-only. The server binds to loopback.

The API exposes `GET /api/operator`, `POST /api/operator/jobs` (instruction only),
and `POST /api/operator/jobs/{job_id}/stop`. Mutations require the
`X-Bimanual-Operator: 1` header and reject foreign browser origins. One worker
runs at a time. Stop remains `stopping` until worker termination is confirmed;
server shutdown requests cancellation and waits for the bounded process cleanup.
A network error does not mean the worker stopped; refresh status before retrying.

`finished` describes process completion, not independently verified dinner-table
success. Inspect sealed evidence separately. The interface shows process status, reported step progress and last-capture camera
previews. Actual learned-run display validation remains pending. No validated full
seven-skill learned cohort is available yet, so enabling controls alone does not
make the workflow ready. Do not run it alongside local GPU training.

Run history requests 20 fully verified records per page. Older/Newest controls
navigate the archive; failed and corrupted records are retained in page order.
`GET /api/runs?limit=20&before=<last-run-id>` uses an exclusive run-ID cursor,
so newly sealed runs do not shift subsequent older pages. Omitting the limit
retains the complete listing. Verification of a single large run can still be
slow; the project description and operator status load independently.

The operator panel also displays the last worker state, reason, reported completed
steps and attempt count. These are unsealed progress updates, not independent
physical scoring. They may remain unchanged during a long model call, and the last
update remains visible after stopping. The process outcome takes precedence over
this historical snapshot. Camera previews are described below. Progress is never fed back
into model observations, action authorization or success scoring.

Three last-capture camera previews are now available with progress. They reuse
worker-owned observations and never trigger rendering from the browser. The
parent checks all three image hashes and RGB PNG dimensions as one synchronized
capture before publishing it. Capture sequence and simulation time are visible;
a stopped or planning worker may continue to show its last capture. Synthetic
camera tests are labeled `injected_unverified`. This display does not certify
freshness for control or task success; the control path retains its own checks.
Actual learned-run camera display validation is still pending.

Terminal timeout and clarification outcomes retain their verified run links.
Clarification appears separately so the operator can revise the instruction for a
new job. Failed jobs show the bounded verified worker reason when available; a
parent timeout always reports that the time limit was reached. These explanations
do not replace the sealed logs or change success scoring.
