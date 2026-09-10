# Contact-based cup placement

The `cup` command runs one scripted skill: grasp a hollow cup by its outside
walls, carry it, and release it upright on the workbench. It does not accept a
natural-language instruction or execute the full dinner-table task.

```sh
.venv/bin/bimanual cup
.venv/bin/bimanual cup --arm right
.venv/bin/bimanual cup --fault missing-object --no-render
.venv/bin/bimanual cup --fault skip-close --no-render
```

Open the local portal and select the contact cup teacher replay. Failed attempts
are retained alongside successes. The implementation is in
[`cup.py`](../src/bimanual/cup.py); acceptance and fault checks are in
[`test_cup.py`](../tests/test_cup.py).

## Declared operating envelope

This first cup is approximately 62 mm across its hollow body, 63 mm high, and
60 g. A base and sixteen collision walls leave its interior open. Three capsule
segments form an actual loop handle; this teacher grasps the walls, not the
handle. The handle increases the overall width. There is no fluid in the cup.

The cup starts at world `(-0.136, -0.110, 0.378)` metres. Its target is
`(-0.066, -0.153, 0.378)`. These coordinates refer to the cup body's base frame,
not its centre of mass. By default the left arm acts and the right arm remains at reset. With
`--arm right`, world X/Y coordinates and cup yaw are rotated by 180 degrees,
and the left arm stays at reset. This mirrored scene keeps the cup away from
the drawer region when composing the future dinner scene. The original SO-101 joint limits, gains and collision assets
remain unchanged. Physics runs at 200 Hz and control at 20 Hz.

Cup friction is `1, 0.005, 0.0001`; its contact parameters are
`solref="0.01 1"` and `solimp="0.95 0.99 0.001"`. These choices and the nominal
geometry have not been validated across masses, shapes or friction variations.
Peak single-jaw normal force was **88.1 N** in the nominal run. This is a
simulation measurement, not a validated hardware force or a force-control limit.

## How the teacher works

The gripper opens to 1.2 radians, approaches downward, and closes to 0.7 radians
around the cup walls. A two-second airborne hold must pass before transport.
Lowering ends when the cup makes load-bearing contact with the table. The jaws
then open and retreat, followed by two seconds of released settling.

For transport and lowering, [`check_carried_path`](../src/bimanual/teacher.py)
measures the current object-to-tool transform and predicts that transform along
the proposed trajectory in a separate MuJoCo data instance. This avoids treating
the cup's old position as a stationary obstacle. The prediction samples joint
changes at no more than 0.02 radians; it does not guarantee continuous clearance
or predict slipping. The actual cup remains an unactuated free body, moved only
by live contacts. Every live physics step retains the collision/overlap checks.

The teacher uses simulator truth for planning and scoring. Camera/joint
observations exclude object positions, orientation checks and contact forces.
The recorded observation trace is diagnostic, not a LeRobot demonstration export.

## Acceptance and evidence

Success requires all of the following, with continuous timestamps and ordered
phases:

- 400 consecutive physics samples with bilateral jaw support, no table support,
  and at least 40 mm of lift.
- 600 consecutive transport samples with the same airborne contact conditions.
- 400 terminal settling samples supported by the table, with no jaw support,
  within 20 mm of the target horizontally and 4 mm vertically, linear speed
  below 10 mm/s and angular speed below 0.1 rad/s.
- Cup axis within ten degrees of upright throughout those settling samples,
  at least 60 mm of actual horizontal displacement, zero forbidden contacts,
  and no contact overlap greater than 2.5 mm.

| Integrated run | Result |
|---|---|
| `20260910T214209-e2fd6aaa7727` | No-render nominal pass; 21.95 simulated seconds |
| `20260910T214956-40fa1c16d088` | Mirrored right-arm no-render pass; original left-arm controls remained at reset |
| `20260910T214357-4255abc01ac6` | Rendered nominal pass; 21.95 simulated / 9.98 wall seconds; verified artifact seal |

The rendered run lifted 52.24 mm, displaced 69.37 mm horizontally, and finished
12.79 mm from the requested target. All 400 hold, 600 transport and 400 settling
samples passed; maximum overlap was 1.931 mm. These are working-tree development
runs based on commit `224b87d`, not held-out release evaluations. Their local
bundles include the scene/assets, joint observations, independent contact trace,
source hashes and three-camera replay.

The non-render tests cover actual placement, corrupted success evidence,
missing cup, failed grasp, unowned-arm commands, contact violations, scratch/live
state isolation and interruption. A separate render test checks all three views
and a multi-frame replay. Full-task success remains unset.

## Five-minute exercise

Read the final `settled` rows in `scoring-truth.jsonl`. Why must both jaw forces
be zero even though the cup is in the correct location?

**Check your answer:** a robot can hold a cup over the target without placing it.
Table support, no jaw support, low velocity and continued upright orientation
provide evidence of a stable release. A single image or one high position sample
cannot establish that. Reading this answer is exposure; demonstrate the reasoning
in your own words before recording mastery.
