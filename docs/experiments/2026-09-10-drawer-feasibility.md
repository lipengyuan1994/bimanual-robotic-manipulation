# Contact-driven drawer feasibility — September 10, 2026

Native ARM64 development on the M1 Pro continues M1. The experiment establishes
a scripted drawer-opening skill with stored utensil proxies. It does not prove
utensil extraction, dinner-task success, learned control, Intel compliance, or
production reliability.

## Scene and controls

A cabinet sits toward the front of the workbench: drawer origin
`(-0.02,-0.18,0.39)` metres. Fixed cabinet walls, floor and roof surround five
moving drawer panels. The passive slide axis is `(-1,0,0)`, nominal joint range
`[0,0.11]` metres, damping 1 N·s/m and friction loss 0.4 N. The drawer including
handle weighs 0.22 kg before its contents. Its rail is represented by the slide
constraint; actual rollers are not simulated.

Two independent free objects start at `(-0.08,-0.18,0.397)` (spoon) and
`(-0.05,-0.18,0.397)` (fork), oriented along world Y. Primitive collision geometry
approximates a shaft/bowl and a shaft/bridge/four tines. They move because of
contact with the drawer floor. After opening about 8.7 cm, both rows lie in front
of the cabinet roof; successful robot extraction remains untested.

The contact handle centre starts at `(-0.157,-0.18,0.40)`. The downward pinch
approach is `(-0.157,-0.18,0.47)`, grasp target
`(-0.157,-0.18,0.413)`, and pull target `(-0.247,-0.18,0.413)`.
The left gripper closes to `-0.1` rad, then opens to `0.8` rad after the held-open
check; retreat target is `(-0.247,-0.18,0.47)`. Right-arm targets remain parked.
The shared bounded teacher solves downward IK on separate kinematic state;
no simulator object/joint state is edited after reset.

There are twelve original robot actuators, no drawer or utensil actuators, no
weld/equality attachment, and no applied object force or gravity compensation.
Finger contacts with both knob and mounting stem are explicitly allowed. Other
robot/task contacts are rejected; utensil/drawer-interior contacts are allowed.
Every 5 ms physics sample is audited, alongside sampled joint-path collision
checks. Geometric overlap and passive-joint overtravel are bounded separately.

## All exploratory attempts

Scratch files live under `.artifacts/drawer-exploration/`. Results include failed
attempts; original scripts `drawer01.py` through `drawer03.py` preserve earlier
versions. The latest `drawer.py` reproduces attempt 04. Use a new output label.

| Attempt | Outcome |
|---|---|
| 01 | Original placement overlapped the left robot near its base. Initial path rejected `left/collision_or_visual_7` versus `drawer/left`; no motion executed. |
| 02 | Rotated cabinet into front workspace. Settling, approach and descent succeeded; closing path rejected mounting-stem contact because only the knob was allowed. |
| 03 | Explicitly classified knob and stem as handle assembly. Contact pull opened drawer about 85 mm, held for two seconds, with no forbidden contacts. No stored utensils or closed roof yet; therefore not accepted as complete drawer evidence. |
| 04 | Added closed cabinet roof and free spoon/fork proxies. Contact pull and hold succeeded, then release/retreat left drawer 87.381 mm open for two seconds with zero finger support. Contents remained on the drawer floor. |

## Integrated evidence

The sequence is implemented in `src/bimanual/drawer.py`; see
[the walkthrough](../DRAWER.md). Operating observations expose no drawer position,
contact force or utensil truth. Separate scoring requires 1,200 bilateral-grasp
pull samples, 400 stable gripped-open samples, 400 stable released-open samples,
retained utensil centres, proper phase order and continuous 200 Hz records.

Initial no-render integrated run `20260910T211309-87ddb942fa63` completed 24 seconds
of simulation in 1.159 wall seconds. The run bundle preserves its evolving
working-tree source lineage; it is not a clean-checkpoint release run.

Measurements: final opening **87.381 mm**, maximum contact overlap **0.925 mm**,
maximum passive closed-stop overtravel **0.731 mm**, zero forbidden contacts.
The right arm stayed parked. Both utensils remained in the moving drawer; centre
positions after release were approximately `(-0.1674,-0.18,0.3969)` and
`(-0.1376,-0.18,0.3968)` metres.

The preserved upstream position-controller geometry produces peak summed jaw
normal force around **143.5 N** during pull. This is not force-aware control or a
validated hardware load envelope. Stem contact and passive-rail constraints
create side loads that need improvement before stronger realism or hardware
claims. The contact and friction assumptions, rigid utensil proxies, ideal rail,
compliant stops and lack of perturbation testing remain explicit limitations.

Eighteen focused tests pass: contact-only exported scene and passive/free joints,
truth separation, actual opening and released hold, retained utensils, sample
count/timing/closing/support/grip/collision/limit negative controls, missing-handle
and skip-close stop-before-pull failures, initially closed and net-opening checks, ordered
contiguous pull/hold/release phases, terminal release, parked-arm/contact guards and interrupted
run sealing. Ruff passes for the new module and tests. Full-repository and clean
release checks belong to the parent integration.

Parent-rendered integrated run `20260910T211628-5b774988145f` also passed: 24
simulation seconds, 11.26 wall seconds, final opening 87.38 mm. Both rendered
and no-render runs use the same contact/control sequence. Scoring was subsequently
hardened to require an initially closed state (absolute opening no more than
1 mm), at least 8 cm net opening, consecutive pull timestamps and a terminal
released-open hold; negative controls cover false already-open and reordered traces.

Agent-rendered run `20260910T211520-32a13203c20a` completed and verified,
13.438 wall seconds including recording. Both rendered traces were independently
rescored with the hardened closed-start/net-travel/phase-order scorer and passed.
