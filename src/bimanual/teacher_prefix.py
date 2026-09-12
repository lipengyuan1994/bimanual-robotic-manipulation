"""Verified teacher preparation for isolated learned-skill diagnostics.

This module is deliberately separate from the deployed workflow.  It advances the
real MuJoCo scene with the recorded teacher joint targets up to one frozen skill
boundary.  The subsequent learned policy must complete the selected skill through
contacts.  Such a run is teacher-assisted component evidence and can never establish
an autonomous dinner workflow or release quality.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from bimanual.dinner_control import DinnerControlWorker
from bimanual.dinner_teacher import phase_permissions
from bimanual.evidence import canonical, digest_file
from bimanual.skill_views import SkillView, load_skill_views
from bimanual.teacher import check_carried_path, check_joint_path

_VERIFIED = object()


@dataclass(frozen=True)
class TeacherPrefix:
    """Immutable binding from a verified skill view to its original teacher plan."""

    skill_id: str
    action_count: int
    parent_episode_id: str
    dataset_root: Path
    skill_views_path: Path
    export_manifest_sha256: str
    views_manifest_sha256: str
    views_file_sha256: str
    source_manifest_sha256: str
    scene_sha256: str
    plan_sha256: str
    plan_steps_sha256: str
    _verified: object = field(default=None, init=False, repr=False, compare=False)

    def report(self) -> dict:
        return {
            "profile": "dinner_teacher_prefix_diagnostic_v1",
            "skill_id": self.skill_id,
            "teacher_prefix_actions": self.action_count,
            "parent_episode_id": self.parent_episode_id,
            "dataset_root": str(self.dataset_root),
            "skill_views_path": str(self.skill_views_path),
            "export_manifest_sha256": self.export_manifest_sha256,
            "views_manifest_sha256": self.views_manifest_sha256,
            "views_file_sha256": self.views_file_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "scene_sha256": self.scene_sha256,
            "plan_sha256": self.plan_sha256,
            "plan_steps_sha256": self.plan_steps_sha256,
            "teacher_actions_used": self.action_count > 0,
            "autonomous_workflow_evidence": False,
            "release_qualified": False,
        }

    @property
    def prefix_sha256(self) -> str:
        return hashlib.sha256(canonical(self.report())).hexdigest()

    def reverify(self) -> TeacherPrefix:
        current = load_teacher_prefix(
            self.dataset_root, self.skill_views_path, skill_id=self.skill_id
        )
        if self._verified is not _VERIFIED or current != self:
            raise ValueError("Teacher prefix sources changed after verification")
        return current


def _source_paths(dataset_root: Path, parent_episode_id: str) -> tuple[dict, Path]:
    exported = json.loads((dataset_root / "export_manifest.json").read_text())
    entry = next(
        (row for row in exported["episodes"] if row["episode_id"] == parent_episode_id), None
    )
    if entry is None:
        raise ValueError("Skill-view parent episode is absent from the dataset export")
    raw = (dataset_root / entry["raw_root"]).resolve()
    manifest_path = raw / "manifest.json"
    if digest_file(manifest_path) != entry["evidence_manifest_sha256"]:
        raise ValueError("Teacher source manifest changed after dataset export")
    source = json.loads(manifest_path.read_text())
    if hashlib.sha256(
        canonical({key: value for key, value in source.items() if key != "manifest_sha256"})
    ).hexdigest() != source.get("manifest_sha256"):
        raise ValueError("Teacher source body seal mismatch")
    return source, raw


def load_teacher_prefix(
    dataset_root: Path, skill_views_path: Path, *, skill_id: str
) -> TeacherPrefix:
    """Bind a skill start to the exact sealed plan that produced its training scene."""

    dataset_root = Path(dataset_root).resolve(strict=True)
    skill_views_path = Path(skill_views_path).resolve(strict=True)
    views_file_sha256 = digest_file(skill_views_path)
    views = load_skill_views(skill_views_path, dataset_root=dataset_root)
    if views.profile != "dinner_nominal_skill_views_v2":
        raise ValueError("Teacher-prepared component evaluation requires nominal-v2 views")
    view: SkillView | None = next((row for row in views.views if row.skill_id == skill_id), None)
    if view is None:
        raise ValueError("Unknown dinner skill")
    source, raw = _source_paths(dataset_root, views.parent_episode_id)
    plan_path = raw / "teacher-assets/plan.json.gz"
    scene_path = raw / "scene.xml"
    controller = json.loads((raw / "controller.json").read_text())
    if (
        source.get("kind") != "dinner_teacher"
        or source.get("outcome") != "completed"
        or controller.get("kind") != "scripted_teacher"
        or controller.get("teacher_uses_simulator_truth") is not True
        or controller.get("plan") != "teacher-assets/plan.json.gz"
        or controller.get("plan_sha256") != digest_file(plan_path)
        or source.get("files", {}).get("teacher-assets/plan.json.gz") != digest_file(plan_path)
        or source.get("files", {}).get("scene.xml") != digest_file(scene_path)
    ):
        raise ValueError("Unsupported or changed teacher-prefix lineage")
    plan = json.loads(gzip.decompress(plan_path.read_bytes()))
    steps = plan.get("steps")
    if (
        plan.get("schema_version") not in (1, 2)
        or (plan.get("physics_hz"), plan.get("control_hz")) != (1000, 20)
        or not isinstance(steps, list)
        or not 0 <= view.start < len(steps)
    ):
        raise ValueError("Unsupported teacher plan for prefix preparation")
    # Validate all selected actions now; the worker repeats limit/path/contact checks live.
    for step in steps[: view.start]:
        phase_permissions(step.get("phase", ""))
        q = np.asarray(step.get("q"), dtype=float)
        if q.shape != (12,) or not np.isfinite(q).all():
            raise ValueError("Malformed teacher prefix joint target")
    prefix = TeacherPrefix(
        skill_id=skill_id,
        action_count=view.start,
        parent_episode_id=views.parent_episode_id,
        dataset_root=dataset_root,
        skill_views_path=skill_views_path,
        export_manifest_sha256=views.export_manifest_sha256,
        views_manifest_sha256=views.manifest_sha256,
        views_file_sha256=views_file_sha256,
        source_manifest_sha256=source["manifest_sha256"],
        scene_sha256=digest_file(scene_path),
        plan_sha256=digest_file(plan_path),
        plan_steps_sha256=hashlib.sha256(canonical(steps[: view.start])).hexdigest(),
    )
    object.__setattr__(prefix, "_verified", _VERIFIED)
    return prefix


class TeacherPreparedDinnerControlWorker(DinnerControlWorker):
    """Diagnostic worker advanced by a disclosed teacher prefix before first capture."""

    def __init__(self, directory: Path, registry, *, prefix: TeacherPrefix, **kwargs):
        if not isinstance(prefix, TeacherPrefix) or prefix._verified is not _VERIFIED:
            raise ValueError("A verified teacher prefix is required")
        prefix = prefix.reverify()
        super().__init__(directory, registry, **kwargs)
        try:
            if digest_file(self.directory / "scene.xml") != prefix.scene_sha256:
                raise ValueError("Teacher prefix and diagnostic worker scenes differ")
            _, raw = _source_paths(prefix.dataset_root, prefix.parent_episode_id)
            plan_path = raw / "teacher-assets/plan.json.gz"
            if digest_file(plan_path) != prefix.plan_sha256:
                raise ValueError("Teacher plan changed before physical preparation")
            steps = json.loads(gzip.decompress(plan_path.read_bytes()))["steps"][
                : prefix.action_count
            ]
            if hashlib.sha256(canonical(steps)).hexdigest() != prefix.plan_steps_sha256:
                raise ValueError("Teacher prefix actions changed before physical preparation")
            for index, step in enumerate(steps):
                q = np.asarray(step["q"], dtype=float)
                if np.any(q < self._env.lower) or np.any(q > self._env.upper):
                    raise ValueError("Teacher prefix exceeds physical joint limits")
                self._env.phase = step["phase"]
                self._env.active_contacts, carried, arm = phase_permissions(step["phase"])
                if step.get("arm_object_contacts") == "none":
                    self._env.active_contacts = {}
                previous = (
                    self._env.data.qpos[self._env.qadr].copy()
                    if step.get("path_start") == "measured"
                    else self._env.data.ctrl[self._env.actuator_ids].copy()
                )
                if carried:
                    check_carried_path(
                        self._env,
                        previous,
                        q,
                        self._env.allowed,
                        body_name=carried,
                        site_name=arm + "/pinch",
                    )
                else:
                    check_joint_path(self._env, previous, q, self._env.allowed)
                before = float(self._env.data.time)
                self._env.step(q, episode_id=self.episode_id, sequence=self._env.sequence)
                self._record(
                    "teacher-prefix-actions.jsonl",
                    {
                        "index": index,
                        "phase": step["phase"],
                        "targets_rad": q.tolist(),
                        "simulation_seconds_before": before,
                        "simulation_seconds_after": float(self._env.data.time),
                        "applied": True,
                    },
                )
            self._env.active_contacts = {}
            self._env.phase = "policy/idle"
            self.flush_physics_trace()
            (self.directory / "teacher-prefix.json").write_bytes(canonical(prefix.report()))
            worker = json.loads((self.directory / "worker.json").read_text())
            worker.update(
                teacher_schedule_used=prefix.action_count > 0,
                teacher_prefix_actions=prefix.action_count,
                teacher_prefix_sha256=prefix.prefix_sha256,
                manipulation_success=None,
            )
            (self.directory / "worker.json").write_bytes(canonical(worker))
        except BaseException:
            self.close()
            raise
