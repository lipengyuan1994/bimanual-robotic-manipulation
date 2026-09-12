"""Write-once local workflow release declaration; no evaluation execution here."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import canonical, digest_file
from bimanual.planner import verify_model
from bimanual.scene_variant_suite import SceneVariantSuiteEntry, load_scene_variant_suite
from bimanual.workflow_manifest import SKILLS, load_workflow_manifest


def _runtime_sources() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {
        path.relative_to(root).as_posix(): digest_file(path) for path in sorted(root.glob("*.py"))
    }


class WorkflowReleaseProtocol(Contract):
    profile: Literal["local_dinner_workflow_release_protocol_v1"] = (
        "local_dinner_workflow_release_protocol_v1"
    )
    workflow_manifest: str
    workflow_manifest_file_sha256: Digest
    workflow_manifest_sha256: Digest
    execution_profile_sha256: Digest
    planner_model_root: str
    planner_model_manifest_file_sha256: Digest
    planner_model_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    scene_suite_run: str
    scene_suite_manifest_sha256: Digest
    perturbation_protocol_manifest_sha256: Digest
    cases: Annotated[tuple[SceneVariantSuiteEntry, ...], Field(min_length=16, max_length=16)]
    instruction: Annotated[str, Field(min_length=1, max_length=4096)]
    policy_device: Literal["mps"] = "mps"
    planner_device: Literal["mps"] = "mps"
    camera_profile: Literal["overhead1920_wrist480_v1"] = "overhead1920_wrist480_v1"
    wall_timeout_seconds: Literal[1800] = 1800
    step_timeout_seconds: Literal[300] = 300
    max_tokens: Literal[384] = 384
    runtime_sources: dict[str, Digest]
    selection_rule: Literal["evaluate_every_frozen_scene_once_in_declared_order"] = (
        "evaluate_every_frozen_scene_once_in_declared_order"
    )
    scope: Literal["local_arm64_prequalification_before_intel_release"] = (
        "local_arm64_prequalification_before_intel_release"
    )
    intel_validated: Literal[False] = False
    release_success: None = None
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_declaration(self):
        for value in (
            self.workflow_manifest,
            self.planner_model_root,
            self.scene_suite_run,
        ):
            if not value or Path(value).is_absolute():
                raise ValueError("Release source paths must be relative to the protocol")
        if len({case.case_id for case in self.cases}) != 16:
            raise ValueError("Release protocol requires sixteen unique frozen scene cases")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Workflow release protocol body seal mismatch")
        return self


def create_workflow_release_protocol(
    *,
    workflow_manifest: Path,
    planner_model_root: Path,
    scene_suite_run: Path,
    perturbation_protocol_path: Path,
    instruction: str,
    destination: Path,
) -> WorkflowReleaseProtocol:
    """Freeze a candidate and every local release input before evaluation."""
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Workflow release protocol already exists")
    workflow_manifest = workflow_manifest.resolve(strict=True)
    planner_model_root = planner_model_root.resolve(strict=True)
    scene_suite_run = scene_suite_run.resolve(strict=True)
    perturbation_protocol_path = perturbation_protocol_path.resolve(strict=True)
    workflow = load_workflow_manifest(workflow_manifest)
    if (
        tuple(binding.view.skill_id for binding in workflow.bindings) != SKILLS
        or workflow.manifest.execution is None
        or tuple(row.skill_id for row in workflow.manifest.execution) != SKILLS
        or workflow.manifest.execution_profile_sha256 is None
    ):
        raise ValueError("Release candidate lacks the canonical seven-skill execution profile")
    model = verify_model(planner_model_root)
    scene_manifest, scene_index = load_scene_variant_suite(
        scene_suite_run, protocol_path=perturbation_protocol_path
    )
    body = {
        "schema_version": 1,
        "profile": "local_dinner_workflow_release_protocol_v1",
        "workflow_manifest": os.path.relpath(workflow_manifest, destination.parent),
        "workflow_manifest_file_sha256": digest_file(workflow_manifest),
        "workflow_manifest_sha256": workflow.manifest.manifest_sha256,
        "execution_profile_sha256": workflow.manifest.execution_profile_sha256,
        "planner_model_root": os.path.relpath(planner_model_root, destination.parent),
        "planner_model_manifest_file_sha256": digest_file(
            planner_model_root / "model-manifest.json"
        ),
        "planner_model_revision": model["revision"],
        "scene_suite_run": os.path.relpath(scene_suite_run, destination.parent),
        "scene_suite_manifest_sha256": scene_manifest.manifest_sha256,
        "perturbation_protocol_manifest_sha256": scene_index.protocol_manifest_sha256,
        "cases": [entry.model_dump(mode="json") for entry in scene_index.entries],
        "instruction": instruction,
        "policy_device": "mps",
        "planner_device": "mps",
        "camera_profile": "overhead1920_wrist480_v1",
        "wall_timeout_seconds": 1800,
        "step_timeout_seconds": 300,
        "max_tokens": 384,
        "runtime_sources": _runtime_sources(),
        "selection_rule": "evaluate_every_frozen_scene_once_in_declared_order",
        "scope": "local_arm64_prequalification_before_intel_release",
        "intel_validated": False,
        "release_success": None,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = WorkflowReleaseProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_workflow_release_protocol(path: Path) -> WorkflowReleaseProtocol:
    path = path.resolve(strict=True)
    protocol = WorkflowReleaseProtocol.model_validate_json(path.read_bytes())
    workflow_path = (path.parent / protocol.workflow_manifest).resolve(strict=True)
    workflow = load_workflow_manifest(workflow_path)
    if (
        digest_file(workflow_path) != protocol.workflow_manifest_file_sha256
        or workflow.manifest.manifest_sha256 != protocol.workflow_manifest_sha256
        or workflow.manifest.execution_profile_sha256 != protocol.execution_profile_sha256
    ):
        raise ValueError("Frozen release workflow candidate changed")
    model_root = (path.parent / protocol.planner_model_root).resolve(strict=True)
    model = verify_model(model_root)
    if (
        digest_file(model_root / "model-manifest.json")
        != protocol.planner_model_manifest_file_sha256
        or model["revision"] != protocol.planner_model_revision
    ):
        raise ValueError("Frozen release planner model changed")
    suite_root = (path.parent / protocol.scene_suite_run).resolve(strict=True)
    copied_perturbation_protocol = suite_root / "protocol.json"
    scene_manifest, scene_index = load_scene_variant_suite(
        suite_root, protocol_path=copied_perturbation_protocol
    )
    if (
        scene_manifest.manifest_sha256 != protocol.scene_suite_manifest_sha256
        or scene_index.protocol_manifest_sha256 != protocol.perturbation_protocol_manifest_sha256
        or scene_index.entries != protocol.cases
    ):
        raise ValueError("Frozen release scene suite changed")
    if _runtime_sources() != protocol.runtime_sources:
        raise ValueError("Release runtime sources changed after protocol freeze")
    return protocol
