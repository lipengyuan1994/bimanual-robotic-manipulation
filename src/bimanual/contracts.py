"""Versioned, fail-closed interchange records for future collection and policy adapters.

These records do not change the synchronous simulator interface. Image references
must be verified with ``validate_episode_artifacts`` before dataset ingestion.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bimanual.dual_arm import CAMERAS, CONTROL_HZ, JOINT_ORDER

Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
JointVector = Annotated[tuple[Finite, ...], Field(min_length=12, max_length=12)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=256)]
Counter = Annotated[int, Field(strict=True, ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class Artifact(Contract):
    path: str
    sha256: Digest

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or value == "."
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or ":" in value
            or path.as_posix() != value
        ):
            raise ValueError("Artifact path must be a canonical relative POSIX path")
        return value

    def verify(self, root: Path) -> Path:
        root = root.resolve(strict=True)
        target = (root / self.path).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("Artifact escapes the root or is not a file")
        if hashlib.sha256(target.read_bytes()).hexdigest() != self.sha256:
            raise ValueError(f"Artifact digest mismatch: {self.path}")
        return target


class CameraFrame(Contract):
    camera: Literal["overhead", "left/wrist_cam", "right/wrist_cam"]
    sequence: Counter
    simulation_seconds: Annotated[Finite, Field(ge=0)]
    observed_monotonic_ns: Counter
    width: Literal[480] = 480
    height: Literal[270] = 270
    encoding: Literal["rgb8_png"] = "rgb8_png"
    artifact: Artifact


class Observation(Contract):
    episode_id: Identifier
    instruction_revision: Counter
    sequence: Counter
    simulation_seconds: Annotated[Finite, Field(ge=0)]
    observed_monotonic_ns: Counter
    joint_order: tuple[str, ...] = JOINT_ORDER
    joint_position_rad: JointVector
    joint_velocity_rad_s: JointVector
    frames: Annotated[tuple[CameraFrame, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def mapping_and_capture(self) -> Self:
        if self.joint_order != JOINT_ORDER:
            raise ValueError("Unexpected joint order")
        if tuple(frame.camera for frame in self.frames) != CAMERAS:
            raise ValueError("Camera order must be overhead, left wrist, right wrist")
        for frame in self.frames:
            if (frame.sequence, frame.simulation_seconds, frame.observed_monotonic_ns) != (
                self.sequence,
                self.simulation_seconds,
                self.observed_monotonic_ns,
            ):
                raise ValueError("Stale or unsynchronized camera frame")
        return self


class JointLimits(Contract):
    lower_rad: JointVector
    upper_rad: JointVector

    @model_validator(mode="after")
    def nonempty_ranges(self) -> Self:
        if any(lo >= hi for lo, hi in zip(self.lower_rad, self.upper_rad, strict=True)):
            raise ValueError("Empty joint range")
        return self

    def validate_targets(self, targets: JointVector) -> None:
        if any(
            value < lo or value > hi
            for value, lo, hi in zip(targets, self.lower_rad, self.upper_rad, strict=True)
        ):
            raise ValueError("Action exceeds joint/actuator bounds")


class ActionChunk(Contract):
    episode_id: Identifier
    instruction_revision: Counter
    observation_sequence: Counter
    observed_monotonic_ns: Counter
    generated_monotonic_ns: Counter
    expires_monotonic_ns: Counter
    control_hz: Literal[20] = CONTROL_HZ
    joint_order: tuple[str, ...] = JOINT_ORDER
    policy_sha256: Digest
    targets_rad: Annotated[tuple[JointVector, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def timing_and_mapping(self) -> Self:
        if self.joint_order != JOINT_ORDER:
            raise ValueError("Unexpected joint order")
        if not (
            self.observed_monotonic_ns <= self.generated_monotonic_ns < self.expires_monotonic_ns
        ):
            raise ValueError("Invalid action time interval")
        return self

    def validate_for(
        self,
        observation: Observation,
        limits: JointLimits,
        *,
        now_monotonic_ns: int,
        max_observation_age_ns: int,
        expected_policy_sha256: str,
    ) -> None:
        """Validate the whole chunk before enqueueing; executors must recheck expiry."""
        if (
            self.episode_id,
            self.instruction_revision,
            self.observation_sequence,
            self.observed_monotonic_ns,
        ) != (
            observation.episode_id,
            observation.instruction_revision,
            observation.sequence,
            observation.observed_monotonic_ns,
        ):
            raise ValueError("Stale action identity")
        if self.policy_sha256 != expected_policy_sha256:
            raise ValueError("Incompatible policy artifact")
        if (
            max_observation_age_ns <= 0
            or not (self.generated_monotonic_ns <= now_monotonic_ns < self.expires_monotonic_ns)
            or now_monotonic_ns - observation.observed_monotonic_ns > max_observation_age_ns
        ):
            raise ValueError("Expired action or stale observation")
        for target in self.targets_rad:
            limits.validate_targets(target)


class SkillRequest(Contract):
    episode_id: Identifier
    instruction_revision: Counter
    observation_sequence: Counter
    skill: Literal["open_drawer", "pick", "place", "handoff", "stop", "clarify"]
    arm: Literal["left", "right", "both", "none"]
    target: Literal["drawer", "spoon", "fork", "plate", "cup", "practice_block"] | None = None
    destination: Literal["table", "drawer", "left_gripper", "right_gripper"] | None = None
    explanation: Annotated[str, Field(min_length=1, max_length=2048)]

    @model_validator(mode="after")
    def supported_arguments(self) -> Self:
        if self.skill in ("stop", "clarify"):
            if self.arm != "none" or self.target is not None or self.destination is not None:
                raise ValueError("Stop/clarify cannot include manipulation arguments")
        elif self.skill == "handoff":
            if (
                self.arm != "both"
                or self.target in (None, "drawer")
                or self.destination not in ("left_gripper", "right_gripper")
            ):
                raise ValueError("Hand-off requires both arms, an object and receiving gripper")
        elif self.arm not in ("left", "right"):
            raise ValueError("This skill requires one arm")
        elif self.skill == "open_drawer":
            if self.target != "drawer" or self.destination is not None:
                raise ValueError("Open drawer requires drawer target only")
        elif self.target in (None, "drawer"):
            raise ValueError("Pick/place requires a movable object")
        elif self.skill == "place" and self.destination not in ("table", "drawer"):
            raise ValueError("Placement requires table or drawer destination")
        elif self.skill == "pick" and self.destination is not None:
            raise ValueError("Pick does not accept a destination")
        return self


class EpisodeLineage(Contract):
    code_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    source_sha256: Digest
    scene: Artifact
    config: Artifact
    controller: Artifact
    controller_kind: Literal["scripted_teacher", "learned_policy"]
    seed: Counter
    split: Literal["train", "validation", "test"]


class DemonstrationFrame(Contract):
    observation: Observation
    action_rad: JointVector | None


class DemonstrationEpisode(Contract):
    episode_id: Identifier
    instruction: Annotated[str, Field(min_length=1, max_length=4096)]
    instruction_revision: Counter
    lineage: EpisodeLineage
    joint_limits: JointLimits
    outcome: Literal["success", "failure", "cancelled"]
    outcome_reason: Annotated[str, Field(min_length=1, max_length=4096)]
    interventions: Counter
    frames: Annotated[tuple[DemonstrationFrame, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def aligned_transitions(self) -> Self:
        previous = None
        for index, frame in enumerate(self.frames):
            observation = frame.observation
            if (observation.episode_id, observation.instruction_revision, observation.sequence) != (
                self.episode_id,
                self.instruction_revision,
                index,
            ):
                raise ValueError("Episode identity or sequence discontinuity")
            if previous is not None and (
                observation.observed_monotonic_ns <= previous.observed_monotonic_ns
                or not math.isclose(
                    observation.simulation_seconds - previous.simulation_seconds,
                    1 / CONTROL_HZ,
                    rel_tol=0,
                    abs_tol=1e-8,
                )
            ):
                raise ValueError("Episode capture time discontinuity")
            if index == len(self.frames) - 1:
                if frame.action_rad is not None:
                    raise ValueError("Terminal observation cannot carry an action")
            elif frame.action_rad is None:
                raise ValueError("Nonterminal observation requires an action")
            else:
                self.joint_limits.validate_targets(frame.action_rad)
            previous = observation
        return self


def validate_episode_artifacts(episode: DemonstrationEpisode, root: Path) -> None:
    """Verify external files; this proves integrity/format, not physical success."""
    for artifact in (episode.lineage.scene, episode.lineage.config, episode.lineage.controller):
        artifact.verify(root)
    for frame in episode.frames:
        for camera in frame.observation.frames:
            path = camera.artifact.verify(root)
            with Image.open(path) as image:
                if image.format != "PNG" or image.mode != "RGB" or image.size != (480, 270):
                    raise ValueError("Expected 480 x 270 RGB PNG camera artifact")
                image.load()


def validate_split_seeds(episodes: tuple[DemonstrationEpisode, ...]) -> None:
    """Reject reused seeds across splits and duplicated episode IDs."""
    owners: dict[int, str] = {}
    identities: set[str] = set()
    for episode in episodes:
        if episode.episode_id in identities:
            raise ValueError("Duplicate episode ID")
        identities.add(episode.episode_id)
        seed, split = episode.lineage.seed, episode.lineage.split
        if seed in owners and owners[seed] != split:
            raise ValueError("Seed leakage across dataset splits")
        owners[seed] = split
