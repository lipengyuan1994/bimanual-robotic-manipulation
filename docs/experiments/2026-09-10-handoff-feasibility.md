# Two-arm contact hand-off feasibility — September 10, 2026

This is exploratory physics evidence for M1. It is not a released teacher, a
learned policy, utensil manipulation, a complete dinner workflow, or an Intel
result. The prototype is deliberately outside `src/` until its scoring,
failure handling and interface are integrated and tested.

## Runtime and retained artifacts

Native `.venv/bin/python` reported `platform.machine() == "arm64"`. MuJoCo uses
unchanged upstream SO-101 meshes, dynamics and limits through `DualArm`.
Prototype code, all nine attempted runs, scene XML, summary, and replay are in
`.artifacts/handoff-exploration/` (ignored local artifacts). `physical01.py` through
`physical07.py` preserve successive prototype versions; `physical.py` adds the
rendering option to the seventh version. `reach-grid.json` preserves the preceding
kinematic grid, including unreachable and colliding configurations.

Reproduce the final exploratory run from the checkout:

```bash
.venv/bin/python .artifacts/handoff-exploration/physical.py another-attempt --render
```

Use a new label to preserve earlier attempts. The current prototype writes output
files directly and has not yet adopted the released immutable evidence-store API.
The rendered ninth run required native macOS graphics access outside the execution
sandbox. The eighth attempt's graphics failure is retained.

## Geometry and approach

A single free rigid practice bar starts at `(0, 0, 0.391)` metres, dimensions
`0.18 × 0.02 × 0.032` metres, mass `0.025` kg. No weld, equality attachment,
object position edits after reset, object forces, or gravity compensation are used.
The only commands during execution are the original twelve position actuators.

The box geom explicitly uses `condim=6`, `priority=1`,
`friction="1 .01 .002"`, and `solref=".01 1"`. This is a documented contact
model assumption, not a measured material. The stock finger geoms have priority
one, so object friction changes at priority zero do not govern finger contacts.
The chosen rolling resistance reduces sag of the long lever arm; sensitivity
and material realism remain unvalidated. No stock robot parameter is modified.

Both downward-facing grippers use wrist-roll target `1.57` radians to align their
opening across the bar's narrow dimension. A scratch IK variant solves the first
four joints with wrist roll held fixed, checks position error below 0.1 mm and
downward-axis error below 0.001, and respects all intersected joint/actuator limits.
The stock free-roll solver drifts in wrist orientation and is unsuitable for this
bar without the additional constraint.

| Phase | Pinch target or action |
|---|---|
| Left approach | `(-0.075, 0, 0.46)` metres |
| Left grasp | `(-0.075, 0, 0.404)`, close to `-0.1` rad |
| Left lift and hold | Return to approach target; hold two seconds |
| Right receiver point | Actual bar centre plus actual bar rotation applied to local `(0.075,0,0)`, then add world `(0,0,0.013)` |
| Right approach | Receiver point plus `(0,0,0.022)` |
| Right close | Receiver point, close to `-0.1` rad; both hold two seconds |
| Left release | Open to `0.8` rad |
| Left retreat | `(-0.09,-0.04,0.47)` metres |
| Receiver-only hold | Keep right actuator targets for two seconds |

The receiver target is privileged simulator truth, sampled once after the left
hold. It is never proposed as an operating visual-policy input. Nominal receiver
target was `(0.06718735, -0.02093456, 0.44282473)` metres. Per-physics-step checks
reject any contacts except bar–workbench and bar–finger contacts; they also reject
contact overlap exceeding 2.5 mm. A separate kinematic scratch-data path check
samples at most 0.02 rad between joint waypoints.

## Results and limitations

Attempts 07 and 09 each ran 31.5 simulation seconds (6,300 physics samples):

- 400/400 left-only airborne bilateral-grasp samples during the initial hold.
- 400/400 airborne bilateral-grasp samples from **both** arms during shared hold.
- 400/400 receiver-only airborne bilateral-grasp samples after left retreat:
  left jaw forces exactly zero, right jaw forces above 0.01 N, no table support.
- No forbidden contact samples; maximum overlap **1.806 mm**.
- Final receiver-only object-centre height **0.42942 m**, minimum in that hold.
- Object sag during the two-second receiver-only hold was **1.519 mm**.

The final bar centre is about 38.4 mm above its reset height. A successful
handoff does not imply a four-centimetre-height gate was met throughout. The
slow sag is a reliability issue for longer holds and later placement. Gripping
forces around 38 N arise from the preserved upstream position-controller setup;
this is not hardware grasp-force validation. These are repeated identical
nominal trials, not independent seeds or a robustness success rate.

The prototype labels a completed control loop `completed`; the independent
`summary.json` sample checks establish the stronger receiver-only claim. In
particular, attempt 06 completed its loop but **failed** receiver-only ownership.
Integration must make that distinction an explicit outcome gate before continuing.

## All attempted physical runs

| Attempt | Outcome and change |
|---|---|
| 01 | Free-roll IK, default bar contact parameters. Bar sagged/rotated; right jaws missed. Left release exceeded the 2.5 mm overlap bound. |
| 02 | Fixed-roll IK and higher object friction at priority zero. Right missed; left release exceeded overlap bound. |
| 03 | Added six-dimensional contact; higher-priority stock finger settings still dominated. Same failure class. |
| 04 | Object priority raised to one. Mixed contact softness produced 2.516 mm overlap during left close; stopped. |
| 05 | Matched object contact softness to stock finger setting. Both arms gripped; left retreat was rejected for predicted self-collision. |
| 06 | Retreat `(-0.09,0,0.47)`. Loop finished, but left fixed jaw still supported bar; receiver-only handoff rejected by independent summary. |
| 07 | Retreat moved to `(-0.09,-0.04,0.47)`. Receiver-only hold passed 400/400 samples. |
| 08 | Same physics, rendering requested inside sandbox. CoreGraphics connection failed after 40 physics samples; retained. |
| 09 | Same physics, native graphics access available. Same successful receiver-only measurements and three-camera replay. |

Next: integrate a reusable fixed-roll teacher interface, explicit hand-off ownership
stages and scoring, cancellation/fault cases, immutable run evidence, and bounded
placement after receipt. Keep this practice bar distinct from the eventual dinner
utensil geometry.

## Integrated teacher follow-up

The tested sequence is now implemented in `src/bimanual/handoff.py` with
`HandoffConfig` and `run_handoff`. The [walkthrough](../HANDOFF.md) explains its
scope and local command. These changes add sealed evidence-store runs,
source/mapping/asset provenance, operating-observation versus scoring-truth
separation, explicit stage ownership checks, and failure gates before the donor
opens. All three ownership phases require 400 consecutive physics samples;
the full transfer after donor ownership must stay airborne. The final success
flag is false on any late recording or interruption failure.

Retained integrated attempts (all from the evolving working tree, not clean Git
checkpoints):

| Run | Evidence |
|---|---|
| `20260910T210320-b5ecc858e272` | Failed at 23.15 simulation seconds because exact floating-point equality in the parked-arm guard rejected interpolation roundoff. Partial observations/contact trace sealed. Guard now allows only 1e-12 rad numerical roundoff. |
| `20260910T210331-bb9dbbca6504` | Completed no-render transfer, same 400/400 phase outcomes and 1.806 mm overlap. |
| `20260910T210502-0b02ebe46b9f` | Completed rendered transfer, manifest verified. 31.5 simulated seconds, 14.002 wall seconds including 5 Hz three-camera replay. Same 400/400 ownership phases, no forbidden contacts and 1.519 mm receiver sag. |

Subsequent scoring hardening also rejects a table touch between hold phases,
non-contiguous phase timestamps and unknown movement stages. Thirteen targeted
tests pass: exported contact-only scene, nominal independent scoring, truth-field
separation, false-support/one-jaw/timing/collision negative controls, missing bar,
receiver-not-closing with donor-release prevention, bounded fixed-roll IK without
live-state edits, arm-ownership/penetration guards, and interrupted-run sealing.
Ruff passes for the new module and tests. The parent integration is responsible
for full-repository checks, CLI/portal wiring and clean-checkpoint release evidence.
