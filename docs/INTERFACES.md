# Observation, action and demonstration interfaces

The version-1 contracts live in `src/bimanual/contracts.py`. They establish a
validated interchange format for upcoming policy and dataset adapters. The
[existing simulator](DUAL_ARM_FOUNDATION.md) still returns its original in-memory
observation dictionaries. `src/bimanual/demonstrations.py` supplies a recording
adapter for those dictionaries; no trained policy, LeRobot export or deployed
action consumer is claimed. M2 still requires M1 and actual task data.

## Common rules

Records are immutable Pydantic models, reject unknown fields, and carry
`schema_version: 1`. Arrays are immutable tuples in Python and arrays in JSON.
Floating-point measurements must be finite; strings and booleans are not accepted
as numeric measurements. Counts are nonnegative integers. Units are explicit in
field names; all positions and joint targets are **radians**, velocities are
**radians per second**, and simulation time is **seconds**. Joint target values are
absolute actuator targets, not velocities or deltas. No normalization is applied.

The twelve joints are ordered left arm first, then right arm, with each arm using:
`shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`.
Names include the `left/` or `right/` prefix. `JointLimits` must be constructed from
the loaded scene's intersection of physical joint and actuator control ranges.
These limits cannot be inferred from an arbitrary checkpoint.

Camera order is exactly `overhead`, `left/wrist_cam`, `right/wrist_cam`. Each image
is a lossless **480 × 270 RGB PNG**, interpreted as height × width × 3 uint8 when
decoded. Training-specific resizing or normalization belongs in a separately
versioned model configuration; these records contain original sensor pixels.

## Policy-facing observations

`Observation` contains episode identity, instruction revision, sequence, simulation
time, capture time, twelve joint positions and velocities, and three `CameraFrame`
records. Each frame references an `Artifact` with a relative path and SHA-256.
All three frame identities/timestamps must match the observation. This describes
three renderings of the same paused simulation state, not three hardware camera
clocks synchronized after capture.

Monotonic nanoseconds are local to the capture worker's clock domain. They are for
freshness checks within that running worker; they are not UTC, portable timestamps
across machines, or proof that the pixels are current. A future live adapter must
render new pixels, stamp the observation at capture, and validate that its action
consumer shares that clock. Restart/reset requires a new episode identity.

The schema has **no exact object positions, contact truth, teacher waypoints or
success labels**. Those belong in separate scoring/training artifacts and must not
be inserted into policy observations. `extra="forbid"` rejects such fields; it does
not itself isolate processes or prevent an application from exposing the full scene.
The adapter and operating policy still need explicit truth-separation tests.

## Action chunks and instruction changes

`ActionChunk` contains 1–100 twelve-joint target vectors at 20 Hz, the source
observation identity/capture time, instruction revision, policy SHA-256, generation
time and expiry. `validate_for(...)` checks the whole chunk before enqueueing:

- Episode, instruction revision, observation sequence and capture time agree.
- The expected policy artifact hash agrees.
- The current time is after generation and before expiry; observation age fits
  the caller's explicit maximum age.
- Every target is finite and inside supplied joint/actuator limits.

This validator is atomic because it does not mutate the simulator. It does not
implement a queue or cancellation. The future executor must clear its queue on
stop, reset or instruction change; recheck expiry/active identity before every
consumed action; and continue per-physics-step collision checks. It must never
replace validation failure with clipping or silently execute a different policy.
An instruction change requires a new revision and fresh observation; changing
instruction text in the middle of a demonstration requires a new episode record.

## Supported skill requests

`SkillRequest` validates planner proposals for `open_drawer`, `pick`, `place`,
`handoff`, `stop` and `clarify`. It rejects unknown skills, unsupported object names,
world coordinates and incompatible arguments. A hand-off requires both arms and
an explicit receiving gripper. Stop/clarify cannot carry manipulation arguments.
Targets are drawer, spoon, fork, plate, cup and the practice block; destinations
are table, drawer, or the receiving gripper where the skill permits it.

These names describe the planned interface, **not currently implemented skills**.
The future supervisor must additionally check available skills, actual scene
presence/reachability, prerequisites, ownership, instruction revision, and outcome.
The `explanation` field is display text, never an executable instruction.

## Demonstration episodes and lineage

`DemonstrationEpisode` holds the instruction and revision, bounded action mapping,
ordered observations/actions, outcome reason and intervention count. Each
nonterminal frame's action is the command applied **after that observation**, to
reach the next observation. The final frame always has `action_rad: null`.
Sequences start at zero and are contiguous; captures increase monotonically and
simulation time advances by exactly 0.05 seconds (within numerical tolerance).
A one-frame failure is valid so failures before the first action remain recorded.
Such an episode supplies zero training transitions.

`EpisodeLineage` records Git revision, source digest, scene/config/controller file
references, controller kind, seed and train/validation/test split. Scripted teacher
and learned policy episodes remain distinct. Source digest is needed even when
the Git revision exists because a working tree may be dirty. Dataset/checkpoint
manifests must later bind all these episode records and preprocessing settings.
The schema validates digest syntax; external integrity requires verification.

Before ingestion, call `validate_episode_artifacts(episode, root)` to verify each
referenced file's SHA-256 and fully decode every camera image as RGB PNG. Paths
must be canonical relative paths, and resolved symlinks may not escape the root.
The verifier checks the referenced scene file, not its transitive mesh assets;
continue using the existing self-contained scene bundle/provenance verification.
Call `validate_split_seeds(episodes)` across the **entire candidate collection** to
reject duplicated episode IDs and seeds reused across different splits. Calling it
separately on each split would miss leakage. Distinct seeds alone do not prove that
scenes, instructions or assets are sufficiently different for generalization.

Outcomes and interventions are retained regardless of success. An outcome string
is an evaluator's reported result; neither schema validation nor image integrity
proves physical manipulation success. Independent contact/release scoring, frozen
seed manifests, full attempted-episode accounting and trained-policy evaluation
remain required. Failed records must never disappear from run history even when
a later explicit dataset filter excludes them from imitation-learning examples.

## Verification and integration order

Run `.venv/bin/pytest tests/test_contracts.py -q` after the native environment
checks described in [setup](SETUP.md). Tests exercise malformed numeric values,
stale action identity and expiry, camera alignment, whole-chunk limit rejection,
planner argument constraints, artifact corruption/escape, terminal observations,
failed episodes and cross-split seed leakage.

`DemonstrationRecorder(root, instruction=..., instruction_revision=...,
lineage=..., joint_limits=...)` writes inside an existing, unsealed evidence
directory. `root` must contain the scene, config and controller artifacts referenced
by `EpisodeLineage`; their hashes are verified on finalization. A recording refuses
to overwrite an existing `demonstration/frames` directory.

Capture `before = env.observe(render=True)`, execute the step, then call
`recorder.record(before, action)` after confirming that the step completed. At the
end call `recorder.record(env.observe(render=True), None)` and
`recorder.finalize(outcome=..., outcome_reason=..., interventions=...)`. The returned
path is `demonstration/episode.json`. Finalization validates timestamps, image files
and lineage. The caller then seals the containing evidence bundle.

The recorder copies camera pixels and joint values into immutable records/files. It
rejects non-RGB data, missing cameras, unrecognized observation fields, episode
changes and skipped or partially completed control steps. A partial failed physics
step must remain in the caller's ordinary failure evidence; it cannot be made into
a complete training transition by inventing timestamps. A failure before the first
action can be recorded with one terminal observation. If collection is interrupted
before finalization, the incomplete image directory remains for diagnosis and must
not be counted as a complete episode.

`require_successful_training_episode(episode)` provides an explicit success-only
intake check: train split, successful reported outcome, zero interventions and at
least one confirmed transition. It does not verify physical success, discard
failed evidence, establish train/validation separation, or replace the collection-
wide artifact/seed checks above.

Run `.venv/bin/pytest tests/test_contracts.py tests/test_demonstrations.py -q` for
contract and recorder checks. Next wire recording into actual physical skill runs
with fresh images at every 20 Hz control observation and seal their lineage. The
existing replay GIF and decimated camera capture cannot substitute for these raw
images. After physical skills pass M1, add the LeRobot adapter, validate its
timestamps/channel mappings against these records, and only then train or export
a model. Contracts and a recorder alone do not complete M2.
