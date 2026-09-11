import json

import pytest

from bimanual.workflow_progress import read_progress, write_snapshot


def report():
    return dict(
        workflow_id="w",
        task_id="t",
        state="executing",
        reason="working",
        supervisor_state="running",
        completed_steps=["handoff"],
        attempt_count=1,
        active_attempt_id="a",
        planning_job_id=None,
        execution_complete=False,
        independent_task_success=None,
        recovery_implemented=True,
    )


def test_atomic_display_snapshot_is_explicitly_unverified(tmp_path):
    path = tmp_path / "runs" / "r" / "workflow-snapshot.json"
    path.parent.mkdir(parents=True)
    write_snapshot(path, report())
    result = read_progress(tmp_path)
    assert result["snapshot"]["completed_steps"] == ["handoff"]
    assert result["evidence_verified"] is False
    assert result["task_success_verified"] is False
    assert not path.with_name(path.name + ".tmp").exists()
    updated = report() | {"state": "execution_complete", "execution_complete": True}
    write_snapshot(path, updated)
    assert read_progress(tmp_path)["task_success_verified"] is False


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b" " * 32769,
        json.dumps(report() | {"independent_task_success": True}).encode(),
        json.dumps(report() | {"extra": "not allowed"}).encode(),
    ],
)
def test_bad_snapshot_is_not_progress(tmp_path, content):
    path = tmp_path / "runs" / "r" / "workflow-snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    assert read_progress(tmp_path) is None


def test_ambiguous_or_escaped_snapshot_is_not_progress(tmp_path):
    root = tmp_path / "child"
    first = root / "runs" / "a" / "workflow-snapshot.json"
    first.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(report()))
    first.symlink_to(outside)
    assert read_progress(root) is None
    first.unlink()
    write_snapshot(first, report())
    second = root / "runs" / "b" / "workflow-snapshot.json"
    second.parent.mkdir()
    write_snapshot(second, report())
    assert read_progress(root) is None


def test_nonregular_snapshot_never_blocks_parent(tmp_path):
    import os

    path = tmp_path / "runs" / "r" / "workflow-snapshot.json"
    path.parent.mkdir(parents=True)
    os.mkfifo(path)
    assert read_progress(tmp_path) is None


def test_progress_read_failure_is_absent(tmp_path, monkeypatch):
    from pathlib import Path

    def fail(*args, **kwargs):
        raise OSError("fixture filesystem failure")

    monkeypatch.setattr(Path, "glob", fail)
    assert read_progress(tmp_path) is None
