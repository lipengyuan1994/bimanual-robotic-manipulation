"""Lossless, synchronous episode recording; no teacher truth enters observations."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import TypeAdapter

from bimanual.contracts import (
    Artifact,
    CameraFrame,
    DemonstrationEpisode,
    DemonstrationFrame,
    EpisodeLineage,
    JointLimits,
    JointVector,
    Observation,
    validate_episode_artifacts,
)
from bimanual.dual_arm import CAMERAS, CONTROL_HZ, JOINT_ORDER

_OBSERVATION_FIELDS = {
    "schema_version",
    "episode_id",
    "sequence",
    "simulation_seconds",
    "observed_monotonic_ns",
    "joint_order",
    "joint_position_rad",
    "joint_velocity_rad_s",
    "rgb",
    "camera_order",
}


class DemonstrationRecorder:
    """Write one complete episode inside an existing, unsealed evidence directory.

    Capture before stepping; record that observation/action only after the step
    succeeds. Finally record the terminal observation with ``action_rad=None``.
    A partially applied failed step is not a complete 20 Hz training transition;
    retain it in the caller's failure evidence instead of changing its timestamps.
    """

    def __init__(
        self,
        root: Path,
        *,
        instruction: str,
        instruction_revision: int,
        lineage: EpisodeLineage,
        joint_limits: JointLimits,
    ):
        self.root = root.resolve(strict=True)
        self.instruction = instruction
        self.instruction_revision = instruction_revision
        self.lineage = lineage
        self.joint_limits = joint_limits
        self.frames: list[DemonstrationFrame] = []
        self.finalized = False
        self.image_root = self.root / "demonstration" / "frames"
        # Do not overwrite a prior recording, even if it was interrupted.
        self.image_root.mkdir(parents=True, exist_ok=False)

    def record(self, observation: dict, action_rad=None) -> None:
        if self.finalized or (self.frames and self.frames[-1].action_rad is None):
            raise ValueError("Demonstration has already terminated")
        if set(observation) != _OBSERVATION_FIELDS:
            raise ValueError("Unexpected simulator observation fields; teacher truth is forbidden")
        if observation["schema_version"] != 1:
            raise ValueError("Unsupported simulator observation schema")
        if tuple(observation["joint_order"]) != JOINT_ORDER:
            raise ValueError("Unexpected simulator joint order")
        if tuple(observation["camera_order"]) != CAMERAS or tuple(observation["rgb"]) != CAMERAS:
            raise ValueError("All three fresh cameras are required for demonstration recording")
        action = None
        if action_rad is not None:
            values = action_rad.tolist() if isinstance(action_rad, np.ndarray) else action_rad
            action = TypeAdapter(JointVector).validate_python(values)
            self.joint_limits.validate_targets(action)
        for camera in CAMERAS:
            pixels = observation["rgb"][camera]
            if (
                not isinstance(pixels, np.ndarray)
                or pixels.dtype != np.uint8
                or (pixels.shape != (270, 480, 3))
            ):
                raise ValueError("Expected fresh 270 x 480 x 3 uint8 RGB camera arrays")
        capture = {
            key: observation[key]
            for key in ("sequence", "simulation_seconds", "observed_monotonic_ns")
        }
        references = []
        for index, camera in enumerate(CAMERAS):
            relative = f"demonstration/frames/{len(self.frames):06d}-{index}.png"
            references.append(
                CameraFrame(
                    camera=camera, **capture, artifact=Artifact(path=relative, sha256="0" * 64)
                )
            )
        record = Observation(
            episode_id=observation["episode_id"],
            instruction_revision=self.instruction_revision,
            **capture,
            joint_order=tuple(observation["joint_order"]),
            joint_position_rad=np.asarray(observation["joint_position_rad"]).tolist(),
            joint_velocity_rad_s=np.asarray(observation["joint_velocity_rad_s"]).tolist(),
            frames=tuple(references),
        )
        if record.sequence != len(self.frames):
            raise ValueError("Recording must start at sequence zero without gaps")
        if self.frames:
            previous = self.frames[-1].observation
            if record.episode_id != previous.episode_id or (
                record.observed_monotonic_ns <= previous.observed_monotonic_ns
                or not math.isclose(
                    record.simulation_seconds - previous.simulation_seconds,
                    1 / CONTROL_HZ,
                    rel_tol=0,
                    abs_tol=1e-8,
                )
            ):
                raise ValueError("Recording episode/time discontinuity")
        stored = []
        for frame in references:
            target = self.root / frame.artifact.path
            with target.open("xb") as stream:
                Image.fromarray(observation["rgb"][frame.camera]).save(stream, format="PNG")
            stored.append(
                frame.model_copy(
                    update={
                        "artifact": Artifact(
                            path=frame.artifact.path,
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                        )
                    }
                )
            )
        record = record.model_copy(update={"frames": tuple(stored)})
        self.frames.append(DemonstrationFrame(observation=record, action_rad=action))

    def finalize(
        self,
        *,
        outcome: Literal["success", "failure", "cancelled"],
        outcome_reason: str,
        interventions: int = 0,
    ) -> Path:
        if self.finalized or not self.frames:
            raise ValueError("Empty or already finalized demonstration")
        episode = DemonstrationEpisode(
            episode_id=self.frames[0].observation.episode_id,
            instruction=self.instruction,
            instruction_revision=self.instruction_revision,
            lineage=self.lineage,
            joint_limits=self.joint_limits,
            outcome=outcome,
            outcome_reason=outcome_reason,
            interventions=interventions,
            frames=tuple(self.frames),
        )
        validate_episode_artifacts(episode, self.root)
        destination = self.root / "demonstration" / "episode.json"
        with destination.open("x") as stream:
            stream.write(episode.model_dump_json(indent=2) + "\n")
        self.finalized = True
        return destination


def require_successful_training_episode(episode: DemonstrationEpisode) -> None:
    """Apply explicit success-only ACT intake rules without deleting failed evidence."""
    if episode.lineage.split != "train":
        raise ValueError("Only training-split episodes may enter training intake")
    if episode.outcome != "success" or episode.interventions != 0:
        raise ValueError("Success-only intake rejects failed, cancelled or intervened episodes")
    if len(episode.frames) < 2:
        raise ValueError("Training requires at least one confirmed transition")
