"""Frozen development protocol for six teacher-prepared physical evaluations."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import canonical, digest_file
from bimanual.skill_views import INTERVALS_V2
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol

_BUDGETS = {skill: 2 * (end - start) for skill, start, end in INTERVALS_V2[1:]}
_SOURCES = (
    "skill_physical_evaluation.py",
    "teacher_prefix.py",
    "skill_executor.py",
    "skill_outcomes.py",
    "successor_readiness.py",
    "dinner_control.py",
    "dinner_scoring.py",
    "dinner_teacher.py",
    "skill_registry.py",
    "skill_physical_protocol.py",
    "skill_physical_protocol_runner.py",
    "skill_physical_process.py",
    "skill_physical_suite.py",
    "skill_policy.py",
    "policy_rollout.py",
    "supervised_control.py",
    "contracts.py",
    "teacher.py",
    "dual_arm.py",
    "supervisor.py",
    "training.py",
    "workflow_guardian.py",
    "workflow_process.py",
    "worker_lease.py",
    "evidence.py",
)


def _configs() -> tuple[dict, ...]:
    return tuple(
        {
            "skill_id": skill,
            "device": "mps",
            "execute_chunk_steps": 2,
            "max_actions": _BUDGETS[skill],
            "wall_timeout_seconds": 1200.0,
            "scene": "authored_nominal_v2_training_scene",
            "preparation": "sealed_teacher_prefix_to_exact_skill_start",
            "checkpoint_selection": "cohort_final_update_20000_only",
        }
        for skill in COHORT_SKILLS
    )


class SkillPhysicalProtocol(Contract):
    profile: Literal["six_skill_teacher_prepared_physical_protocol_v1"] = (
        "six_skill_teacher_prepared_physical_protocol_v1"
    )
    training_cohort_path: str
    training_cohort_file_sha256: Digest
    training_cohort_manifest_sha256: Digest
    evaluation_sources: dict[str, Digest]
    configs: tuple[dict, ...]
    selection_rule: Literal["evaluate_every_completed_cohort_checkpoint_once"] = (
        "evaluate_every_completed_cohort_checkpoint_once"
    )
    scope: Literal["teacher_prepared_component_only_not_autonomous_workflow"] = (
        "teacher_prepared_component_only_not_autonomous_workflow"
    )
    release_qualified: Literal[False] = False
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_declaration(self):
        if not self.training_cohort_path or Path(self.training_cohort_path).is_absolute():
            raise ValueError("Training cohort path must be relative to this protocol")
        if tuple(self.configs) != _configs():
            raise ValueError("Physical evaluation parameters must match the frozen six-skill suite")
        if set(self.evaluation_sources) != set(_SOURCES):
            raise ValueError("Physical evaluation protocol requires the exact runtime source set")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Physical evaluation protocol body seal mismatch")
        return self


def create_skill_physical_protocol(training_cohort_path: Path, destination: Path):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Physical evaluation protocol already exists")
    cohort_path = Path(training_cohort_path).resolve(strict=True)
    cohort = load_training_cohort_protocol(cohort_path)
    root = Path(__file__).resolve().parent
    body = {
        "schema_version": 1,
        "profile": "six_skill_teacher_prepared_physical_protocol_v1",
        "training_cohort_path": os.path.relpath(cohort_path, destination.parent),
        "training_cohort_file_sha256": digest_file(cohort_path),
        "training_cohort_manifest_sha256": cohort.manifest_sha256,
        "evaluation_sources": {name: digest_file(root / name) for name in _SOURCES},
        "configs": _configs(),
        "selection_rule": "evaluate_every_completed_cohort_checkpoint_once",
        "scope": "teacher_prepared_component_only_not_autonomous_workflow",
        "release_qualified": False,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = SkillPhysicalProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(canonical(result.model_dump(mode="json")))
        stream.write(b"\n")
    return result


def load_skill_physical_protocol(path: Path) -> SkillPhysicalProtocol:
    path = Path(path).resolve(strict=True)
    protocol = SkillPhysicalProtocol.model_validate_json(path.read_bytes())
    cohort_path = (path.parent / protocol.training_cohort_path).resolve(strict=True)
    if digest_file(cohort_path) != protocol.training_cohort_file_sha256:
        raise ValueError("Frozen training cohort file changed")
    cohort = load_training_cohort_protocol(cohort_path)
    if cohort.manifest_sha256 != protocol.training_cohort_manifest_sha256:
        raise ValueError("Frozen training cohort body changed")
    root = Path(__file__).resolve().parent
    for name, expected in protocol.evaluation_sources.items():
        if digest_file(root / name) != expected:
            raise ValueError(f"Physical evaluator source changed after protocol freeze: {name}")
    return protocol
