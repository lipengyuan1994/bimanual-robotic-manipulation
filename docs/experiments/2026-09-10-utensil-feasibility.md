# Drawer-to-table utensil retrieval feasibility — September 10, 2026

This experiment runs drawer opening and utensil retrieval in **one uninterrupted
live simulation**. It does not detach, reset, reposition or directly actuate the
utensils after opening. Only the original twelve SO-101 actuators are commanded.
All exploratory scripts, scene XML, physics traces and failures are retained in
`.artifacts/utensil-exploration/`; no canonical scene or runtime module is changed
by this prototype.

## Established result

**Latest: attempt 38 completed both utensils in one uninterrupted run.** See the
full-workflow evidence below. Attempt 30 remains the earlier spoon-only milestone.

Attempt 30 completed physical drawer opening, spoon pickup, airborne transport,
and released placement on the workbench. It used the explicitly described
**ergonomic-handle variant and 1 kHz physics profile**, not the original thin-shaft
proxy or the current 200 Hz application default.

- 59.2 simulated seconds, 59,200 individually audited physics samples.
- 2,000/2,000 samples in the two-second spoon hold had bilateral finger force
  above 0.01 N and no drawer, cabinet or workbench support.
- 7,200/7,200 transport samples had the same bilateral, unsupported grasp.
- 2,000/2,000 final settling samples had zero finger force and workbench-only
  support. Maximum translational speed in that interval was about 3.4e-11 m/s.
- No forbidden contacts; maximum measured contact overlap **1.380 mm**.
- Spoon centre ended at approximately `(-0.11614, 0.04410, 0.38093)` metres,
  clear of the cabinet. The fork remained in the opened drawer.

This is one nominal scene and an exploratory teacher. It does not establish
ordinary flatware support, generalization, learned control, or a production
release. Attempt 30's successful physical outcome was verified from all phase
samples; merely reaching the end of the script is not sufficient.

## Named geometric and contact assumptions

The canonical drawer experiment's original spoon/fork shaft radius is 3 mm.
Their flat supporting surfaces and the stock gripper's finger geometry prevented
reliable pickup in the early attempts. Those failures remain recorded; the
canonical objects have not been silently replaced.

The successful variant changes each utensil handle to a **12 × 40 × 12 mm box**,
centred at local `(0,-0.032,0)` with mass 12 g. A 2.5 mm-radius capsule neck
connects local Y `-0.012` to `0.035`, mass 2 g. The original spoon bowl remains
an ellipsoid with semi-axes `(0.011,0.014,0.003)` m and mass 3 g; total spoon mass
is **17 g**. The fork retains its original bridge and four tines; total fork mass
is **17.6 g**. These primitives represent chunky ergonomic handles, not measured
commercial cutlery. Both start at Z 0.400 m and are shifted 15 mm toward the
cabinet back relative to the canonical drawer rows, providing gripper/front-wall
clearance after full opening.

Only the handle geoms explicitly set `condim=6`, `priority=1`,
`friction="1 .01 .002"`, `solref=".01 1"`. These are uncalibrated contact-material
assumptions consistent with the earlier practice-bar experiment. Other utensil
geometries retain their source settings. The drawer remains an unactuated slide
with its original 11 cm travel, cabinet roof and real contents. Pull target
changes to `(-0.269,-0.18,0.413)` metres; after release the drawer reaches its
11 cm open stop. The compliant limit remains subject to the unchanged 2.5 mm
overtravel guard.

## Tool points, planning and dynamics

A separate kinematic tool site at gripper-local `(-0.001,-0.000218,-0.0982)`
metres targets the spoon's handle near the finger tips. It changes no collision
geometry. The spoon's world grip point is its actual body transform applied to
local `(0,-0.025,0)`, plus 4.5 mm in world Z. Wrist-roll initialization is 1.1 rad;
the gripper is preshaped to 0 rad and closes to **-0.07 rad** in attempt 30.
All targets stay inside original limits. The teacher uses explicit simulator
truth; it is not a camera-driven policy.

After a tip-height lift to 0.45 m and two-second hold, clearance height becomes
0.458 m. Cartesian transport follows waypoints `(-0.15,-0.10)`, `(-0.10,-0.04)`,
`(-0.12,0.02)` at that height, subdivided into three steps each. A scratch IK
iteration preserves the gripper's world yaw, rather than keeping wrist roll
constant while the shoulder turns. Lowering uses tip target `(-0.12,0.02,0.391)`.
The gripper then opens, retreats, and the object settles for two seconds.

The collision predictor for carried phases uses the **measured gripper-to-object
relative transform in scratch MjData**. It transforms only that scratch object's
pose along a candidate joint path. Live body poses, free-joint coordinates,
velocities and external forces are never edited. Real contact dynamics determine
whether the grasp holds, and each physics step is independently checked. The
frozen-object checker otherwise rejects a valid lowering path when the robot
camera passes through where the carried object used to be.

At 200 Hz, several transport attempts produced grip oscillation, loss or overlap
beyond the unchanged 2.5 mm limit. The 1 kHz diagnostic profile sets a 1 ms physics
step and executes 50 physics steps per 20 Hz action. Contact audits run at **every
1 ms step**; successful two-second phases require 2,000 samples, not 400. This is
a proposed explicit numerical-integration profile and has not changed the
application's default. It must be integrated/configured and regression-tested
before reuse as a released skill.

## Attempt register

Every attempt also runs the physical drawer-opening sequence from reset; failed
retrieval attempts do not reuse a magically pre-opened scene.

| Attempts | Finding |
|---|---|
| 01–02 | Original thin shafts and block-oriented tool point. Finger/front-wall or finger-mesh/front-wall collision prevented closing/descent. |
| 03 | Thin shaft, fixed wrist roll and higher grasp point. Script finished but the spoon stayed in the drawer: **failed retrieval**, not success. |
| 04 | Bowl grasp compressed the thin object against the floor beyond the overlap guard. |
| 05–08 | Thick cylindrical handles tested; narrow preshape, wall collisions and fixed-finger pressure against the floor rejected these variants. |
| 09 | Added a tip tool point; 0.47 m approach was outside joint-limited reach. |
| 10–12 | Lower approach, adjusted wrist yaw and narrower preshape with original thin shafts. Attempt 12 established transient contact but never lifted the spoon; failed airborne hold. |
| 13–16 | Box-shaped ergonomic handles, row clearance and tip-height refinement. Attempts stopped at front wall, floor, or excessive close/lift overlap. All thresholds unchanged. |
| 17 | Ergonomic spoon lifted and passed an airborne two-second hold at 200 Hz. Direct placement path rejected robot self-collision. |
| 18–20 | Changed wrist orientation and clearance height. Roof collision or unreachable height rejected the routes. |
| 21 | Cartesian route avoided roof but an intermediate target was inside the arm's minimum reachable radius. |
| 22–25 | Reachable curved routes and friction/grip variations still failed the overlap guard or lost the object during transport. |
| 26 | Slow transport loop finished but spoon dropped onto mixed workbench/drawer support near the cabinet: **failed placement**. |
| 27–28 | Shorter route and world-yaw compensation improved geometry; 200 Hz overlap guard still stopped the carry. |
| 29 | Same route at 1 kHz preserved the grasp throughout transport. Lowering was rejected by frozen-object path prediction. |
| 30 | Scratch carried-object prediction plus the 1 kHz profile completed spoon retrieval and verified released tabletop placement. |
| 31 | Spoon completed again, then same-environment fork approach was rejected because its gripper mesh intersected the cabinet roof. |

Further fork experiments keep the successful spoon sequence and the live scene.
A fork-specific tool orientation may be needed because the rear row offers less
roof clearance. Those results will be appended below rather than rewriting
failed runs.

## Fork continuation and flush-roof variant

Attempts 32–36 rotated the fork grasp by 90 degrees to avoid the roof with
unchanged cabinet geometry. Attempt 32 failed the close-overlap guard;
attempts 33–35 lifted and held the fork but lost it during clearance or transport;
attempt 36 again failed close overlap. No fork placement is claimed for these
runs. Attempt 35 added an explicit carry-contact check during execution, and
support classification now includes contact with the other utensil.

Attempt 37 instead makes the roof's front face flush with the closed drawer's
front exterior. `cabinet_roof` changes from position `(-0.020,-0.180,0.433)` and
half-size `(0.102,0.093,0.004)` to position `(-0.014,-0.180,0.433)` and half-size
`(0.096,0.093,0.004)` metres. The back face stays at X 0.082; the front face moves
from X -0.122 to -0.110. Thus only a 12 mm roof overhang is removed. The closed
interior remains roofed; moving drawer panels, stationary cabinet walls and
stored free-body contents all remain collidable. This is an explicit authored
scene variant, not a change to the canonical drawer module.

The flush-roof variant lets the fork use the same tip site and narrow-axis box
handle pinch as the spoon, with wrist-roll initialization 1.0 rad, local grip
point `(0,-0.025,0)` plus world Z 4.5 mm, preshape 0 and close -0.07 rad.
Attempt 37 lifted and held the fork for two seconds, but the requested 0.458 m
clearance height failed bounded inverse kinematics from that rear-row position.

## Full drawer → spoon → fork success: attempt 38

Reducing only the fork's tip clearance/transport height to **0.453 m** made its
bounded path reachable. Spoon clearance remains 0.458 m. Fork Cartesian XY
waypoints are `(-0.15,-0.10)`, `(-0.10,-0.04)`, `(-0.06,0.03)`, each subdivided
into three moves of 16 control steps. Lowering target is `(-0.06,0.03,0.391)`;
then the gripper opens, retreats to Z 0.45, and allows a two-second settle.
The previously placed spoon stays in the scene for the entire fork sequence.

The native ARM64 run has **94.4 simulated seconds and 94,400 contiguous physics
samples**. An independent audit of every relevant sample, saved as
`.artifacts/utensil-exploration/attempt38-audit.json`, confirms:

| Evidence | Spoon | Fork |
|---|---:|---:|
| Two-second unsupported bilateral hold | 2,000 / 2,000 | 2,000 / 2,000 |
| Unsupported bilateral clearance | 3,000 / 3,000 | 3,000 / 3,000 |
| Unsupported bilateral transport | 7,200 / 7,200 | 7,200 / 7,200 |
| Released workbench-only settling | 2,000 / 2,000 | 2,000 / 2,000 |
| Minimum transport jaw normal force | 15.620 N | 16.236 N |
| Maximum transport jaw normal force | 16.854 N | 16.973 N |
| Final body centre, metres | `(-0.11614,0.04410,0.38093)` | `(-0.05698,0.05284,0.38093)` |

There are **zero forbidden contacts** throughout. Maximum overlap is 1.380 mm;
maximum passive drawer-limit overtravel is 0.687 mm. The drawer finishes open at
109.439 mm. Both final objects have zero finger force and only workbench support;
settling translational speed is below 3.4e-11 m/s. The workbench top is Z 0.375 m.
No object transforms or velocities are edited in live state after reset.

The high contact normals come from an uncalibrated position-controlled primitive
contact model; they do not establish safe real-hardware grip forces. This result
covers one authored scene, ergonomic handles, a flush-roof cabinet, an explicit
1 kHz integration profile and a truth-assisted teacher. It does not establish
ordinary flatware support, robustness, learned control, hand-off integration,
plate/cup placement or a complete dinner-table task.

Frozen reproduction inputs:

- `.artifacts/utensil-exploration/utensil38.py`: SHA-256
  `f1b2590dc39097e40c4c6e80196d912624715ac6bf3e3da650510cc5039a9a4c`.
- `.artifacts/utensil-exploration/tip_ik.py`: SHA-256
  `206661340b1c37a5dc7825ec97c04fd8f565e1218ba50140799546bd10394881`.
- `.artifacts/utensil-exploration/attempt38.xml`: SHA-256
  `1b006f3f82c0e4ead587ca4d1c0d3580e0cfda6042b09d4e3472d5d320fe5214`.
- Full attempt JSON SHA-256:
  `e47b9490ac168d53bd8f63935bbbc80d5d396b7e54dcae7f801179166b8a712b`.

The original frozen driver uses a process-local physics-rate override matching
its 1 ms XML. Canonical integration must use the new explicit per-environment
physics-rate API rather than retain that scratch override. The prototype's
post-run audit is needed in addition to its loop completion marker.

## Explicit timing repeat and integrated implementation

Attempt 39 repeats the full successful sequence with the new
`DualArm(xml=..., physics_hz=1000)` interface, with no global timing override.
Its three-camera rendered replay and final image are retained as
`.artifacts/utensil-exploration/attempt39.gif` and `attempt39-final.png`.
The independent audit again passed all 94,400 physics samples. The final image
shows both released utensils outside the opened drawer.

The implementation now lives in `src/bimanual/utensils.py`:

- `UtensilConfig(render=True, missing_object=None, skip_close=None,
  scene_variant="ergonomic_flush_roof_v1")` validates configuration.
- `missing_object` is either `"spoon"` or `"fork"`; that physical free body is
  absent from the XML and the attempt fails before any motion.
- `skip_close` selects `"spoon"` or `"fork"`; the selected grasp remains at its
  preshape command and the run must fail without a placement claim. Earlier
  drawer opening and any completed spoon steps remain in its evidence.
- `UtensilEnvironment` owns only the left arm, enforces a 1 kHz XML and runtime,
  and audits every contact step. It does not override global timing settings.
- `utensils_xml(config)` exposes the named scene variant for later composition.
- `score_utensils(trace)` independently checks the complete ordered 94,400-step
  sequence, initially closed drawer, sustained pull/open/released phases,
  unsupported bilateral hold and transport, both released final destinations,
  collisions and overlap. Missing, reordered, interrupted or shortened phases
  cannot count as success.
- `run_utensils(config, store=..., project_root=...)` returns a sealed Manifest
  of kind `contact_utensils_teacher`. Metrics include `utensils_success`,
  `drawer_opened`, `spoon_placed`, `fork_placed`, and
  `manipulation_success=null` because this remains a component demonstration.

Policy observations and robot actions go to `observations.jsonl`; exact object
poses, velocities, support, per-jaw normal forces, drawer position and all contact
pairs remain separate in `scoring-truth.jsonl`. Scene XML, asset license,
upstream/mapping metadata and configuration are sealed with every attempted run.
The teacher and collision predictor explicitly consume simulator truth; these
must not be confused with a learned, image-conditioned deployment policy.

First integrated no-render run: **`20260910T215606-949186e83a27`**, completed,
94.4 simulated seconds, zero forbidden contacts and 1.380 mm maximum overlap.

Integrated rendered run: **`20260910T215812-a683b622283e`**, completed and sealed;
473 replay frames, integrity verification passed and the final frame was visually
inspected. The initial 19 targeted tests passed in 74.91 seconds, including
missing-spoon/fork, skipped-spoon/fork closure, interruption, geometry/actuation,
truth separation, timing/order, carry contact, destination and collision guards.
Independent review then added stricter all-row trace validation and further
negative controls; final verification is recorded below.

This rendered integrated attempt took 65.285 wall-clock seconds including
recording and evidence work; this is a local smoke measurement, not an Intel
benchmark. Peak recorded utensil jaw normal forces across all phases were
24.153 N for the spoon and 24.805 N for the fork. These contact-model values are
reported rather than treated as validated real-hardware forces.

The two integration runs above used a scratch evidence-store root of
`.artifacts/runs`, so their actual sealed directories are
`.artifacts/runs/runs/<run-id>`. They are not automatically entries in the
portal's normal evidence index. A normal CLI run should use the configured
application store; the scratch records remain preserved in place.

Independent review found and fixed acceptance of omitted idle-object records and
nonfinite values in trace fields. The scorer now validates both object records
on every physics row, finite vectors of exact dimensions and nonnegative force,
overlap and overtravel before evaluating completion. The hardened targeted suite
passed **33/33 tests in 96.78 seconds**. Review also added explicit disturbances
to the already-placed spoon during the fork's final settling phase.

Lowering now requires another **3,000/3,000 unsupported bilateral samples for
each utensil**, preventing premature release during that part of transport from
counting as success. Both integrated sealed traces passed this final scorer;
none of these scoring changes modified the physics sequence or overwritten
sealed evidence.

Direct negative controls against the final scorer reject a single missing jaw
contact during either spoon or fork lowering. Ruff checks and formatting checks
passed for the integrated module and its tests. The additional lowering pytest
and repository-wide checks are part of the parent integration verification.
