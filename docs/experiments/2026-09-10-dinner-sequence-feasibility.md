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

## Complete motion loop, failed acceptance, and calibrated follow-up

**Attempt 15** changed only the V6 ordering to hand-off/bar parking, plate, cup,
then drawer/utensils. All motions finished in one 238.95-second episode
(128.28 seconds wall time), but **full-task acceptance failed**. The independent
scratch audit checked all 238,950 consecutive 1 kHz rows: zero forbidden contacts,
1.830624 mm maximum overlap and 100.137 N maximum aggregated jaw normal force.
All required ownership, drawer, airborne transport and released-placement gates
passed except the plate's position. Its final `(0.09761,0.00375,0.37800)` is
38.45 mm from the predeclared `(0.12,0.035,0.378)` destination, outside the unchanged
20 mm tolerance. Spoon, fork, cup and parked bar stayed within their release gates
through the rest of the episode. The plate result is never rescored against a
new destination. Raw evidence and independent scoring are retained at
`.artifacts/dinner-scene-exploration/attempt15/{physics.jsonl.gz,full-audit.json}`.

**Attempt 16 (V7)** was an explicitly exploratory alternative: destination
`(0.12,0,0.378)` and a fixed +22.4 mm X waypoint correction. The destination was
frozen before running to increase clearance from the source cup. It failed at
123.37 seconds when the right gripper touched the placed plate during cup descent.
Its Y target was not regenerated through a target-to-tool calibration, so this
variant is not adopted as a calibrated baseline even independently of that failure.

**Attempt 17 (V8) failed at 126.65 seconds.** A scratch-only grid reconstructed the
cup's settled pose, tested candidate plate release/withdrawal paths against every
scene object, and found the V6 intended destination incompatible with the sampled
cup-first wrist-camera clearance. V8 therefore declares plate destination
`(0.14,-0.015,0.378)` before running, with the same 20 mm acceptance tolerance.
The fixed measured plate-minus-tool XY offset from failed attempt 15 is
`(0.007612912,-0.041254826)`. Both commanded carry/lower XY coordinates are computed
as **declared destination minus this offset**; withdrawal and retreat are generated
from that same target. This produces tool XY `(0.132387088,0.026254826)` and a
west/up withdrawal delta `(-0.06,0,0.025)`, chosen by collision checking before the
physical trial. Order returns to hand-off/bar parking, cup, plate, then utensils.
The source scene shapes, contact settings, masses, other destinations and scoring
tolerances are unchanged. These are authored-layout experiments, not arbitrary
scene generalization. No full-task success or canonical V8 adoption is claimed.

Scratch planning is separate `MjData`/environment state; no candidate placement is
written into the live experiment. Frozen source/targets/calibration and raw traces
remain under `layout-v8.json`, `layout-v8.xml`, `release-grid.json` and `attempt17/`.

Attempt 17's diagonal plate carry was rejected before contact with the parked
right fixed jaw. At rejection the plate centre was approximately
`(0.0910,0.1013,0.4708)` and the right fixed jaw centre
`(0.1631,0.1207,0.4984)`. All earlier executed steps remain retained.

**Attempt 18 (V9) failed at 124.95 seconds.** It keeps V8's exact source geometry,
destination, tool/object calibration and withdrawal path. A predeclared
`(-0.03,0.025,0.48)` plate-tool clearance waypoint moves toward the front before
the rightward carry, avoiding the parked right arm. This adds a separately
audited two-second airborne transport phase; it does not relax any acceptance
gate. The layout manifest and driver are frozen before execution.

V9's front clearance point was too close to the left robot base for the required
plate orientation: bounded IK rejected it before executing that segment.
**Attempt 19 (V10) failed during the rightward carry.** The replacement clearance waypoint
`(0.04,0.02,0.48)` passes 41 interpolated bounded IK poses from the actual plate
hold. The V8 destination and all other calibration/withdrawal/scoring settings
remain unchanged. Each failed attempt keeps its own frozen driver, scene and trace.

Attempt 19 completed its frontward clearance but the carried plate still approached
the north-parked right gripper. The carried-object checker rejected that segment.
**Attempt 20 (V11) failed at 129.20 seconds.** It preserves V10's plate source, target,
calibration and complete route, and changes the empty right arm's supervised
plate-stage shoulder-pan parking angle from +1 to -1 rad. The arm moves there
through its original actuator, before the left arm grasps the plate; no object is
repositioned. This vacates the positive-Y carry volume. Its return to home remains
a checked physical transition before drawer operation.

At -1 rad parking, the right shoulder's collision geometry still obstructed the
plate. A separate carried-transform grid reconstructed the actual held plate and
checked 41 points per remaining carry/lower segment across five parking angles
and three heights. The -1.8 rad candidate cleared all three tested heights;
**V12** retains the original 0.48 m height and all V11 geometry, destinations and
calibration, changing only that empty-arm parking angle. Grid results are retained
in `park-carry-grid.json`; prediction is not itself contact-manipulation evidence.

**Attempt 21** tried V12 with three-camera rendering but stopped at the first
capture because the restricted process could not establish a macOS CoreGraphics
connection. It is retained as an environment failure. **Attempt 22 is active and
unscored**, repeating the identical V12 controller with native macOS graphics
access. It captures all three cameras at 2 Hz for a replay labelled as 5x speed.
No full-task acceptance has passed as of this register entry.

Root follow-up: attempt 22 is terminal (`loop_completed_unscored`). Independent
`audit_full.py attempt22` read all 240,950 physics samples and failed only the
plate settled gate. Final plate position (0.117282, -0.021320, 0.377997) m is
23.5808 mm from the unchanged (0.14, -0.015) m XY target. Zero forbidden samples,
1.830624 mm maximum overlap, one continuous action episode and all other final
placements passed. `terminal_all_placed_samples` remains zero. Preserve
`attempt22/full-audit.json` and `attempt22-audit.log`; this is not full-task success.
Next adjust the physical plate release trajectory with unchanged destination and
20 mm acceptance, then rerun the whole workflow and audit.

## Release compensation after attempt 22

`release22-diagnosis.json` reconstructs tool poses from the recorded joints and
compares them with recorded plate poses; it sends no actions. Plate center is
(0.137156, -0.015905, 0.397170) m at the first supported lower endpoint, then
settles to (0.117282, -0.021320, 0.377997) m during withdrawal. Most of the error
comes from the tilted plate settling into flat contact, rather than the airborne
transport endpoint.

V13 freezes tool XY compensation (+0.022718, +0.006320) m before **attempt 23**.
Scene SHA-256, plate destination and 20 mm acceptance remain unchanged. Attempt 23
is rejected at the end of the clearance phase because its compensated high carry
would intersect `right/collision_or_visual_7` with `plate/rim4`; the rejected
segment is not executed.

V14 applies that same correction only to lowering/withdrawal/retreat, retaining
the previously passing high transport. **Attempt 24** reaches the lower phase but
stops at 131.766 simulated seconds on contact between the right shoulder geometry
and `plate/rim5`; overlap is 0.652 mm. The failure is preserved. An offline
reconstruction of that collision clears the plate/right-arm contact when the
right shoulder pan is +1.8 rad instead of -1.8 rad. Snapshot clearance alone
cannot establish trajectory clearance.

V15 changes only the empty right arm's parking angle to +1.8 rad. **Attempt 25 is
active and unscored** with full continuous physics, the same lower compensation,
geometry, destinations and acceptance rules. All new drivers, manifests, traces,
results and the snapshot probe remain in `.artifacts/dinner-scene-exploration/`.

Attempt 25 is terminal and failed. Parking at +1.8 rad clears the corrected
lower/release, but `left/camera_box2` contacts the placed cup at 134.979 simulated
seconds during withdrawal (0.0553 mm overlap). **V16 / attempt 26** shifts the
withdrawal and retreat 60 mm south; it clears the cup but the settling plate
contacts `cabinet_right` at 137.664 seconds, also 0.0553 mm overlap. No contact
allowlist, object shape, destination or tolerance was relaxed. Both traces and
failures are retained; neither is full-workflow success.

The next release experiment should evaluate candidate withdrawal paths against
both the cup/camera clearance and the plate/cabinet clearance, preferably from a
faithfully replayed pre-withdrawal simulation snapshot for economical diagnosis.
A successful snapshot diagnostic would still require a fresh full continuous
workflow and independent final audit before integration.

**V17 / attempt 27:** the 20 mm southward withdrawal finishes the plate motions,
but the plate remains tilted (upright cosine 0.6342), at z=0.4272 m and with
0.269 N fixed-jaw contact. The return trajectory is rejected on that retained
contact. Finishing the scripted phases is not placement success.

**V18 / attempt 28:** withdraw 120 mm west and 20 mm south at the measured release
tool height before lifting. The complete sequence then passes `audit_full.py`:
240,950 continuous samples, zero forbidden contacts, all required intervals,
zero prior-placement disturbances and all 2,000 final all-placed samples.
Plate XY error is 13.555 mm; the cup is 18.071 mm, both within unchanged 20 mm
limits. Run is unrendered: 240.95 simulated / 124.26 wall seconds.

Sealed self-contained evidence: `20260911T011032-a9fda4aee41f`. Scene load and
manifest integrity verify. It preserves exact runtime source, original input
teacher trajectory/manifests, actual action/physics traces, licenses, scene assets
and audit source/results. This is the first passing authored-scene teacher
feasibility run, not a learned workflow or held-out release evaluation. Next
package and reproduce it from the supported repository command with cameras.
