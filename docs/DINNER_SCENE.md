# Combining the skills into one dinner scene

The individual drawer/utensil, plate, cup and practice-bar skills now have a first
successful continuous scripted-teacher baseline. This is one authored scene and
one episode, not learned execution or a production reliability result. The `dinner-teacher` command now packages the baseline; a three-camera reproduction
from clean committed source now passes.

An initial combined layout was checked using the existing authored scene elements:

- The ergonomic utensil drawer and its physical cabinet.
- The plate and source rack at `(.15,-.09)` metres.
- The mirrored right-arm cup at `(.136,.110)` metres.
- The practice hand-off bar centred at `(0,0)` metres.
- Both original SO-101 instances and all three cameras.

Sealed layout probe `20260910T220035-a5c40c643f17` advanced 1,000 consecutive
1 ms steps, with zero forbidden contacts and maximum overlap 0.0664 mm. All five
free objects ended below 0.01 m/s linear and 0.1 rad/s angular speed. Its local
bundle contains the combined scene/assets, exact probe script, source hashes,
contact trace and final positions/velocities. Earlier probe
`20260910T215759-120f72776ee9` checked contacts but did not explicitly gate final
object velocities; both remain recorded.

This proves only that the initial layout can be constructed and settle. It does
not prove motion clearance, reachability of the combined paths, success of any
skill in that cluttered scene, or a full workflow. In particular, the bar may
obstruct later utensil placement, and the plate skill uses a different right-arm
parking pose. These require actual guarded execution and coordination, not an
assumption that isolated successes automatically compose.

## First passing continuous teacher episode

Attempt 28 / scene profile `dinner_horizontal_release_v18` passed the independent
full audit. Sealed evidence run **`20260911T011032-a9fda4aee41f`** includes the
exact driver, action trace, compressed physics trace, all input teacher trajectories
and their original manifests, runtime source copies, self-contained scene/assets,
licenses and audit source/results. Its seal verifies and the copied scene loads
independently. The original scratch attempt and all preceding failures remain.

The sequence is hand-off and bar parking → cup → plate → drawer opening and
spoon/fork retrieval. There are no object resets, artificial attachments or direct
object forces during the episode. Earlier source trajectories supply teacher
joint commands; the combined run executes them again through actual continuous
physics rather than concatenating independent recordings.

| Final object | Declared XY target (m) | Final XY error |
|---|---|---|
| Spoon | (-0.12, 0.045) | 3.969 mm |
| Fork | (-0.06, 0.062) | 9.640 mm |
| Plate | (0.14, -0.015) | 13.555 mm |
| Cup | (0.066, 0.153) | 18.071 mm |
| Hand-off bar | (0.025, 0.21) | 5.996 mm |

All 240,950 physics samples are contiguous at 1 kHz. The audit verifies separate
donor/shared/receiver hand-off ownership, airborne transport, released drawer,
every required hold/placement interval, and 2,000 final samples with all objects
placed. There are zero forbidden-contact samples or disturbances of previously
accepted placements. Maximum overlap is 1.831 mm. Cup and plate are released
flat/upright within the unchanged 20 mm position gate; utensils/bar use 25 mm.
The cup remains close to its tolerance, so this is not robustness evidence.

The final release change withdraws the jaw 120 mm west and 20 mm south at its
measured release height before lifting. This allows the tilted plate to settle
free of the jaw, while clearing the cup and cabinet. Destination and scoring
thresholds remained fixed through these release experiments. The north rack,
right-arm parking angle, geometry and calibration are explicitly preserved in
`layout-manifest.json`; this is a different declared layout from the initial
static probe above. See [every attempt](experiments/2026-09-10-dinner-sequence-feasibility.md).

The run took 240.95 simulated seconds and 124.26 wall seconds **without camera
rendering**. This timing includes teacher planning and audits and is not a live
camera/inference benchmark. There is no passing-run video yet. Earlier rendered
failed runs must not be presented as media for this successful attempt.

## Next integration checks

1. Package the passing controller and immutable scene/trajectory assets so a clean
   checkout can execute one explicit teacher command without historical `.artifacts`
   directories. Keep the actor and independent scorer separate.
2. Reproduce that command with camera rendering and verify the complete audit,
   cancellation and failure handling from the committed implementation.
3. Record synchronized demonstrations and skill boundaries from the validated
   continuous episode; do not turn decimated replay frames into training data.
4. Resolve the nominal learned-policy start failure, then train/integrate bounded
   dinner skills. Visual reasoning and recovery remain separate M2 exit checks.

The original scope remains in [PLAN](PLAN.md), with readiness gates in
[ROADMAP](ROADMAP.md). This teacher baseline does not establish the 10-seed
hackathon target, production reliability, or Intel compliance.

## Supported fixed-scene teacher command

Run `.venv/bin/bimanual dinner-teacher` for a camera replay, or add `--no-render`
for the physics-only baseline. The command runs 4,819 frozen IK-generated joint
targets over 240.95 simulated seconds. It reserves both arms for this one worker.
There is no language planner or learned policy in this command.

Versioned assets live in `src/bimanual/models/dinner_teacher_v1/`. Their manifest
binds the source evidence seal, source actions/driver and packaged bytes. The
wheel includes these assets; it can load the complete scene from outside the
repository without historical experiment folders. Both original robot licenses
and meshes are retained. Target units/order and camera order are explicit.

Execution validates the entire target plan against joint/actuator limits, checks
each control segment for collisions, and audits contacts at every 1 ms physics
step. The plan only contains joint targets and phases. Object states come from
fresh physics and are written solely for independent scoring. No object state
is replayed, reset, attached or forced into a successful result.

`dinner_scoring.py` streams the raw trace independently of the controller. It
checks complete 20 Hz action/1 kHz physics coverage, a single episode, required
holds, hand-off ownership, drawer opening, stable placements and retained prior
placements. Re-scoring preserved attempt 28 reproduces all original physical
metrics; attempt 22 still fails. Malformed and partial traces fail explicitly.
Cancellation before initialization and midway through a physics step produces a
sealed interrupted run with no success claim. A partial action is marked unapplied.

Camera replay is sampled at 2 Hz and labelled teacher / 5x playback. It is not a
20 Hz training dataset. Run artifacts contain scene/assets, runtime source,
actual actions, compressed physics, score and optional replay. Report simulation
time separately from actor wall time; the latter includes capture but excludes
post-run scoring and GIF encoding. This fixed layout establishes feasibility,
not robustness or completion of M2–M4.


Clean checkpoint `bc0b5c084affc4bfd06653a660af58f750cdc7c2` produced completed run
`20260911T013229-b7184e9ba66a`. Its seal verifies, all original physical metrics
match, and the 483-frame camera replay shows the actual continuous execution.
Actor/capture wall time is 147.90 seconds; simulated time is 240.95 seconds.

The first packaged trial, `20260911T012748-2d4a69c7807d`, had a passing physical
score but an outer failed outcome because the actor read an incorrect result-field
name. That run remains unchanged. The corrected clean run establishes command
completion; no earlier failed video is substituted.

## Repaired recipe v2

Use `bimanual dinner-teacher --recipe v2` to select the separately packaged repair.
The default remains v1 while the new recording and skill boundaries are validated.
V2 preserves the same scene/layout bytes and all targets outside the repaired
section. Its 5,049 targets come from physical run `20260911T112302-2cba6a2aa0ac`,
independently rescored as `20260911T112722-fd2f1119487f`.

V2 adds ten bar-settling controls, a staged plate release and a checked return.
The last 40 return-hold controls are labeled `plate/settled`; target values remain
identical to the verified source. Version 2 adds explicit `path_start` and
`arm_object_contacts` fields. The former selects measured joints or previous
command for collision checking; the latter can only retain normal phase permissions
or restrict all arm/object contacts. It cannot widen them. Missing/unknown fields
are rejected. The post-release return uses measured joints and forbids arm/object
contact, as in the physical trial.

The supported v2 command requires both the existing stage audit and the independent
stage-free dinner scorer to pass. All new teacher runs record explicit partial-action
timing and retain their source-inspected instrumentation declaration. Those
counter declarations are not a detector for arbitrary unlogged simulator changes.

Capture the full-rate dataset separately from the replay:

```sh
.venv/bin/bimanual dinner-teacher --recipe v2 --record-demonstration
```

Adding `--no-render` omits only the presentation replay; demonstration recording
still renders all three full-rate training cameras. Packaging/unit checks passed;
a clean supported recording and successor-boundary checks remain required before
adopting a replacement dataset. V1 assets and datasets remain unchanged.


The first v2 recording `20260911T113458-5a8697f744a0` is retained as **failed**:
5,049 actions, 5,050 observations and 15,150 camera images, zero forbidden contacts,
and passing independent task score. The stage audit rejected exactly one gate:
`plate/settled` had 3,000 successful samples instead of its prescribed 2,000.
The packaging correction labels only the final 40 controls as settled, leaving the
preceding 20 as retreat. Targets, timing, guards and scoring thresholds are unchanged.
A fresh recording is required; the failed source is not edited or exported as success.

The corrected clean recording **`20260911T114540-8b3b1ff0238d`**, checkpoint
`106f5ed`, passes both stage and independent audits: 5,049 applied controls,
252,450 physics samples, zero forbidden contacts, 5,050 observations and 15,150
RGB images. Its source seal is
`37ec8a70353517d668f4bc18cf8252c2067e2fe4db6b7d1060e1c43d782808ff`.
The failed predecessor remains immutable. This proves the supported teacher
recording in one authored scene; learned execution and successor readiness are
separate gates.
