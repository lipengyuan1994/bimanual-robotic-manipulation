# Two-arm placement and synchronized recording

Date: 2026-09-10. Scope: nominal scripted practice-block skills, not dinner-task
completion, held-out evaluation or learned-policy performance. The object,
contact parameters, joint limits and scoring envelope are described in
[CONTACT_GRASP](../CONTACT_GRASP.md).

## Attempt register

All runs below are retained under `.artifacts/runs/`; they are working-tree
descendants of `86f4fe1`. Each manifest identifies its exact source digest and
configuration. These are engineering attempts, not a frozen test suite.

| Run | Conditions | Outcome |
|---|---|---|
| `20260910T205424-297bbf397432` | Left, destination (-0.15, 0) | Failed: lowered target unreachable after the hold |
| `20260910T205425-df763025a537` | Right, destination (0.15, 0) | Same explicit reach failure |
| `20260910T205447-7fc1fc22ae06` | Left, destination (-0.15, 0.08), physics only | Passed |
| `20260910T205448-55ef283ac60f` | Right, destination (0.15, -0.08), physics only | Passed |
| `20260910T205616-477446f274be` | Left rendered inside macOS sandbox | Failed at time zero: CoreGraphics context unavailable |
| `20260910T205617-c4192a3caeba` | Right rendered inside macOS sandbox | Same platform failure |
| `20260910T205643-b8ef7d25ba59` | Left, macOS graphics access | Passed; 23 simulated seconds / 19.67 wall seconds |
| `20260910T210237-50fcd0cc7d99` | Left with raw demonstration recording | Passed; 23 simulated seconds / 41.21 wall seconds |

The rendered left placement lifted 54.4 mm, passed 400/400 hold, 600/600 transport
and 400/400 settling samples, with zero forbidden contacts. Maximum overlap was
1.932 mm and final position error 7.77 mm. The commanded horizontal displacement
was 160 mm. Different destination geometry can fail despite a reachable elevated
pose; the lowered pose must independently satisfy the arm's limits.

The raw recording contains 460 confirmed action transitions, 461 observations
and 1,383 lossless RGB camera images. Images are captured at every 20 Hz control
boundary, while the display replay remains 10 Hz. Scene, controller sources,
configuration and hashes accompany the recording. Seed 0 is a metadata label;
no random scene variation was introduced by that label.

## Validation and interpretation

Physical tests cover both arms, an incorrect destination, loss of contact during
transport, movement commands for the unowned arm, and malformed destinations.
Actual rendered recorder tests cover successful placement, a missing object and
failure after one 5 ms physics substep. The partial failure retains its actual
physics history but exports zero applied training transitions, ending at the
last complete camera boundary. Failed episodes cannot enter success-only intake.

Native training dependencies were installed separately under
`.artifacts/training-venv` from the frozen lock, using explicit ARM64 Python
3.12.13. The architecture audit checked 370 compiled extensions, including eight
universal libraries containing ARM64, with no incompatible libraries. LeRobot
0.6.1, PyArrow 25.0.1, ACTPolicy and LeRobotDataset imported successfully. Importing
the image/video stack reported duplicate AVFoundation Objective-C classes from
OpenCV and PyAV's bundled libraries; imports completed, but this is an unresolved
platform warning to track. No package binaries were modified.

These results establish recording and nominal teacher movement. They do not
establish utensil/plate/cup handling, generalization, a learned policy, Intel
performance, or a complete dinner-table workflow.
