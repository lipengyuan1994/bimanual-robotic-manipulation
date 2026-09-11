# Live planner integration design

Status: proposed implementation; no live dispatch is claimed. The current
reset-only sensor bundle remains non-authorizing. This design addresses the
measured 91–95 second Qwen inference time while preserving the two-second action
freshness guard. See [planner](PLANNER.md), [sensors](PLANNER_SENSORS.md), and
[supervisor](SUPERVISOR.md).

## Owned pause and fresh revalidation

One simulation worker owns stepping, camera capture, task revision and dispatch.
After the prior skill finishes or stops, it clears action queues and pauses at a
recorded physics boundary. A pause record identifies the worker generation, task
revision, scene/configuration revision and simulation time. The UI must state
that simulation is paused while planning; wall time continues normally.

Capture actual live planner images and retain their original wall timestamps and
hashes. Run Qwen asynchronously so stop/task-change requests remain responsive.
Its returned proposal continues to reference those original images. Do not edit
its timestamps or present it as a fresh model response.

Before dispatch, genuinely capture again under the same exclusive pause. Check
unchanged worker generation, task/configuration identity, pause ownership,
measured joint state and exact planner-camera pixels. A mismatch discards the
proposal. Object truth is not an alternative source of confirmation.

A separate worker-issued revalidation record links the immutable proposal and
both captures. Only that verified bridge may derive an executor request referencing
the fresh capture. Action expiry remains two seconds; the execution timeout starts
at dispatch, not before the long planning call. Every ACT forecast retains its
own fresh observations and action guards.

## Required implementation boundaries

- Introduce live capture/pause provenance separately from `recorded_reset_only`.
- Add planner job lifecycle and cancellation, including rejection of late results.
- Add an explicit supervisor revalidation entry point; existing direct dispatch
  must continue rejecting an old proposal paired with a new observation.
- Distinguish capture progress from physical progress. A paused recapture advances
  wall time and sequence but not simulation time. Allow this only on the verified
  pause path; same-time captures cannot prove task completion or recovery progress.
- Register incremental skill executors sharing one environment. The continuous
  scripted dinner teacher does not establish learned skill availability.

## Acceptance checks

A simulated 95-second planning delay must fail direct dispatch and succeed only
through a valid fresh recapture bridge. Reject reused image files presented as
new captures, changed image/joint/configuration identity, lost ownership, worker
restart, task replacement and expired revalidation. Cancellation during planning
must prevent any late dispatch and leave action queues empty.

Physical completion still requires independent outcome checks and actual physical
progress. Qwen's apparent-completion statement is not task success. Recovery
limits remain unchanged. Unsupported learned dinner skills stop with an explicit
reason rather than falling back silently to the teacher.
