# Recorded planner sensor profiles

The planner can use genuine higher-resolution overhead images without changing
ACT's existing three-camera 480×270 observation contract. This module only
reconstructs **recorded reset observations**. It provides no live capture or action
authority, and improved image detail is not evidence of improved model quality.

## Interfaces

`bimanual.planner_sensors.create_sensor_bundle(recording, *, profile, store,
project_root)` creates a new sealed `Manifest` with kind `planner_sensor_bundle`.
Relative recording paths resolve against `project_root`. Supported profiles are:

| Profile | Overhead | Left wrist | Right wrist |
|---|---|---|---|
| `overhead960_wrist480_v1` | 960×540 | 480×270 | 480×270 |
| `overhead1920_wrist480_v1` | 1920×1080 | 480×270 | 480×270 |

`load_sensor_bundle(bundle_root, *, observation, source_run_id,
source_manifest_sha256)` returns the three RGB PIL images in overhead, left-wrist,
right-wrist order. The source hash argument is the verified source
`Manifest.manifest_sha256`: the canonical seal payload hash, **not** the SHA-256
of the JSON file. The copied manifest's file digest is preserved separately.

The immutable `SensorBundle` in `sensor-bundle.json` contains `profile`, the exact
canonical full `Observation` hash, source run/seal identity, image dimensions and
hashes, calibration artifact identity and source scene hash. It explicitly states
`mode="recorded_reset_only"` and `live_dispatch_authorized=false`. Capture start
and end times describe this replay render, not a new live robot observation.

The loader verifies the complete outer seal, copied original source seal and
selected source files, observation equality, recorded scene/config/controller
lineage, reset-state digest, calibration identity and actual PNG mode/dimensions.
Changing the episode, instruction revision, timestamps, measured joints, image
references or source seal invalidates the link. Returned values are RGB images
only. Preserved XML, calibration and source evidence must not be supplied as
additional model context; they are independent reproduction evidence.

## Local commands

After the [native setup](SETUP.md), create a recorded reset source and render a
sensor bundle using its reported run ID:

```sh
.venv/bin/bimanual grasp --record-demo
.venv/bin/bimanual planner-sensors \
  --recording .artifacts/runs/SOURCE_RUN_ID \
  --profile overhead960_wrist480_v1
```

Replace `SOURCE_RUN_ID` with the recording ID printed by the first command.
For 1080p use `overhead1920_wrist480_v1`. Each invocation creates a new evidence
run; retain its printed bundle ID. The render needs a working offscreen graphics
context. It does not need the reasoning environment or any model weights.

Once the existing [local Qwen setup](PLANNER.md) is ready, use the matching source
and bundle IDs for a recorded-only planner probe:

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 .artifacts/reasoning-venv/bin/bimanual planner-probe \
  --model-root .artifacts/models/qwen3-vl-4b-instruct \
  --recording .artifacts/runs/SOURCE_RUN_ID \
  --sensor-bundle .artifacts/runs/SENSOR_BUNDLE_RUN_ID \
  --frame 0 --device mps --instruction 'Pick up the practice block.'
```

The source ID must be exactly the bundle's source; another episode or frame is
rejected. Existing local IDs in the evidence table below can be used when those
artifacts are present. They are not distributed with the repository. A probe
consumes local compute and records its result; it still does not execute an action.

## Reconstruction boundary

Only the first episode observation with sequence zero and simulation time zero
is accepted. The scene initializes free objects; the renderer restores recorded
robot joint state and reset actuator targets. It never changes object positions,
steps physics, changes geometry, adjusts camera optics, attaches objects or
applies object forces.

All three 480×270 baseline renders must be pixel-identical to the original sealed
RGB images before any higher-resolution view is rendered. Only framebuffer
capacity changes. The overhead image is then rendered at the chosen native
resolution; wrist images retain the verified baseline pixels. No interpolation,
crop, overlay, segmentation, target box or simulator object pose becomes model
input. Hashes confirm qpos, qvel, actuator targets and simulation time remain
unchanged. Camera calibration is checked again after rendering.

This strict pixel check can reject a different renderer or software version even
when its view is visually similar. Such a mismatch is a retained failure, not a
reason to silently relax validation. Arbitrary recorded frames cannot be rebuilt
from policy observations alone; this API does not pretend otherwise.

Failures and keyboard interruptions are sealed with their error and available
artifacts. Successful bundles preserve original scene XML, mesh assets, SO-101
license, upstream record, config, controller, episode manifest, selected original
frames, source manifest, and the sensor implementation snapshot. Original runs
are verified before and after capture and remain unchanged.

## Verification evidence

Eighteen ordinary tests in [test_planner_sensors.py](../tests/test_planner_sensors.py)
exercise both profiles, immutable contracts, complete observation/source binding,
re-sealed invalid calibration or image content, ordinary corruption, baseline
mismatches, reset-state mutation, interruption, unsupported profiles and the
planner's copied-bundle integration. Their mock renderer fixtures verify lifecycle
behavior; they are not real image evidence. One additional render-marked test
creates a genuinely rendered reset bundle and passes it through that same planner
copy/load path with a stub planner; it passes without loading model weights.

Four actual native MuJoCo captures were created and loaded successfully:

| Source | Profile | Sealed bundle run |
|---|---|---|
| Nominal `20260910T210237-50fcd0cc7d99` | overhead 960 | `20260910T230311-bd2900475d32` |
| Same nominal reset | overhead 1920 | `20260910T230312-e3420adfd0d3` |
| Missing `20260910T223829-5df5f39f2e88` | overhead 960 | `20260910T230313-9ef6c518b351` |
| Same missing reset | overhead 1920 | `20260910T230314-5b45c35c1c32` |

These local bundles are under `.artifacts/runs/`. Every baseline matched exactly;
state remained unchanged; loader and evidence verification passed. A subsequent
explicit episode-lineage consistency check was also applied when reloading all
four preserved bundles. No Qwen model was loaded for these checks, and no action
was dispatched.

The preceding `.artifacts/camera-resolution-diagnostic/` measured the nominal
block's overhead footprint as 5×5 pixels at 480×270, 10×10 at 960×540 and 20×18 at
1920×1080. The left wrist sees a clipped corner; the right wrist sees none. More
pixels improve detail but cannot recover missing field of view. Both resolutions
remain development candidates. Planner integration must record actual processor
image grids, token count, latency and memory; a higher-resolution PNG alone does
not establish that the model received extra detail or recognized the target.

The existing [planner](PLANNER.md), [supervisor](SUPERVISOR.md) and
[policy interfaces](INTERFACES.md) retain their separate roles. This replay bundle
must never bypass live observation freshness or supply policy observations with
simulator truth.
