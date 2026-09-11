"""Unsealed, display-only workflow progress. Never used to authorize robot actions."""

from __future__ import annotations

import json
import os
import stat
from itertools import islice
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bimanual.camera_preview import read_camera_preview
from bimanual.evidence import canonical


class DisplayProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    workflow_id: str
    task_id: str | None
    state: str
    reason: str
    supervisor_state: str
    completed_steps: tuple[str, ...]
    attempt_count: int = Field(ge=0)
    active_attempt_id: str | None
    planning_job_id: str | None
    execution_complete: bool
    independent_task_success: None = None
    recovery_implemented: bool = True


def write_snapshot(path: Path, report: dict) -> None:
    """Replace the current snapshot atomically so a reader never sees half a JSON."""
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(canonical(report))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_progress(child_root: Path) -> dict | None:
    """Read only one worker's bounded snapshot; malformed/ambiguous state is absent.

    This is intentionally not evidence verification. Every returned payload is
    explicitly unverified, even when it describes execution completion.
    """
    try:
        paths = list(islice((child_root / "runs").glob("*/workflow-snapshot.json"), 2))
        if len(paths) != 1:
            return None
        path = paths[0]
        if not path.resolve().is_relative_to(child_root.resolve()):
            return None
        # Progress must not block cancellation on a FIFO or follow a replaced link.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            content = stream.read(32769)
        if len(content) > 32768:
            return None
        report = DisplayProgress.model_validate_json(content)
    except (OSError, ValueError, RuntimeError):
        return None
    return {
        "snapshot": json.loads(report.model_dump_json()),
        "camera_preview": read_camera_preview(path.parent / "worker"),
        "evidence_verified": False,
        "task_success_verified": False,
    }
