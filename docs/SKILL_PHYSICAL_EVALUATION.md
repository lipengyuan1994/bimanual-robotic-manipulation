# Teacher-prepared learned-skill evaluation

The single-skill evaluator measures whether one ACT checkpoint can complete its
physical outcome and reach the next recorded skill boundary. It is intended for
fast diagnosis before a seven-checkpoint workflow exists.

For skills after the initial hand-off, a clean simulator cannot begin at the
correct physical state. The evaluator therefore replays the sealed scripted
teacher targets from reset up to the selected skill's exact nominal-v2 start.
Those targets advance the real MuJoCo scene through collision and contact checks;
objects are never teleported or attached. The teacher stops before the evaluated
skill. All later actions come from the checkpoint.

Every result records `teacher_actions_used`, `teacher_prefix_actions`, the prefix
source hash, learned action count, physical outcome, and successor or final-parking
readiness. A component passes only when both its physical outcome and transition
readiness pass. Even a pass keeps `independent_task_success`,
`autonomous_workflow_success`, and `release_qualified` unset or false.

The command below is available after the corresponding cohort child training run
has sealed. It shares `.artifacts/.model-job.lock` with training and full workflow
inference, so it stops before allocating an evaluation run while another model job
is active.

The six-skill suite was frozen before any of those checkpoints completed at
[`experiments/six-skill-physical-evaluation-protocol-v1.json`](experiments/six-skill-physical-evaluation-protocol-v1.json),
seal `141e34751c7ae112eb15fb4214f0db65dac2e00d4002a7eb4b02cec03e8f0a25`.
It selects final-update20,000 checkpoints, MPS, a two-action execution prefix,
the authored nominal-v2 scene, exact teacher preparation, per-skill action budgets
equal to twice the nominal duration, and a1,200-second wall limit. It requires one
attempt for every completed cohort checkpoint; observed outcomes cannot change the
suite.
The current seal covers 115 package/runtime and authored-scene/SO-101 files,
including the deployment selection path used before guarded execution. No component
case had run when this unused protocol was regenerated.

Run a completed cohort attempt through the frozen path:

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .artifacts/training-venv/bin/bimanual skill-physical-protocol-run \
  docs/experiments/six-skill-physical-evaluation-protocol-v1.json \
  --skill bar_place_and_return --training-attempt COHORT_ATTEMPT
```

The protocol runner verifies the cohort, exact training child, checkpoint source,
every Python module in the package, and the authored nominal-v2 and SO-101 asset
trees. It repeats protocol and source verification after execution. It reserves the
shared model lease before allocating an attempt, transfers that lease through a
separate guardian to the worker, and independently verifies the child after both
processes are reaped. It exposes a child result only when the process wrapper proves
clean exits, reaps, no forced interruption and complete child binding. It returns an
existing sealed result instead of retrying it; multiple matches stop as ambiguous.
A failed or timed-out physical attempt stays failed. If the root process dies before
it can seal its own record, the preserved unsealed declaration requires manual
adjudication and also blocks automatic retry.

After all six declared evaluations have run, seal their complete result table:

```sh
.artifacts/training-venv/bin/bimanual skill-physical-suite-report \
  docs/experiments/six-skill-physical-evaluation-protocol-v1.json
```

The resumable coordinator performs that sequence without choosing checkpoints by
hand. It first verifies every exact cohort wrapper and child, including the explicit
adjudication of any excluded failed attempt, before it starts a model. It then reuses
or runs each one-time case in frozen order and seals the suite after all six finish:

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .artifacts/training-venv/bin/bimanual skill-physical-protocol-run-all \
  docs/experiments/six-skill-physical-evaluation-protocol-v1.json
```

A normal component failure remains in the result table and does not hide later
skills. A timeout, cancellation, guardian failure or unsealed attempt stops the
sequence for adjudication. The coordinator cannot claim dinner-task, autonomous or
release success.

The report requires exactly one verified result and its clean process wrapper for
every skill, rebinds each result to its sealed cohort wrapper and training child,
and preserves every failure. It refuses a partial, interrupted or ambiguous suite.
Even when all six components pass, the report
keeps independent dinner-task success, autonomous-workflow success and release
qualification unset because every component used a disclosed teacher prefix.

## Preserved v1 preflight failures and corrected v2 evaluation

The v1 suite `20260912T065623-0cb7569a9716` is sealed failed with all six
cases preserved. Its workers were blocked before policy load by the restricted
execution environment reporting MPS unavailable, so every case recorded zero
autonomous actions. A separate real-MPS replay
`20260912T071218-08ff1d062398` preserved those identities, verified native
ARM64 MPS, and found a second integration defect: checkpoint/readiness validation
could make the dispatched capture expire before the first policy input.

The pre-action capture refresh fixes only that stationary-boundary handoff. It
requires the same active attempt, task identity, simulation sequence and
simulation time; it rejects queued actions, altered state, old timestamps and
ordinary duplicate captures. The real-MPS smoke
`20260912T071719-2fcd09c2f758` loaded on `mps:0` and applied one learned action;
its failed outcome is expected because the smoke deliberately imposed a one-action
budget.

The corrected source is frozen in
[`experiments/six-skill-physical-evaluation-protocol-v2.json`](experiments/six-skill-physical-evaluation-protocol-v2.json),
seal `90ad4e2ee6d87ad4104b9b17393cfc4525303136df175c578681185911fbd0df`.
It is a new, separately reported six-case evaluation. It does not replace v1 or
turn either preflight result into manipulation success. Run v2 from a process with
actual Metal access:

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .artifacts/training-venv/bin/bimanual skill-physical-protocol-run-all \
  docs/experiments/six-skill-physical-evaluation-protocol-v2.json
```

V2 completed as suite `20260912T081226-097d224c93cd`, seal
`8b93c3543edb15278afbabe4b3dab0acfd8dbf38f08fe7acf3a89f8ea5005488`.
All six component and process records independently verify, but none passed. Bar
stopped at an explicit forbidden contact in the teacher-prepared boundary. Cup,
plate and fork exhausted their complete learned budgets without a grasp; drawer
and spoon exhausted theirs without their physical milestone. These are failures,
not a basis for an autonomous-workflow or release claim. The next work is trace
diagnosis and, only if justified, a distinct frozen corrective-data and retraining
experiment.

The sealed read-only diagnosis
[`2026-09-12-six-skill-failure-diagnosis.md`](experiments/2026-09-12-six-skill-failure-diagnosis.md)
adds the per-component contact and displacement evidence. It also preserves the
bar's 52 confirmed action-log entries and its partial rejected 53rd action, which
the original failure summary could not count after the contact-guard exception.

```sh
.venv/bin/bimanual skill-physical-failure-analyze 20260912T081226-097d224c93cd
```

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .artifacts/training-venv/bin/bimanual skill-physical-eval \
  --training-run .artifacts/runs/COHORT/training-evidence/runs/TRAINING \
  --dataset .artifacts/datasets/dinner-nominal-v2 \
  --skill-views .artifacts/dinner-skill-views-v2.json \
  --skill bar_place_and_return --device mps \
  --execute-chunk-steps 2 --max-actions 2000
```

The direct `skill-physical-eval` command runs in the calling process and remains a
development diagnostic. The frozen protocol command uses a non-daemon guardian and
spawned worker with bounded cancellation, terminate and kill escalation. It handles
operator timeout and original-parent loss, reaps the native worker, verifies the
shared model lease is released, and never converts a process completion into a
physical component pass.
