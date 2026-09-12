"""Host-local, fail-closed activation history for verified workflow manifests."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import canonical
from bimanual.worker_lease import WorkerLease
from bimanual.workflow_manifest import load_workflow_manifest

PROFILE = "local_workflow_deployment_v1"


class WorkflowDeployment(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    profile: Literal["local_workflow_deployment_v1"] = PROFILE
    deployment_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    action: Literal["activate", "rollback"]
    created_at: str = Field(min_length=1)
    workflow_manifest: str = Field(min_length=1)
    workflow_file_sha256: Digest
    workflow_manifest_sha256: Digest
    previous_deployment_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    previous_record_sha256: Digest | None = None
    rollback_target_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    rollback_target_record_sha256: Digest | None = None
    learned_workflow_success: None = None
    release_qualified: bool = False
    intel_validated: bool = False
    record_sha256: Digest

    @model_validator(mode="after")
    def valid_seal_and_links(self):
        body = self.model_dump(mode="json", exclude={"record_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.record_sha256:
            raise ValueError("Deployment record seal mismatch")
        if (self.previous_deployment_id is None) != (self.previous_record_sha256 is None):
            raise ValueError("Previous deployment identity and seal must be paired")
        rollback = self.action == "rollback"
        if rollback != (
            self.rollback_target_id is not None and self.rollback_target_record_sha256 is not None
        ):
            raise ValueError("Rollback target identity and seal disagree with action")
        return self


def _read_regular_json(path: Path, *, limit: int = 65536) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Deployment record must be a regular file")
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Deployment record is oversized")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Deployment record must be an object")
    canonical(value)
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _replace_pointer(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _paths(root: Path) -> tuple[Path, Path]:
    resolved = Path(root).resolve()
    return resolved / "deployments", resolved / "current.json"


def _load_record(directory: Path, deployment_id: str) -> WorkflowDeployment:
    if len(deployment_id) != 32 or any(c not in "0123456789abcdef" for c in deployment_id):
        raise ValueError("Invalid deployment id")
    record = WorkflowDeployment.model_validate(
        _read_regular_json(directory / f"{deployment_id}.json")
    )
    if record.deployment_id != deployment_id:
        raise ValueError("Deployment filename and identity disagree")
    return record


def _reverify(record: WorkflowDeployment) -> None:
    verified = load_workflow_manifest(Path(record.workflow_manifest))
    if (
        verified.file_sha256 != record.workflow_file_sha256
        or verified.manifest.manifest_sha256 != record.workflow_manifest_sha256
    ):
        raise ValueError("Active workflow manifest changed after deployment")


def _create_record(**fields) -> WorkflowDeployment:
    unsealed = WorkflowDeployment.model_construct(
        schema_version=1, record_sha256="0" * 64, **fields
    )
    body = unsealed.model_dump(mode="json", exclude={"record_sha256"})
    return WorkflowDeployment.model_validate(
        body | {"record_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )


def load_active_workflow(root: Path) -> WorkflowDeployment | None:
    """Return the active identity only after reverifying its full checkpoint lineage."""
    directory, pointer_path = _paths(root)
    if not pointer_path.exists():
        if directory.exists() and any(directory.iterdir()):
            raise RuntimeError("Prepared deployment exists without an active pointer")
        return None
    pointer = _read_regular_json(pointer_path, limit=1024)
    if (
        set(pointer) != {"profile", "deployment_id", "record_sha256"}
        or pointer["profile"] != PROFILE
    ):
        raise ValueError("Active deployment pointer is invalid")
    record = _load_record(directory, pointer["deployment_id"])
    if pointer["record_sha256"] != record.record_sha256:
        raise ValueError("Active pointer and deployment record seal disagree")
    _reverify(record)
    return record


def _publish(root: Path, record: WorkflowDeployment) -> WorkflowDeployment:
    directory, pointer_path = _paths(root)
    directory.mkdir(parents=True, exist_ok=True)
    _write_once(directory / f"{record.deployment_id}.json", record.model_dump(mode="json"))
    _replace_pointer(
        pointer_path,
        {
            "profile": PROFILE,
            "deployment_id": record.deployment_id,
            "record_sha256": record.record_sha256,
        },
    )
    return load_active_workflow(root)  # type: ignore[return-value]


def activate_workflow(workflow_manifest: Path, root: Path) -> WorkflowDeployment:
    """Activate a manifest only after full lineage verification; never load a model."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(root / ".deployment.lock"):
        current = load_active_workflow(root)
        verified = load_workflow_manifest(Path(workflow_manifest))
        if current is not None and current.workflow_file_sha256 == verified.file_sha256:
            return current
        record = _create_record(
            deployment_id=uuid4().hex,
            action="activate",
            created_at=datetime.now(UTC).isoformat(),
            workflow_manifest=str(verified.path),
            workflow_file_sha256=verified.file_sha256,
            workflow_manifest_sha256=verified.manifest.manifest_sha256,
            previous_deployment_id=current.deployment_id if current is not None else None,
            previous_record_sha256=current.record_sha256 if current is not None else None,
        )
        return _publish(root, record)


def rollback_workflow(root: Path, target_id: str | None = None) -> WorkflowDeployment:
    """Create a new activation pointing to a previously recorded, still-verifiable manifest."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(root / ".deployment.lock"):
        current = load_active_workflow(root)
        if current is None:
            raise RuntimeError("No active workflow can be rolled back")
        selected = target_id or current.previous_deployment_id
        if selected is None:
            raise RuntimeError("Active workflow has no previous deployment")
        if selected == current.deployment_id:
            raise ValueError("Rollback target is already active")
        directory, _ = _paths(root)
        target = _load_record(directory, selected)
        _reverify(target)
        record = _create_record(
            deployment_id=uuid4().hex,
            action="rollback",
            created_at=datetime.now(UTC).isoformat(),
            workflow_manifest=target.workflow_manifest,
            workflow_file_sha256=target.workflow_file_sha256,
            workflow_manifest_sha256=target.workflow_manifest_sha256,
            previous_deployment_id=current.deployment_id,
            previous_record_sha256=current.record_sha256,
            rollback_target_id=target.deployment_id,
            rollback_target_record_sha256=target.record_sha256,
        )
        return _publish(root, record)


def deployment_report(record: WorkflowDeployment | None) -> dict:
    if record is None:
        return {"profile": PROFILE, "active": None, "model_loaded": False}
    return {
        "profile": PROFILE,
        "active": record.model_dump(mode="json"),
        "model_loaded": False,
        "scope": "Verified local activation identity; physical and release quality are unchanged",
    }


def active_workflow_path(root: Path) -> Path:
    record = load_active_workflow(root)
    if record is None:
        raise RuntimeError("No active workflow is deployed")
    return Path(record.workflow_manifest)
