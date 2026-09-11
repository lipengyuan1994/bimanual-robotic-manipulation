# Workflow step evidence

Every integrated workflow run that reaches worker creation writes a sealed
`step-report.json`. This is the review table for step outcomes and latency. It
does not independently score whether the dinner table is correct.

The report joins four append-only evidence sources:

- the final supervisor snapshot for canonical attempts, retries, outcomes and
  monotonic start/end times;
- planner job files for model response, fresh-camera revalidation and dispatch;
- worker action rows for applied, rejected and partial-physics counts;
- skill-execution rows for ACT inference samples, physical milestones,
  successor readiness and structured failure codes.

Each attempt identifies its frozen checkpoint and capability. Timings distinguish
planner inference, total planning, fresh revalidation, camera capture, learned
policy inference, execution wall time and simulated duration. Planner model load
time is run setup and is not charged to an individual step.

The join fails closed. A duplicate or missing planner dispatch, orphan worker
action, mismatched attempt, regressing timestamp, non-finite latency, broken retry
link, action-count disagreement or contradictory completion state downgrades the
enclosing workflow run to `failed`. Later task steps remain visible as
`not_attempted` after an early terminal outcome.

`execution_complete=true` means all declared supervised steps ended successfully.
`independent_task_success` remains `null`; the frozen dinner evaluator must make
that separate finding from physical scene state.

Focused validation:

```bash
.venv/bin/python -m pytest -q \
  tests/test_workflow_step_report.py tests/test_workflow_execution.py
```
