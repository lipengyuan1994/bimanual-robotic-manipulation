# Continuous dinner workflow runner

`DinnerWorkflowRunner` connects the local asynchronous visual planner, the live paused-camera bridge, and preloaded `DinnerSkillExecutor` factories to **one continuous dinner worker**. It does not reset the scene, replay teacher actions, manufacture grasp completion, or load a model between capture and execution.

This is development orchestration. The tests use real MuJoCo stepping with injected images/policy forecasts and explicitly synthetic termination results to check lifecycle wiring. They do **not** demonstrate learned dinner-table success, visual reasoning quality, production readiness, or Intel execution.

## Interfaces and preparation order

```python
runner = DinnerWorkflowRunner(
    worker,
    LocalPlannerRunner(LivePlanningSession(worker), preloaded_planner),
    loaded_workflow.executor_factories(worker),
)
runner.start(task)
# Invoke regularly on the same owning thread; at most one control step per tick.
status = runner.tick()
runner.cancel("Operator stop")
runner.close()
```

`executors` maps capability IDs to zero-argument factories that return fresh `DinnerSkillExecutor` objects for this exact worker. Each policy must already be loaded. The selected factory runs **before** planner submission and all camera capture, allowing its reference verification to finish before freshness deadlines start. A prepared executor cannot be reused for another attempt. Policy capability, worker identity, canonical attempt identity, and supervisor termination must agree.

The actor calls `start`, `tick`, `snapshot`, `cancel`, and `close` serially from the constructing thread. Cross-thread and reentrant operations are rejected. The planner's own model thread only receives copied context/images; its completion is polled on the actor. Skill policy inference remains synchronous inside the executor, with existing cancellation, ownership, camera-age, and action-deadline checks before physics. This is not a process supervisor, worker-thread scheduler, or web endpoint.

`start(task)` loads an initial task or explicitly replaces the current task with a new ID and newer instruction revision, within the same physical episode. During replacement the supervisor revokes old execution first; only then is the old planner cancelled, so its late result cannot cancel the replacement task. If another owner replaces a task externally, the old runner reports `replaced` and leaves that replacement alone.

## States and evidence

Normal progress is `ready → planning → executing`, repeated across successful skill boundaries. Each next planning job genuinely recaptures the unchanged successful boundary through the existing stationary transition API. A physical-success milestone alone does not finish a chained skill: the executor must also pass its registered successor-readiness gate.

Terminal states include `execution_complete`, `cancelled`, `needs_clarification`, `failed`, `replaced`, and `recovery_required`. `execution_complete` means that the canonical supervisor recorded all requested executor steps. `independent_task_success` remains `None`; the separate full-workflow physical evaluator owns that conclusion. Planner statements, action-queue exhaustion, or an executor return value without a matching supervisor result cannot set completion.

Events are appended and flushed to disk in `worker/workflow/events.jsonl`, including intents before submission, dispatch-producing polls, executor start and physical control ticks. A persistence failure stops further workflow work and revokes this task's authority, including an attempt already dispatched by the planner. Existing lower-level camera, model, action, physics and outcome evidence stays in the worker directory. The runner does not restart after such an error or claim crash recovery from a partial log.

## Recovery gap

**Automatic failed-step recovery is not implemented.** The supervisor already limits each step to two retries and requires a genuinely newer observation/physical boundary for a retry. The current worker has no approved method for advancing physics without an active owned attempt after failure; its stationary recapture API deliberately covers successful transitions only.

Accordingly, a failed or timed-out attempt reaching `awaiting_observation` produces `recovery_required`, preserving its reason and attempt history. Repeated ticks neither rerun the policy nor consume hidden retries. Guard exceptions stop the workflow safely. No unowned hold step, reset, timestamp relabel, teacher fallback, or retry-budget reset is inserted. A later explicitly owned recovery transition is required before the original recovery milestone can be considered complete.

## Validation

Focused tests cover preparing before capture, two chained steps in one physical environment, genuine next-boundary recapture, failure/action-budget handling, stop/clarify, late planner cancellation, explicit and external replacement, persistence failures before and after dispatch, false executor completion, thread ownership, and mismatched policy factories. A sealed synthetic dataset regression verifies that a reference's canonical **export body seal** is compared against the verified body seal, not against the different byte hash of its JSON file.

Run `tests/test_workflow_runner.py` together with the planner, live bridge, skill executor, and successor-readiness suites. Full learned execution, owned failed-step recovery, clean installation, and actual Intel validation remain separate gates.
