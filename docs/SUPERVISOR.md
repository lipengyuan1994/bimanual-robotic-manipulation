# Deterministic task supervisor

`src/bimanual/supervisor.py` implements an executor-facing lifecycle core. It does
not yet connect the isolated teachers into the combined scene, run a visual model,
or establish a successful learned dinner workflow. There are no default registered
capabilities: an integration must explicitly register the executors it can actually
run in its current environment.

## Inputs and authority

- `Capability` fixes a supported skill, symbolic target/destination, arm selection
  and whether that executor needs the shared workspace. Optional `auxiliary_arms`
  grants the other arm to a composite executor and requires shared-workspace
  ownership. The planner still names only the primary arm and cannot request
  auxiliary permissions. This grants joint control for the entire attempt, not
  a restriction to parking movements. Its arguments must satisfy
  the existing `SkillRequest` contract. Registry IDs are unique and records immutable.
- `StepSpec` names one capability, prerequisite step IDs, a positive timeout in
  monotonic nanoseconds and a retry limit from zero through two.
- `TaskSpec` contains task/episode identity, instruction revision, instruction and an
  ordered plan. Duplicate steps, forward/missing prerequisites and unregistered
  capabilities are rejected before replacement of a current task.
- `Observation` is the existing frozen camera/joint contract. No world-object pose,
  simulator contact truth or evaluator success flag is accepted in this input.
- An optional `SkillRequest` proposal must exactly match the next registered step
  and source observation identity. Explanation text is never parsed as success.
  `stop` cancels; `clarify` clears actions and waits for a replacement task with a
  newer instruction revision.

Only the trusted executor adapter calls `finish(..., executor_outcome=...)` with
`succeeded`, `failed` or `unreachable`. A validated `VisibleAssessment` can accompany
that result, using `apparently_complete`, `incomplete` or `uncertain`. It remains
advisory and is preserved even when it disagrees with the executor. The adapter must
choose its executor outcome using the skill's real termination conditions; it must
not forward a planner's completion claim as an executor outcome.

The last executed step produces **`execution_complete`**, not independent task
success. Every snapshot's `evaluation_success` stays null. A separate evaluator
must inspect the actual run and establish the complete dinner-task predicates.
Neither visual confidence, successful model loading nor a passed lifecycle unit
test supplies that evidence.

## Executor API

```python
from bimanual.supervisor import Capability, StepSpec, TaskSpec, TaskSupervisor

# Register only when this callable skill is implemented by the active executor.
registry = [Capability(
    capability_id="drawer-left", skill="open_drawer", arm="left", target="drawer",
    shared_workspace=True,
)]
supervisor = TaskSupervisor(registry, clear_actions=clear_all_pending_actions)
supervisor.load_task(TaskSpec(
    task_id="operator-task-001", episode_id=observation.episode_id,
    instruction_revision=observation.instruction_revision,
    instruction="Open the drawer",
    steps=(StepSpec(step_id="drawer", capability_id="drawer-left",
                    timeout_ns=30_000_000_000, max_retries=2),),
))
attempt = supervisor.dispatch(observation, proposal=validated_planner_request)
```

This fragment illustrates adapter wiring; it does not execute a robot or advertise
a currently composed dinner-scene executor. `dispatch` returns an immutable
`Attempt` with request, source observation, attempt number, deadline and resource
lease. A clarification/stop proposal returns no attempt.

The worker must call `authorize(attempt.attempt_id, current_observation, arm=...,
shared_workspace=...)` **before every action**. Wrong arms/workspace, stale identity,
invalid observations and expired attempts are rejected. Lease checks do not replace
joint bounds, policy checkpoint validation, collision guards or action-queue
sequence/expiry checks. `GuardedActionQueue` remains responsible for the latter.
For a hand-off capability, both arms belong to the same attempt; another step cannot
start concurrently in this supervisor.

When the executor stops, call `finish` with the same attempt ID, its latest valid
observation, an explicit outcome and a bounded reason. Successful completion requires
sequence, capture time and simulation time to advance beyond the attempt's start.
An invalid completion payload or rejected execution observation clears pending
actions and ends that attempt as failed; it cannot silently resume under the old ID.

Call `tick()` regularly while the executor is waiting or blocked. The injected
clock defaults to `time.monotonic_ns`; the core does not create a timer thread.
`authorize`, `dispatch` and `tick` enforce an exact `now >= deadline` timeout. A late
success cannot overwrite a timed-out result. Each attempt has its own step timeout;
three attempts can consume up to three such windows. There is no separate overall
task deadline yet.

## Fresh observations and bounded recovery

The default live dispatch/authorization age limit is **2,000,000,000 ns (two wall
seconds)** from camera capture, not from inference completion. The constructor
accepts an explicit positive limit for a documented integration; it never adjusts
that limit according to model latency. A Qwen response that took longer than the
accepted age cannot dispatch from its old source observation. Capture a fresh
observation and obtain a fresh proposal; never retag an old response with a new
sequence number. ACT queue expiry is still checked separately and is not extended.

Every step change and every retry requires a capture strictly after the previous
attempt ended, with strictly larger observation sequence and simulation time.
Changing only one timestamp, relabelling an old frame, or reusing the finishing
observation is rejected. Within an attempt, repeating the exact same immutable
observation is permitted for checks; reusing its sequence with changed capture,
time, joints or images is rejected. A higher sequence must advance capture and
simulation time together. The observation contract checks camera synchronization;
image artifact integrity remains the capture/loader adapter's responsibility.

A recoverable `failed` or `timed_out` result enters `awaiting_observation` when a
retry remains. Recovery preserves the failed attempt and never auto-dispatches
another action. The caller must supply a genuinely fresh observation and may
request the same bounded executor again. There are at most two retries, hence three
attempts per step. Exhaustion and `unreachable` end the task as failed. This is a
retry mechanism, not yet a learned recovery strategy or automatic missing-object
resolution.

## Cancellation, task changes and records

`clear_actions` is an injected synchronous callback. Call it with no arguments;
for the existing queue it may be `queue.clear`. If the executor also caches actions
inside a policy, the callback must clear that cache too, for example by calling
both `queue.clear()` and `policy.reset()`. Cancellation, task changes, attempt
boundaries, timeouts and rejected execution contexts clear pending actions.
A callback exception marks the supervisor failed and raises a worker-stop error;
the host must stop the worker because the core cannot guarantee the external queue
was cleared.

`cancel()` requires no observation, so the operator need not wait for a camera or
model response. Loading another validated task cancels any active attempt and
clears the queue. Task IDs cannot be reused. Within the same episode, replacement
requires a strictly newer instruction revision. Late results with old attempt IDs
cannot complete a new task.

`snapshot()` returns frozen task specifications, completed-step IDs, the current
attempt and tuple-based attempt/event history, including failures and replacements.
Stored observations and requests are also frozen contracts. Earlier snapshots do
not change when the supervisor advances. Persist snapshots/events through the
application's evidence layer; this core has no database, crash-recovery process or
automatic disk writer yet.

Use one serialized supervisor/worker per simulation. The core is synchronous and
not a cross-thread/distributed lock. The application must serialize authorization,
action dispatch, cancellation and result delivery so no action bypasses a lease
check after cancellation. No FastAPI route or web control is wired by this module.

## Validation

`tests/test_supervisor.py` covers serial prerequisites, capability validation,
resource leases, immutable history, real `GuardedActionQueue` cancellation, task
replacement, planner/visible-assessment authority separation, stale/future/reused
observations, fresh step transitions, all three allowed attempts, deadline expiry,
unreachable objects, malformed executor results, clock regression and queue-clear
failure. These lifecycle checks run without model downloads or physics success
claims. Full-scene physical execution, automatic recovery quality and independent
release evaluations remain separate work.

## Guarded policy-control bridge

`SupervisedPolicyControl` owns the supervisor and one bound action queue for a
serialized simulation worker. It registers no capabilities automatically and
performs no inference or physical stepping. `bind(attempt_id, ...)` resolves the
canonical active attempt rather than accepting caller-provided ownership. The
binding fixes checkpoint identity, action horizon, controlled arms and hold targets.

`offer` and `take` authorize the same attempt, arms, shared workspace and current
observation before accessing the queue. Normal and temporal queues both retain
whole-forecast validation and freshness checks. A second bind cannot replace the
controller within the same attempt. Pending forecasts cannot be replaced, and
after draining, a new forecast requires the next observation sequence with
advancing capture and simulation times. The deadline is checked again at the
actual queue timestamp, so expiry during authorization cannot return an action. Lifecycle callbacks discard queue and temporal
history on cancellation, task replacement, timeout and finish.

Rejected operations fail the matching active attempt through the supervisor;
already closed timeout/context failures remain intact. They cannot clear a queue
and silently retry under the same attempt ID. A retry requires the supervisor's
fresh-observation checks and remaining retry budget. Merely clearing state is not
a successful step or a new attempt.

Regression tests cover deadline crossing, repeated forecasts, pending replacement,
fresh continuation and lifecycle clearing. The temporal suite separately passes
all 35 tests in the native LeRobot environment. See [status](STATUS.md) for the
current full-suite result. These validate the control contract, not a
learned dinner policy. The worker must serialize these calls with physical
stepping; this bridge is not a thread-safe physical actor by itself.

## Successful stationary transition

`dispatch_stationary` is an explicit trusted-worker entry point for a newly
rendered capture after a successful step while physics remains paused. It requires
the actual predecessor terminal, unchanged state and camera digests, distinct
artifact paths and capture after the finish. It records the exception and leaves
normal dispatch, recovery and completion rules intact. See
[continuous dinner control](DINNER_CONTROL.md) for the worker responsibilities.
