# Project status

Updated: 2026-09-10. Branch: `codex/preparation-foundation`.

## Current boundary

M0 is complete. M1 is in progress: block placement, bar hand-off, drawer-to-table
spoon/fork retrieval, hollow cup placement with either arm, and plate placement
onto the bare table pass their authored-scene teacher checks. A full continuous
dinner-scene workflow is not yet established. The user authorized event-window implementation following
the event's explicit online kickoff instructions; see [decision 0003](decisions/0003-event-window-implementation.md).
Earlier preparation remains identified in Git history. No organizer ruling on
pre-existing-code reuse is claimed.

There is no complete dinner-task execution, successful learned manipulation policy,
integrated live visual planning/recovery, or Intel deployment yet. A local Qwen
proposal adapter and deterministic supervisor core now exist separately. The full
product and M1's manipulation exit checks remain incomplete.

## Implemented

- Two namespaced SO-101 instances from pinned MuJoCo Menagerie assets with original
  license and per-file SHA-256 provenance, above a simple workbench.
- Twelve mapped channels, original joint/actuator dynamics, intersected limits,
  finite-value and episode/sequence checks, synchronous stop/reset, and 200 Hz
  default physics with a 20 Hz control interface. An explicit 1 kHz profile
  checks every finer physics step without changing the action rate; see
  [decision 0004](decisions/0004-explicit-physics-profiles.md).
- Overhead and two wrist cameras, reproducible reset pose, actual joint traces,
  replay GIF, mapping/config and self-contained scene bundles. Wrist optical axes
  are adjusted in the builder; upstream files are unchanged.
- New `bimanual sim` CLI and portal replay support. Read the
  [foundation walkthrough](DUAL_ARM_FOUNDATION.md), including a short exercise.
- New `bimanual grasp`: bounded downward IK, sampled trajectory checking,
  per-physics-step contact guards and independently scored block grasp/placement.
  [Walkthrough and exercise](CONTACT_GRASP.md); either arm acts while the other remains parked.
  Failed replays are selectable as well as successes. This command uses a scripted teacher.
- New `bimanual handoff`: a contact-only practice-bar transfer with independently
  checked donor-only, shared and receiver-only airborne ownership. See
  [HANDOFF](HANDOFF.md), including contact-model assumptions and retained failures.
- New `bimanual drawer`: opens a passive slide-joint drawer by its handle, releases
  it, and checks that the drawer stays open with spoon/fork proxies retained.
  [Drawer walkthrough](DRAWER.md). This drawer-only scene retains the original
  thin-shaft proxies; retrieval uses the explicit variant below.
- New `bimanual cup`: physical transport and upright release of a hollow 60 g cup.
  [Cup walkthrough](CUP.md) records the declared geometry, contact forces,
  carried-object path prediction, acceptance checks and rendered evidence.
- New `bimanual plate`: a physical source-rack grasp, carry and edge-first release
  onto the bare table. [Plate walkthrough](PLATE.md); its 18.74 mm nominal position
  error is close to the 20 mm limit and is not robustness evidence.
- New `bimanual utensils`: opens the drawer and retrieves/places both spoon and
  fork in one uninterrupted 94.4-second simulation. [Utensil walkthrough](UTENSILS.md)
  discloses the ergonomic handles, flush roof and 1 kHz contact profile.
- An initial [combined dinner layout](DINNER_SCENE.md) loads and settles all objects;
  executing the skills together without resets or disturbing placements remains next.
- `grasp --record-demo` records raw three-camera RGB observations and confirmed
  actions at 20 Hz, with terminal observations, failure outcomes and source lineage.
  [Versioned interfaces](INTERFACES.md) reject malformed/stale action chunks and
  inconsistent recordings. The recorder keeps simulator scoring truth separate.
- `dataset-export` converts verified successful training recordings into actual
  image-backed LeRobot v3 datasets, checks all decoded values against source, and
  copies immutable source evidence. [Dataset operations](DATASETS.md).
- An isolated native training environment is available at `.artifacts/training-venv`.
  [ACT runtime probes](TRAINING.md) exercise real forward/backward/optimizer and
  inference on synthetic data. These are not trained dinner-task checkpoints.
- `train` now performs actual ACT updates from the verified placement recording
  on CPU/MPS and saves policy, normalization processors, optimizer/RNG state and
  dataset/code lineage. Reload checks reproduce raw joint targets. The tiny
  pilot checkpoints have not demonstrated learned manipulation or generalization.
- `policy-rollout` executes a verified ACT checkpoint with image/joint inputs,
  saved preprocessing, whole-chunk action validation and explicit right-arm
  ownership. No teacher targets control the left arm. The first real rollout
  failed its airborne-hold check; [diagnostic and evidence](POLICY_ROLLOUT.md).
- A [task supervisor core](SUPERVISOR.md) checks explicit capabilities,
  prerequisites, arm/workspace ownership, deadlines and at most two retries.
  Cancellation/task changes clear actions; every step change requires a fresh
  observation. Its 26 lifecycle tests do not establish integrated physical recovery.
- [Local Qwen proposals](PLANNER.md) now consume verified recorded camera images
  and measured joints. Actual CPU/MPS inference executes; malformed output,
  contradictory decisions and nominal visibility false negatives are retained.
  No live actions are dispatched.
- Existing native bootstrap/doctor, generic pendulum lab, evidence store/SQLite
  index, read-only portal, seven lessons, GitHub Pages and README synchronization.
- [Zero-cost Intel access request](INTEL_ACCESS.md) submitted for
  `bimanual-sim-intel`, BM-PTL Series 3, one week. Intel shows Pending Review;
  there is no granted host or spend.

## Verification and checkpoint

The latest `scripts/check.sh` passed **366 ordinary tests**, with three explicit
optional-training skips, Ruff, formatting, documentation links and README checks.
The preceding `--render` run passed **seven actual rendering tests**; the new
sensor module additionally passed its actual-render integration test. Four real
paired sensor bundles and four actual Qwen probes were separately executed and
verified. The latest ordinary suite deselects eight rendering tests. Native
ARM64 TypeScript checks and the portal production build also pass. The portal now
links directly to recorded planner decisions from run history.

An actual one-step CPU ACT update, checkpoint reload and sampler RNG continuation
check passed in the isolated training environment after the sampler changes.
Earlier optional LeRobot/ACT checks passed 30 together and the real dataset export
check separately. Skips are not counted as passes. Logs for the latest work are
`.artifacts/checks-planner-sensors.log`,
`.artifacts/checks-planner-v2-final.log`,
`.artifacts/checks-planner-supervisor.log`, and
`.artifacts/checks-sampler-real-training.log`. Earlier physical integration logs
remain in `.artifacts/checks-tableware-integration.log`.

Previous committed checkpoint validation: **45 tests pass** (43 ordinary checks and two rendering
checks), Ruff, documentation links, README synchronization, TypeScript and
portal production build pass. Contact-grasp tests cover physical completion,
failure cases, collision guards, IK and truth separation.
The earlier implementation also passed [GitHub CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34515825221)
on Linux, including offscreen rendering and the portal build.
The more recent checkpoint `224b87d` also passed [Linux CI, rendering and portal build](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34532628755).
Native doctor previously passed an 85-library architecture
audit and CPU/MPS arithmetic comparison. These are not learned-policy tests.

See [M1 foundation evidence](experiments/2026-09-10-dual-arm-foundation.md) for
run history, source lineage, timing and limitations; historical preparation
results remain in [the M0 record](experiments/2026-09-05-preparation.md).

Current four-second rendered run: `20260910T181537-0ad4964dab31`, from clean
implementation commit `5332ac3e0105a2173fbdb505028a103ad65364c2`.
It has 81 observations, zero contacts across checked physics steps, and maximum
post-step tracking error 0.000605 rad. Three-camera rendering measured about
0.81–0.88× real time in two short runs; the no-render loop is much faster.
A synchronized nominal placement dataset now exists (below), but no deployed task
checkpoint has passed a manipulation evaluation. Earlier exploratory runs have dirty
source digests; only the named clean checkpoint has a false dirty flag.

Current grasp run: `20260910T184050-a80163092a64`, from clean implementation
commit `a145917795e603c8246ebc2f96c93f0695cc4f07`; manifest integrity verified.
The block lifted 54.4 mm, passed 400/400 airborne bilateral hold samples and
400/400 released settling samples, with zero forbidden contacts and maximum
contact overlap 1.93 mm. The 20-second simulation took 15.79 seconds including
10 Hz three-camera replay and encoding. This is one nominal scripted skill, not
full-task or generalization evidence. See the [complete attempt register](experiments/2026-09-10-contact-grasp.md).
Clean-checkpoint fault runs were also verified: missing object
`20260910T184104-7afa5e68dac4` stopped at time zero; skip-close
`20260910T184104-84bed25f39cd` stopped at 11.5 simulated seconds with a failed
hold and retained replay. Both returned nonzero exit codes as expected.

Latest working-tree placement recording: `20260910T210237-50fcd0cc7d99`, verified
seal, 460 confirmed transitions / 461 observations / 1,383 camera images. The
block moved 160 mm between target positions, passed all 600 transport samples
and settled 7.77 mm from target. The LeRobot export at
`.artifacts/datasets/placement-probe` has 460 rows; real LeRobot read-back matched
all actions, joint values, timestamps and camera pixels. See the
[complete placement register](experiments/2026-09-10-placement.md).

Latest integrated rendered hand-off: `20260910T210623-5fab3e3b1d93`, verified seal,
31.5 simulated seconds / 14.62 wall seconds. All three ownership phases passed
400/400 samples, with zero forbidden contacts and 1.806 mm maximum overlap.
Receiver sag was 1.519 mm during its two-second hold; longer holds and utensils
remain unvalidated. These runs retain dirty source digests; they are engineering
evidence, not frozen release evaluations.

Rendered drawer run `20260910T211628-5b774988145f` opened 87.38 mm and remained
released/open for 400 physics samples, with both utensils inside and no forbidden
contacts. Maximum overlap was 0.925 mm. Peak summed jaw contact force of 143.5 N
and the ideal passive rail are documented model limitations, not hardware results.

Actual ACT pilot checkpoints: corrected CPU run `20260910T211456-55d5d5db50cc`
(one optimizer step) and MPS run `20260910T211727-eaf518d3ec4c` (three steps,
fallback disabled). Both use the same 460-transition nominal training recording,
the small 11.9-million-parameter ACT and all three full-resolution cameras.
The earlier CPU pilot with inaccurate constant-joint statistics is retained;
current training computes numeric statistics in float64 with a declared standard
deviation floor. See [dataset/training evidence](DATASETS.md).

The first actual learned diagnostic, `20260910T212314-08d05dd65d98`, applied 230
control steps from 23 ACT chunks and stopped at 11.5 simulated seconds: 0/400
airborne-hold samples passed. It had no forbidden contacts, but the block stayed
at pickup. The failed run, camera images, raw/accepted proposals and replay are
retained. This uses the one-step CPU pilot and its training scene; it is not a
held-out or full-task result. The bounded 500-update MPS run
`20260910T212647-8c539d28090b` completed in 110.93 seconds, but its learned rollout
`20260910T212856-6da67f992681` also failed the hold (0/400 samples) at 11.5 seconds.
Training loss decreased without a successful grasp. Diagnosis of prediction
error and approach/closure timing is the next learning step; do not promote either
checkpoint as a working manipulation policy.

## Latest physical integration and learning evidence

- Supervisor/planner integration checks: the full `scripts/check.sh --render`
  passed 317 ordinary tests, three explicit optional-training skips, and seven
  rendering tests in `.artifacts/checks-planner-supervisor.log`. Subsequent planner
  provenance/path/output regressions passed with all 29 planner tests and all 26
  supervisor tests. After temporal-sampler integration, the complete ordinary
  check passed 334 tests with three optional skips; an actual CPU ACT optimizer /
  checkpoint / sampler reload check also passed separately. Version-2 visibility
  guards subsequently passed all 32 planner tests. See
  `.artifacts/checks-planner-supervisor-final.log` and
  `.artifacts/checks-sampler-real-training.log`.
- Clean committed checkpoint `70fec2bcf6c8e7795eb5c0a7d9f20254d8ec1051`:
  rendered cup `20260910T221241-17c01a9d7b28`, plate
  `20260910T221253-4b21be6b045f`, and continuous drawer-to-table utensils
  `20260910T221313-83f9236a633b` all passed their skill checks. Each source
  manifest reports `git_dirty=false`; seals were verified. These are separate
  authored-scene skill runs, not one complete dinner-table episode.
- Cup right-arm rendered run `20260910T215542-576bc5a35e98`: 69.37 mm travel,
  upright release, all timed gates passed. See [CUP](CUP.md).
- Plate CLI run `20260910T215918-56c30c949063` and rendered run
  `20260910T215707-0266b4a5e7fb`: 140.12 mm travel, released flat on the bare table;
  18.74 mm final error against a 20 mm limit. See [PLATE](PLATE.md).
- Canonical portal utensil run `20260910T220228-82cffdf64f0b`: 94.4 simulated /
  65.96 wall seconds with replay, 94,400 audited samples, both utensils released,
  zero forbidden contacts and 1.380 mm maximum overlap. Its seal and strengthened
  scorer were verified. See [UTENSILS](UTENSILS.md). Earlier agent-generated
  utensil runs live in the explicitly documented nested store; none were moved.
- Shared-layout probe `20260910T220035-a5c40c643f17`: all objects load and settle
  together, but no integrated manipulation sequence has passed. See
  [DINNER_SCENE](DINNER_SCENE.md).
- ACT run `20260910T213909-88c7e1c3a78b`: 2,000 MPS updates in 424.72 seconds;
  matched training-frame error improved from 0.1841 to 0.04882 rad. Its physical
  rollout `20260910T214631-6fd7bfd78a0c` still failed the grasp. The separate
  100-step prediction-horizon experiment also completed and failed: rollout
  `20260910T221237-b592ded438b5` passed 0/400 hold samples. Matched training-frame
  error regressed to 0.18713 rad. See [the controlled comparison](POLICY_ROLLOUT.md).
  Every forecasted action, including its unused tail, must pass bounds.
- Approach collection: all six training and two validation teacher cases passed;
  only the six training cases enter the 480-transition dataset. The 2,000-update
  approach ACT still failed all three predeclared physical tests. Offline diagnosis
  found endpoint prediction error even on teacher observations, plus compounding
  starting-motion drift. See [the full experiment](POLICY_ROLLOUT.md).
- Qwen MPS probe `20260910T223047-5e5897fcb203` executed but returned a schema
  instead of a decision; parsing correctly failed. A compact decision-format prompt
  produced valid `pick / left / practice_block` in
  `20260910T223500-0dd265bcb84b`: 25.77 seconds inference, float16, 929 input and
  141 output tokens. This is one nominal recorded-scene proposal, not verified
  reachability, visual grounding quality or full-task success. CPU run
  `20260910T223705-2f35cd2e4c13` returned the same nominal proposal in 220.85 seconds
  at float32. The missing-object run `20260910T224238-f170359764b9` recognized absent
  pixels in its explanation but still requested pick: a semantic failure despite
  valid version-1 JSON. Version-2 proposals now require explicit visibility and
  reject manipulation of an unconfirmed target. Paired follow-up
  `20260910T224604-d53894e8e957` / `20260910T224701-352de484c373` returns clarification
  for both missing and present scenes: safe abstention, but a nominal visibility
  false negative. The planner is not ready for live dinner-task execution.
- Independent review reproduced false-success paths from malformed scoring truth.
  All-row finite/shape/object-presence checks and final-placement checks now reject
  them. Successful physical recordings still pass; no trajectories or old evidence
  were altered to obtain that result.

The cup checkpoint `3a6818f` passed [GitHub CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34534143440).
The subsequent plate/utensil, explicit-physics, scoring and action-prefix checkpoint
`70fec2b` also passed [GitHub CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34536292665).
[Draft PR #1](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/pull/1)
tracks the development branch; no merge or production release is claimed. New
planner/supervisor/sampling checkpoint `781556d` also passed
[GitHub CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34539691869).
The new sensor-profile implementation has its separate local checks above; its
subsequent committed CI result must be checked independently.

## Latest camera and continuous-scene checks

The optional [planner sensor profiles](PLANNER_SENSORS.md) preserve ACT's original
camera contract. All six baseline camera renders matched their original PNGs
exactly before creating higher-resolution overhead views; state remained unchanged.
Four sealed Qwen probes in protocol `20260910T230553-d67de55a7054` confirm actual
processor grids. The 1920 profile correctly distinguishes the paired present and
missing practice-block scenes, taking 91.01/95.12 seconds; the 960 missing case
still contradicts itself and is rejected. All four outcomes are preserved in
comparison `20260911T004313-10b11352cb3c`; no live-planner readiness is claimed.
See [the results](PLANNER.md).

Combined teacher attempt 22 completed 240,950 continuous physics samples and
all movements with zero forbidden contacts, but independent full audit failed
`plate/settled`: 23.58 mm final plate error against the unchanged 20 mm limit.
All other objects passed final placement checks. This remains a failed full task;
the next physical change must adjust the release trajectory, not its target or
acceptance tolerance. The last agent ended after saving the completed trace;
root independently ran the preserved full-audit script on attempt 22.

## External dependencies

| ID | Needed | Consequence |
|---|---|---|
| B1 | Event-window authorization | Resolved for new implementation by decision 0003; prior-code eligibility remains a submission question |
| B2 | Actual free Core Ultra Series 2/3 allocation | BM-PTL request Pending Review; Intel deployment and final compliance remain blocked |
| B3 | Assets/seeds, pouring scope, prior-code eligibility, interactive-hosting interpretation | Submission packaging and scope remain provisional |

Verified deadline: September 16, 2:30 PM EDT (18:30 UTC). Event Guidelines require
an application URL, cover, video and slides as well as the track package. See the
[signed-in source comparison](ORGANIZER_QUESTIONS.md). The user completed Intel
registration and an instance request has been submitted. No organizer message or
hackathon submission has been sent.

## Next executable step

Current source is the development branch HEAD with the sensor-profile changes
recorded above; use `git rev-parse HEAD` for its exact revision. The preceding
implementation checkpoint is `781556df04e6bb6eebe5e1e94320146838904b4f`,
committed and pushed to the development branch / draft PR. The controlled
`approach_regions_v1` training run `20260910T225506-3f5e98132b20` completed all
2,000 MPS updates in 413.30 seconds from that clean checkpoint. Frozen comparison
`20260910T230229-4797222025f2` found 26–33% lower starting prediction error and
endpoint error reduced from 3.50 to 1.18 mm. All three unchanged four-second
physical tests still failed: final errors 18.62, 6.70 and 1.27 mm. The closest
case passed only seven consecutive physics samples, versus 100 required.
All training/diagnostic/rollout processes for this experiment are terminal.
See [the full comparison and next diagnostic](POLICY_ROLLOUT.md).

The combined-scene teacher reached the end of every motion in attempt 15, but
independent acceptance failed: plate position error was 38.446 mm against the
unchanged 20 mm gate. All 238,950 physics samples were contiguous, with zero
forbidden contacts; other ownership/placement gates passed. This is not full-task
success. Preserve the failure and test newly declared waypoint/layout variants.

Run `.venv/bin/bimanual utensils` and inspect the uninterrupted drawer-to-table
replay. Run `.venv/bin/bimanual plate` and `.venv/bin/bimanual cup --arm right`
for the other tableware skills. Next implement the [shared-scene sequence](DINNER_SCENE.md)
with continuous physics and final checks of every placement.
The temporal-sampling comparison improved prediction and physical proximity but
still failed all three frozen tests. Diagnose delayed convergence versus ongoing
replanning movement before any additional training; preserve those deadline failures.
The first approach policy and both full-placement experiments also failed;
neither longer forecasts nor lower training error established learned task success. The higher-resolution pair now distinguishes these two practice-block scenes,
but 91–95-second inference, broader dinner-scene grounding and live observation
handling remain unresolved. CPU and MPS inference execute; reliable live visual
planning remains unproven. Integrate
the supervisor only with real, registered skill executors and preserve the live
observation freshness rules.
M1 is complete only after the [roadmap](ROADMAP.md) exit checks pass.

In parallel, await Intel review notification, advertised within three days. The
request currently shows September 10–17, with no timezone identified for its
displayed end time. Both eligible catalog options offered only Windows 11;
Ubuntu was requested in the short intended-use field. Once approved, verify
actual hardware, expiry, installation permissions, rendering and OpenVINO CPU
inference. Windows compatibility and Intel compliance are still untested.
