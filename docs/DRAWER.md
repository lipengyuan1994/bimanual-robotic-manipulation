# Open a physical drawer in simulation

The left SO-101 grasps a drawer handle, pulls the drawer open, releases it, and
retreats. A spoon and fork remain inside the moving drawer. This is a scripted
physical skill; **retrieving the utensils and setting the table are not implemented
by this command**.

## Try it

```bash
.venv/bin/bimanual drawer
.venv/bin/bimanual drawer --no-render
.venv/bin/bimanual drawer --fault skip-close --no-render
.venv/bin/bimanual drawer --fault missing-handle --no-render
```

The two faults must stop before pulling and retain a failed run. The ordinary
command simulates 24 seconds and records overhead and wrist views at 5 Hz.
Physics remains 200 Hz and joint commands remain 20 Hz. Inspect the run's
`scoring-truth.jsonl` for drawer displacement, contact force, utensil position,
velocity, collision and overlap measurements. These fields are independent
scoring data, separate from operating camera/joint observations.

## What the scene represents

The cabinet has a floor, two sides, a back and an opaque roof. Inside it, a rigid
five-panel drawer travels along one **passive slide joint**. It has 11 cm of
nominal travel, damping 1 N·s/m and friction loss 0.4 N. These are declared
simulation assumptions, not measurements from a particular real drawer.

Only the twelve robot joint actuators are driven. The drawer has no motor,
welded attachment, external applied force, or runtime position edits. The slide
joint constrains the drawer like a simplified rail mechanism. It is not a model
of ball-bearing rollers, rail flexibility or drawer jamming.

The drawer's approximate 16.4 cm square interior contains two independent free
bodies: a spoon with a rounded bowl and a fork with four tines, each approximately
11–12 cm long. Their simplified rigid collision shapes test storage clearance;
they have not been validated for grasping. Gravity and contact friction keep them
on the moving drawer floor. A closed roof limits access; after opening, both
utensil rows are exposed in front of the roof. Tool access and extraction still
need separate physical tests.

The handle consists of a knob and its mounting stem. Both are allowed finger
contact surfaces. Contact with the drawer front, cabinet, workbench or the other
arm stops the run. Utensil contact with the drawer interior is allowed; robot-to-
utensil contact is outside this opening skill. The right arm remains parked.

## Acceptance checks

A successful run requires all of these, with no missing physics samples:

- The drawer starts closed (within 1 mm), and achieves at least 8 cm of net opening.
- Both left jaws grip the handle assembly throughout the six-second pull.
- The drawer stays at least **8 cm open** for two seconds while gripped.
- It then stays at least **8 cm open** for two seconds with zero finger support,
  after release and retreat. Drawer speed must remain below 1 cm/s.
- Both utensils remain in the drawer throughout the run. The ordered pull, held-open
  and released-open phases end with the released-open hold.
- No forbidden contacts, contact overlap over 2.5 mm, or slide-limit overtravel
  over 2.5 mm occur.

The slide uses MuJoCo's compliant joint limits. Nominal evidence includes about
0.73 mm of closed-stop overtravel during grip acquisition, which is recorded
explicitly. It is not a perfectly rigid zero-travel stop. Nominal final opening
is about **87.4 mm**, maximum contact overlap about **0.925 mm**.

Peak summed jaw normal force is about **144 N** in this geometry with unchanged
upstream position actuators. This skill has no force controller and is not a
validated low-force physical-robot technique. The mounting stem contacts and
passive rail constraints produce significant side loads; improving force-aware
approach and control is future work. Geometry and friction variation are also
untested. These results prove a nominal simulated opening, not production
reliability or hardware safety.

All runs retain scene assets and licenses, configuration, source provenance,
operating observations, separate truth traces, errors and optional replay. See the
[full attempt register](experiments/2026-09-10-drawer-feasibility.md).

## Five-minute exercise: what caused the drawer to move?

Find the first and last `pull` rows in the truth trace. Compare `opening_m` and
`jaw_normal_force_n`. Then inspect a `released_hold` row.

Why does the drawer stay open when jaw forces become zero?

**Answer:** a horizontal drawer does not automatically return to its starting
position. In this model, the passive slide's friction and damping oppose movement;
there is no return spring. Opening is retained by the drawer mechanics, rather
than an invisible attachment to the robot. A spring-loaded drawer would need a
different task strategy and acceptance test.

Connect this to [Lesson 03](../lessons/0003-contacts-grasps-handoffs.html) and
[Lesson 06](../lessons/0006-evaluation-and-uncertainty.html). Reading the answer is
not recorded as demonstrated mastery.
