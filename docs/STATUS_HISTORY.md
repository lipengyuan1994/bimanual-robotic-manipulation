# Historical status entries

This preserves the accumulated status through the workflow-cohort implementation
turn on September 11. Process and next-step statements below are historical.
Use [STATUS](STATUS.md) for the current handoff.

# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Readiness follows [ROADMAP](ROADMAP.md); original scope remains in [PLAN](PLAN.md).

## Current readiness

- **M0 complete:** native environment, evidence infrastructure, portal, seven
  lessons, learning site and README/CI synchronization.
- **M1 locally complete:** the supported `dinner-teacher` command completes the
  continuous contact workflow with all three cameras from clean source. This is
  one authored scene with scripted control; Intel checks remain blocked by B2.
- **M2 in progress:** real ACT training/inference, guarded actions, Qwen proposals
  and a supervisor core exist. Learned open-hand approach passes two validation
  starts but fails nominal. No learned grasp or complete learned dinner workflow
  has passed. Live paused-scene planning is connected; learned skill termination
  and recovery still need end-to-end validation.
- **M3 incomplete:** no frozen release evaluation, Intel/OpenVINO execution or
  submission package. **M4 pending:** production reliability and operational gates.

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Prior-code eligibility is still unconfirmed; no organizer approval is claimed.
Spend remains zero. Physical-robot deployment is outside this simulation release.

## First continuous teacher success

Sealed run **`20260911T011032-a9fda4aee41f`** preserves passing attempt 28,
profile `dinner_horizontal_release_v18`. It executes hand-off/bar parking, cup,
plate, drawer opening, spoon and fork in **one continuous episode**. No objects
are reset, attached artificially or moved by direct object forces during execution.

The independent audit verifies:

- 240,950 contiguous physics samples at 1 kHz, with 20 Hz controls.
- Donor/shared/receiver ownership, airborne transports, drawer operation and all
  required release/hold intervals.
- Zero forbidden contacts or disturbances of previously accepted placements.
- All 2,000 final samples with every object placed and stable.
- Final XY errors: spoon 3.969 mm, fork 9.640 mm, plate 13.555 mm, cup 18.071 mm,
  bar 5.996 mm. Plate/cup retain the 20 mm limit; utensils/bar retain 25 mm.

The run took 240.95 simulated / 124.26 wall seconds **without camera rendering**.
The cup is close to its tolerance; this is not robustness evidence. The sealed
bundle includes the scene/assets/licenses, original teacher input trajectories
and manifests, actual actions/physics traces, runtime source and audit source/results.
Its integrity verifies and the self-contained scene loads. The original feasibility run has no video. A later clean supported-command run
`20260911T013229-b7184e9ba66a` supplies its own passing camera replay.

[Full result and integration work](DINNER_SCENE.md);
[all attempts](experiments/2026-09-10-dinner-sequence-feasibility.md).
Attempts 15 and 22 completed their motion loops but failed plate position.
Attempts 23–27 exposed arm/camera/cabinet collisions or retained jaw support.
Attempt 28 withdraws the jaw horizontally before lifting, allowing the plate to
settle free. Those failures remain unchanged.

## Learned-control evidence

Weighted ACT training `20260910T225506-3f5e98132b20` completed 2,000 native MPS
updates in 413.30 seconds from clean checkpoint `781556d`; model, processor and
sampler continuation checks passed. It uses six training cases, with validation
cases excluded. Improved prediction errors did not make the original four-second
physical tests pass.

The fixed eight-second protocol `20260911T005034-081e3e8a71ed` also failed all three
starts: position converged to 1.43–1.48 mm, but only 37/100 terminal samples passed
because of repeated movement. More time alone did not solve the problem.

The next six-run comparison, **`20260911T010051-7d76cac619de`**, verifies identical
checkpoint bytes and declared starts for two modes under protocol
`20260911T005658-6ada62ed651f`:

| Mode | Nominal start 1000 | Validation 2000 / 2001 |
|---|---|---|
| Replan every control step | Failed, stalls 125.7 mm away | Both pass all 100 terminal samples |
| Same cadence + ACT ensemble 0.01 | Failed, stalls 122.9 mm away | Both pass, 0.976 mm endpoint error |

Ensembling uses the installed LeRobot implementation. Every raw forecast is
validated before averaging, and the averaged action is validated again. No
teacher target enters inference; all runs retain actual images/joints, forecasts,
actions and independent scoring truth. These are **open-hand approach** outcomes,
not grasp or dinner-task successes. The repeated validation starts are not four
independent successful scenes. The nominal failure blocks adoption as a reliable
skill. The optional runtime adapter now has history/cancellation and official LeRobot
parity tests; those checks do not resolve the nominal policy failure. [Complete runs, caveats and next diagnosis](POLICY_ROLLOUT.md).

## Visual planning and execution authority

Local Qwen3-VL-4B runs on CPU and MPS from pinned, verified weights. Version-2
proposals reject malformed output and manipulation of an unconfirmed target.
A sealed four-probe resolution comparison, `20260911T004313-10b11352cb3c`, preserves
all outcomes. The 1920-pixel overhead pair distinguishes present/missing practice
blocks, taking 91–95 seconds inference; the 960 missing case contradicts itself
and is rejected. These development cases do not prove live planning or broader
scene understanding. [Planner](PLANNER.md), [sensor evidence](PLANNER_SENSORS.md).

The sensor bundle preserves original ACT observations and verifies reset identity,
calibration, baseline pixel equality and actual processor grids. It is explicitly
reset-only, not a way to relabel old images as fresh. The [supervisor](SUPERVISOR.md)
has tested prerequisites, ownership, deadlines, cancellation and at most two
retries. A continuous worker and live planner bridge are now connected; see the
current handoff below for actual evidence and remaining recognition/skill gaps.

## Implemented foundation and references

Two pinned, namespaced SO-101 arms retain source licenses, joint limits and actuator
behavior. Native stepping, overhead/wrist cameras, bounded IK, per-physics-step
contact checks and actual contact grasp/hand-off exist. Default physics is 200 Hz;
[explicit 1 kHz profiles](decisions/0004-explicit-physics-profiles.md) support tableware.

Supported individual commands remain `bimanual grasp`, `handoff`, `drawer`,
`utensils`, `plate` and `cup`. The complete fixed-scene teacher is available as `bimanual dinner-teacher`. The portal at `http://127.0.0.1:8768/` is read-only, with evidence,
replays, lessons and recorded planner decisions; it is not a live robot operator UI.

- [Physical foundation](DUAL_ARM_FOUNDATION.md), [grasp](CONTACT_GRASP.md),
  [hand-off](HANDOFF.md), [drawer](DRAWER.md), [utensils](UTENSILS.md),
  [cup](CUP.md), [plate](PLATE.md).
- [Interfaces](INTERFACES.md), [validated LeRobot export](DATASETS.md),
  [native ACT training](TRAINING.md), [learning record](LEARNING.md).
- [Documentation index](README.md) and linked experiment registers preserve earlier
  successes/failures; historical preparation remains separate from manipulation.

## Verification and source checkpoint

Earlier implementation checkpoint **`4c8af294965a702c1ddbef1a035abf12d6edcc86`** passed
[GitHub CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34547899994).
The supported dinner teacher is committed at `bc0b5c0`; its clean rendered result
and portal are committed at `bdcd4e4`. Use `git rev-parse HEAD` for the latest
handoff commit; subsequent sampler changes do not alter the sealed teacher run. [Draft PR #1](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/pull/1)
is open and unmerged.

Latest `scripts/check.sh`: **777 passed, fourteen explicit optional-training skips,
eight rendering tests deselected**, with Ruff, formatting, docs and README checks.
Log: `.artifacts/checks-dinner-evaluation.log`; all current auxiliary-arm,
stationary transition, registry, policy adapter and worker cases are included.
The preceding dinner-only
checkpoint had 403 passing tests. The preceding seven actual
rendering tests and the additional sensor integration rendering test passed
separately; do not count deselections/skips as passes. Four actual sensor bundles
and real Qwen/ACT runs also have separate verified evidence.

The real one-step CPU ACT/checkpoint/sampler check passed previously in the isolated
training environment. Native TypeScript checks and portal build passed before this
documentation-only turn; no frontend source changed. Earlier native audits include
CPU/MPS execution and architecture checks; those do not establish model quality
or Intel compliance.

## External dependencies

| ID | Needed | Effect |
|---|---|---|
| B1 | Event-window authorization | Resolved for new work by decision 0003 |
| B2 | Free Core Ultra Series 2/3 allocation | Last checked: BM-PTL request Pending Review; no granted host or Intel validation |
| B3 | Assets/seeds, pouring scope, prior-code eligibility, hosting interpretation | Submission scope/packaging remain provisional |

The user registered and requested `bimanual-sim-intel`, BM-PTL Series 3, September
10–17. Catalog choices offered Windows 11; Ubuntu was requested. Verify hardware,
expiry, permissions, rendering and OpenVINO after access is granted. See
[Intel access](INTEL_ACCESS.md) and [organizer questions](ORGANIZER_QUESTIONS.md).
Verified submission deadline: September 16, 2:30 PM EDT; required presentation
assets include application URL, cover, video and slides. No organizer message or
hackathon submission has been sent.

## Current handoff — live planning, independent scoring and training

The continuous worker integration is committed at `1e9e1cb`. This follow-up adds
an independent outcome evaluator, owned-pause planning, a background local model
runner, and an optional terminal learning-rate schedule. Final checks pass and checkpoint `9ca38d1` is pushed. The development diagnostics
retain their recorded dirty-source lineage.

- Fixed 20,000-update MPS training **`20260911T023624-0e2a88d90d4a`** completed
  in 3,704.47 seconds from clean `c279611`. Checkpoint, processor, sampler and
  seal verification pass. Handle 61071 is terminal.
- Offline assessment `20260911T033850-4724772f122e` and frozen gate
  **`20260911T033913-cf2f84439152`** pass five of six checks but fail initial
  pan direction. Nominal launch tool error falls to 0.542 mm, yet the first pan
  prediction is -0.002877 rad against +0.000564 rad. **No physical rollout or
  promotion follows.** All prior failures and the acceptance thresholds remain.
- Phase-free audit **`20260911T033217-cd9792a67e58`** passes the retained clean
  teacher trajectory after replacing every stage label. It checks 4,819 actions
  and 240,950 samples using physical outcomes. Instrumentation declarations are
  source-inspected, not proof against unlogged edits. [Evaluator](DINNER_OUTCOMES.md).
- First real paused-camera check `20260911T033645-856f3c6ca453` failed exact pixel
  equality: 75 overhead channels differed by one level on cold initialization.
  Repeat capture diagnostic `20260911T033750-b04cbcf18f9f` isolated this effect.
  The bridge now retains a separate warm-up capture before the planning capture;
  exact equality remains mandatory. Warmed actual-camera check
  **`20260911T034215-002b8fea4b87`** passes a simulated 95-second planning delay,
  rejecting direct stale dispatch and allowing only verified fresh revalidation.
- Actual live Qwen MPS run **`20260911T034324-a1bda3e43bd4`** completed with
  18.11 seconds load and 29.50 seconds inference, three 480-pixel cameras, and
  verified recapture. It reported the bar not visible and requested clarification;
  the supervisor applied **zero actions**. This is a functioning integration,
  not successful object recognition or manipulation. All three completed new
  diagnostic seals verify. [Live planner](PLANNER_LIVE_INTEGRATION.md).

Next: validate and preregister the fixed 20,000-update terminal-decay comparison,
then train from the same initialization with unchanged data and frozen gates.
Only a fully passing final checkpoint may enter the existing physical protocol.
Live high-resolution recognition and measured skill termination remain open.
No model job is active after the completed Qwen diagnostic; check the final
entry for any subsequently launched training handle.

## Historical implementation entries

The entries below preserve the implementation sequence and earlier process
observations. Their “active” or “next” wording is historical; the current handoff
above and final entry below determine present process state.

## Packaged teacher integration checkpoint

The first supported-command run `20260911T012748-2d4a69c7807d` reproduces all
240,950 physics samples and passes the independent full-workflow score, with zero
failed gates (126.17 actor wall seconds). Its outer manifest remains **failed**:
the actor originally read the wrong scorer field name. That integration error is
fixed and regression-tested; the historical failed manifest is retained unchanged.
A fresh corrected run now passes (below). No learned policy was involved.

Nine actor tests pass, including altered asset rejection and cancellation before
initialization/midway through a physics step. The independent scorer has 28 passing
tests and reproduces attempt 28 while rejecting attempt 22. The built wheel loads
its assets and scene from outside the repository without historical experiment
folders. Full checks and clean rendered reproduction now pass.

ACT analysis `20260911T012244-b6feaf688748` verifies exact nominal reset input
matches training, yet the first predicted movement has the wrong sign. Proposal
`20260911T012605-8265a1f82ac4` changes only training-anchor sampling; its completed follow-up failed the offline
gate below, and held-out cases remain excluded. See [training](TRAINING.md).


### Clean rendered M1 reproduction

Run **`20260911T013229-b7184e9ba66a`** is completed and its seal verifies. Source
is clean checkpoint `bc0b5c084affc4bfd06653a660af58f750cdc7c2`. All physical metrics
match the initial baseline: 240,950 samples, 4,819 applied controls, zero forbidden
contacts, maximum overlap 1.831 mm, and 2,000 terminal all-placed samples. Actual
three-camera capture produced 483 replay frames at 2 Hz, played at 5x. Final camera
image inspected. Execution/capture took 147.90 wall seconds for 240.95 simulation
seconds; post-run scoring/encoding is excluded from that actor timing.

M1 local physical foundation is complete. The built wheel includes the fixed
scene/plan, the worker validates controls and contacts, and the independent scorer
rejects malformed, partial and physically unsuccessful traces. This establishes
one authored scripted workflow, not learned execution, scene robustness or Intel
compliance. The portal now exposes the dinner replay and its independent score;
native ARM64 TypeScript checks and production build pass. The updated portal was
opened and checked: completed dinner replay, independent score link and M1 status
are visible; the score endpoint serves the verified result.


The `approach_nominal_launch_v1` sampler passes 32 focused tests (one real-ACT
check explicitly skipped). Full checks pass: 414 tests, three optional-training
skips and eight render deselections (`.artifacts/checks-nominal-launch-profile.log`).

Run `20260911T014325-bad8e53b82db` completed 2,000 native MPS updates in 415.15 seconds
from clean `497e23a`; checkpoint/processor/sampler reloads and evidence seal verify.
Offline run `20260911T015030-96f6a94b5887` and comparison
`20260911T015050-0e94cba7b117` fail the preregistered gate: nominal launch tool error
improves 6.960→2.828 mm, but its first pan command remains backward; endpoint error
worsens 1.180→1.918 mm, and other training starts regress beyond tolerance. No
physical run was attempted with the new model. Do not promote it or alter the gate.

The nominal-launch experiment is terminal. Its subsequent no-VAE and dropout
follow-ups are recorded below. Keep all six training trajectories eligible and validation
states excluded. Prepared training-only diagnostic drivers remain
`.artifacts/approach-nominal-launch-offline.py <training-run>` and
`.artifacts/compare-nominal-launch-offline.py <offline-run>`; the latter retains
this experiment's frozen gate, not a generic future acceptance threshold.


Next experiment: matched no-VAE ACT under protocol
`20260911T015715-5ef000508650`. Label audit `20260911T015423-6a91877d602a` found no
exact input/label conflicts in the verified 480 training frames. Analysis
`20260911T015525-e3f5eb07e758` motivates removing the optional VAE branch while
retaining the same 2,000-update budget and all other settings. Exact shared
initialization is verified by `20260911T015639-f799b069df61`; four actual LeRobot
initializer/CPU-training/checkpoint/reference-rejection tests pass. Standard ACT remains the default.
The preregistered offline gate must pass before any new physical trial.


No-VAE run `20260911T020002-4ce2f8fd061b` completed 2,000 native MPS updates
in 383.62 seconds from clean `1ae01ae`. Shared initialization, checkpoint,
processor and sampler reload checks pass; its evidence seal verifies.
Offline assessment `20260911T021007-6e147d54a964` and frozen comparison
`20260911T021025-e0da5ef47834` **fail**: nominal launch tool error is 7.635 mm
versus 6.960 mm baseline, the first pan target remains backward, and other
training starts regress. No physical trial was run or checkpoint promoted.
See [training results](TRAINING.md).

The supported optional temporal action queue is implemented with full-forecast
validation before official LeRobot averaging, second-stage target checks, and
complete history clearing on errors/cancellation/task changes. All 33 queue
tests pass in the native training environment, including real official parity;
30 pass in the base environment with three optional checks skipped. The full
base suite passes 445 tests (ten optional skips, eight render deselections).
Logs: `.artifacts/temporal-actions-lerobot-tests.log` and
`.artifacts/checks-temporal-no-vae-final.log`. No new physical success is claimed.

The no-VAE training and assessment are terminal. The fitting audit and next
controlled intervention are recorded below. Do not repeat failed candidates or
add validation states to training. The frozen no-VAE comparison remains unchanged.


Follow-up declared: dropout-zero protocol `20260911T021430-2b8791b001be` keeps
all other no-VAE settings and the original acceptance gates. The retained
training-only audit is `20260911T021301-8ac3000fe6d8`. An actual one-update CPU
checkpoint/processor/sampler round-trip passes for this configuration. Full
checks passed: 445 tests, 11 explicit optional-training skips, eight rendering
deselections; log `.artifacts/checks-dropout-config.log`. The actual dropout-zero
CPU test passes separately.

Dropout-zero training `20260911T021733-b67e2a69d96e` is completed from clean
`6f878db`; native MPS, 2,000 updates, 374.88 seconds (not an isolated benchmark).
Offline assessment `20260911T022407-3ae87ae922f8` and frozen comparison
`20260911T022426-bc9a525f85c4` fail: nominal tool error improves to 1.470 mm but
first-pan direction and other-start retention fail. Checkpoint seal/reloads pass.
No physical rollout or promotion follows. Processes 67509 and 33394 are terminal.


Continuous dinner recording is implemented behind `dinner-teacher
--record-demonstration`, independent of replay. Fifteen focused tests pass,
including complete-transition and interruption boundary checks. Full checks pass: 452 tests, eleven optional-training skips and eight render
deselections (`.artifacts/checks-dinner-recorder.log`); handle 58082 is terminal.
Full-rate capture and export are verified below. The proposed [live planner bridge](PLANNER_LIVE_INTEGRATION.md)
records explicit pause ownership/fresh revalidation requirements and remains
unimplemented; old images are never simply retimestamped.


Physical capture `20260911T022644-a24a56ff004c` is completed from clean
`6c6c991`; process 84841 is terminal. Independent audit
`20260911T023608-8896f729ffd5` verifies the successful physical score, 4,819 aligned
actions, 4,820 observations and 14,460 RGB files. Actor/capture time 445.07 seconds,
240.95 simulated seconds; source size approximately 595 MiB. Final preview inspected.


Long-episode export timestamp verification now compares the exact LeRobot
float32 storage value, replacing a tolerance that could reject correct late
frames. All 23 native LeRobot dataset tests pass, including an actual 4,819-frame
numeric timestamp fixture. Full checks pass: 461 tests, twelve optional skips and eight render deselections;
handle 26057 is terminal. Log `.artifacts/checks-long-timestamps.log`.

Next model experiment is declared by `20260911T023056-6649c0803bb0`: same
no-VAE/dropout-zero settings and frozen acceptance gates, fixed 20,000 updates
from the same initialization. It is now running as described below. Estimate about 62.5 minutes
native MPS, zero spend; physical capture ended before it started. Prepared driver:
`.artifacts/approach-fixed-20000.py`. Prepared post-capture recording audit:
`.artifacts/verify-dinner-recording.py`; it requires the sealed successful run.


Active jobs (check handles before restarting):

- Fixed-duration ACT: `20260911T023624-0e2a88d90d4a`, handle 61071,
  `.artifacts/approach-fixed-20000.log`. 20,000 updates; inference/physical gates
  remain pending. Source lineage will be verified after sealing.
- Dinner LeRobot export completed; handle 99921 is terminal. All-row read-back
  and manifest verification pass for `.artifacts/datasets/dinner-nominal-v1`: 4,819
  transitions, one nominal training episode. Manifest file SHA-256
  `cffe319f4e63a422e32cf740989932d06deccd49a9883ed05f53f545e3ed4df9`.
- Skill-view and trainer integration now passes the real CPU test described
  below; learned bimanual execution remains unimplemented.

After model completion, run `.artifacts/approach-fixed-20000-offline.py <run>`
then `.artifacts/compare-fixed-20000-offline.py <offline-run>`. Failed gates still
prohibit physical validation. Do not select intermediate checkpoints.


Bounded skill-view/trainer integration passes the real CPU test below; full
checks pass.
CLI flags `train --skill-views <manifest> --skill-id <id>` select a verified
interval; numeric normalization and sample indices use that interval, images
retain explicitly declared parent-training statistics. Adapter/view and actual CPU checkpoint tests pass; full checks now pass.
The existing 20,000-update MPS job remains untouched and is the only GPU job.


Dinner export verification `20260911T024510-e940a5d9fee0` is completed. The seven
real skill views are created at `.artifacts/dinner-skill-views-v1.json`, canonical
hash `45bf9464a68a93f04ccc23fdd7ebbe473040af40e6b6f1e6414e9e5b521487f2`.
Three native CPU integration tests pass, including one ACT optimizer step on the
real 940-transition bar-placement view and checkpoint/processor/sampler reload.
This proves the selected data path, not learned skill success. Full checks pass: 510 tests, thirteen optional skips and eight render
deselections. Handle 13759 is terminal; log `.artifacts/checks-skill-training.log`. Export/view
creation/CPU-test handles 99921, 78500, 40623 and 56003 are terminal.


Explicit owned queues and a supervisor control bridge are committed at
`d99bcdc`. Fixed left/right/both permissions come from the canonical active
attempt, never model outputs. Invalid operations fail that attempt and cannot
silently rebind/retry; lifecycle changes clear temporal history. The final bridge-focused suite passes 29 tests, including both auxiliary-arm
directions. Native temporal suite: all 35 passed. The preceding full check
(541 passes) under handle 61834 is terminal; final regression handle 83108
is terminal: **553 passed, thirteen optional skips, eight render
deselections**, 207.65 seconds, 340 documentation links and README synchronization
passed (`.artifacts/checks-supervised-control-final.log`). Two subsequently added
auxiliary integration cases pass in the 29-test focused suite; they were not
collected by that already-running full check.
No new learned physical execution is claimed.

Plan audit `20260911T025456-e018c8864c19` identifies both-arm entry parking in
the plate/drawer composite views. The registry now supports explicit auxiliary-arm ownership without changing
planner request permissions. Plate/drawer need auxiliary right; bar placement
also needs auxiliary left. This grants joint control for the entire attempt,
not a restriction to parking. Verified skill/checkpoint registration and actual
continuous learned execution remain next; the bridge never infers permissions.

Review fixes reject deadline crossing during authorization, replacement of pending
forecasts, and repeated or skipped observations at forecast boundaries. Invalid
operations close the attempt, preserving the supervisor timeout/retry record.
`docs/project.json` reflects this integration; README synchronization passes.
The fixed MPS run is still active under 61071; 9,551 updates were observed this
turn. Its final checkpoint and frozen quality gates remain pending.


## Continuous learned-control integration in progress

The preceding goal turn made implementation progress at `d99bcdc`; the full
objective remains active. The development checkpoint registry verifies sealed
training, exact skill/view lineage, sampler boundaries, normalization and ACT
interfaces. A local inference adapter binds the checkpoint package to the exact
registered capability and exposes only cameras/joints to ACT.

Actual one-update CPU bar-view training `20260911T031045-ba4157987d18` completed
in 21.19 seconds. Runtime check `20260911T031612-91ae14d2402a` loaded that saved
checkpoint and predicted a finite 10-by-12 forecast from original training frame
630. Load/verification took 18.16 seconds and one CPU inference 0.103 seconds,
with four CPU threads. Zero physical actions were applied and no learned-quality
claim is made. Source dirty state is recorded honestly. CLI `skill-checkpoint`
verified this same artifact.

The incremental physical worker and successful stationary handover pass
focused tests and review. Stationary dispatch requires newly rendered image artifacts after a
successful predecessor, unchanged physical state, and a worker-owned pause;
normal dispatch and failed-step recovery retain their existing rules.
See [continuous dinner control](DINNER_CONTROL.md). Full checks passed under terminal handle 96318: 612 tests, thirteen optional
skips, eight render deselections, 344 documentation links and README
synchronization (`.artifacts/checks-continuous-control.log`, 222.21 seconds). The MPS run remains active under 61071 (13,391 updates
observed); do not duplicate or promote it before the fixed final assessment.


Actual worker camera/control check `20260911T032007-745257453221` completed: six
real images, one held-target control step (0.05 simulated seconds), then explicit
cancellation. Seal and image artifacts verify; overhead and both wrist views
were inspected. This tests worker plumbing, with no learned policy or task
completion claim. CPU check 57476, inference check 75406, CLI check 74832 and
camera check 1635 are terminal. Focused combined registry/policy/supervisor tests
pass 100 cases; worker/bridge tests pass 47 separately (overlapping suites, not
147 independent tests). The only active model job remains 61071.


Continuous worker/registry/inference integration is ready for a feature-branch
checkpoint. Full checks include the latest stationary and model-integrity guards.
The actual camera diagnostic and CPU inference evidence are separate from those
base tests; neither establishes learned task quality. Next executable model work
remains the unchanged final offline gate for 61071 once its 20,000 updates seal.

## Latest verification and next training protocol

The four-update actual CPU ACT schedule/reload check passes (6.44 seconds) with
the repository-local Hugging Face cache. The first invocation failed before
training because its default cache location was unwritable; both logs remain.
The native base suite completed under terminal handle 4841: 689 passed,
14 optional skips, eight render deselections in 287.04 seconds.
Previous committed `1e9e1cb` GitHub CI is now verified successful.

Preregistered comparison **`20260911T034840-1019934f5c06`** changes only the
terminal learning-rate schedule: 1e-5 through update 15,000, linear decrease to
1e-6 at update 20,000. Same initialization, data, sampler, seed and six gates.
Final checkpoint only; zero spend. This protocol is sealed before training.
Training started after final checks and clean checkpoint `9ca38d1`; see below.

All eight actual rendering tests pass (71.75 seconds;
`.artifacts/render-live-planning-checkpoint.log`). The updated documentation
index checks 351 links and README synchronization passes. A short exercise in
[learning](LEARNING.md) connects the failed prediction gate to lessons 4 and 6.

Final checks pass with Ruff, formatting, 351 documentation links and README
synchronization. Rendering handle 50703 and CPU schedule handle 79058 are terminal.
Once the clean checkpoint is saved, launch `.artifacts/approach-terminal-decay.py`
in the verified native training environment. Its final offline driver is
`.artifacts/approach-terminal-decay-offline.py <training-run>`; apply
`.artifacts/compare-terminal-decay-offline.py <offline-run>` afterward. Failed
gates prohibit physical execution; the old failed candidate remains unpromoted.

### Active model job

Terminal-decay ACT run **`20260911T035236-64462d013810`** is active under
handle **27780**, log `.artifacts/approach-terminal-decay.log`. It started from
clean `9ca38d1` after Qwen finished; 33 applied optimizer updates were observed.
Do not duplicate or run another GPU workload concurrently. Estimate about
62 minutes total from the preceding measured run; this is not a new benchmark.
Apply the frozen final-checkpoint offline gates after sealing. The implementation
and docs are pushed on `codex/preparation-foundation`; draft PR #1 is updated.
Current-checkpoint GitHub CI is pending; earlier `1e9e1cb` CI passed.

## Current follow-up — measured skill execution and HD planner path

The preceding goal turn made verified implementation progress; the full goal
remains active. Training handle 27780 was polled live again in this turn and
continues the same experiment, without restart or overlapping GPU work.

`DinnerSkillExecutor` now connects a preloaded ACT policy to confirmed physical
steps and a separate per-attempt outcome monitor. Ten actor/fixture tests pass,
including budgets, cancellation during inference, stale output, missing physics,
replacement tasks and failure to record termination. Policies receive only
cameras and joints. Physics truth goes explicitly to the monitor, not the model.
A passing physical outcome does not certify successor arm posture or full-task
success; those remain separate integration work. [Skill execution](SKILL_EXECUTION.md).

The optional live `overhead1920_wrist480_v1` profile is implemented with separate
ACT/planner artifacts and calibration. Thirty live-planning tests pass; actual
HD rendering and Qwen validation remain pending until the training GPU is free.
The original ACT input dimensions are unchanged. Base regression completed under terminal
handle 92019 (`.artifacts/checks-skill-execution-hd.log`): 734 passed, fourteen
optional skips and eight render deselections in 333.86 seconds.

Per-attempt monitor tests pass all 27 cases. Sealed audit
`20260911T040117-901674a49b49` verifies all seven nominal teacher-segment outcomes,
with phase labels ignored; the seal verifies. These are physical termination
checks on one existing authored trajectory, not learned-policy successes.
The bar outcome completes 409 controls before the training view ends, exposing
the need for a separate next-skill arm-posture check.

Next executable work after this checkpoint:

1. Keep watching training 27780; only run the declared offline evaluation after
   the final checkpoint seals. Do not select intermediate checkpoints.
2. Implement a separate arm-readiness condition before chaining learned skills.
   Physical completion can precede the recorded next-start posture substantially;
   per-skill success currently leaves `successor_start_ready` unknown.
3. After GPU training terminates, use the prepared
   `.artifacts/live-qwen-hd-check.py` in the native reasoning environment for an
   actual HD capture/model/revalidation diagnostic. It applies zero robot actions.
   No HD camera/model-quality result is claimed before that execution.

Successor analysis `20260911T040255-4778b5b83120` is sealed and verified. It
measures a 1.080203 rad bar/right-elbow gap and 0.551752 rad plate/left-wrist gap
between first physical success and next training entry. A proposed joint-only
readiness scan also finds insufficient settled bar-transition coverage. The
combined readiness gate and any new transition demonstrations remain next work;
no reference posture is supplied as an action target.

Final checkpoint checks pass: Ruff, formatting, 734 base tests, 354 documentation
links and README synchronization. No actual HD rendering was run during the
active MPS experiment. Training handle 27780 remains active; 4647 updates were
observed at this handoff. Its final checkpoint and frozen gates remain pending.

## Successor readiness implementation and transition probe

The preceding goal turn changed authoritative code/evidence and was progress.
`SuccessorReadinessMonitor` now binds measured training-entry posture and checks
all physics samples plus ten new fresh observations. Nonfinal chained execution
requires a matching reference; physical success remains a separate milestone
while the same learned attempt retreats. Optional final parking cannot invent a
successor. Source/reference verification occurs before live capture.

Twenty-eight focused readiness tests pass. Sealed combined teacher audit
`20260911T041524-a18f4e1922da` verifies six ready transitions and retains the
original bar failure. Reference matching does not prove model generalization.

The ten-control bar settling probe `20260911T041046-acd11fe83176` fails the full
workflow on a later plate/cabinet collision. Its hold alone passes numerical
joint/contact predicates. No cameras were captured and no existing data was
overwritten. Diagnosis `20260911T041433-5d21278da297` shows tiny initial
differences amplifying during release/withdrawal. Both seals verify; do not
relabel the failed probe as validated training data. See
[successor readiness](SUCCESSOR_READINESS.md).

Base checks completed under terminal handle 81586, log
`.artifacts/checks-successor-readiness.log`. Training 27780 remains the only GPU
job; no new rendering or model runs were started. Next teacher work is a bounded
release-clearance repair experiment, followed by full physical revalidation.

Read-only clearance proposal `20260911T041924-2c2111b5399c` is sealed and verified.
A candidate plate destination shift of +20 mm Y gives at least 15.688 mm static
clearance across 16 restored poses, with reachable sampled endpoint IK. No new
physics was run and this does not prove dynamic success. Next teacher trial:
preregister a separate scene/target revision, regenerate corresponding tool goals,
retain ten bar holds, and run the unchanged full physical gates. Preserve the
original scene/data and all failures; adopt no new dataset before full validation.

Final verification for this checkpoint: **767 tests passed**, fourteen optional
skips and eight render deselections, 344.19 seconds; Ruff, formatting, 359 documentation links
and README synchronization passed. Training 27780 is still active with 9507 updates
observed; the final checkpoint and frozen offline gates remain pending. No
additional GPU work started. Actual HD camera/Qwen validation remains pending.

## Supported evidence evaluation and plate repair preflight

`bimanual dinner-evaluate` now re-scores sealed runs and preserves source outcome,
instrumentation provenance and full-trace diagnostics. Ten focused boundary tests
pass. Actual CLI evaluation `20260911T043031-3fe61f7bd44b` passes the original
teacher's 4,819 actions / 240,950 samples using its explicitly linked declaration
audit. The failed hold probe stays failed in evaluation
`20260911T043017-446d1af42961`: 2,732 confirmed actions, one partial action and one
forbidden-contact sample among all 136,644 retained samples. No new manipulation
or learned success is claimed. [Command and semantics](DINNER_OUTCOMES.md).

The +20 mm Y plate candidate was preregistered in
`20260911T042704-a6719c36b78d`. Candidate `20260911T042731-bfb18f06e6f0` fails
preflight at original control 2622, plate/lower: left wrist camera versus placed
cup. Zero physics actions ran. The candidate preserves pinch-axis orientation,
not a full six-dimensional pose; the original scene/data remain unchanged.
Diagnosis `20260911T043223-6583271ffaf0` identifies 0.05183 rad tool rotation
change and 0.212 mm camera/cup overlap. East20 alternative preflight
`20260911T043309-29dffffbd62f` also fails: control 2590, plate versus parked right
arm. Neither executes physics. Next candidate needs coordinated right-arm parking
and a separately recorded protocol; see [repair evidence](SUCCESSOR_READINESS.md).

Training 27780 remains active, with 14,612 updates observed. Continue the same
20,000-update protocol and evaluate only its final checkpoint. No GPU/rendering
work overlaps it. Full checks pass: **777 tests**, fourteen optional skips, eight
render deselections, 357.78 seconds; Ruff, formatting, 362 documentation links
and README synchronization pass. Log: `.artifacts/checks-dinner-evaluation.log`.
Next: preregister a coordinated arm/plate candidate after scratch path checks;
run final ACT gates once training seals. Actual HD rendering remains pending.

A diagnostic import added an unsealed Python cache to the failed north20 run.
The integrity check rejected it. The exact cache was preserved outside the run,
all original bytes and the manifest were left unchanged, and the original seal
verifies again. Retained-source diagnostics now disable bytecode writes. Both
failed preflights and the diagnosis were independently reverified afterward.

Repair-design note `20260911T043714-e0cc9763cf19` records exact right-arm
commanded/measured posture and required whole-route checks. Constant home also
fails scratch preflight `20260911T043522-96f2ddd534c7`. No new valid endpoint or
repaired trajectory has been established. Both additional seals verify.

## Complete-workflow orchestration checkpoint in progress

The previous goal turn delivered committed evaluator code and verified evidence;
it was progress. Training handle 27780 was confirmed live again this turn and is
unchanged. The fixed final-checkpoint protocol remains mandatory.

A pinned development cohort now binds all seven selected skill training runs,
checkpoint hashes, one dataset and measured successor references. New CLI commands
`workflow-create` and `workflow-check` create/version and verify this record without
model inference. Preloading finishes before live capture; one mutable policy set
belongs to one worker. No physically validated seven-model cohort exists yet.
See [cohort contract](WORKFLOW_MANIFEST.md).

The serialized [workflow runner](WORKFLOW_RUNNER.md) connects visual planning to
prepared executors and subsequent successful boundaries without resetting the
scene. It persists intents/outcomes and stops on authority or persistence failures.
An integration bug comparing export file hashes to canonical body seals is fixed;
a sealed synthetic-source regression covers the distinction. Thirty focused
runner/executor tests pass. Full learned dinner execution remains unvalidated.

Failed-step recovery is an explicit remaining gap: the current worker stops after
failure and only supports stationary recapture at successful boundaries. The runner
reports `recovery_required`; it never advances unowned physics or silently resets
the retry budget. An owned failed-boundary recovery API is still required.

Bounded static repairs all remain failed: twelve constant right-arm poses
`20260911T044110-b2ccb7287b2f`, three cup shifts
`20260911T044402-fc46384331dc`, and eight timed parked-to-home transitions
`20260911T044606-5359e25ac580`. No new physics trial ran and no production asset,
scorer target or dataset was replaced. The next read-only investigation asks
whether the original cup segment already includes sufficient unchanged settling
controls to support a separately versioned skill boundary.

Full checks are running in `.artifacts/checks-workflow-cohort.log`, handle 65292.
The last observed ACT update was 18,192 of 20,000. No model/render job overlaps it.


## September 11: v2 recording and profile development handoff

# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Use `git rev-parse HEAD` for the exact checkpoint; previous pushed checkpoint is
`6719928`. Current work packages and records the repaired v2 teacher recipe.
[Roadmap](ROADMAP.md), [original plan](PLAN.md), [history](STATUS_HISTORY.md).

## Readiness

| Milestone | Evidence and remaining gate |
|---|---|
| M0 complete | Native tooling, evidence portal, seven lessons, learning site, README/CI synchronization |
| M1 locally complete | One authored continuous teacher dinner scene passes contact, placement, drawer and hand-off checks |
| M2 in progress | Learned training, visual planner, skill monitors, pinned cohorts, runner and bounded recovery exist. No learned grasp or full learned dinner success |
| M3 incomplete | No frozen release suite, Intel/OpenVINO execution or final submission package |
| M4 pending | Production reliability, held-out perturbations, interruption/rollback and operational gates incomplete |

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Spend remains zero. Prior-code eligibility remains unconfirmed. Physical robot
deployment is outside this release. Runtime, fixture and integrity checks do not
establish model quality or Intel compliance.

## Latest ACT training and quality gate

Training **61437 is terminal**. Run `20260911T053104-2b24b508ff79` completed
20,000 native MPS updates in 3,667.71s, fallback disabled, from clean `1f7c0a0`.
Protocol `20260911T052340-2416748543bb` changes temporal L1 weighting only: first
action 50%, remaining nine share 50%, valid-target normalization. Dataset,
initialization, sampler, terminal learning-rate schedule and all six gates stayed fixed.

Offline run `20260911T110831-7101df3ccdb6` and comparison
`20260911T110901-a43fc6ef185a` pass **five of six** gates. Launch mean tool-target
error is 0.344 mm and settled error 0.033 mm, but the first pan command remains
-0.001956 rad versus teacher +0.000564 rad. No physical rollout or promotion.
Previous terminal-decay run `20260911T035236-64462d013810` also passed five of six.
The next ACT step is to diagnose the persistent signed launch error before declaring
another controlled training experiment. [Training](TRAINING.md), [policy evidence](POLICY_ROLLOUT.md).

Qwen **50272 is terminal**. No GPU model job remains active from this session.
Full teacher trial **76771 is terminal and passed**. The corrected v2 recording
18623 is active; preserve all source runs and the original dataset.

## Workflow execution and recovery

- [Pinned cohorts](WORKFLOW_MANIFEST.md) bind all seven selected policies to their
  dataset, view and successor references. No validated seven-model cohort exists.
- [Workflow runner](WORKFLOW_RUNNER.md) chains authorized steps in one simulation.
  Eligible incomplete action-budget attempts may request fresh visual assessment
  and retry at most twice. Collision, partial-action and stopped-worker failures
  remain ineligible. No reset, teacher fallback or artificial grasp is inserted.
- [Local execution command](WORKFLOW_EXECUTION.md) is implemented. It verifies
  sources and loads ACT/Qwen before creating the worker, records final supervisor
  history and preserves failed outcomes. The CLI now defaults to a spawned process
  with cooperative cancellation, bounded terminate/kill escalation and reaping.
  `--in-process` retains cooperative debugging. Parent-crash recovery, unmanaged
  subprocess trees and the live operator UI remain incomplete.
- Saved workflow traces now retain their verified scene layout for independent
  scoring. The scorer requires exact sealed paths and scene/layout digest binding;
  missing intervention evidence remains a failed condition. No object locations
  enter planner or policy inputs. The original portal remains read-only.
  Executor completion is separate from independent dinner-task success.

A new locked `.artifacts/workflow-venv` contains both training and reasoning extras.
Run `20260911T053930-398fa0529139` verifies native ARM64, all 372 compiled libraries
and ACT/Qwen class imports. No weights or inference were run in that environment.
The active `.artifacts/training-venv` was not modified.

## Visual reasoning

Actual HD Qwen run `20260911T045505-ef9d1f373348` reports the visible cyan bar
missing and requests clarification; zero actions follow. Recognition is unresolved.
Two preregistered paired replay attempts, `20260911T110859-4158aa25c243` and
`20260911T111049-12b26169fffe`, stopped before inference because historical RGB
was not bit-identical. The overhead differs in 88 channels by one intensity level;
both wrist images match. Both failed attempts remain preserved.

New protocol `20260911T111218-c75b807e19fb` freezes the last captured positive and
negative pair. Four cases use identical saved pixels per scene and unchanged
visual-decision gates; no historical exact replay is claimed. Evaluation
`20260911T111242-65da2d81e562` completes all four cases: both present cases fail,
both absent cases pass. The appearance description is not promoted.
[Planner evidence](PLANNER_LIVE_INTEGRATION.md).

## Physical foundation and plate repair

Teacher `20260911T013229-b7184e9ba66a` completes 4,819 controls and 240,950 samples
at 1kHz, with zero forbidden contacts and final placement hold. Recording
`20260911T022644-a24a56ff004c` exports to `.artifacts/datasets/dinner-nominal-v1`;
views are `.artifacts/dinner-skill-views-v1.json`. Preserve both unchanged.
[Scene](DINNER_SCENE.md), [datasets](DATASETS.md).

The original bar boundary has six stationary observations; ten are required.
Adding holds perturbs the subsequent plate release. Destination/parking searches
and boundary repartitioning have not produced a validated replacement.

Measured prefix diagnostics retain original destinations and all live guards:

- North5 mm: `20260911T053109-6c16dbcb8104`, 2,761 controls/138,050 samples,
  zero forbidden contacts. Fixed jaw supports the tilted plate throughout all
  3,000 endpoint-hold samples; release fails.
- +5-degree tilt: `20260911T053710-429c53f79518`, same complete coverage and no
  forbidden contacts. Final jaw load 0.365 N, tilt 17.3 degrees, height +19.2 mm;
  sustained release fails. Analysis `20260911T053909-574e0b62c3ed` preserves details.

The earlier static-heuristic failure `20260911T052918-cdeba1a0c381` remains retained.
No failed diagnostic is relabeled as a repaired workflow. Read-only design
`20260911T054402-12a65c47f446` rejects plate-before-cup ordering: the cup source
blocks the path earlier. Design `20260911T054615-6660a468f379` proposes outward
and downward withdrawal after measuring load transfer between two fixed-jaw
patches. Coupled west10/down3 mm diagnostic `20260911T055847-e6acdec0f110`
then completes 2,781 controls/139,050 samples without forbidden contacts, but again
fails release: 0.369 N final jaw load, 15.0-degree tilt, height +16.7 mm and no
jaw-free hold samples. Analysis `20260911T060027-65687a2def5a` is retained.
An earlier static filter wrongly included a visual-only mesh; corrected preflight
and the original rejection are both retained. No ordering, dataset or gate changed.
The larger west30/south5/down10 mm trial `20260911T060903-2e2b0e5fc492` also
completes 2,781 controls/139,050 samples collision-free but fails release. Final
jaw load is 0.389 N, tilt 10.45 degrees and height +11.74 mm; no hold sample is
jaw-free. Analysis `20260911T061047-d494cfcfd579` preserves the support migration.
The next measured down2 mm / northwest24 mm sequence **passes release** in
`20260911T111745-e717fe08f3a5`: 2,901 controls/145,050 samples, zero forbidden
contacts. Analysis `20260911T112034-4540db745aa4` confirms all final 2,000 rows pass;
plate target error is 2.270 mm, with zero jaw forces and essentially flat placement.
A 120-control return route passes static checks in `20260911T112143-e4f5f6790080`.
Full continuous teacher run `20260911T112302-2cba6a2aa0ac` passes all 5,049
controls/252,450 samples, with zero forbidden contacts. Independent rescore
`20260911T112722-fd2f1119487f` confirms completion, zero partial actions and no trace
errors; learned execution remains false. The recipe is packaged; the corrected recording and
verified skill boundaries remain necessary before adopting a replacement dataset.
[All transition evidence](SUCCESSOR_READINESS.md).

## Verification

- Clean recovery regression: **822 passed**, fourteen optional skips, nine render
  deselections, 446.40s; `.artifacts/checks-recovery-clean.log` (68236 terminal).
- Clean final ACT-loss regression: **837 passed**, eighteen optional skips, nine
  render deselections, 473.74s; `.artifacts/checks-first-action-loss-final.log`
  (1206 terminal). This precedes the new workflow entrypoint.
- Actual weighted-loss CPU suite: sixteen pass, one MPS skip, including a real
  update and checkpoint/processor/sampler/loss reload. Separate native Metal test
  passes in 11.51s with fallback disabled. Runtime evidence is not quality evidence.
- Recovery CI 34565689004 failed because its lifecycle fixture used real time and
  slow work exceeded the unchanged two-second freshness guard. The fixture now
  uses controlled time, with a separate deliberately stale-frame rejection test:
  **19 pass**, `.artifacts/workflow-logical-clock-check.log`. Workflow checkpoint
  `4434407` CI 34567398213 now passes, including rendering. Scoring checkpoint
  `852b7fa` CI 34568561533 and 34568558635 both pass.
- Workflow entrypoint plus CLI: **38 pass** in the combined native environment,
  including immutable-source output confinement, real-worker lifecycle fixtures,
  late-model-output rejection and preserved final supervisor history. Log:
  `.artifacts/workflow-execution-combined-check.log`. No learned cohort was executed.
- Workflow entrypoint aggregate **8916 completed**: 876 passed, eighteen optional
  skips, nine render deselections, 476.53s;
  `.artifacts/checks-workflow-execution-final.log`.
- New scene-layout retention tests: 22 pass. Independent evaluator tests: 21 pass.
  Historical teacher rescore `20260911T055358-51d16be3e162` passes all 240,950
  samples/4,819 actions; this reuses old physics and does not certify learned control.
- Scoring aggregate **62130 completed**: 890 passed, eighteen optional skips,
  nine render deselections, 480.11s; `.artifacts/checks-workflow-scoring-final.log`.
  Ruff, formatting, 389 documentation links and README synchronization pass.
- Process isolation: nineteen real spawned CPU tests pass, including ignored
  termination, kill/reap, parent interruption, corrupt child evidence and a child
  sealed as completed while a background thread hangs. Four CLI wiring tests pass.
- Actual default CLI missing-cohort run `20260911T061251-260718b9a590` returns
  failed in 0.389s, verifies its failed child and reaps it. No model is loaded.
- Process aggregate **75625 completed**: 911 passed, eighteen optional skips,
  nine render deselections, 481.95s; `.artifacts/checks-workflow-process-final.log`.
  Ruff, formatting, documentation links and README synchronization pass.
- Native camera recovery test previously passes (3.61s); no new render job runs
  alongside training. Documentation/README checks pass.

## Next executable steps

1. V2 recipe and CLI selection are implemented; 24 focused teacher tests pass.
   Baseline regression **1316 passed: 919 tests**, `.artifacts/checks-dinner-v2-final.log`.
   Corrected recording **18623** is active from clean `106f5ed`.
   Verify its seal, export separately, and audit all seven boundaries. Preserve v1.
2. ACT input diagnosis `20260911T111920-7fd911a11b83` finds weak joint-state
   sensitivity: +/-0.08 rad state changes shift nominal-image first pan by only
   0.000389 rad. Diagnose/train a declared representation change; no failed rollout.
3. Improve visual recognition under a new matched protocol; the appearance pair failed.
4. Verify CI after the checkpoint push. Keep draft PR #1 unmerged.
5. Validate the full learned cohort, live operator UI and remaining release gates.

## External dependencies

Intel BM-PTL Series3 request `bimanual-sim-intel` was last Pending Review. No actual
Intel/OpenVINO validation exists. Access was requested for September10–17, with
Ubuntu requested; verify hardware identity, expiry and rendering when granted.
Organizer clarifications on assets/seeds, pouring, prior-code eligibility and
hosting remain provisional. Deadline last verified: September16, 2:30PM EDT.
No organizer message or hackathon submission has been sent.
[Intel access](INTEL_ACCESS.md), [questions](ORGANIZER_QUESTIONS.md).


## Current continuation: v2 recording correction

Recording `20260911T113458-5a8697f744a0` finished **failed**, preserved unchanged.
All 5,049 controls and 15,150 images were captured; independent physical scoring
passes with zero forbidden contacts. The stage audit requires exactly 2,000
plate-settled samples, while the packaged labels supplied 3,000. Only the first
20 labels of that 60-control hold are corrected to `plate/retreat`; all targets,
guards and acceptance thresholds remain unchanged. Re-record before export.

The explicit v2 skill-view profile is implemented with pinned plan identity,
profile/count/interval consistency and mandatory independent score. Original v1
manifests remain compatible. View tests: 29 pass. Successor/training adapters:
30 pass, one optional skip. Aggregate 70584 predates the phase correction and
cannot establish the final corrected asset check. Next: finish focused correction
checks, record the corrected recipe, then export and audit all seven boundaries.


Active corrected recording: session **18623**, run
`20260911T114540-8b3b1ff0238d`, started from clean `106f5ed`.
Log `.artifacts/dinner-v2-corrected-recording.json`; stderr has a matching basename.
Poll this process instead of restarting it. The first recording session46979 is
terminal failed. Combined corrected teacher/view tests: **53 pass** in 13.63s,
`.artifacts/v2-phase-correction-tests.log`. Actual original v1 manifest reload also
passes and retains hash `45bf9464a68a93f04ccc23fdd7ebbe473040af40e6b6f1e6414e9e5b521487f2`.
Aggregate **70584 remains active**; its assets were corrected during execution,
so rerun the final aggregate after completion before claiming a clean final check.
Only one rendering job is active. No ACT/Qwen inference runs concurrently.

After the corrected source seals successfully, export to the new
`.artifacts/datasets/dinner-nominal-v2`, create
`.artifacts/dinner-skill-views-v2.json`, then execute the prepared retained-data
audit `.artifacts/audit-dinner-v2-boundaries.py`. The audit is not yet executed.
No v2 dataset or validated successor boundaries exist yet. Local commits `dbf0217`
and `106f5ed` are not pushed; keep draft PR #1 unmerged.


Neutral Qwen description protocol `20260911T114805-29483c134fad` is sealed before
inference, using the exact saved positive/negative camera images and pinned model.
Driver `.artifacts/qwen-description-diagnosis.py` asks for visible objects/colors
without the structured skill-selection prompt. This is qualitative diagnosis,
not a replacement planner or promotion gate. No inference has run yet; wait for
recording18623 to finish before using MPS. Native preparation31233 is terminal.

Corrected wheel build passes offline with native uv. The archive's asset digests,
5,049-action count and exactly 40 plate-settled controls verify; its loader also
runs from outside the repository. Artifact:
`.artifacts/wheels-dinner-v2-corrected/bimanual_sim-0.1.0-py3-none-any.whl`.
This is packaging validation, not a new clean-install physics run. README generated
sections remain synchronized with `docs/project.json`.

Aggregate70584 is terminal: 922 pass, one failure, eighteen optional skips and
nine rendering deselections. Its sole failure is the expected old imported plan
hash versus the asset corrected during that run. Focused corrected tests pass;
a fresh fixed-snapshot aggregate is required. Exact comparison
`20260911T115118-910bbec745e4` verifies all 5,049 targets equal the successful
physical source and only indices3021–3040 change phase labels; guards are identical.


## Archived handoff before live camera checkpoint, September 11

All process handles and next actions in this archived section are historical.

# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Current committed checkpoint: `c429601`; previous pushed checkpoint: `6719928`.
[Roadmap](ROADMAP.md), [original plan](PLAN.md), [detailed history](STATUS_HISTORY.md).

## Readiness

| Milestone | Evidence and remaining gate |
|---|---|
| M0 complete | Native tooling, evidence portal, seven lessons, learning site, README/CI synchronization |
| M1 locally complete | Continuous contact-based teacher dinner workflow passes in one authored scene |
| M2 in progress | Training, visual planner, outcome/readiness monitors and isolated workflow runner exist; no learned grasp or full learned dinner success |
| M3 incomplete | No frozen release suite, Intel/OpenVINO execution or submission package |
| M4 pending | Held-out reliability, operational recovery, rollback and support gates incomplete |

Implementation is authorized by [decision0003](decisions/0003-event-window-implementation.md).
Spend remains zero. Prior-code eligibility remains unconfirmed. Physical hardware
deployment is outside scope. Runtime checks never establish model quality or Intel compliance.

## Corrected dinner recording: passed

Clean `106f5ed` recording **`20260911T114540-8b3b1ff0238d`** completed:
5,049 actions, 5,050 observations, 15,150 RGB images and 252,450 physical samples.
Both the fixed stage audit and independent task score pass, with zero forbidden
contacts. Source seal:
`37ec8a70353517d668f4bc18cf8252c2067e2fe4db6b7d1060e1c43d782808ff`.
Session18623 is terminal. This remains an authored teacher demonstration, not learned success.
[Scene](DINNER_SCENE.md), [datasets](DATASETS.md), [skill training](SKILL_TRAINING.md).

The first v2 recording `20260911T113458-5a8697f744a0` is retained failed: physical
outcomes passed, but the plate-settled stage had 3,000 samples instead of exactly
2,000. The correction changes 20 phase labels only; targets, guards and thresholds
are unchanged. Exact comparison `20260911T115118-910bbec745e4` verifies all 5,049
targets against the successful physical source `20260911T112302-2cba6a2aa0ac`.
Original v1 recording/dataset/views remain immutable and still load successfully.

V2 views have an explicit pinned plan/profile, exact partition and mandatory
independent score. Corrected plan hash:
`0c93816e3791ac577cc3284fc8b9932ee0e34a2f067eca805ad12f72117b9231`.
Physical readiness at all seven boundaries is not yet verified.

## Active processes and next executable actions

- **6150: native LeRobot export**, `.artifacts/dinner-v2-export.log`.
  Driver `.artifacts/export-dinner-v2.py` checks the successful source, exports to
  `.artifacts/datasets/dinner-nominal-v2`, performs full image/state/action readback,
  then creates and reloads `.artifacts/dinner-skill-views-v2.json`.
  Poll this handle; do not restart or overwrite partial output.
- **60454: native MPS Qwen description diagnostic**, fallback disabled.
  Protocol `20260911T114805-29483c134fad`; exact frozen positive/negative images,
  pinned weights, neutral descriptions instead of structured skill proposals.
  Log `.artifacts/qwen-description-diagnosis.log`. No action authority or promotion.
- **22860: fixed-snapshot full checks** from `c429601`,
  `.artifacts/checks-v2-corrected-snapshot.log`. No code/assets changed since launch.

After export succeeds, run `.artifacts/audit-dinner-v2-boundaries.py`. It verifies
new v2 references and replays recorded physical/observation evidence through the
unchanged outcome/readiness monitors. Require ten consecutive qualifying
observations at each actual terminal boundary, including final parking. Clock is
replayed from capture timestamps; no live freshness or learned reliability claim.

Then finish verification, update evidence/README, push the checkpoint, and update
draft PR#1 without merging. Continue ACT and Qwen quality work, learned cohort,
live operator controls and release gates. No seven-policy cohort is validated.

## Learned-model quality

ACT first-action-weighted run `20260911T053104-2b24b508ff79` completed 20,000 MPS
updates. Offline comparison `20260911T110901-a43fc6ef185a` passes **five of six**
gates; first pan remains -0.001956 rad versus teacher +0.000564 rad. No physical
rollout or promotion. Input diagnosis `20260911T111920-7fd911a11b83` shows weak
joint-state sensitivity under crossed inputs; it is not a causal/physical result.
Next: declare and evaluate a representation change against unchanged quality gates.
[Training](TRAINING.md), [policy evidence](POLICY_ROLLOUT.md).

Qwen frozen paired evaluation `20260911T111242-65da2d81e562`: both present-object
cases fail and both absent-object cases pass. Adding the cyan-bar appearance
phrase did not repair recognition. Earlier exact historical pixel replay attempts
failed before inference and remain preserved. Current description diagnostic
separates image recognition from skill-prompt demands.
[Planner evidence](PLANNER_LIVE_INTEGRATION.md).

## Application and verification

[Workflow execution](WORKFLOW_EXECUTION.md) verifies all seven models and Qwen
before starting one simulation worker. It retains action/observation evidence,
bounded recovery and independent evaluation. The default spawned process supports
cooperative cancellation then terminate/kill/reap. Parent-crash recovery and the
live operator UI remain incomplete; the current portal is read-only.

- Recipe baseline: 919 pass, eighteen optional skips, nine render deselections;
  `.artifacts/checks-dinner-v2-final.log`.
- Corrected teacher/view tests: 53 pass in13.63s;
  `.artifacts/v2-phase-correction-tests.log`.
- Successor/training adapter checks: 30 pass, one optional real-training skip.
- Aggregate70584 ended with922 pass/one failure because assets changed after its
  old hash was imported. It is superseded by active fixed-snapshot22860.
- Corrected wheel builds offline; packaged digests/counts and external-directory
  loading pass. No new clean-install physics claim.
- Earlier process-isolation regression:911 pass; actual real-child cancellation,
  escalation and reap tests are recorded in the history. No hung GPU claim.

## External dependencies

Intel BM-PTL Series3 request `bimanual-sim-intel` is Rejected on the September11 signed-in check. No actual
Intel/OpenVINO validation exists. The rejection has no explanation. Defer access
work and Intel setup until local training is complete, then verify hardware
identity and rendering on the eventual target.
Organizer details on assets/seeds, pouring, prior-code eligibility and hosting
remain provisional. Deadline last verified: September16, 2:30PM EDT.
No organizer message or hackathon submission has been sent.
[Intel access](INTEL_ACCESS.md), [questions](ORGANIZER_QUESTIONS.md).

## Latest continuation

Export6150 is terminal failed: LeRobot's readback requested a restricted default
Hugging Face dataset cache. Failed output is preserved at
`.artifacts/datasets/dinner-nominal-v2-export-failed-cache`. Retry **82810** uses
explicit project-local `HF_HOME`/`HF_DATASETS_CACHE`, offline flags and a fresh v2
destination; log `.artifacts/dinner-v2-export-retry.log`. Do not overwrite it.

Qwen60454 is terminal completed, run `20260911T115608-34d5fb7f9763`: positive
image describes a cyan beam but rejects the word bar; negative describes only the
small cyan drawer part. Neither output is truncated. Alias protocol
`20260911T115919-698f78cadeac` tests bar/beam/strip terminology with unchanged
presence/absence decision gates. No deployment promotion or actions.

Fixed-snapshot22860 is terminal:922 pass/one failure. Cooperative cancellation
used a test-only150ms grace, shorter than production2s; the child sealed but was
forced during shutdown under concurrent load. Only that test now uses the
production default. Forced-stop test deadlines and runtime code remain unchanged.
All19 process tests pass in14.84s; `.artifacts/process-production-grace-tests.log`.
A final aggregate is still required after the test adjustment.
Alias inference **38174** is active; log `.artifacts/qwen-alias-pair.log`.
Only this job uses MPS. Export82810 uses CPU. Timings are not isolated benchmarks.
Final aggregate **58592** is active from clean `56437fa`;
`.artifacts/checks-v2-production-grace-final.log`. No code/assets changed since launch.

Intel request was rechecked in the signed-in Instances page on September11:
`bimanual-sim-intel` is **Rejected**, not Pending Review. No reason is shown in the
list, and no replacement request or support message was sent. The user has been
asked for any non-sensitive rejection-email explanation. Local work continues.

Alias inference38174 remains active, run `20260911T120355-678cc31f134e`. Its first
case recognizes the cyan target but requests `left_gripper` instead of the
instructed `right_gripper`, so that case fails. New frozen protocol
`20260911T120740-a2070b401571` tests receiver-first wording in both directions and
both present/absent scenes. Driver `.artifacts/qwen-direction-pair.py`; no inference
has run yet. It supersedes an unused draft protocol whose inherited positive-gate
text named only right; the final protocol explicitly requires the requested direction.
Wait for38174 to terminate before another MPS job. Export82810 and aggregate58592
remain active at this checkpoint; no completion is assumed from output files alone.

User steering September11: Intel rejection has no explanation. Defer Intel setup
until local training is complete, then handle it as a separate step. No further
access investigation or support request now. Zero spend and actual Intel execution
requirements remain unchanged. Continue the local dataset, policy training and
visual-planning work; the Intel rejection does not block those tasks.

Export82810 is terminal successful. Dataset v2 has full native LeRobot
image/state/action readback parity; export hash
`38a7939bca2c0465858492a24c9217673a8fe8c57fb0789ca78916062aafeab2`.
View hash `004d0bf3efa4998f1debd0e86a989fdab6ae7370e919c5c710548fdb45a449d3`.
Boundary audit **11316** is active, `.artifacts/dinner-v2-boundary-audit.log`.
Alias38174 is terminal completed: positive fails recipient, negative passes.
Direction protocol `20260911T120740-a2070b401571` is now launched; log
`.artifacts/qwen-direction-pair.log`. No production prompt change is adopted.

Boundary audit11316 is terminal **passed**, run
`20260911T121108-abc948e25b7d`, seal
`b14dfe17570b2c13528cbbaf524e309e5ce13c7f37e9bc1d5154736424f8a0e7`.
All seven physical outcomes and boundary readiness checks pass. Terminal stable
observation counts:43,16,20,64,43,43,43. No gates changed and no learned success
claimed. See SUCCESSOR_READINESS.md for exact interpretation.

Direction test **69764** remains the sole active MPS job.
First full hand-off ACT training driver `.artifacts/train-dinner-handoff-v2.py`
is prepared:20,000 updates, small ACT, chunk10/batch1, uniform skill sampling,
first-action-weighted loss, terminal learning-rate schedule, final checkpoint only.
Protocol preparation55788 verifies the completed dataset and boundary audit before
sealing; log `.artifacts/dinner-handoff-v2-training-protocol.log`. Do not start
training until69764 is terminal. This separate full-skill experiment does not
relabel failed approach-checkpoint gates. No training has started yet.
Training protocol preparation55788 completed:
`20260911T121325-10260896f896`. Launch the frozen driver with this protocol only
after direction69764 finishes, using native training-venv, fallback disabled and
explicit project-local Hugging Face caches/offline settings.

Aggregate58592 completed: **923 passed**, eighteen optional skips, nine render
deselections,661.80s. Documentation links402 and README synchronization pass.
Log `.artifacts/checks-v2-production-grace-final.log`. No remaining code test failure.
The prepared exhaustive hand-off evaluator is
`.artifacts/evaluate-dinner-handoff-v2.py`; it must run on the completed trained
checkpoint, cover all630 source observations, retain every forecast/error, and
report bounds and joint-target errors without claiming physical success.

Qwen direction69764 is terminal completed, run `20260911T121102-7f242fa1b264`:
all four frozen presence/absence and right/left recipient cases pass. This validates
only the preregistered wording on the fixed images; no general planner promotion.
Next GPU job is the prepared ACT hand-off training protocol
`20260911T121325-10260896f896`.

New `operator_jobs.py` implements one active background workflow, job-specific
stop requests, verified final evidence and explicit shutdown-timeout reporting.
Eleven CPU tests pass, including simultaneous starts, stale stop IDs, corrupted
results and failed thread startup. It is not yet wired into the API or UI; the
portal remains read-only. Job completion never claims independent task success.

ACT hand-off training **95347 is active**, run
`20260911T122319-b2ee550f005b`, started from clean `284e86f` with protocol
`20260911T121325-10260896f896`. Native MPS, fallback disabled, explicit local
Hugging Face caches,20,000 planned updates. Actual step175 is recorded; no result
or checkpoint quality is claimed. Log `.artifacts/dinner-handoff-v2-training.log`;
progress is the run's `steps.jsonl`. Do not run another GPU/model/render job alongside it.

Next independent implementation: wire the tested OperatorJobs controller into an
opt-in local API and UI, preserving read-only default, one active simulation,
job-specific cancellation, request-origin protection and no task-success claim
from process completion. No validated seven-model cohort exists yet. Run the full
regression after API/UI integration; the new controller currently has11 focused
passing tests. Latest pushed checkpoint is `c3479a3`; operator component `284e86f`
is local. Draft PR#1 remains open/unmerged; CI34598151792 was last in progress.

Operator integration checkpoint: optional `serve --operator-config` now wires
OperatorJobs into the API and a React instruction/start/stop panel. Default is
read-only. Sixteen focused API/controller tests pass; native ARM frontend build
passes. The panel polls process status and preserves job-specific stop identity;
process completion never claims table success. Live cameras/per-step UI and
browser interaction validation remain outstanding. Full regression is running
in session33890, log `.artifacts/checks-operator-integration.log`; do not claim its
result until terminal. Training95347 was re-polled live at this checkpoint, with
step2615 recorded toward20000. No second GPU job was started.

Operator setup verification: five CLI tests pass (valid opt-in/default read-only,
relative configuration path, malformed/incomplete configuration rejected before
server start, loopback bind). Temporary portal54779 on8769 displayed the unconfigured
operator message in the real browser; no start control exposed. This is only
read-only browser verification; configured interactions remain to check. Original
portal8768 was left untouched. Full regression33890 and training95347 both
confirmed live again; latest observed training step3440. No learned-quality claim.

Configured browser fixture verification (no models/physics): native Node24 with
installed Chrome, isolated evidence root `.artifacts/operator-browser-fixture/evidence`.
Start initially disabled, instruction enabled Start, active job disabled duplicate
start/edit, Stop showed `stopping`, polling reached `cancelled`. Fixture run
`20260911T123653-f9bcf0d10a98`, seal
`85f5211c6b2b409bf7ef75bd71c68bdd04d79b73fddf81bf26c7a8fc31ee5500`.
Snapshots retained in `output/playwright/operator/`. Only console error was a
missing favicon404. This does not verify learned execution or physical stopping.
Large existing run archives still delay `/api/runs` because every artifact is
hashed; operator polling is independent, but archive pagination remains next work.

Operator integration full regression33890 completed: **936 passed,18 skipped,
9 render deselected**,501.83s;403 documentation links pass and generated README
is synchronized. This full run predates the subsequent pagination changes and
five separately verified CLI tests. It is not a rendering or model-quality test.

Run-history follow-up: optional `limit`/`before` cursor pagination verifies only
selected records and preserves corrupt/failed entries. CLI/default unpaged API
behavior remains available; portal requests20 records with Older/Newest controls.
Project data now renders without waiting for run verification. No integrity cache
or unverified-success shortcut was introduced. One very large run may still be
slow; no latency target is claimed. Targeted evidence/API/controller/CLI checks
cover this delta; live browser pagination remains to verify. Training95347 remains
active; do not launch GPU evaluation until it is terminal and sealed.

Live progress implementation: workflow snapshots now replace atomically; parent
process reads bounded display-only snapshots at most4Hz and relays them to the
operator job. UI shows last reported state/reason, completed steps and attempt
count, explicitly unverified. No camera stream or task certification is implied.
Malformed, oversized, escaped or ambiguous snapshots are ignored; task-success
claims in snapshots are rejected.78 targeted API/operator/execution/process/
progress tests pass, plus two added spawned-delivery and terminal-state tests.
Native frontend build passes. Full subsequent regression is the next check.
Checkpoint5430df7 was pushed to the existing draft branch, no merge. The progress
changes described here are newer and not yet committed.

Progress-reader follow-up: nonblocking regular-file reads now reject FIFOs and
symlinks so malformed display artifacts cannot stall the parent's cancellation
loop. Glob/resolve failures also return unavailable progress. Eight reader tests
pass. Full regression19814 is still running (`.artifacts/checks-live-progress.log`);
this reader delta was made after its collection and has separate focused coverage.
Training95347 confirmed live, step9147 recorded toward20000. Next camera work can
reuse worker-owned PNG captures without another renderer: `DinnerControlWorker.capture`
already writes the synchronized three-camera observation and artifact digests.
Expose a separate display-only snapshot, preserve capture identity/timestamps,
and verify bounded image bytes before serving them; never generate extra captures
from an API request or use previews as action authority. Camera display not yet built.

Camera preview implementation now reuses the worker's existing three PNG captures.
An atomically replaced metadata record carries the exact Observation and source
(`live_mujoco` versus `injected_unverified`). The parent accepts only bounded,
regular, confined files whose bytes match the recorded hashes, with RGB PNG
480x270 dimensions; one invalid frame drops the whole preview. API output contains
only named images and capture identity/time, never joint or scoring truth. UI
labels the last capture and warns it can remain unchanged during planning/after
stop. No additional rendering or observation capture occurs on browser requests.
72 control/progress/execution tests pass (including synthetic camera reuse,
corruption, missing/FIFO/oversized/escaped files and wrong dimensions), and native
frontend build/lint pass. This is synthetic-camera integration evidence; actual
learned-run/browser camera validation remains pending. Prior full regression19814
is still running and predates camera changes. Training95347 remains the only GPU
job; do not start render or model evaluation concurrently.

Browser camera check: all three saved teacher PNGs rendered with correct names,
sequence0/simulation0s and explicit `injected_unverified` source in an isolated
fixture. Source images were hash-checked from teacher114540. Screenshot and AX
snapshot: `output/playwright/operator/camera-panel.png` and `camera-panel.yml`.
The fixture dispatched no simulation/model work and made no task-success claim.
Stop was exercised; isolated browser and fixture server were shut down. This
verifies browser display of saved captures, not a live learned workflow.
Prepared post-training evaluator now explicitly limits CPU threads to4; syntax
checked only, no inference launched. Training95347 remains active.
