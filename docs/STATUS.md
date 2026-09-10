# Project status

Updated: 2026-09-10. Branch: `codex/preparation-foundation`.

## Current boundary

M0 is complete. M1 is in progress: either arm can physically grasp and place a
practice block, the arms can transfer a practice bar through contact, and a
contact-driven drawer opens and remains open after release. A small hollow cup
can also be carried and released upright in its nominal scene. The user authorized event-window implementation following
the event's explicit online kickoff instructions; see [decision 0003](decisions/0003-event-window-implementation.md).
Earlier preparation remains identified in Git history. No organizer ruling on
pre-existing-code reuse is claimed.

There is no complete dinner-task scene, task-trained deployed policy, visual
planner, recovery supervisor, or Intel deployment yet. The full product and M1's
manipulation exit checks remain incomplete.

## Implemented

- Two namespaced SO-101 instances from pinned MuJoCo Menagerie assets with original
  license and per-file SHA-256 provenance, above a simple workbench.
- Twelve mapped channels, original joint/actuator dynamics, intersected limits,
  finite-value and episode/sequence checks, synchronous stop/reset, and 200 Hz
  physics with a 20 Hz control interface.
- Overhead and two wrist cameras, reproducible reset pose, actual joint traces,
  replay GIF, mapping/config and self-contained scene bundles. Wrist optical axes
  are adjusted in the builder; upstream files are unchanged.
- New `bimanual sim` CLI and portal replay support. Read the
  [foundation walkthrough](DUAL_ARM_FOUNDATION.md), including a short exercise.
- New `bimanual grasp`: bounded downward IK, sampled trajectory checking,
  per-physics-step contact guards and independently scored block grasp/placement.
  [Walkthrough and exercise](CONTACT_GRASP.md); either arm acts while the other remains parked.
  Failed replays are now selectable as well as successes. No learned control yet.
- New `bimanual handoff`: a contact-only practice-bar transfer with independently
  checked donor-only, shared and receiver-only airborne ownership. See
  [HANDOFF](HANDOFF.md), including contact-model assumptions and retained failures.
- New `bimanual drawer`: opens a passive slide-joint drawer by its handle, releases
  it, and checks that the drawer stays open with spoon/fork proxies retained.
  [Drawer walkthrough](DRAWER.md); utensil retrieval remains unimplemented.
- New `bimanual cup`: physical transport and upright release of a hollow 60 g cup.
  [Cup walkthrough](CUP.md) records the declared geometry, contact forces,
  carried-object path prediction, acceptance checks and rendered evidence.
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
- Existing native bootstrap/doctor, generic pendulum lab, evidence store/SQLite
  index, read-only portal, seven lessons, GitHub Pages and README synchronization.
- [Zero-cost Intel access request](INTEL_ACCESS.md) submitted for
  `bimanual-sim-intel`, BM-PTL Series 3, one week. Intel shows Pending Review;
  there is no granted host or spend.

## Verification and checkpoint

Current changes passed **189 ordinary tests and six actual rendering tests**,
Ruff, documentation-link checks, README synchronization and the TypeScript/portal
production build. Optional real LeRobot/ACT tests run separately in the isolated
training environment: 30 checks passed together and the explicit real LeRobot
export check passed separately. Skips in the base environment are not counted as passes.
The reviewer reproduced and fixed failed-outcome vocabulary mismatches in held-out
dataset checks and duplicate-timestamp false positives in physical grasp scoring.
Regression tests now cover both. Learned-rollout checks are recorded below. The cup addition passed 13 ordinary
checks and its separate three-camera rendering check; the full ordinary suite
passed in `.artifacts/checks-cup.log`. The earlier five rendering checks remain
recorded in `.artifacts/render-checks-placement-handoff.log`.

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

Run `.venv/bin/bimanual handoff` and inspect the replay and contact evidence in the
portal. Use `--fault skip-receiver-close --no-render` to verify that the donor
keeps ownership when the receiver fails to establish its grasp.
Next implementation slice: retrieve the stored utensils, finish plate handling, integrate cup handling,
and combine skills in one dinner scene. In parallel, run the early ACT checkpoint
through the same physics and action checks; retain any failed learned rollout.
M1 is complete only after the [roadmap](ROADMAP.md) exit checks pass.

In parallel, await Intel review notification, advertised within three days. The
request currently shows September 10–17, with no timezone identified for its
displayed end time. Both eligible catalog options offered only Windows 11;
Ubuntu was requested in the short intended-use field. Once approved, verify
actual hardware, expiry, installation permissions, rendering and OpenVINO CPU
inference. Windows compatibility and Intel compliance are still untested.
