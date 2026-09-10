# Local contact-grasp experiment — September 10, 2026

## Purpose and scope

Validate a scripted, contact-only pick/hold/release on the native Apple M1 Pro
while Intel allocation is Pending Review. This is engineering development, not a
frozen competition evaluation or a learned-policy score. The right arm remains
parked. Drawer, utensils, separate destination placement and hand-off are pending.

Environment: native ARM64 Python 3.12.13, MuJoCo 3.12.0, CPU physics, existing
OpenGL renderer. No training dataset, checkpoint, hosted inference or GPU training.
The unchanged SO-101 source is pinned in `UPSTREAM.json`. Each sealed run contains
its exact configuration, scene/assets and working-source hashes. Unless otherwise
noted, these exploratory runs are dirty descendants of `ff8048f`.

## Attempt register

| Attempt | Outcome / interpretation |
|---|---|
| Scratch IK at (-0.06, -0.12, 0.48) and (0.02, -0.08, 0.46) m | Downward direction could not be satisfied within wrist-flex limits; no live movement |
| `.artifacts/grasp-exploration/attempt1.json` | Wide 32 mm box pushed away during descent; failed grasp |
| `.artifacts/grasp-exploration/attempt2.json` | Cylinder lifted, but gripper touched the table; unacceptable |
| `.artifacts/grasp-exploration/attempt3.json` | Raised approach removed observed robot-table contact; exploratory boundary samples did not establish continuous hold or settling |
| `20260910T183228-d5f709d3f9f8` (unsealed) | Serialization failed because an acceptance count was a NumPy integer. Trace files retained in its unsealed run directory; not a valid verified result |
| `20260910T183254-cb8cc960f5af` | Cylinder held for all 400 hold samples but failed settling; rocking velocity remained too high |
| `20260910T183321-045dc3308942` | Smaller box held and settled, but max overlap 4.35 mm prompted a stricter physics gate. Historical manifest predates that gate and must not be counted as a current pass |
| `20260910T183356-1b8cf927cbf4` | Release above support surface reduced maximum overlap to 1.93 mm; hold and release passed |
| `20260910T183508-1d6a886231b4` | Rendered run with explicit 2.5 mm overlap guard passed. 20 simulated seconds took 16.39 wall seconds, including replay encoding but excluding source hashing and sealing |
| `20260910T184050-a80163092a64` | Clean commit `a145917795e603c8246ebc2f96c93f0695cc4f07`, verified manifest. Same physical results; 20 simulated seconds, 15.79 wall seconds including replay encoding |
| `20260910T184104-7afa5e68dac4` | Same clean commit. Deliberate missing object: failed before movement, no success claim, verified manifest |
| `20260910T184104-84bed25f39cd` | Same clean commit. Deliberate skip-close: failed hold, stopped at 11.5 simulated seconds, retained rendered replay, verified manifest |

Scratch probes and raw outputs are retained under `.artifacts/grasp-exploration`.
They are engineering diagnostics, not sealed evaluation episodes. No bad seed was
replaced within an evaluation suite: no such suite has been declared for this skill.

## Current acceptance and checks

The rendered run lifted the 25 g block **54.4 mm**, maintained an airborne
bilateral grasp for **400/400 physics samples**, then settled after release for
**400/400 samples**. Forbidden-contact samples: **0**. Maximum contact overlap:
**1.93 mm**, below the explicit **2.5 mm** experiment gate. No full-task success.

Tests cover bounded non-mutating IK, unreachable targets, planned collision
rejection, per-physics-step collision/overlap stopping, portable scene loading,
no attachment/object actuator/gravity compensation, truth separation, full hold
and release scoring, missing object and deliberately unclosed gripper. Negative
scoring controls reject a single-jaw hold, table-supported hold, forbidden contact,
excess overlap and incomplete settling. See [the walkthrough](../CONTACT_GRASP.md).

Local validation passed: 45 tests, Ruff, 165 documentation links, README
synchronization, native TypeScript check and production portal build. The portal
shows the correct skill, success/failure and contact-evidence link.
The same implementation passed [GitHub Linux and portal CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34515825221),
including offscreen rendering. Linux CI is not an Intel Core Ultra hardware test.
The formal source checkpoint is recorded in [STATUS](../STATUS.md).

## Next experiment

Transport the block to a different reachable placement zone, then establish a
right-arm counterpart and a shared-workspace ownership protocol before hand-off.
Freeze a small validation envelope before adjusting parameters for robustness.
Intel validation remains a separate platform milestone; Windows 11 is the current
cloud catalog offering, not a tested deployment target.
