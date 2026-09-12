# Plate and cup contact feasibility — September 10, 2026

Both declared nominal objects have now been grasped, carried and released using
MuJoCo contacts. This is physical teacher evidence for M1, not learned-policy
success, a combined dinner-table workflow, held-out robustness, or Intel compliance.
The cup is a small hollow cup; the plate is a small rimmed plate retrieved from a
physical source rack and placed on the **bare tabletop**. No destination trivet
is present in the successful plate scene.

## Runtime and preservation

Native `.venv/bin/python` reported `platform.machine() == "arm64"`.
The cup prototype uses 200 Hz physics and 20 Hz joint commands; the final plate
uses 1,000 Hz physics and the same 20 Hz commands. SO-101 assets, joint limits,
actuators and robot dynamics remain upstream values. Plate contact settings are
an explicit simulation assumption, not measured hardware material properties.

All exploratory result directories remain under `.artifacts/tableware-exploration/`.
Each contains actual scene XML, per-physics-step scoring truth and a result; newer
runs also freeze their script and checksums. The first 13 attempts predate script
snapshotting: their exact Python revisions are unavailable, although XML/results/
traces remain. `attempts.csv` indexes every result. These local ignored artifacts
are not an externally published dataset. Integrated runs use `EvidenceStore` and
bundle robot meshes, license, mapping, scene, controller settings and source hashes.

No equality attachment, weld, live object pose change after initialization, object
force, or gravity compensation is used. Only the original robot position actuators
receive commands. The teacher is privileged: IK and collision prediction use exact
simulator state. Prediction moves an object in **separate scratch data only**;
actual object motion remains contact-driven and is checked at every physics step.
The integrated teacher uses the shared rigid object-to-tool prediction from
`teacher.check_carried_path`; early prototypes predicted only object translation.
Neither prediction is a deployed visual-policy observation.

## Cup envelope and evidence

The cup has a 28 mm radius, 6 mm thick base and sixteen wall boxes centred on a
29 mm radius. Each wall's radial/tangential/vertical half-sizes are
1.8 / 5.9 / 30 mm, centred 30 mm above the body origin. The shell is approximately
61.6 mm across and 63 mm high including the base; it is genuinely hollow.
Three 4 mm radius capsules form a real handle from x=28 to49 mm, z=13 to47 mm.
The handle exists physically but is not the grasp target. Total mass is 60 g:
30% base, 55% walls and 15% handle. Object friction is `1 .005 .0001`,
`solref=".01 1"`, `solimp=".95 .99 .001"`.

The left gripper pinches the exterior walls at `(-.15,-.08,.405)` metres.
Object origin starts `(-.136,-.110,.378)`; intended destination is
`(-.066,-.153,.378)`. Gripper open/close targets are1.2 /0.7 rad, lift target
z=.47 m. Joint-space paths are checked, and lower stops when support contact
appears. The object is released before the final two-second stationary check.

Frozen successful source and rendered evidence:
`.artifacts/tableware-exploration/1789075852398199000-cup/`.
The preceding unrendered repeat `1789075842203867000-cup` produced identical
physics. Both moved **69.373 mm**, lifted **52.243 mm**, passed400/400 airborne
hold samples,600/600 airborne transport samples,400/400 released settled samples,
and had **zero forbidden contacts**, maximum overlap **1.931 mm**. The initial
candidate `1789075705133274000-cup` was labelled completed by its older scorer,
but actual displacement was59.701 mm: it does **not** meet the subsequently
explicit actual-displacement>=60 mm requirement. It has not been relabelled.

Reproduction arguments to that frozen script are
`--z .405 --offset .014 -.03 --rotation 0 --close .7 --render`.
Its output root is its own parent directory; copy it into a fresh scratch directory
before running. Integrated cup behavior is maintained separately in `cup.py`.

## Plate envelope, grasp and release

The plate has a130 mm diameter,6 mm thick base and24 physically colliding rim
segments. Rim centres have63 mm radius and7 mm height; each box has radial,
tangential and vertical half-sizes3 /8.4 /7 mm. The rim extends14 mm above the
body origin; overall plate height is17 mm. This is an80 g small plate, with
60 g in the base and20 g in the rim. It does not represent arbitrary dinner plates.

The source rack is a fixed,70 mm diameter cylinder35 mm high, resting on the
375 mm high workbench; its top is at410 mm. The source plate origin is
`(.15,-.09,.413)` metres. The overhang gives access below the plate's edge without
forcing the gripper palm into the workbench. The destination has **no rack**:
`(.13,-.23,.378)` metres is a predetermined bare-table goal.

The plate uses friction `1.5 .01 .0001`, priority1, `solref=".005 1"`,
`solimp=".95 .99 .001"`, and1 ms integration. Priority1 lets its stiffer contact
settings govern table interaction rather than being mixed with the lower-priority
table settings. The robot's own contact parameters remain unchanged. Without this
combination, edge-first release produced table overlap above2.5 mm. The threshold
was not relaxed. Contact forces can exceed60 N under these unchanged position
actuators; this is not validation of a real plate's stress tolerance.

The left hand closes across the plate vertically. IK constrains its pinch site's
Z axis, respects the joint limits and uses damped least squares in scratch data.
During initial settle only, the right shoulder-pan actuator is moved to1.0 rad;
its other joints stay home. Subsequent commands must preserve that parked pose.
This avoids the right wrist/camera intersecting the plate's approach/carry region.

| Phase | Nominal command |
|---|---|
| Side approach | Pinch `(.04,-.08,.46)` m, open0.3 rad |
| Descend and insert | Descend toz=.424 m, insert tox=.10 m |
| Close | Left gripper -0.14 rad |
| Lift and hold | Pinch `(.10,-.08,.47)` m, then hold2 s |
| Carry | Move toward goal with fixed+20 mm X release calibration,3 s |
| Lower | Interpolate closing axis toward normalized`(.42,-.27,.866)`, about30 degrees; pinchz=.405 m; stop on support |
| Release | Open to0.3 rad, wait1.5 s |
| Withdraw | Move pinch by`(-.084,.054,0)` m over5 s |
| Retreat/settle | Raise at withdrawn XY, then verify2 s without finger support |

The+20 mm calibration and reachable goal were selected after exploratory misses,
then fixed **before** the successful runs. This is nominal teacher calibration, not
a final-test result. Edge-first placement lets one plate edge touch the table while
the lower jaw withdraws;1 kHz integration resolves the subsequent contact.
Earlier horizontal withdrawal dragged the plate; stronger wrist tilt encountered
IK limits or palm/table contacts. A destination-trivet experiment also failed its
position gate and was abandoned; it does not satisfy the product target.

Frozen successful bare-table prototype:
`.artifacts/tableware-exploration/1789076998567155000-plate/`.
Rendered repeat `1789077023384005000-plate` produced identical physics and was
visually inspected. Both moved **143.252 mm**, lifted **51.573 mm**, passed
2,000/2,000 airborne hold samples,3,000/3,000 transport samples,2,000/2,000
released settled samples, with **zero forbidden contacts**, **0.993 mm** maximum
overlap and9.614 mm final position error. These are two repeats of one tuned scene.
The frozen scratch scripts use an experimental module-level physics-rate override;
the supported integration uses an explicit `DualArm(..., physics_hz=1000)` instead.

## Integrated plate API and acceptance

`PlateConfig(render=True, missing_object=False, skip_close=False)` is intentionally
left-arm-only. `run_plate(config, *, store, project_root)` returns a sealed manifest.
`PlateEnvironment`, `plate_xml` and `score_plate` expose the scene and independent
scorer. There is no random-seed/general-size input or learned-policy claim.

The scorer requires consecutive1 ms timestamps, a full2 s airborne bilateral
hold >=4 cm above the source,3 s airborne carry, and2 s upright bare-table rest.
Both jaws must apply >0.01 N during the hold/carry, then exactly zero during final
rest. Position tolerances are<2 cm XY and<4 mm Z, speeds<.01 m/s and<.1 rad/s,
upright tilt<=10 degrees, actual travel>=6 cm. Every physics sample must remain
free of forbidden contacts and overlap must be<=2.5 mm. Rack support cannot pass
the final bare-table gate. Terminal observations carry no future action.

Initial integrated nonrendered run `20260910T215250-9ff243e278b2` passed all gates:
140.122 mm actual displacement,51.573 mm lift,18.743 mm final position error,
0.727 mm maximum overlap, zero forbidden contacts. It is a separate run from the
scratch evidence, with its own source/scene digests; the exact trajectories/results
are not interchangeable. `manipulation_success` remains null.

Tests cover real dynamics, an independently rebuilt scene and mass/geometry,
missing object, skipped grasp, interrupted worker, unowned arm commands, live
collision stop, scratch-only IK, malformed IK, timing gaps, insufficient duration,
loss of grip, moving/tilted objects and source-rack substitution in final scoring.
All faults preserve failures and claims remain empty. The first15 nonrendered
tests passed. Rendered integrated run `20260910T215433-5c092d5f4332` matched the
nonrendered result and saved all three camera views. Subsequent review strengthened
input-shape/initial-limit checks and requires zero rack support at final placement
and zero support of any magnitude during airborne hold/carry. The final17
nonrendered tests passed (one render test deselected), and Ruff passed. Final
rendered run `20260910T215707-0266b4a5e7fb` passed the strengthened scorer
with the same physical measurements; its sealed manifest and three-camera replay
were verified. Final-image inspection confirms the plate resting flat on the bare
table, separate from the source rack. These are nominal repeats only.

## All exploratory physical attempts

The following are development attempts, including intended inspection stops and
renderer failures. They are not an independent-seed success-rate denominator.

| Run | Recorded outcome / stopping reason |
|---|---|
| `1789075404026280000-cup` | Downward grasp target unreachable within IK tolerances and joint limits |
| `1789075425886945000-cup` | No bilateral airborne hold |
| `1789075436171575000-cup` | Inspection stop after descent |
| `1789075460085639000-cup` | Planned trajectory intersects forbidden geometry: ('left/collision_or_visual_7', 'cup/wall4') |
| `1789075466898164000-cup` | No bilateral airborne hold |
| `1789075482070096000-cup` | No bilateral airborne hold |
| `1789075493760477000-cup` | Overlap 0.0025047350937606873 exceeds2.5mm |
| `1789075545613789000-cup` | Independent placement scorer failed |
| `1789075593108020000-cup` | Overlap 0.0025174332610367277 exceeds2.5mm |
| `1789075605105993000-cup` | Overlap 0.002504444932084749 exceeds2.5mm |
| `1789075643175198000-cup` | No bilateral airborne hold |
| `1789075662090506000-cup` | Planned trajectory intersects forbidden geometry: ('left/camera_box1', 'cup/wall1') |
| `1789075705133274000-cup` | Older scorer completed; actual59.701 mm travel fails current60 mm gate |
| `1789075749441506000-cup` | invalid CoreGraphics connection |
| `1789075761382048000-cup` | Overlap 0.002531300191703627 exceeds2.5mm |
| `1789075782483075000-plate` | Overlap 0.0027249903946612165 exceeds2.5mm |
| `1789075799682628000-cup` | Overlap 0.0025422003888335614 exceeds2.5mm |
| `1789075814425659000-cup` | Overlap 0.002573472317746673 exceeds2.5mm |
| `1789075826964193000-cup` | Overlap 0.002573472317746673 exceeds2.5mm: ['left/moving_jaw_box3', 'cup/wall13'] |
| `1789075835167256000-cup` | Overlap 0.0025049998592312937 exceeds2.5mm: ['left/moving_jaw_box3', 'cup/wall13'] |
| `1789075842203867000-cup` | Passed nominal gates |
| `1789075852398199000-cup` | Passed nominal gates |
| `1789075861946440000-plate` | Overlap 0.004332340608511834 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789075884930532000-plate` | Overlap 0.0028458142480668395 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789075920864799000-plate` | No bilateral airborne hold |
| `1789075955197097000-plate` | Overlap 0.0025397409124591273 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789075970845266000-plate` | Overlap 0.0038023247059455123 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076017950739000-plate` | Overlap 0.0030442283193850565 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076027218466000-plate` | Overlap 0.0025029693085899924 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076059028826000-plate` | Overlap 0.0031380793181726443 exceeds2.5mm: ['plate/base', 'left/collision_or_visual_41'] |
| `1789076323163843000-plate` | Planned trajectory intersects forbidden geometry: ('workbench', 'left/collision_or_visual_30') |
| `1789076368042304000-plate` | Forbidden contact during approach: ('workbench', 'left/collision_or_visual_30') |
| `1789076411492444000-plate` | Planned trajectory intersects forbidden geometry: ('workbench', 'left/collision_or_visual_30') |
| `1789076426840617000-plate` | Forbidden contact during insert: ('workbench', 'left/collision_or_visual_30') |
| `1789076441852532000-plate` | Forbidden contact during lift: ('left/camera_box2', 'right/collision_or_visual_30') |
| `1789076458270498000-plate` | Independent placement scorer failed |
| `1789076517704291000-plate` | Forbidden contact during retreat: ('workbench', 'left/collision_or_visual_30') |
| `1789076668121788000-plate` | Independent placement scorer failed |
| `1789076713959672000-plate` | Planned trajectory intersects forbidden geometry: ('left/camera_box1', 'plate/rim11') |
| `1789076727689222000-plate` | Planned trajectory intersects forbidden geometry: ('left/camera_box1', 'plate/rim11') |
| `1789076761078784000-plate` | Overlap 0.0031273695934674983 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076787362231000-plate` | Overlap 0.003376935224874524 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076814368804000-plate` | Horizontal-axis IK unreachable |
| `1789076824964050000-plate` | Horizontal-axis IK unreachable |
| `1789076839393653000-plate` | Overlap 0.0034992293234011405 exceeds2.5mm: ['plate/base', 'left/fixed_jaw_box5'] |
| `1789076851648077000-plate` | Forbidden contact during unseat: ('workbench', 'left/collision_or_visual_30') |
| `1789076886440826000-plate` | Independent placement scorer failed |
| `1789076925652642000-plate` | Overlap 0.0026502225498685355 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076939601043000-plate` | Overlap 0.002537863327789979 exceeds2.5mm: ['plate/base', 'workbench'] |
| `1789076954601330000-plate` | Independent placement scorer failed |
| `1789076979643286000-plate` | Horizontal-axis IK unreachable |
| `1789076998567155000-plate` | Passed nominal gates |
| `1789077023384005000-plate` | Passed nominal gates |
