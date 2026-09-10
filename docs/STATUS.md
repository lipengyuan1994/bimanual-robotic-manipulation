# Project status

Updated: 2026-09-10. Branch: `codex/preparation-foundation`.

## Current boundary

M0 is complete. M1 is in progress: the first dual-arm simulation slice runs and
has local verification. The user authorized event-window implementation following
the event's explicit online kickoff instructions; see [decision 0003](decisions/0003-event-window-implementation.md).
Earlier preparation remains identified in Git history. No organizer ruling on
pre-existing-code reuse is claimed.

There is no dinner-task scene, grasp/hand-off teacher, learned policy, visual
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
- Existing native bootstrap/doctor, generic pendulum lab, evidence store/SQLite
  index, read-only portal, seven lessons, GitHub Pages and README synchronization.
- [Zero-cost Intel access request](INTEL_ACCESS.md) submitted for
  `bimanual-sim-intel`, BM-PTL Series 3, one week. Intel shows Pending Review;
  there is no granted host or spend.

## Verification and checkpoint

Local validation: 39 Python tests including two rendering checks, Ruff, TypeScript
and portal production build pass. Native doctor passes an 85-library architecture
audit and CPU/MPS arithmetic comparison. These are not learned-policy tests.

See [M1 foundation evidence](experiments/2026-09-10-dual-arm-foundation.md) for
run history, source lineage, timing and limitations; historical preparation
results remain in [the M0 record](experiments/2026-09-05-preparation.md).

Current four-second rendered run: `20260910T181537-0ad4964dab31`, from clean
implementation commit `5332ac3e0105a2173fbdb505028a103ad65364c2`.
It has 81 observations, zero contacts across checked physics steps, and maximum
post-step tracking error 0.000605 rad. Three-camera rendering measured about
0.81–0.88× real time in two short runs; the no-render loop is much faster.
No manipulation dataset/checkpoint exists. Earlier exploratory runs have dirty
source digests; only the named clean checkpoint has a false dirty flag.

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

Run `.venv/bin/bimanual sim --seconds 4` and inspect the replay/mapping in the
portal. Next implementation slice: add a reachable object and constrained IK
teacher, then validate a genuine contact grasp/release before drawer and hand-off.
M1 is complete only after the [roadmap](ROADMAP.md) exit checks pass.

In parallel, await Intel review notification, advertised within three days. The
request currently shows September 10–17, with no timezone identified for its
displayed end time. Both eligible catalog options offered only Windows 11;
Ubuntu was requested in the short intended-use field. Once approved, verify
actual hardware, expiry, installation permissions, rendering and OpenVINO CPU
inference. Windows compatibility and Intel compliance are still untested.
