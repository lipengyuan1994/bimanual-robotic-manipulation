# Continuous dinner-scene teacher feasibility — September 10, 2026

This scratch exploration starts from the exact combined layout in sealed static
probe `20260910T220035-a5c40c643f17`, described in [DINNER_SCENE](../DINNER_SCENE.md).
Both SO-101 arms, the ergonomic spoon/fork drawer, plate and physical source rack,
right-arm cup and practice hand-off bar remain present and collidable throughout.
Nothing is removed to make an isolated path pass.

The baseline replays previously recorded **teacher joint targets** in a single
live environment. It is not video concatenation, learned control, or a reset
between skills. Every 20 Hz action is applied to 1 kHz MuJoCo physics with one
episode identity and a continuous clock. Live object positions, velocities and
external forces are never edited. Transitions move real joints through checked
paths. Carried-object prediction changes only a separate scratch kinematic state;
live grasping still depends on physical contacts.

Initial order: drawer/spoon/fork, plate, mirrored right-arm cup, practice-bar
hand-off. The source action traces are:

- Utensils: `20260910T215606-949186e83a27`.
- Plate: `20260910T215707-0266b4a5e7fb`.
- Right-arm cup: `20260910T214956-40fa1c16d088`.
- Hand-off: `20260910T210623-5fab3e3b1d93`.

Their action-file hashes are recorded in each attempt. Cup and hand-off source
runs used 200 Hz physics; replaying their targets at 1 kHz is a new experiment,
not reuse of their earlier success claim. Every attempt retains the exact driver,
scene XML, action trace, compressed per-physics-step state/contact trace, result
and phase counts under `.artifacts/dinner-scene-exploration/attemptNN/`.

## Acceptance boundary

A loop reaching its end is labelled `loop_completed_unscored`; it does not claim
a successful dinner task. Independent checks must confirm the drawer opened
from closed; unsupported bilateral utensil, plate and cup carries; stable released
placements of both utensils, plate and cup after subsequent skills; and actual
donor/shared/receiver hand-off ownership. Every physics step is checked for
forbidden contacts and a 2.5 mm overlap/passive-drawer-overtravel limit.

The practice bar is still a dedicated hand-off object. A utensil hand-off remains
unestablished. All work here is a privileged precomputed teacher baseline in one
authored scene, with no robustness or learned-policy claim.

## Attempt register

| Attempt | Outcome |
|---|---|
| 01 | Drawer opening and spoon lift/carry/lowering executed with all other objects present. Spoon hold 2,000/2,000, clearance 3,000/3,000, transport 7,200/7,200 and lowering 3,000/3,000 physics samples had unsupported bilateral contact. At 52.75 s the next opening command was rejected because the moving-jaw mesh would collide with the hand-off bar. No full utensil placement or workflow success. |
| 02 | A bounded 0-rad spoon release/retreat aperture completed spoon placement: 2,000/2,000 settled samples had zero finger force and workbench-only support. Fork grasp/carry followed, but lowering hit the still-present bar at 85.916 s. |

The first failure is specifically `practice_object` versus
`left/collision_or_visual_40`, the stock moving-jaw mesh. It occurs during gripper
opening after lowering, rather than during airborne transport. This illustrates
why isolated successful skill paths cannot be assumed to compose safely.

## Hand-off first and physical bar parking

Attempt 02 established that the intended fork destination and initial bar
footprint conflict. Subsequent attempts retain the bar and perform the hand-off
first, then physically place the bar in a clear strip beyond the utensil targets.
The initial scene and requested tableware destination coordinates are unchanged.

| Attempt | Outcome |
|---|---|
| 03 | Hand-off first with every tableware object present: 2,000/2,000 donor-only, 2,000/2,000 shared, and 2,000/2,000 receiver-only airborne contact samples. Zero forbidden contacts; 1.831 mm maximum overlap. No later dinner skills attempted in this probe. |
| 04 | Hand-off passed; initial raised bar-parking path failed bounded inverse kinematics before carry. |
| 05 | Lower intermediate route successfully parked the bar. Receiver-only unsupported carry passed 12,000/12,000 samples, then released settling passed 2,000/2,000 samples. Empty-arm return failed bounded IK at 65.0 s. |
| 06 | Splitting return translation and raising still encountered a bounded-IK initial-guess limitation; bar remained released and stable. No utensil sequence began. |
| 07 | Bounded wrist-roll candidate search clears the empty-arm return. Hand-off, bar parking and both utensil placements complete in the continuous episode. The next plate approach hits `cabinet_right` with the left gripper at 184.325 s. |

The successful bar-parking segment first physically parks the donor left arm.
The receiver then lowers the held bar in the clear central area to a 0.43 m tip
height, carries around the cup via tip waypoints `(0.025,0.14,0.43)` and
`(0.10,0.21,0.43)`, and lowers to `(0.10,0.21,0.405)` metres. Each route segment is
subdivided and collision checked. The teacher preserves gripper world yaw through
bounded joint-limited IK. It opens the gripper and retreats, leaving the bar on
the workbench at approximately `(0.02932,0.21416,0.39097)` metres. Its two-second
settled phase has zero force from all four fingers, workbench-only support,
position inside a 25 mm destination radius, and velocities below the same
10 mm/s and 0.1 rad/s settling limits.

The unsuccessful return paths do not undo this measured parking result, but they
do block sequence completion. All source layout and action bundles were verified
against their evidence-store seals before continuing. Current exploration stays
outside production modules and preserves all failed attempts.

## Original combined layout: cup also passes; plate access blocks completion

Attempt 08 changes only the order after utensils to cup then plate. The independent
`attempt08/partial-audit.json` checks **210,275 consecutive 1 ms samples**, all with
all five free objects present. Its successful physical phases include:

- Hand-off: 2,000/2,000 samples for each donor-only/shared/receiver-only phase.
- Bar parking: 12,000/12,000 unsupported receiver-carry samples and
  2,000/2,000 released settling samples.
- Drawer: 6,000/6,000 bilateral pull samples, 2,000/2,000 held-open samples and
  2,000/2,000 released-open samples, from a closed initial drawer.
- Each utensil: 2,000/2,000 held, 3,000/3,000 clearance, 7,200/7,200 transported,
  3,000/3,000 lowered and 2,000/2,000 released settling samples.
- Cup: 2,000/2,000 held and 3,000/3,000 transported samples, followed by
  2,000/2,000 upright released settling samples at its intended target.
- During the cup's final settling interval, the previously placed spoon, fork
  and bar also retain zero finger force, workbench-only support, acceptable
  target error and low velocities.

The final plate approach fails at **210.275 seconds**. That forbidden-contact
sample is retained, so the whole attempted run has one forbidden-contact sample
and is a failure. No full-workflow success is claimed. The largest overlap
throughout is 1.831 mm. All completed phases precede the failing contact.

The plate's isolated side-insertion path enters the physical cabinet. A simple
higher approach does not clear its later low insertion; a bounded right-arm
vertical-pinch search around the original near-base plate position did not find
a reachable grasp. The authored layout therefore needs a reachable plate source
and release corridor, not removal of the cabinet or scoring exceptions.

## Explicit authored layout variants

These variants preserve every object, the original object shapes/masses/contact
parameters, the 20 mm plate placement tolerance and all physical scoring gates.
Sources, targets, route calibration and scene hashes are frozen **before** each
physical trial. Kinematic candidates are evaluated in separate scratch data;
this never moves an object in the live episode.

- V2/V3: front plate source `(0.16,-0.025,0.413)` with candidate front-table
  destinations. Static access checks found a close-to-base reach limitation or
  a fork/camera collision during withdrawal; these are planning probes, not
  successful physics runs.
- V4: same front source, plate destination `(0.12,0.035,0.378)`, original release
  tilt and a staged withdrawing path. **Attempt 09** rejected the initial scene:
  the plate rack conflicts with the right robot's resting geometry. No motion
  was executed.
- V5: plate/rack source `(0,0.24,0.413)` (rack centre Z 0.3925), plate destination
  `(0.12,0.035,0.378)`, and a new bar parking destination
  `(0.205,-0.205,0.391)`. The bar follows an elevated, constant-radius arc around
  the right base, preserving its world yaw. All other source locations and
  tableware destinations remain unchanged. Source JSON/XML are retained as
  `layout-v5.json` and `layout-v5.xml`.

Attempt 10 used V5 but its higher bar carry conflicted with the home-position
left gripper. Attempt 11 uses a physically controlled left shoulder parking
angle of -0.8 rad while the right arm carries, but the carried bar would intersect
the cabinet roof at 47.5 seconds; that route is rejected. Attempt 12
is explicitly a **plate-approach/lift/hold diagnostic** in the V5 scene with all
objects present, stopping after hold. It passed all 2,000 airborne hold samples
at 16.5 seconds with 0.701 mm maximum overlap. It does not perform the hand-off
or claim a complete workflow.

V5 frozen scene SHA-256: `328b34f106d7653783952be1d223bd4d232ef7f3cde35c63e52805bf985c53d5`.

Attempt 13 tried a smaller-radius, 0.48 m high southern bar path. Physical bar
sag still made the cabinet-roof crossing unsafe, and the carried-object checker
rejected it. This attempt is retained as another failed route.

**Attempt 14 failed at 131.85 seconds.** Its frozen V6 layout places the plate/rack
at `(0,0.30,0.413)` (rack centre Z 0.3925), retains plate destination
`(0.12,0.035,0.378)`, and restores the previously successful northern bar parking
at `(0.025,0.21,0.391)`. All shapes, masses, contact settings, other objects and
placement tolerances remain unchanged. The plate is lifted/carried at a 0.48 m
tool height to clear the already placed cup. The full candidate route passes
bounded inverse kinematics checks before physical execution. Order is hand-off,
bar parking, cup, plate, then utensils. Hand-off, bar parking, cup placement and
plate lift/carry/release completed, but the plate withdrawal checker rejected a
collision between the left wrist camera and the already placed cup handle.
All 131,850 executed physics samples were guarded; this is not a full-workflow
success. The failed route and raw evidence are preserved.

V6 frozen scene SHA-256: `b06f86fd640d13ea2de97919b0383f57e5d82f65cfd0c7f7027a90aac0994f3a`.
