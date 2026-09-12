"""Bounded real-process parent-loss check; no robot or model is loaded."""

import multiprocessing as mp
import sys
import time
from pathlib import Path

from bimanual.evidence import EvidenceStore
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_process import _child, _owner_cancelled


def _cooperative_entry(config, *, store, cancelled, **kwargs):
    root = store.root
    (root / "ready").write_text("ready")
    deadline = time.monotonic() + 10
    while not cancelled() and time.monotonic() < deadline:
        time.sleep(0.01)
    state = "cancelled" if cancelled() else "failed"
    directory = store.new_run()
    return store.seal(
        directory,
        kind="dinner_workflow_execution",
        outcome=state,
        config={},
        metrics={"state": state, "independent_task_success": None},
        source={},
        claims=[],
    )


def _watch_owner(root, sender, event):
    config = WorkflowExecutionConfig(
        workflow_manifest="cohort.json",
        planner_model_directory="model",
        instruction="CPU parent-loss fixture",
    )
    _child(
        config.model_dump(mode="json"),
        root,
        root,
        event,
        sender,
        sys.executable,
        _cooperative_entry,
    )
    Path(root, "finished").write_text("worker returned after sealing")


def _owner(root):
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    event = context.Event()
    child = context.Process(target=_watch_owner, args=(root, sender, event))
    child.start()
    sender.close()
    child.join(12)
    receiver.close()


def test_real_parent_exit_revokes_cooperative_authority(tmp_path):
    owner = mp.get_context("spawn").Process(target=_owner, args=(str(tmp_path),))
    owner.start()
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "ready").exists()
        assert not (tmp_path / "finished").exists()
        owner.terminate()
        owner.join(3)
        assert not owner.is_alive()
        deadline = time.monotonic() + 5
        while not (tmp_path / "finished").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "finished").exists()
        manifests = list((tmp_path / "runs").glob("*/manifest.json"))
        assert len(manifests) == 1
        result = EvidenceStore(tmp_path).verify(manifests[0].parent.name)
        assert result.outcome == "cancelled"
        assert result.metrics["independent_task_success"] is None
    finally:
        if owner.is_alive():
            owner.kill()
        owner.join(3)


def test_explicit_cancel_without_spawn_parent():
    event = mp.get_context("spawn").Event()
    assert not _owner_cancelled(event, None)
    event.set()
    assert _owner_cancelled(event, None)
