# Live planner integration design

Status: lifecycle and actual local Qwen recapture verified in development;
recognition and learned dinner execution remain incomplete. The current
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

- Live jobs retain capture/pause provenance separately from `recorded_reset_only`.
- Planning jobs preserve original context, raw responses and revalidation records;
  cancellation and late-result rejection remain explicit.
- The worker dispatches through explicit revalidation; existing direct dispatch
  must continue rejecting an old proposal paired with a new observation.
- Distinguish capture progress from physical progress. A paused recapture advances
  wall capture time and artifact identity while retaining the control sequence
  and simulation time. Allow this only on the verified
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

## Current API and execution boundaries

`LivePlanningSession(worker)` exposes `begin`, `images`, `check_pending`,
`complete`, `fail` and `cancel`. `begin` acquires an exclusive planning pause and
records the original context. Model code receives verified image copies and the
immutable context. `complete` parses the original response, rechecks unchanged
worker/model/task identity, renders fresh images and records their link to the
original proposal before dispatch. The default profile remains 480-pixel policy cameras. The optional
`overhead1920_wrist480_v1` profile captures a live 1920-by-1080 overhead image
with the original 480-by-270 wrist images. Its live rendering/model integration
check is pending; the recorded-reset high-resolution bundle still cannot authorize
a live action.

`LocalPlannerRunner(session, preloaded_planner)` provides `submit`, nonblocking
`poll`, `cancel` and `close`. A single background thread invokes the already-loaded
planner's `generate` method. All capture, expiry, cancellation and dispatch methods
run on the serialized simulation actor. Poll regularly so expired jobs lose
authority even while model computation continues. Running generation may not be
interruptible; cancelled output is discarded and cannot dispatch later.

Load the model before creating a live planning observation. Generation metadata
and the loaded model-manifest digest are retained separately from the model's
reasoning text. A stub without model provenance remains explicitly unidentified.
The runner does not create a web UI, cross-thread lock or crash supervisor.

## Actual camera and model evidence

A cold renderer changed 75 overhead channels by one level on the second capture
in failed run `20260911T033645-856f3c6ca453`. A six-capture diagnostic
`20260911T033750-b04cbcf18f9f` found subsequent captures identical. `begin` now
retains one explicit warm-up observation before its planning observation, both
under the unchanged owned pause. It does not retry until images happen to match
or relax exact pixel equality. Every original, warm-up and recaptured image remains.

Actual camera run `20260911T034215-002b8fea4b87` passes the injected 95-second
delay with a scripted model response and zero applied actions. Actual local Qwen
MPS run `20260911T034324-a1bda3e43bd4` completes in 29.50 seconds inference after
18.11 seconds model load. It requests clarification because it reports the bar
not visible. Recapture verification passes and no movement occurs. This confirms
the live model/supervisor path; it does not establish accurate recognition or
learned hand-off success. Both evidence seals verify.

## Optional high-resolution live profile

Construct `LivePlanningSession(worker, camera_profile="overhead1920_wrist480_v1")`.
The renderer copies the current compiled model only to enlarge its offscreen
framebuffer, then reads the existing live simulation data. It does not reset the
scene or change the model used for physics. Warm-up, original and fresh captures
retain calibration, source/render model hashes and separate policy observations.
Both planner and ACT image artifacts are reverified before dispatch; the executor
receives the fresh original-resolution policy observation.

Injected-camera and renderer-seam tests verify profile dimensions, unchanged ACT
inputs, camera/model provenance, cancellation and tampered artifacts. Actual
high-resolution rendering and Qwen behavior remain pending while the fixed MPS
training job owns local GPU resources. Earlier actual 480-pixel evidence remains
historical evidence for that profile and source revision.

## Actual high-resolution live check

Run `20260911T045505-ef9d1f373348` completes on native MPS with
`overhead1920_wrist480_v1`, local Qwen weights and exact paused-scene recapture.
The overhead processor grid uses 2,040 vision tokens; each wrist uses 120.
Model load takes 16.62 seconds and inference 85.60 seconds. A CPU regression suite
was running concurrently; these are diagnostic timings, not isolated Intel or
release benchmarks. ACT training was already terminal.

Qwen again reports the practice bar not visible, returns `clarify`, and dispatches
no attempt. Worker evidence has zero physics/action records. The actual overhead
image contains a visible cyan rectangular bar; human inspection therefore suggests
an object-recognition or naming issue rather than complete camera occlusion.
This does not identify its cause. A separately recorded appearance-description
comparison with a corresponding missing-object case is next; do not inject object
coordinates or promote a prompt from a positive case alone. The retained driver,
model response, all warm-up/original/recaptured images and calibration are sealed.

## Paired appearance-description protocol

Protocol `20260911T060932-fab3e0623c4e` freezes four development cases before
inference: bar present/absent, each with the existing instruction and with the
same appended cyan-rectangular-bar description. The added wording explicitly
says the description is not evidence of presence. No location or scene label is
passed to the model. The absent fixture removes only the bar body before model
construction; CPU checks confirm identical remaining body transforms, camera
transforms and robot joints. No physics is stepped and no action is authorized.

The runner requires the current training run to finish, checks the exact model
manifest, and must reproduce the previous positive RGB capture byte-for-byte
before generating. It uses the same HD profile, deterministic local MPS model
and 384-token budget for every case. Positive success requires a valid visible
handoff proposal; negative success requires not-visible with stop/clarify.
Both appearance cases must pass for that pair to pass. One pair is neither full
visual-planner validation nor permission to promote an instruction change.

Prepared driver: `.artifacts/qwen-dinner-appearance-pair.py`; execute with the
protocol ID only after GPU training is terminal. Preparation passed CPU checks;
render replay and all four inference outcomes remain untested.


Replay attempts `20260911T110859-4158aa25c243` and `20260911T111049-12b26169fffe`
both stop before inference: historical overhead pixels differ in 88 channels by
one intensity level, while wrist pixels match. The second uses the live worker's
compiled-model framebuffer override. Exact historical replay remains unproved.
Neither failed attempt is relabeled successful.

Protocol `20260911T111218-c75b807e19fb` instead freezes the last sealed present/absent
captures as a new matched pair. Both instructions see identical saved pixels for
each scene. It retains the original four-case decision gates and records the
historical differences. Driver `.artifacts/qwen-frozen-dinner-pair.py` runs only
local inference, without rendering or action authority. Job 50272 is active;
no inference outcome is claimed yet.


Frozen-pair evaluation `20260911T111242-65da2d81e562` is complete. Baseline and
appearance descriptions both fail with the bar present and pass with it absent.
The appearance-positive response explicitly says no cyan bar is visible. Its
processor retained 2,040 overhead visual tokens (1920x1088 effective pixels) plus
120 per wrist image; the result is not explained by silently reducing the overhead
to the policy camera size. No appearance prompt change is promoted. This is four
captured-image development cases, not a generalization suite or live task run.
