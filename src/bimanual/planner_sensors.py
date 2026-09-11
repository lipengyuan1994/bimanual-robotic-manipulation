"""Versioned recorded-reset sensor views; never a live observation or action authority."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Literal

import mujoco
import numpy as np
from PIL import Image
from pydantic import Field, model_validator

from bimanual.contracts import (
    Artifact,
    Contract,
    Counter,
    DemonstrationEpisode,
    Digest,
    Observation,
)
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance

Profile = Literal["overhead960_wrist480_v1", "overhead1920_wrist480_v1"]
PROFILES = {
    "overhead960_wrist480_v1": ((960, 540), (480, 270), (480, 270)),
    "overhead1920_wrist480_v1": ((1920, 1080), (480, 270), (480, 270)),
}


def observation_digest(observation: Observation) -> str:
    return hashlib.sha256(canonical(observation.model_dump(mode="json"))).hexdigest()


class SensorImage(Contract):
    camera: Literal["overhead", "left/wrist_cam", "right/wrist_cam"]
    width: int = Field(strict=True, gt=0)
    height: int = Field(strict=True, gt=0)
    encoding: Literal["rgb8_png"] = "rgb8_png"
    artifact: Artifact


class SensorBundle(Contract):
    profile: Profile
    mode: Literal["recorded_reset_only"] = "recorded_reset_only"
    live_dispatch_authorized: Literal[False] = False
    source_run_id: str = Field(min_length=1)
    source_manifest_sha256: Digest
    source_observation_sha256: Digest
    observation: Artifact
    source_manifest: Artifact
    source_scene_sha256: Digest
    calibration: Artifact
    reset_state_sha256: Digest
    baseline_pixels_identical: Literal[True]
    state_unchanged: Literal[True]
    capture_started_monotonic_ns: Counter
    capture_finished_monotonic_ns: Counter
    images: tuple[SensorImage, ...] = Field(min_length=3, max_length=3)
    source_copies: tuple[Artifact, ...]

    @model_validator(mode="after")
    def check_mapping(self):
        if tuple(frame.camera for frame in self.images) != CAMERAS:
            raise ValueError("Planner sensor camera order mismatch")
        if tuple((frame.width, frame.height) for frame in self.images) != PROFILES[self.profile]:
            raise ValueError("Planner sensor profile dimensions mismatch")
        if self.capture_finished_monotonic_ns < self.capture_started_monotonic_ns:
            raise ValueError("Invalid sensor capture interval")
        paths = [item.path for item in self.source_copies]
        if len(paths) != len(set(paths)) or any(not p.startswith("source/") for p in paths):
            raise ValueError("Invalid source copy mapping")
        return self


def _artifact(directory: Path, name: str) -> Artifact:
    return Artifact(path=name, sha256=digest_file(directory / name))


def _png(path: Path, dimensions: tuple[int, int]) -> Image.Image:
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode != "RGB" or image.size != dimensions:
            raise ValueError("Expected genuine RGB PNG with declared sensor dimensions")
        image.load()
        return image.copy()


def _reset_model(scene: Path, observation: Observation):
    if observation.sequence != 0 or observation.simulation_seconds != 0:
        raise ValueError("Only sequence-zero, time-zero reset observations can be reconstructed")
    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    joint_ids = np.array([model.joint(name).id for name in JOINT_ORDER])
    actuator_ids = np.array([model.actuator(name).id for name in JOINT_ORDER])
    data.qpos[model.jnt_qposadr[joint_ids]] = observation.joint_position_rad
    data.qvel[model.jnt_dofadr[joint_ids]] = observation.joint_velocity_rad_s
    data.ctrl[actuator_ids] = observation.joint_position_rad
    mujoco.mj_forward(model, data)
    return model, data


def _state_digest(data) -> str:
    values = (data.qpos, data.qvel, data.ctrl, np.array([data.time]))
    return hashlib.sha256(b"".join(value.tobytes() for value in values)).hexdigest()


def _calibration(model, data) -> dict:
    # Camera transforms, not object poses. Evidence only; never passed to the model.
    return {
        "schema_version": 1,
        "cameras": [
            {
                "camera": name,
                "fovy": model.cam_fovy[model.camera(name).id].tolist(),
                "intrinsic": model.cam_intrinsic[model.camera(name).id].tolist(),
                "sensor_size": model.cam_sensorsize[model.camera(name).id].tolist(),
                "resolution": model.cam_resolution[model.camera(name).id].tolist(),
                "position": data.cam_xpos[model.camera(name).id].tolist(),
                "rotation": data.cam_xmat[model.camera(name).id].tolist(),
            }
            for name in CAMERAS
        ],
    }


def _render(model, data, camera: str, dimensions: tuple[int, int]) -> Image.Image:
    width, height = dimensions
    with mujoco.Renderer(model, width=width, height=height) as renderer:
        renderer.update_scene(data, camera=camera)
        return Image.fromarray(renderer.render().copy())


def _source_names(source: Manifest, episode: DemonstrationEpisode) -> set[str]:
    if episode.lineage.scene.path != "scene.xml":
        raise ValueError("Recorded scene must be the preserved scene.xml")
    lineage = (episode.lineage.scene, episode.lineage.config, episode.lineage.controller)
    for artifact in lineage:
        if artifact.sha256 != source.files.get(artifact.path):
            raise ValueError("Recorded episode lineage disagrees with source manifest")
    return (
        {
            "scene.xml",
            "controller.json",
            "config.json",
            "LICENSE-SO101",
            "upstream.json",
            "demonstration/episode.json",
        }
        | {name for name in source.files if name.startswith("assets/")}
        | {frame.artifact.path for frame in episode.frames[0].observation.frames}
        | {artifact.path for artifact in lineage}
    )


def create_sensor_bundle(
    recording: Path, *, profile: str, store: EvidenceStore, project_root: Path
) -> Manifest:
    """Create an independently sealed reset replay; retain failures and interruptions."""
    project_root = project_root.resolve()
    recording = (project_root / recording).resolve()
    directory = store.new_run()
    source_at_start = provenance(project_root)
    shutil.copyfile(Path(__file__), directory / "planner-sensors-source.py")
    config = {"recording": str(recording), "profile": profile}
    metrics = {"live_dispatch_authorized": False, "manipulation_success": None}
    outcome = "failed"
    try:
        if profile not in PROFILES:
            raise ValueError("Unsupported planner sensor profile")
        source_store = EvidenceStore(recording.parent.parent)
        source = source_store.verify(recording.name)
        manifest_digest = digest_file(recording / "manifest.json")
        episode = DemonstrationEpisode.model_validate_json(
            (recording / "demonstration/episode.json").read_text()
        )
        if "demonstration/episode.json" not in source.files:
            raise ValueError("No sealed demonstration in source")
        observation = episode.frames[0].observation
        if observation.sequence != 0 or observation.simulation_seconds != 0:
            raise ValueError("Only sequence-zero, time-zero reset observations are supported")
        required = _source_names(source, episode)
        for name in sorted(required):
            if name not in source.files:
                raise ValueError(f"Missing sealed scene dependency: {name}")
            original = Artifact(path=name, sha256=source.files[name]).verify(recording)
            target = directory / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        shutil.copyfile(recording / "manifest.json", directory / "source-manifest.json")
        (directory / "observation.json").write_bytes(
            canonical(observation.model_dump(mode="json")) + b"\n"
        )
        model, data = _reset_model(directory / "source/scene.xml", observation)
        initial = _state_digest(data)
        calibration = _calibration(model, data)
        (directory / "calibration.json").write_bytes(canonical(calibration) + b"\n")
        model.vis.global_.offwidth, model.vis.global_.offheight = PROFILES[profile][0]
        began = time.monotonic_ns()
        # Validate ALL baseline cameras before rendering any higher-resolution image.
        baseline = []
        for camera, frame in zip(CAMERAS, observation.frames, strict=True):
            original = _png(frame.artifact.verify(directory / "source"), (480, 270))
            reconstructed = _render(model, data, camera, (480, 270))
            if not np.array_equal(np.asarray(original), np.asarray(reconstructed)):
                raise ValueError(f"Reset reconstruction is not pixel-identical: {camera}")
            if _state_digest(data) != initial:
                raise ValueError("Rendering changed reset state")
            baseline.append(reconstructed)
        images = []
        for index, (camera, dimensions) in enumerate(zip(CAMERAS, PROFILES[profile], strict=True)):
            image = _render(model, data, camera, dimensions) if index == 0 else baseline[index]
            name = f"images/{index}.png"
            (directory / "images").mkdir(exist_ok=True)
            image.save(directory / name)
            if _state_digest(data) != initial or _calibration(model, data) != calibration:
                raise ValueError("Rendering changed reset state or calibration")
            images.append(
                SensorImage(
                    camera=camera,
                    width=dimensions[0],
                    height=dimensions[1],
                    artifact=_artifact(directory, name),
                )
            )
        if digest_file(recording / "manifest.json") != manifest_digest:
            raise ValueError("Source manifest changed during capture")
        source_store.verify(recording.name)
        bundle = SensorBundle(
            profile=profile,
            source_run_id=source.run_id,
            source_manifest_sha256=source.manifest_sha256,
            source_observation_sha256=observation_digest(observation),
            observation=_artifact(directory, "observation.json"),
            source_manifest=_artifact(directory, "source-manifest.json"),
            source_scene_sha256=source.files["scene.xml"],
            calibration=_artifact(directory, "calibration.json"),
            reset_state_sha256=initial,
            baseline_pixels_identical=True,
            state_unchanged=True,
            capture_started_monotonic_ns=began,
            capture_finished_monotonic_ns=time.monotonic_ns(),
            images=tuple(images),
            source_copies=tuple(
                _artifact(directory, f"source/{name}") for name in sorted(required)
            ),
        )
        (directory / "sensor-bundle.json").write_text(bundle.model_dump_json(indent=2) + "\n")
        metrics.update(baseline_pixels_identical=True, state_unchanged=True)
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        (directory / "error.txt").write_text(traceback.format_exc())
    (directory / "metrics.json").write_bytes(canonical(metrics) + b"\n")
    return store.seal(
        directory,
        kind="planner_sensor_bundle",
        outcome=outcome,
        config=config,
        metrics=metrics,
        source=source_at_start,
        claims=[],
    )


def load_sensor_bundle(
    bundle_root: Path,
    *,
    observation: Observation,
    source_run_id: str,
    source_manifest_sha256: str,
) -> tuple[Image.Image, ...]:
    """Return RGB only after checking the sealed replay's exact source and calibration."""
    bundle_root = bundle_root.resolve()
    seal = EvidenceStore(bundle_root.parent.parent).verify(bundle_root.name)
    if seal.kind != "planner_sensor_bundle" or seal.outcome != "completed" or seal.claims:
        raise ValueError("Not a completed, non-authorizing planner sensor bundle")
    bundle = SensorBundle.model_validate_json((bundle_root / "sensor-bundle.json").read_text())
    if (bundle.source_run_id, bundle.source_manifest_sha256, bundle.source_observation_sha256) != (
        source_run_id,
        source_manifest_sha256,
        observation_digest(observation),
    ):
        raise ValueError("Planner sensor source observation or manifest identity mismatch")
    saved = Observation.model_validate_json(bundle.observation.verify(bundle_root).read_text())
    if saved != observation:
        raise ValueError("Saved sensor observation differs from requested observation")
    source = Manifest.model_validate_json(bundle.source_manifest.verify(bundle_root).read_text())
    if (
        source.run_id != source_run_id
        or source.manifest_sha256 != source_manifest_sha256
        or hashlib.sha256(canonical(source.model_dump(exclude={"manifest_sha256"}))).hexdigest()
        != source.manifest_sha256
    ):
        raise ValueError("Invalid original source manifest")
    copies = {item.path.removeprefix("source/"): item for item in bundle.source_copies}
    episode = DemonstrationEpisode.model_validate_json(
        (bundle_root / "source/demonstration/episode.json").read_text()
    )
    required = _source_names(source, episode)
    if set(copies) != required:
        raise ValueError("Missing or unexpected source evidence copies")
    for name, artifact in copies.items():
        if artifact.sha256 != source.files.get(name):
            raise ValueError("Copied evidence does not match source manifest")
        artifact.verify(bundle_root)
    if bundle.source_scene_sha256 != source.files["scene.xml"]:
        raise ValueError("Source scene identity mismatch")
    if episode.frames[0].observation != observation:
        raise ValueError("Source episode reset observation mismatch")
    model, data = _reset_model(bundle_root / "source/scene.xml", observation)
    if _state_digest(data) != bundle.reset_state_sha256:
        raise ValueError("Reconstructed reset state identity mismatch")
    expected = json.loads(bundle.calibration.verify(bundle_root).read_text())
    if _calibration(model, data) != expected:
        raise ValueError("Sensor camera calibration identity mismatch")
    return tuple(
        _png(frame.artifact.verify(bundle_root), (frame.width, frame.height))
        for frame in bundle.images
    )
