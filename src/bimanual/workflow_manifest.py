"""Portable, pinned checkpoint cohorts for the development dinner workflow."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import canonical, digest_file
from bimanual.skill_registry import SkillCheckpointBinding, load_skill_checkpoint
from bimanual.skill_views import INTERVALS, load_skill_views
from bimanual.successor_readiness import SuccessorReference, load_successor_reference

SKILLS = tuple(row[0] for row in INTERVALS)


class WorkflowCheckpoint(Contract):
    skill_id: str
    training_run: str = Field(min_length=1)
    training_manifest_sha256: Digest
    checkpoint_sha256: Digest


class CorrectiveWorkflowCheckpoint(WorkflowCheckpoint):
    corrective_dataset_root: str = Field(min_length=1)
    corrective_export_file_sha256: Digest

    @model_validator(mode="after")
    def handoff_only(self):
        if self.skill_id != "handoff_transfer":
            raise ValueError("Corrective workflow checkpoint must be handoff_transfer")
        if Path(self.corrective_dataset_root).is_absolute():
            raise ValueError("Corrective workflow path must be relative")
        return self


class WorkflowManifest(Contract):
    profile: Literal["dinner_development_workflow_v1", "dinner_development_workflow_v2"] = (
        "dinner_development_workflow_v1"
    )
    dataset_root: str = Field(min_length=1)
    export_file_sha256: Digest
    skill_views_path: str = Field(min_length=1)
    skill_views_file_sha256: Digest
    checkpoints: tuple[CorrectiveWorkflowCheckpoint | WorkflowCheckpoint, ...] = Field(
        min_length=7, max_length=7
    )
    manifest_sha256: Digest

    @model_validator(mode="after")
    def complete_order(self):
        if tuple(item.skill_id for item in self.checkpoints) != SKILLS:
            raise ValueError("Workflow requires all seven skills in their fixed order")
        has_corrections = any(
            isinstance(item, CorrectiveWorkflowCheckpoint) for item in self.checkpoints
        )
        if has_corrections != (self.profile == "dinner_development_workflow_v2"):
            raise ValueError("Workflow profile and corrective entries disagree")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Workflow manifest body seal mismatch")
        return self


@dataclass(frozen=True)
class VerifiedWorkflow:
    path: Path
    file_sha256: str
    manifest: WorkflowManifest
    bindings: tuple[SkillCheckpointBinding, ...]
    successor_references: tuple[SuccessorReference, ...]

    def report(self):
        return {
            "profile": self.manifest.profile,
            "manifest_path": str(self.path),
            "manifest_file_sha256": self.file_sha256,
            "manifest_sha256": self.manifest.manifest_sha256,
            "checkpoints": [binding.report() for binding in self.bindings],
            "successor_references": [ref.report() for ref in self.successor_references],
            "release_available": False,
            "learned_workflow_success": None,
            "scope": "Verified lineage only; all policies must pass physical evaluation",
        }

    def reverify(self):
        current = load_workflow_manifest(self.path)
        if current != self:
            raise ValueError("Workflow cohort changed after verification")
        return current


def load_workflow_manifest(path: Path) -> VerifiedWorkflow:
    path = Path(path).resolve()
    file_hash = digest_file(path)
    manifest = WorkflowManifest.model_validate_json(path.read_text())
    dataset = (path.parent / manifest.dataset_root).resolve()
    views_path = (path.parent / manifest.skill_views_path).resolve()
    if digest_file(dataset / "export_manifest.json") != manifest.export_file_sha256:
        raise ValueError("Workflow dataset file digest mismatch")
    if digest_file(views_path) != manifest.skill_views_file_sha256:
        raise ValueError("Workflow skill views file digest mismatch")
    views = load_skill_views(views_path, dataset_root=dataset)
    bindings = []
    corrective_hashes = []
    for entry, view in zip(manifest.checkpoints, views.views, strict=True):
        overrides = {}
        if isinstance(entry, CorrectiveWorkflowCheckpoint):
            corrective_root = (path.parent / entry.corrective_dataset_root).resolve()
            export_path = corrective_root / "export_manifest.json"
            if digest_file(export_path) != entry.corrective_export_file_sha256:
                raise ValueError("Workflow corrective export digest mismatch")
            corrective_hashes.append((export_path, entry.corrective_export_file_sha256))
            overrides["corrective_dataset_root"] = corrective_root
        binding = load_skill_checkpoint(
            (path.parent / entry.training_run).resolve(),
            skill_id=entry.skill_id,
            dataset_root=dataset,
            **overrides,
        )
        if overrides and getattr(binding, "corrective_dataset_root", None) != corrective_root:
            raise ValueError("Workflow corrective path differs from binding")
        if (
            binding.training_manifest_sha256 != entry.training_manifest_sha256
            or binding.checkpoint_sha256 != entry.checkpoint_sha256
            or binding.view != view
        ):
            raise ValueError("Workflow checkpoint identity or view mismatch")
        bindings.append(binding)
    references = tuple(
        load_successor_reference(
            dataset, views_path, skill_id=skill, final_parking=(skill == SKILLS[-1])
        )
        for skill in SKILLS
    )
    # References carry the export's canonical body seal, not its file hash.
    if any(
        ref.export_manifest_sha256 != views.export_manifest_sha256
        or ref.parent_episode_id != views.parent_episode_id
        for ref in references
    ):
        raise ValueError("Workflow reference dataset lineage mismatch")
    if (
        any(digest_file(p) != sha for p, sha in corrective_hashes)
        or digest_file(path) != file_hash
        or digest_file(dataset / "export_manifest.json") != manifest.export_file_sha256
        or digest_file(views_path) != manifest.skill_views_file_sha256
    ):
        raise ValueError("Workflow source changed during verification")
    return VerifiedWorkflow(path, file_hash, manifest, tuple(bindings), references)


def create_workflow_manifest(
    dataset_root: Path,
    skill_views_path: Path,
    training_runs: dict[str, Path],
    destination: Path,
    *,
    corrective_dataset_roots: dict[str, Path] | None = None,
) -> VerifiedWorkflow:
    """Pin explicitly selected runs; never discover or promote a latest checkpoint."""
    if set(training_runs) != set(SKILLS):
        raise ValueError("Explicit training runs for all seven skills are required")
    corrective_dataset_roots = corrective_dataset_roots or {}
    if set(corrective_dataset_roots) - {"handoff_transfer"}:
        raise ValueError("Only the handoff checkpoint supports corrective datasets")
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("Workflow manifest already exists; choose a new version")
    dataset_root, skill_views_path = Path(dataset_root).resolve(), Path(skill_views_path).resolve()
    views = load_skill_views(skill_views_path, dataset_root=dataset_root)
    entries = []
    for skill, view in zip(SKILLS, views.views, strict=True):
        overrides = (
            {"corrective_dataset_root": corrective_dataset_roots[skill]}
            if skill in corrective_dataset_roots
            else {}
        )
        binding = load_skill_checkpoint(
            training_runs[skill], skill_id=skill, dataset_root=dataset_root, **overrides
        )
        if binding.view != view:
            raise ValueError("Checkpoint view differs from cohort view")
        fields = dict(
            skill_id=skill,
            training_run=os.path.relpath(binding.training_run, destination.parent),
            training_manifest_sha256=binding.training_manifest_sha256,
            checkpoint_sha256=binding.checkpoint_sha256,
        )
        corrective_root = getattr(binding, "corrective_dataset_root", None)
        if corrective_root is not None:
            entry = CorrectiveWorkflowCheckpoint(
                **fields,
                corrective_dataset_root=os.path.relpath(corrective_root, destination.parent),
                corrective_export_file_sha256=digest_file(corrective_root / "export_manifest.json"),
            )
        else:
            entry = WorkflowCheckpoint(**fields)
        entries.append(entry.model_dump(mode="json"))
    body = dict(
        schema_version=1,
        profile=(
            "dinner_development_workflow_v2"
            if any("corrective_dataset_root" in e for e in entries)
            else "dinner_development_workflow_v1"
        ),
        dataset_root=os.path.relpath(dataset_root, destination.parent),
        export_file_sha256=digest_file(dataset_root / "export_manifest.json"),
        skill_views_path=os.path.relpath(skill_views_path, destination.parent),
        skill_views_file_sha256=digest_file(skill_views_path),
        checkpoints=entries,
    )
    manifest = WorkflowManifest.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as stream:
        stream.write(manifest.model_dump_json(indent=2))
    return load_workflow_manifest(destination)


class LoadedWorkflow:
    """Models loaded before any capture; one cohort instance serves one worker."""

    def __init__(self, verified: VerifiedWorkflow, policies):
        if set(policies) != set(SKILLS) or any(
            policies[binding.view.skill_id].binding != binding for binding in verified.bindings
        ):
            raise ValueError("Loaded policies must match every pinned workflow binding")
        if any(
            getattr(policy, "_workflow_cohort_owner", None) is not None
            for policy in policies.values()
        ):
            raise ValueError("Loaded policies already belong to another cohort")
        self.verified = verified
        self.policies = MappingProxyType(dict(policies))
        self._worker = None
        self._ownership = object()
        for policy in self.policies.values():
            policy._workflow_cohort_owner = self._ownership

    def _executor(self, worker, binding, reference, max_actions):
        from bimanual.skill_executor import DinnerSkillExecutor

        policy = self.policies[binding.view.skill_id]
        if (
            self._worker is not worker
            or policy.binding != binding
            or getattr(policy, "_workflow_cohort_owner", None) is not self._ownership
        ):
            raise ValueError("Loaded policy binding or ownership changed before execution")
        return DinnerSkillExecutor(
            worker, policy, max_actions=max_actions, successor_reference=reference
        )

    def executor_factories(self, worker, *, max_actions=2000):
        if self._worker is not None and self._worker is not worker:
            raise ValueError("Loaded policies cannot be shared across workers")
        if worker.supervisor.snapshot().active is not None:
            raise ValueError("Prepare workflow factories before dispatch")
        self._worker = worker
        factories = {}
        for binding, reference in zip(
            self.verified.bindings, self.verified.successor_references, strict=True
        ):
            factories[binding.capability.capability_id] = (
                lambda binding=binding, reference=reference: self._executor(
                    worker, binding, reference, max_actions
                )
            )
        return MappingProxyType(factories)


def preload_workflow(verified: VerifiedWorkflow, *, device="cpu") -> LoadedWorkflow:
    """No inference or camera capture; missing/incompatible cohorts fail before model load."""
    if device not in {"cpu", "mps"}:
        raise ValueError("Supported local policy devices are cpu and mps")
    current = verified.reverify()
    from bimanual.skill_policy import DinnerSkillPolicy

    policies = {}
    for binding in current.bindings:
        policy = DinnerSkillPolicy(
            binding.training_run,
            skill_id=binding.view.skill_id,
            dataset_root=binding.dataset_root,
            device=device,
            **(
                {"corrective_dataset_root": binding.corrective_dataset_root}
                if getattr(binding, "corrective_dataset_root", None) is not None
                else {}
            ),
        )
        if policy.binding != binding:
            raise ValueError("Loaded policy differs from pinned workflow binding")
        policies[binding.view.skill_id] = policy
    current.reverify()
    return LoadedWorkflow(current, policies)
