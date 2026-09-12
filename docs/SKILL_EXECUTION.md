# Bounded learned skill execution and measured termination

`DinnerSkillExecutor` connects a preloaded `DinnerSkillPolicy`, the continuous
worker and `SkillOutcomeMonitor`. It does not load teacher actions. The policy
receives only the existing three 480-pixel images and twelve measured joint
positions. An independent monitor reads physical samples from the worker's
append-only evidence; only the resulting outcome and reason reach the supervisor.
This is explicitly simulation instrumentation, not an image-based success detector.

Call `start(attempt_id, observation)` for the canonical active attempt, then
`tick()` on the serialized actor. The first tick uses the exact authorized
observation rather than manufacturing another capture with the same sequence.
Later ticks capture after physical progress. Forecasts, cancellation, expiration,
arm ownership and path/contact checks still pass through the existing worker.
The executor uses a one-action prefix and can request the existing ACT temporal
ensemble. It never changes the policy's image ordering or normalization.

Each applied action must own exactly fifty contiguous 1 kHz samples. Missing,
extra, malformed, unconfirmed or partial physical evidence cannot produce success.
Queue exhaustion, a model completion claim and elapsed action budget are not
success predicates. Budgets end incomplete attempts explicitly. The monitor's
contact, transport, hand-off and released-placement conditions decide the physical
skill outcome. The original full-task evaluator remains a separate authority.

The executor is single-attempt. A retry needs fresh supervisor authorization and
a new executor; cancellation or replacement cannot accidentally terminate the
new task. Model inference is synchronous in `tick`; cancellation predicates and
freshness are checked again after inference before motion. A responsive application
must serialize the actor appropriately; this module is not a web service or a
cross-thread worker scheduler.

## Development limits

A physical placement can finish before a training view's final arm retreat or
parking movement. Passing a physical outcome does **not** establish that the next
checkpoint's starting arm posture is supported. A separate [successor-readiness gate](SUCCESSOR_READINESS.md) now keeps the
same learned attempt active through retreat. The full learned chain and visual
recovery remain unvalidated. The monitor makes no claim
that contact traces prove the absence of unlogged simulator state edits.

Fixture tests use actual MuJoCo stepping with explicitly synthetic camera images
and a held-joint policy. They check integration, evidence rejection, budgets,
stale inference and cancellation. They do not establish learned grasp or dinner
success. Actual learned checkpoints still require their independent validation.

## Recorded teacher-segment check

Sealed audit `20260911T040117-901674a49b49` verifies all seven nominal segments
with phase labels ignored. The stricter final hand-off check was rerun; six
unaffected earlier segment results remain explicitly identified in the audit.
Monitor tests pass all 27 cases. First physical-outcome completion versus the
recorded training-view duration illustrates why successor readiness is separate:

| Skill | First physical completion (controls) | View duration (controls) |
|---|---:|---:|
| Hand-off | 582 | 630 |
| Bar placement and return | 531 | 940 |
| Cup | 500 | 519 |
| Plate | 680 | 762 |
| Drawer | 513 | 560 |
| Spoon | 650 | 704 |
| Fork | 650 | 704 |

These are one authored teacher trajectory, not seven independent test scenes.
The monitor uses a 12-second bar-carry requirement within the placement attempt;
the preceding hand-off independently requires two seconds of receiver ownership.
The full-task evaluator retains its own continuous 14-second carry criterion.
No per-attempt outcome replaces that full-task gate.

## Successor posture evidence and next gate

Read-only sealed analysis `20260911T040255-4778b5b83120` matches every compared
training observation to its exact final 1 kHz physics sample. The largest
physical-success to next-entry joint gaps are 1.080203 rad for the bar and
0.551752 rad for the plate; the cup is effectively unchanged.

The implemented readiness gate preserves the physical-success milestone while the same
owned learned policy completes retreat. It verifies measured joint position,
low joint speed and continuous contact/placement invariants before dispatching
a successor. A bound training-entry reference is an acceptance envelope, never
a command target or a source of teacher actions.

The report proposes 0.005 rad / 0.02 rad/s for ten observations as a development
candidate, not an accepted release threshold. Its joint-only scan fails the bar
transition, which has only six qualifying observations before its original view
ends. The combined contact/readiness gate is now implemented and audited in
[SUCCESSOR_READINESS](SUCCESSOR_READINESS.md). Additional
settled transition demonstrations must be recorded and versioned if needed;
the existing dataset and failed cases must remain unchanged.

The executor records physical success, successor readiness and optional final
parking separately. See the [reference and gate contract](SUCCESSOR_READINESS.md).
