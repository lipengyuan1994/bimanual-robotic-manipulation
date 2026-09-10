# M1a: two-arm simulation foundation

Date: September 10, 2026. Task success: **not evaluated**. M1 overall: incomplete.

## Lineage and configuration

Implementation runs below have base Git revision
`a859a7ff5d00c18f087db48150d9c145d73074c7` and dirty working-source hashes stored
in each manifest. Later documentation/formatting edits differ from those recorded
bytes; preserve the manifests rather than rewriting their lineage.
Source: `src/bimanual/dual_arm.py`. Asset revision:
`8161bba264d7fa7c99ca301e91e7fb44737676ad`, robotstudio_so101, Apache-2.0.

Native Apple M1 Pro, macOS 26.5.2 arm64, Python 3.12.13, MuJoCo 3.12.0.
No dataset/model/seed suite: deterministic reset and a small shoulder-pan sweep.
RGB 480×270, overhead/left wrist/right wrist, 200 Hz physics / 20 Hz control.

## Attempt register

| Local run ID | Observation | Interpretation |
|---|---|---|
| 20260910T180455-d6c03266e5cb | Two-second no-render layout had inter-arm contacts and 0.3245 rad tracking error | Unsuitable pose; retained. Early runner recorded completed, meaning loop completion only. Later runner fails unexpected contacts. |
| 20260910T180527-bce2fea8a1cd | Clear raised pose, four seconds, zero contacts; wrist views mostly black | Control check passed; camera framing unsuitable |
| 20260910T180558-1c0b7415067e | Camera axes aimed at grasp site; raised pose still faced away from table | Framing unsuitable; retained |
| 20260910T180630-c30b34a38bec | Wrist-flexed pose, table visible in both wrists, zero contacts, 81 observations | Accepted foundation demonstration, no task success claim |
| 20260910T181127-bdfc3e6301b9 | Final reset/sweep without rendering, four seconds, zero contacts | CPU physics baseline only |
| 20260910T181102-d2715c618f45 | Doctor: 85 extensions native, CPU/MPS arithmetic passed | Runtime evidence only |

All runs live under ignored `.artifacts/runs/`; use `bimanual evidence verify` to
validate a record. Test-induced failures live in pytest temporary stores.

## Measurements

| Four-second run | Loop wall seconds | Setup seconds | Total through encoding | Sim-time / loop-time |
|---|---:|---:|---:|---:|
| Three cameras | 4.5373 | 0.1477 | 6.4305 | 0.8816 |
| No render | 0.0275 | 0.2231 | 0.2522 | 145.34 |

Loop includes rendering when enabled; total excludes provenance hashing before
timer start and final sealing. Maximum post-step joint tracking error: 0.000604723
rad for this sweep. Both record zero contacts at each checked physics step.
These single-run timings are not p50/p95 benchmarks or capacity claims, and
the rendered loop does not maintain 20 Hz wall-clock operation yet.

## Checks

`scripts/check.sh --render`: 37 non-render plus 2 render tests, Ruff and docs checks.
Native Node 24: `npm run check`, `npm run build`. Existing two TestClient dependency
deprecation warnings remain. Robot-specific tests cover upstream dynamics, all 12
channels, invalid values/bounds, the wrist joint/control-range mismatch, stale
episodes/sequences, stop/reset, deterministic stepping, independent RGB frames,
self-contained scene reload and sealed failure records.

## Limits and next experiment

Visual inspection verifies grippers/workbench are visible, not object-recognition
quality. Grasp, drawer, hand-off, constrained trajectory planning, learned inference,
and Intel execution are unimplemented. No hidden object-state input was added.
Next: real contact grasp/release of a reachable object with an explicit teacher-only
IK interface and independent release evidence.
