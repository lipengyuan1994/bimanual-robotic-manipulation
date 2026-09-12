# Contact-based plate placement

Run the nominal plate skill and inspect its replay in the local portal:

```sh
.venv/bin/bimanual plate
.venv/bin/bimanual plate --fault missing-object --no-render
.venv/bin/bimanual plate --fault skip-close --no-render
```

The left arm takes a small rimmed plate from a physical source rack, carries it,
and releases it onto the bare table. The right arm first moves to a checked
parking pose to provide clearance. This is a scripted teacher, not learned control
or the complete dinner-table workflow.

The plate is 130 mm across and 80 g. The source rack is 35 mm high and leaves
space for the lower finger beneath the plate edge. There is **no destination
rack or trivet**. The teacher lowers the plate edge first, opens the gripper,
withdraws sideways, and checks that the released plate remains flat and still.
A [1 kHz physics profile](decisions/0004-explicit-physics-profiles.md) resolves
contacts while actions remain at 20 Hz. Robot actuator settings are unchanged.

Rendered run `20260910T215707-0266b4a5e7fb` lifted the plate 51.57 mm and moved it
140.12 mm horizontally. It passed two seconds of airborne bilateral hold, three
seconds of carry, and two seconds of upright bare-table settling, with zero
forbidden contacts and 0.727 mm maximum overlap. Its final error was **18.74 mm
against a 20 mm limit**: the margin is small, and robustness remains unproven.

The contact properties and a 20 mm release calibration were tuned in development.
They are disclosed in the [complete attempt and geometry record](experiments/2026-09-10-tableware-feasibility.md),
including failures. No object is attached artificially or moved by editing its
live position. The teacher uses exact simulator state in its separate planning
and scoring paths; those values are excluded from camera/joint observations.

Read [the implementation](../src/bimanual/plate.py) and
[acceptance/fault tests](../tests/test_plate.py) to connect this result to code.
The scorer rejects dropped or still-supported plates, timing gaps, wrong target
locations, moving or tilted releases, and placement on the source rack.

## Five-minute exercise

Why is carrying a plate successfully insufficient to claim successful placement?

**Check your answer:** the lower finger can remain trapped beneath the plate,
or withdrawal can drag it away. Success needs evidence after release: no finger
or rack support, actual table support, low velocity, acceptable position, and
continued upright orientation. An image taken while the robot still holds it
cannot prove those conditions. Demonstrate this reasoning before recording mastery.
