# Dual-arm foundation: run and inspect

This is the first part of M1. Two SO-101 arms perform a small, bounded free-space
movement above a workbench. It does not yet open a drawer, grasp objects, execute
language, or run a learned policy. The complete M1 exit gate is still pending.

## Run

From the repository root after native bootstrap:

```sh
.venv/bin/bimanual sim --seconds 4
.venv/bin/bimanual sim --seconds 4 --no-render
.venv/bin/bimanual evidence verify RUN_ID
```

The existing read-only portal lists these runs and their replay. In the saved GIF,
panels are overhead, left wrist, right wrist. `camera-0.png` through `camera-2.png`
are initial images. `scene.xml` and bundled `assets/` reload without the checkout.
Use `.venv/bin/mjpython -m mujoco.viewer --mjcf=.artifacts/runs/RUN_ID/scene.xml`
to inspect the model interactively on macOS. That viewer loads the scene; the
recorded starting pose and actions are in `observations.jsonl`.

## Control and observation contract

`DualArm` in `src/bimanual/dual_arm.py` is synchronous and has one owner. Each
action is 12 raw position targets in radians: left followed by right, each ordered
shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper. No
normalization is applied. Check `mapping.json` for exact model addresses and bounds.

Targets must satisfy both physical joint limits and actuator limits. The upstream
wrist_roll actuator allows a slightly wider range than its joint; we use their
intersection, without editing the original model. Every channel retains upstream
gains, force limits, damping, inertia, and collision geometry.

One control step advances ten 0.005-second physics steps (20 Hz control / 200 Hz
physics). Episode and sequence must match; invalid shape, NaN/Inf, illegal targets,
replayed actions and actions after stop are rejected. Reset creates a new episode.
Stop prohibits further stepping; there is no background action queue. This is not
the planned asynchronous supervisor or its full stale-wall-time/revision contract.
Targets are bounded, but general collision-free trajectory planning is not implemented.

Observations contain joint positions/velocities, episode/sequence, simulation time,
host monotonic time and ordered uint8 RGB images (270 high × 480 wide × 3). All
cameras render the same frozen physics state. No exact object poses or semantic
ground truth are in this observation. Instruction handling is reserved for M2.

The upstream wrist mount/intrinsics are retained, but optical axes are aimed at
the gripper site in local coordinates. The scene builder adds names, an overhead
camera, workbench and lighting. Our chosen reset pose faces the wrist cameras
toward the work surface. Base origins are ±0.28 m on world X and 0.385 m high;
the right base rotates 180 degrees about world Z. World Z is up; lengths are meters.

## What the evidence means

The foundation command fails on unexpected contact anywhere in its sampled
physics steps, while the low-level environment permits physical contacts for
future manipulation. Each arm's displacement check is tested separately. No
MuJoCo warnings or non-finite states are permitted. A completed foundation run
has `manipulation_success: null` and does not establish general collision safety.

Run timing separates setup, the physics/observation/render loop, and total time
through image encoding. Total excludes manifest sealing; the ratio uses loop
time only. Rendering is synchronous and may be slower than real time. All runs,
including exploratory contact cases and failures, remain in the evidence store.

## Five-minute exercise after lessons 1 and 2

Open `mapping.json` and the first two lines of `observations.jsonl` for your run.
How many target values are there? How much simulation time passes between rows?
Why does the final row have a null action? Which coordinate system describes a
wrist camera mount?

Answers: 12 targets; 0.05 seconds; the final row is the observation after the last
action with no subsequent action applied; the camera mount uses its parent body
frame, which moves with the arm. This exercise connects the lesson diagrams to
actual model state; reading the answers alone does not establish mastery.
