# Project status

Updated: 2026-09-10. Branch: `codex/preparation-foundation`.
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
  has passed; live visual planning/recovery remains unintegrated.
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
retries, but is not connected to live skill executors. Planner latency/fresh
execution observations still need an explicit integration solution.

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

Latest `scripts/check.sh`: **612 passed, thirteen explicit optional-training skips,
eight rendering tests deselected**, with Ruff, formatting, docs and README checks.
Log: `.artifacts/checks-continuous-control.log`; all current auxiliary-arm,
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

## Next executable work

See the final handoff entry below for live process handles; do not restart jobs
without checking their actual state.

1. Monitor the fixed 20,000-update ACT run listed below; do not duplicate it.
   Apply its unchanged offline gates only after it seals.
2. Keep the verified full export and seven skill views as one nominal training
   scene. The data/trainer integration passes full checks and the actual CPU
   test, but no learned dinner capability is available yet.
3. Connect measured skill termination/recovery and live visual planning to the
   incremental dinner worker. Train/evaluate the bounded dinner checkpoints before
   advertising availability; the one-update fixture only tests integration.
   Do not expose unsupported skills or silently substitute the teacher.

Verify the current teacher evidence with
`.venv/bin/bimanual evidence verify 20260911T011032-a9fda4aee41f`.

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
