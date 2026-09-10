# Milestones and exit checks

## M0 — Preparation

General environment work, documentation, reproducibility scaffolding, and learning.
Exit: native Python and extension audit, measured CPU/MPS arithmetic, actual
MuJoCo stepping/rendering, deterministic lab replay, usable portal/lessons,
passing checks, and a current handoff record. B1/B2 may remain open without
pretending the whole product is complete.

## M1 — Physical foundation (authorized; in progress)

The event-window authorization is recorded in [decision 0003](decisions/0003-event-window-implementation.md).
Dual-arm loading, mapping, bounded controls and camera rendering are implemented;
see the [foundation walkthrough](DUAL_ARM_FOUNDATION.md). Either arm can grasp and place a practice block with bounded IK; see the
[contact walkthrough](CONTACT_GRASP.md). A contact-only practice-bar transfer is
implemented with independent ownership checks; see [hand-off](HANDOFF.md).
A passive [drawer](DRAWER.md) now opens through contact and remains open after
release with its utensil proxies retained. A hollow [cup](CUP.md) now passes nominal upright placement. Retrieval and plate
handling remain incomplete; all skills still need integration into the full scene.
The steps below still
require task-level evidence before M1 is complete.

1. Import the pinned SO-101 assets with license; namespace joints, actuators and cameras.
2. Build the reachable table/drawer/utensil scene and verify valid reset configurations.
3. Add constrained damped-least-squares IK and collision-checked teacher waypoints.
4. Establish real contact grasp/release and shared-space hand-off.

Exit: joint/action/camera mapping tests, stable scene stepping, drawer/placement/
hand-off evidence from the teacher, explicit failure cases, no artificial attachment.
Run Intel rendering and a tiny OpenVINO conversion probe as soon as B2 resolves.

## M2 — Learned workflow (M1 required)

Record synchronized LeRobot demonstrations, validate them, separate train/validation
seeds, train ACT skills, add Qwen step proposals, and integrate supervisor/recovery.
Measure small training runs before choosing larger budgets. Keep CPU fallback
and test MPS operations actually used by the training code.

Exit: full workflow with learned movements and image-grounded decisions; no teacher
assistance; cancellation, stale-camera, malformed-output, and failed-grasp tests;
per-step outcome/latency records. Loss alone is not manipulation success.

## M3 — Hackathon release (M2, B2 and event details required)

Freeze the candidate and the 10-seed suite, retain all runs, export model components,
validate precision changes, benchmark on exact Intel hardware, and record the demo.
Package setup/scene/train/eval/inference/benchmark commands and the architecture.
Prepare video and platform presentation fields after checking the submission form.

Exit: reproducible clean installation, honest 10-seed outcomes, actual Intel
evidence, and traceable rubric coverage. A failed threshold remains a failed
threshold; do not reclassify it for the deadline.

## M4 — Production hardening (after hackathon)

Evaluate nominal and perturbation suites, expand fault injection, test process
interruption and checkpoint rollback, document support/runbooks, and validate the
declared operating envelope. Run at least 100 nominal and 100 perturbed episodes
for the accepted internal targets. Examine confidence intervals and failure classes.

Pouring and SmolVLA require separate experiment records, outcome definitions,
and comparable evidence. Pouring must disclose its transfer/spill representation;
rigid-particle proxies cannot be called validated real fluid behavior.
