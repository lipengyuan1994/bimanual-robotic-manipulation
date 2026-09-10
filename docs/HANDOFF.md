# Contact-based hand-off between two arms

The scripted teacher transfers a **practice bar** from the left SO-101 to the
right SO-101 through real MuJoCo finger contacts. It is the next physical building
block after [grasping](CONTACT_GRASP.md). It does not understand dinner instructions
and has not learned a policy. A complete dinner-table workflow remains unfinished.

## Run and inspect

```bash
.venv/bin/bimanual handoff
.venv/bin/bimanual handoff --no-render
.venv/bin/bimanual handoff --fault skip-receiver-close --no-render
```

The command writes an independently verifiable run under `.artifacts/runs/`.
An incomplete or interrupted transfer retains its trace and receives no success
claim. The failure command deliberately leaves the receiver open: the teacher
must stop with the donor still closed instead of releasing an unsupported object.
Use `--fault missing-object` for the time-zero missing-bar check.

The experiment simulates 31.5 seconds. Rendering records overhead and two wrist
views at 5 Hz while controls run at 20 Hz and physics runs at 200 Hz. A run bundle
contains a self-contained scene with original mesh assets and license, mapping,
configuration, source provenance, control observations, independent contact truth,
and an optional three-camera replay. Run time and simulation time are separate.

## What counts as a hand-off

The sequence has three physical ownership checks, each covering all **400 physics
samples of a two-second hold**:

1. **Donor ownership:** both left jaws grip the airborne bar; right jaws exert no
   normal force, and the table does not support it.
2. **Shared ownership:** both jaws of both arms grip the airborne bar. Only after
   this check passes may the left arm open.
3. **Receiver ownership:** both right jaws grip the airborne bar after the left arm
   opens and retreats. Left jaw normal forces are zero and there is no table support.

For each hold, the bar centre must stay above 0.42 m, jaw support requires more
than 0.01 N normal force per jaw, and all required phases must appear in order in
a continuous 200 Hz truth trace. A single successful frame, a leftover donor
contact, or finishing the movement loop is insufficient.

The environment checks every physics step for unintended contacts and overlap
above 2.5 mm. After lift, table contact is forbidden. Planned joint paths are
sampled every at most 0.02 radians; this is discrete sampling, not a guarantee of
continuous collision clearance. Each movement phase controls its designated arm;
the other arm holds its existing actuator targets. Emergency stop and stale
sequence/episode rejection are inherited from the common simulation interface.

## The contact model and teacher

The bar is one 25 g free rigid body measuring 18 × 2 × 3.2 cm. It starts on the
workbench. There are no welded constraints, object actuators, gravity compensation,
or object position edits during the run. The maintained SO-101 model's dynamics,
limits and collision geometry remain intact.

The bar declares six-dimensional frictional contact, friction `1 .01 .002`,
contact priority `1`, and `solref=".01 1"`. These are simulation assumptions,
**not measurements of a particular material**. They matter: a long bar applies
torque to a grasp, and rolling resistance influences how quickly it sags. All
parameters are saved in the scene. Stock finger contact priority otherwise
supersedes lower-priority object friction settings.

The teacher holds each wrist roll at 1.57 radians and solves four arm joints for
a downward pinch at a requested XYZ point. Position tolerance is 0.1 mm and the
downward unit-axis tolerance is 0.001. Limits are enforced on the separate
kinematic scratch state, leaving live physics untouched. The receiver target is
computed from the bar's actual pose: this is explicitly privileged teacher
information. Operating observations contain joint/camera information and never
receive the independent object-pose/contact scoring fields.

## Evidence and remaining work

The [feasibility record](experiments/2026-09-10-handoff-feasibility.md) retains the
failed experiments that led to this sequence. The nominal transfer has zero
forbidden contacts and about 1.806 mm maximum overlap. The receiver-only hold
sags about 1.519 mm over two seconds, so a longer hold or a heavier/different
object is not yet validated. Repeat runs of the same scene are not independent
robustness trials. Holding this bar does not demonstrate spoon/fork transfer.

The current teacher stops after receiver ownership. Placement after transfer,
utensils, perturbed-scene validation, learned actions, visual task reasoning,
full workflow recovery and Intel execution remain separate checks. The run's
`handoff_success` describes this experiment; `manipulation_success` remains null
until full-task scoring exists.

## Five-minute exercise: who owns the object?

Open the independent truth trace, `scoring-truth.jsonl`, and find a row from each
hold phase. Compare `jaw_normal_force_n`, `table_contact`, and
`object_position_m`. These fields are for scoring and teacher analysis.

Suppose both receiver jaws report 20 N, the table has no contact, but the donor's
fixed jaw still reports 0.5 N. Has receiver-only hand-off completed?

**Answer:** no. The donor still supplies contact force. Opening its moving jaw
alone does not establish ownership transfer. The donor must retreat and remain
free of contact throughout the receiver-only hold. This was an actual failed
exploration attempt, retained in the experiment record.

Connect this to [Lesson 03: Contacts and grasping](../lessons/0003-contacts-grasps-handoffs.html)
and [Lesson 05: Reasoning and recovery](../lessons/0005-supervision-and-recovery.html).
This exercise is provided material; understanding is recorded separately when
you demonstrate it.
