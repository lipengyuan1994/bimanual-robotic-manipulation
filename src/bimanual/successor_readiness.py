"""Observed development transition readiness; reference postures never become actions."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from bimanual.contracts import DemonstrationEpisode, JointLimits, Observation
from bimanual.dinner_scoring import _airborne, _finite_tree, _number, _placed, _valid_row, _vector
from bimanual.evidence import canonical, digest_file
from bimanual.skill_outcomes import SkillOutcome
from bimanual.skill_views import load_skill_views

PROFILE = "dinner_successor_readiness_development_v1"
JOINT_TOLERANCE_RAD = 0.005
MAX_JOINT_SPEED_RAD_S = 0.02
REQUIRED_OBSERVATIONS = 10
_VERIFIED = object()
_PROTECTED = {
    "handoff_transfer": (),
    "bar_place_and_return": ("practice_object",),
    "cup_pick_place": ("practice_object", "cup"),
    "plate_pick_place": ("practice_object", "cup", "plate"),
    "drawer_open": ("practice_object", "cup", "plate"),
    "spoon_retrieve_place": ("practice_object", "cup", "plate", "spoon"),
    "fork_retrieve_place": ("practice_object", "cup", "plate", "spoon", "fork"),
}


@dataclass(frozen=True)
class SuccessorReference:
    skill_id: str
    successor_skill_id: str | None
    parent_episode_id: str
    export_manifest_sha256: str
    views_manifest_sha256: str
    views_file_sha256: str
    episode_file_sha256: str
    reference_frame: int
    reference_observation_sha256: str
    joint_position_rad: tuple[float, ...]
    joint_limits: JointLimits
    dataset_root: Path
    skill_views_path: Path
    final_parking: bool = False
    _verified: object = field(default=None, init=False, repr=False, compare=False)

    def report(self) -> dict:
        return {
            "profile": PROFILE,
            "skill_id": self.skill_id,
            "successor_skill_id": self.successor_skill_id,
            "final_parking": self.final_parking,
            "parent_episode_id": self.parent_episode_id,
            "export_manifest_sha256": self.export_manifest_sha256,
            "views_manifest_sha256": self.views_manifest_sha256,
            "views_file_sha256": self.views_file_sha256,
            "episode_file_sha256": self.episode_file_sha256,
            "reference_frame": self.reference_frame,
            "reference_observation_sha256": self.reference_observation_sha256,
            "joint_position_rad": list(self.joint_position_rad),
            "joint_limits": self.joint_limits.model_dump(mode="json"),
            "dataset_root": str(self.dataset_root),
            "skill_views_path": str(self.skill_views_path),
            "joint_tolerance_rad": JOINT_TOLERANCE_RAD,
            "max_joint_speed_rad_s": MAX_JOINT_SPEED_RAD_S,
            "required_new_observations": REQUIRED_OBSERVATIONS,
            "operating_action_target": False,
            "generalization_validated": False,
        }

    @property
    def reference_sha256(self) -> str:
        return hashlib.sha256(canonical(self.report())).hexdigest()

    def reverify(self) -> SuccessorReference:
        """Reverify before live capture; this reads source files and may take seconds."""
        current = load_successor_reference(
            self.dataset_root,
            self.skill_views_path,
            skill_id=self.skill_id,
            final_parking=self.final_parking,
        )
        if current != self or self._verified is not _VERIFIED:
            raise ValueError("Successor reference changed after verification")
        return current


def load_successor_reference(
    dataset_root: Path, skill_views_path: Path, *, skill_id: str, final_parking: bool = False
) -> SuccessorReference:
    """Verify immutable training lineage, then select measured observation joints only.

    The skill-view verifier audits its original source provenance. This reference
    derives no target from teacher actions, phases, inverse kinematics or object poses.
    """
    if type(final_parking) is not bool:
        raise ValueError("Final parking must be an explicit boolean")
    dataset_root, skill_views_path = Path(dataset_root).resolve(), Path(skill_views_path).resolve()
    views_file_digest = digest_file(skill_views_path)
    views = load_skill_views(skill_views_path, dataset_root=dataset_root)
    if digest_file(skill_views_path) != views_file_digest:
        raise ValueError("Skill-view reference changed during verification")
    index = next((i for i, v in enumerate(views.views) if v.skill_id == skill_id), None)
    if index is None:
        raise ValueError("Unknown predecessor skill")
    last = index == len(views.views) - 1
    if last != final_parking:
        raise ValueError("Final fork has no successor; request final_parking explicitly only there")
    view = views.views[index]
    successor = None if last else views.views[index + 1]
    if successor is not None and successor.start != view.end:
        raise ValueError("Successor does not begin at the verified predecessor boundary")
    exported = json.loads((dataset_root / "export_manifest.json").read_text())
    if (
        exported["manifest_sha256"] != views.export_manifest_sha256
        or hashlib.sha256(
            canonical({key: value for key, value in exported.items() if key != "manifest_sha256"})
        ).hexdigest()
        != views.export_manifest_sha256
    ):
        raise ValueError("Dataset export changed after skill-view verification")
    entry = next(e for e in exported["episodes"] if e["episode_id"] == views.parent_episode_id)
    episode_path = dataset_root / entry["raw_root"] / "demonstration/episode.json"
    episode_bytes = episode_path.read_bytes()
    if hashlib.sha256(episode_bytes).hexdigest() != entry["episode_sha256"]:
        raise ValueError("Reference episode changed after skill-view verification")
    episode = DemonstrationEpisode.model_validate_json(episode_bytes)
    observation = episode.frames[view.end].observation
    if observation.sequence != view.end or observation.episode_id != views.parent_episode_id:
        raise ValueError("Successor reference observation identity mismatch")
    reference = SuccessorReference(
        skill_id=skill_id,
        successor_skill_id=None if last else successor.skill_id,
        parent_episode_id=views.parent_episode_id,
        export_manifest_sha256=views.export_manifest_sha256,
        views_manifest_sha256=views.manifest_sha256,
        views_file_sha256=views_file_digest,
        episode_file_sha256=entry["episode_sha256"],
        reference_frame=view.end,
        reference_observation_sha256=hashlib.sha256(
            canonical(observation.model_dump(mode="json"))
        ).hexdigest(),
        joint_position_rad=tuple(observation.joint_position_rad),
        joint_limits=episode.joint_limits,
        dataset_root=dataset_root,
        skill_views_path=skill_views_path,
        final_parking=final_parking,
    )
    object.__setattr__(reference, "_verified", _VERIFIED)
    return reference


@dataclass(frozen=True)
class ReadinessOutcome:
    state: Literal["pending", "ready", "failed"]
    reason: str
    counters: Mapping[str, int | float]
    reference_sha256: str
    final_parking: bool
    physical_success: Literal[True] = True

    def report(self) -> dict:
        return {
            "profile": PROFILE,
            "state": self.state,
            "reason": self.reason,
            "counters": dict(self.counters),
            "reference_sha256": self.reference_sha256,
            "physical_success": True,
            "successor_start_ready": None if self.final_parking else self.state == "ready",
            "final_parking_ready": self.state == "ready" if self.final_parking else None,
            "independent_task_success": None,
            "generalization_validated": False,
        }


class SuccessorReadinessMonitor:
    """Same-attempt continuation after verified physical success, not a new controller.

    The caller supplies canonical worker action/observation evidence, owns timeout
    and cancellation, and must retain the original attempt and arm ownership. A
    failed monitor cannot be reset; a new attempt must establish physical success.
    """

    def __init__(
        self,
        reference: SuccessorReference,
        *,
        attempt_id: str,
        physical_success: SkillOutcome,
        initial_observation: Observation,
        layout: dict,
        limits: JointLimits,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        max_observation_age_ns: int = 2_000_000_000,
    ):
        if not isinstance(reference, SuccessorReference) or reference._verified is not _VERIFIED:
            raise ValueError("A verified immutable successor reference is required")
        if not isinstance(physical_success, SkillOutcome) or physical_success.state != "succeeded":
            raise ValueError("Readiness cannot manufacture physical success")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("Canonical active attempt identity is required")
        if (
            type(max_observation_age_ns) is not int
            or not 0 < max_observation_age_ns <= 2_000_000_000
        ):
            raise ValueError("Invalid observation freshness budget")
        if not isinstance(limits, JointLimits) or limits != reference.joint_limits:
            raise ValueError("Live joint limits disagree with the reference environment")
        if (
            not isinstance(layout, dict)
            or not _finite_tree(layout)
            or not _vector(layout.get("bar_destination_m"), 3)
            or not _vector(layout.get("plate_destination_m"), 3)
        ):
            raise ValueError("Malformed placement layout")
        self.reference, self.attempt_id, self.limits = reference, attempt_id, limits
        self._clock, self._max_age = clock_ns, max_observation_age_ns
        self._initial = Observation.model_validate(initial_observation.model_dump())
        self._fresh(self._initial)
        self._limits(self._initial.joint_position_rad)
        if abs(self._initial.simulation_seconds - self._initial.sequence / 20) >= 1e-8:
            raise ValueError("Initial observation control sequence/time mismatch")
        self._previous = self._initial
        self._coordinates = {
            "spoon": (-0.12, 0.045, 0.391),
            "fork": (-0.06, 0.062, 0.391),
            "cup": (0.066, 0.153, 0.378),
            "plate": tuple(layout["plate_destination_m"]),
            "practice_object": tuple(layout["bar_destination_m"]),
        }
        self._state, self._reason = "pending", "Physical success retained; successor not yet ready"
        self._counters = {
            "actions": 0,
            "physics_rows": 0,
            "consecutive_observations": 0,
            "joint_max_error_rad": max(
                abs(a - b)
                for a, b in zip(
                    reference.joint_position_rad, self._initial.joint_position_rad, strict=True
                )
            ),
            "max_joint_speed_rad_s": max(map(abs, self._initial.joint_velocity_rad_s)),
        }

    def _fresh(self, observation):
        if not 0 <= self._clock() - observation.observed_monotonic_ns <= self._max_age:
            raise ValueError("Readiness requires fresh, nonfuture worker observations")

    def snapshot(self) -> ReadinessOutcome:
        return ReadinessOutcome(
            self._state,
            self._reason,
            MappingProxyType(dict(self._counters)),
            self.reference.reference_sha256,
            self.reference.final_parking,
        )

    def fail(self, reason: str) -> ReadinessOutcome:
        if self._state != "pending":
            raise RuntimeError("Terminal readiness monitor cannot be changed")
        self._state, self._reason = "failed", str(reason)
        return self.snapshot()

    def _limits(self, positions):
        if not _vector(positions, 12) or any(
            not low <= value <= high
            for low, value, high in zip(
                self.limits.lower_rad, positions, self.limits.upper_rad, strict=True
            )
        ):
            raise ValueError("Measured/action joints exceed actual environment limits")

    def _contact_invariants(self, row):
        if row["bad"]:
            raise ValueError("Forbidden contact during successor preparation")
        if any(row["drawer_forces"]):
            raise ValueError("Drawer contact resumed after physical success")
        handoff = self.reference.skill_id == "handoff_transfer"
        if handoff and not _airborne(row["objects"]["practice_object"], "right"):
            raise ValueError("Receiver-only airborne grip was lost after handoff")
        for name in _PROTECTED[self.reference.skill_id]:
            if not _placed(row["objects"][name], name, self._coordinates):
                raise ValueError(f"Completed placement disturbed: {name}")
        for name, obj in row["objects"].items():
            if not (handoff and name == "practice_object") and any(
                force for pair in obj["forces"].values() for force in pair
            ):
                raise ValueError("Unexpected jaw contact during successor preparation")
        if (
            self.reference.skill_id
            in ("drawer_open", "spoon_retrieve_place", "fork_retrieve_place")
            and row["opening"] < 0.08
        ):
            raise ValueError("Released open drawer prerequisite was lost")

    def consume(
        self, action: dict, rows: Iterable[dict], observation: Observation
    ) -> ReadinessOutcome:
        if self._state != "pending":
            raise RuntimeError("A terminal readiness monitor cannot consume another action")
        try:
            current = Observation.model_validate(observation.model_dump())
            self._fresh(current)
            previous = self._previous
            before = previous.simulation_seconds
            if (
                current.episode_id != self._initial.episode_id
                or current.instruction_revision != self._initial.instruction_revision
                or current.sequence != previous.sequence + 1
                or abs(current.simulation_seconds - before - 0.05) >= 1e-8
                or current.observed_monotonic_ns <= previous.observed_monotonic_ns
                or any(
                    a.artifact.path == b.artifact.path
                    for a, b in zip(current.frames, previous.frames, strict=True)
                )
            ):
                raise ValueError("Readiness observation identity/progression mismatch")
            if (
                not isinstance(action, dict)
                or not _finite_tree(action)
                or action.get("attempt_id") != self.attempt_id
                or action.get("episode_id") != current.episode_id
                or type(action.get("observation_sequence")) is not int
                or action["observation_sequence"] != previous.sequence
                or not _number(action.get("simulation_seconds_before"))
                or not _number(action.get("simulation_seconds_after"))
                or abs(action["simulation_seconds_before"] - before) >= 1e-8
                or abs(action["simulation_seconds_after"] - current.simulation_seconds) >= 1e-8
                or action.get("applied") is not True
                or action.get("partial_physics") is not False
            ):
                raise ValueError("Unconfirmed or mismatched readiness action")
            self._limits(action.get("targets_rad"))
            iterator = iter(rows)
            for index in range(50):
                row = next(iterator, None)
                if (
                    not isinstance(row, dict)
                    or not _valid_row(row | {"phase": "ignored"})
                    or (abs(row["t"] - before - (index + 1) / 1000) >= 1e-8)
                ):
                    raise ValueError("Missing, malformed or discontinuous 1kHz readiness evidence")
                self._limits(row["joint_position"])
                self._contact_invariants(row)
                self._counters["physics_rows"] += 1
            if next(iterator, None) is not None:
                raise ValueError("More than fifty physical samples for readiness action")
            if any(
                abs(a - b) > 1e-12
                for a, b in zip(row["joint_position"], current.joint_position_rad, strict=True)
            ):
                raise ValueError("Fresh observation does not match final physical joint sample")
            error = max(
                abs(a - b)
                for a, b in zip(
                    self.reference.joint_position_rad, current.joint_position_rad, strict=True
                )
            )
            speed = max(map(abs, current.joint_velocity_rad_s))
            self._counters["joint_max_error_rad"] = error
            self._counters["max_joint_speed_rad_s"] = speed
            qualifying = error <= JOINT_TOLERANCE_RAD and speed <= MAX_JOINT_SPEED_RAD_S
            self._counters["consecutive_observations"] = (
                self._counters["consecutive_observations"] + 1 if qualifying else 0
            )
            self._counters["actions"] += 1
            self._previous = current
            self._fresh(current)  # Evidence validation also consumes wall time.
            if self._counters["consecutive_observations"] >= REQUIRED_OBSERVATIONS:
                self._state, self._reason = "ready", "Measured posture and contact readiness passed"
        except Exception as error:
            self._state, self._reason = "failed", f"{type(error).__name__}: {error}"
        return self.snapshot()
