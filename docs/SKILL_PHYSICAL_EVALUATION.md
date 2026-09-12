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
seal `6acc567dfb58ec76392a811eef868a8eb8a48d57f6b507695438cf34551d8a00`.
It selects final-update20,000 checkpoints, MPS, a two-action execution prefix,
the authored nominal-v2 scene, exact teacher preparation, per-skill action budgets
equal to twice the nominal duration, and a1,200-second wall limit. It requires one
attempt for every completed cohort checkpoint; observed outcomes cannot change the
suite.

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

The report requires exactly one verified result and its clean process wrapper for
every skill, rebinds each result to its sealed cohort wrapper and training child,
and preserves every failure. It refuses a partial, interrupted or ambiguous suite.
Even when all six components pass, the report
keeps independent dinner-task success, autonomous-workflow success and release
qualification unset because every component used a disclosed teacher prefix.

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
