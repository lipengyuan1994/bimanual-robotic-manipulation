"""Write-once six-skill training declarations; no execution or quality promotion."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_views import load_skill_views
from bimanual.training import ACTTrainingConfig, verify_training_dataset
from bimanual.workflow_manifest import SKILLS

COHORT_SKILLS = SKILLS[1:]
ROLES = ("training", "recorded", "physical_prefix2", "physical_prefix5", "experiment_protocol")
KINDS = (
    "act_training",
    "dinner_handoff_recorded_policy_evaluation",
    "learned_handoff_physical_diagnostic_process",
    "learned_handoff_physical_diagnostic_process",
    "corrective_handoff_training_protocol",
)


def _configs(dataset, views):
    return tuple(
        ACTTrainingConfig(
            dataset_path=dataset,
            skill_views_path=views,
            skill_id=skill,
            device="mps",
            architecture="small",
            steps=20000,
            batch_size=4,
            chunk_size=10,
            seed=0,
            cpu_threads=4,
            learning_rate=1e-5,
            learning_rate_schedule="terminal_linear",
            temporal_loss_profile="first_action_half_v1",
            use_vae=False,
            dropout=0.0,
        ).model_dump(mode="json")
        for skill in COHORT_SKILLS
    )


class CohortPrerequisite(Contract):
    role: Literal[
        "training", "recorded", "physical_prefix2", "physical_prefix5", "experiment_protocol"
    ]
    run_id: str = Field(min_length=1)
    manifest_sha256: Digest
    outcome: Literal["completed", "failed", "interrupted", "cancelled", "timed_out", "prepared"]
    nested_evaluation_verified: StrictBool = False
    driver_sha256: Digest | None = None
    wrapper_details: dict = Field(default_factory=dict)


class TrainingCohortProtocol(Contract):
    profile: Literal["six_skill_act_training_protocol_v1"] = "six_skill_act_training_protocol_v1"
    dataset_root: str
    skill_views_path: str
    evidence_root: str
    dataset_file_sha256: Digest
    dataset_manifest_sha256: Digest
    views_file_sha256: Digest
    views_manifest_sha256: Digest
    configs: tuple[dict, ...]
    prerequisites: tuple[CohortPrerequisite, ...]
    checkpoint_selection: Literal["final_update_20000_only"] = "final_update_20000_only"
    scope: Literal["training_runtime_only_no_physical_quality_claim"] = (
        "training_runtime_only_no_physical_quality_claim"
    )
    execution_authorized_by_this_artifact: Literal[False] = False
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_protocol(self):
        if any(
            not value or Path(value).is_absolute()
            for value in (self.dataset_root, self.skill_views_path, self.evidence_root)
        ):
            raise ValueError("Cohort source locations must be relative")
        if tuple(self.configs) != _configs(self.dataset_root, self.skill_views_path):
            raise ValueError("Cohort must freeze exact six ordered ACT configurations")
        if (
            tuple(p.role for p in self.prerequisites) != ROLES
            or len({p.run_id for p in self.prerequisites}) != 5
        ):
            raise ValueError("Cohort requires five distinct ordered handoff prerequisites")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Cohort protocol body seal mismatch")
        return self


def _prerequisites(store, run_ids):
    if set(run_ids) != set(ROLES):
        raise ValueError("All five handoff prerequisites are required")
    experiment = store.verify(run_ids["experiment_protocol"])
    if (
        experiment.kind != "corrective_handoff_training_protocol"
        or experiment.outcome != "prepared"
    ):
        raise ValueError("Expected prepared corrective handoff experiment protocol")
    if (
        experiment.files.get("driver.py") != experiment.config.get("driver_sha256")
        or "driver.py" not in experiment.files
    ):
        raise ValueError("Experiment protocol driver seal mismatch")
    script_names = {
        "recorded": "evaluate-dinner-handoff-v2.py",
        "physical_prefix2": "evaluate-handoff-physical-prefix2.py",
        "physical_prefix5": "evaluate-handoff-prefix5-optimized.py",
    }
    results = []
    training = None
    for role, kind in zip(ROLES, KINDS, strict=True):
        run = store.verify(run_ids[role])
        if run.kind != kind or run.outcome not in {
            "completed",
            "failed",
            "interrupted",
            "cancelled",
            "timed_out",
            "prepared",
        }:
            raise ValueError("Prerequisite must have matching kind and terminal outcome")
        if role != "experiment_protocol" and run.outcome == "prepared":
            raise ValueError("Evaluation/training prerequisite is not terminal")
        if role == "training":
            if (
                run.outcome != "completed"
                or run.config.get("skill_id") != "handoff_transfer"
                or run.metrics.get("training_completed") is not True
            ):
                raise ValueError("Handoff training prerequisite is not completed")
            if run.config != experiment.config.get("training"):
                raise ValueError("Handoff training differs from frozen experiment configuration")
            training = run
        elif role != "experiment_protocol" and run.config.get("training_run") != training.run_id:
            raise ValueError("Evaluation prerequisite belongs to a different handoff checkpoint")
        if role == "recorded" and run.config.get("training_sha256") != training.manifest_sha256:
            raise ValueError("Recorded evaluation checkpoint seal mismatch")
        nested_verified = False
        driver_sha = None
        if role in script_names:
            driver_sha = run.files.get("driver.py")
            expected_driver = experiment.config.get("evaluation_scripts", {}).get(
                script_names[role]
            )
            if driver_sha is None or driver_sha != expected_driver:
                raise ValueError("Evaluation driver differs from frozen experiment protocol")
        elif role == "experiment_protocol":
            driver_sha = experiment.config["driver_sha256"]
        wrapper_details = {}
        if role.startswith("physical"):
            driver_sha = run.files.get("driver.py")
            if driver_sha is None:
                raise ValueError("Physical wrapper lacks its frozen driver")
            wrapper_details = {
                "training_run": run.config.get("training_run"),
                "timeout_seconds": run.config.get("timeout_seconds"),
                "timed_out": run.metrics.get("timed_out"),
                "returncode": run.metrics.get("returncode"),
                "declared_prefix": int(role[-1]),
                "sealed_file_count": len(run.files),
                "sealed_files_sha256": hashlib.sha256(canonical(run.files)).hexdigest(),
            }
            if run.outcome == "completed" and run.metrics.get("child_run_id") is None:
                raise ValueError("Completed physical wrapper requires a sealed child")
        if role.startswith("physical") and run.metrics.get("child_run_id") is not None:
            child = EvidenceStore(store.directory(run.run_id) / "child-evidence").verify(
                run.metrics["child_run_id"]
            )
            if (
                child.manifest_sha256 != run.metrics.get("child_sha256")
                or child.config.get("training_run") != training.run_id
                or child.config.get("execute_chunk_steps") != int(role[-1])
                or child.kind != "learned_handoff_physical_diagnostic"
            ):
                raise ValueError("Physical prerequisite child or execution prefix mismatch")
            nested_verified = True
        results.append(
            CohortPrerequisite(
                role=role,
                run_id=run.run_id,
                manifest_sha256=run.manifest_sha256,
                outcome=run.outcome,
                nested_evaluation_verified=nested_verified,
                driver_sha256=driver_sha,
                wrapper_details=wrapper_details,
            )
        )
    return tuple(results)


def create_training_cohort_protocol(
    dataset_root, skill_views_path, prerequisites, *, store, destination
):
    """Freeze inputs; callers must separately arrange exclusion and execution."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Cohort protocol already exists")
    dataset_root, skill_views_path = Path(dataset_root).resolve(), Path(skill_views_path).resolve()
    dataset = verify_training_dataset(dataset_root)
    views = load_skill_views(skill_views_path, dataset_root=dataset_root)
    if (
        views.profile != "dinner_nominal_skill_views_v2"
        or views.export_manifest_sha256 != dataset["manifest_sha256"]
    ):
        raise ValueError("Cohort requires verified nominal v2 views")
    data_path, views_path = (
        os.path.relpath(p, destination.parent) for p in (dataset_root, skill_views_path)
    )
    body = dict(
        schema_version=1,
        profile="six_skill_act_training_protocol_v1",
        dataset_root=data_path,
        skill_views_path=views_path,
        evidence_root=os.path.relpath(store.root, destination.parent),
        dataset_file_sha256=digest_file(dataset_root / "export_manifest.json"),
        dataset_manifest_sha256=dataset["manifest_sha256"],
        views_file_sha256=digest_file(skill_views_path),
        views_manifest_sha256=views.manifest_sha256,
        configs=_configs(data_path, views_path),
        prerequisites=[p.model_dump(mode="json") for p in _prerequisites(store, prerequisites)],
        checkpoint_selection="final_update_20000_only",
        scope="training_runtime_only_no_physical_quality_claim",
        execution_authorized_by_this_artifact=False,
    )
    result = TrainingCohortProtocol.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as stream:
        stream.write(result.model_dump_json(indent=2))
    return load_training_cohort_protocol(destination)


def load_training_cohort_protocol(path):
    """Reverify the immutable declaration and every transitive source; no model imports."""
    path = Path(path).resolve()
    file_sha = digest_file(path)
    result = TrainingCohortProtocol.model_validate_json(path.read_text())
    dataset_root = (path.parent / result.dataset_root).resolve()
    views_path = (path.parent / result.skill_views_path).resolve()
    if (
        digest_file(dataset_root / "export_manifest.json") != result.dataset_file_sha256
        or digest_file(views_path) != result.views_file_sha256
    ):
        raise ValueError("Cohort input file digest mismatch")
    dataset = verify_training_dataset(dataset_root)
    views = load_skill_views(views_path, dataset_root=dataset_root)
    if (
        dataset["manifest_sha256"] != result.dataset_manifest_sha256
        or views.manifest_sha256 != result.views_manifest_sha256
        or views.profile != "dinner_nominal_skill_views_v2"
        or views.export_manifest_sha256 != result.dataset_manifest_sha256
    ):
        raise ValueError("Cohort nominal v2 source identity mismatch")
    store = EvidenceStore(path.parent / result.evidence_root)
    if (
        _prerequisites(store, {p.role: p.run_id for p in result.prerequisites})
        != result.prerequisites
    ):
        raise ValueError("Cohort prerequisite seal changed")
    if digest_file(path) != file_sha:
        raise ValueError("Cohort protocol changed during verification")
    return result
