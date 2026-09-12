"""Real spawned CPU-only guardian checks; no models or simulation."""

import ctypes
import json
import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_guardian import guardian_entry


def finished(config, **kwargs):
    return SimpleNamespace(run_id="fixture-result")


def hung(config, *, store, **kwargs):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "native-ready").write_text("ready")
    ctypes.PyDLL(None).sleep(60)  # Retains this worker's GIL during native sleep.


def finished_then_hung(config, **kwargs):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Thread(target=lambda: time.sleep(60), daemon=False).start()
    return SimpleNamespace(run_id="completed-before-hang")


def spawn_guardian(root, entry, *, wall=5, lease_path=None):
    context = mp.get_context("spawn")
    event = context.Event()
    config = WorkflowExecutionConfig(
        workflow_manifest="cohort.json",
        planner_model_directory="model",
        instruction="CPU guardian fixture",
    )
    process = context.Process(
        target=guardian_entry,
        args=(
            config.model_dump(mode="json"),
            str(root / "child"),
            str(root / "guardian"),
            str(root),
            event,
            sys.executable,
            entry,
            time.monotonic() + wall,
            0.1,
            0.15,
            0.01,
            lease_path,
        ),
    )
    process.start()
    return process, event


def wait_file(path, seconds=8):
    deadline = time.monotonic() + seconds
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), str(path)
    return json.loads(path.read_text()) if path.suffix == ".json" else None


def cleanup(process):
    if process.is_alive():
        process.kill()
    process.join(3)


@pytest.mark.parametrize(
    "entry,wall,cancel,reason",
    [
        (finished, 5, False, "worker_exited"),
        (hung, 5, True, "cancelled"),
        (hung, 1.5, False, "timed_out"),
        (finished_then_hung, 1.5, False, "timed_out"),
    ],
)
def test_guardian_outcomes(tmp_path, entry, wall, cancel, reason):
    process, event = spawn_guardian(tmp_path, entry, wall=wall)
    try:
        if cancel:
            wait_file(tmp_path / "child/native-ready")
            event.set()
        terminal = wait_file(tmp_path / "guardian/terminal.json")
        process.join(3)
        assert process.exitcode == 0
        assert terminal["reason"] == reason
        assert terminal["worker_reaped"]
        assert terminal["execution_complete"] is False
        assert terminal["independent_task_success"] is None
        if entry is not finished:
            assert terminal["kill_sent"] and terminal["forced_interruption"]
            assert terminal["worker_exitcode"] == -signal.SIGKILL
        else:
            assert terminal["child_message"] == {"run_id": "fixture-result"}
    finally:
        cleanup(process)


def owner(root):
    process, _ = spawn_guardian(Path(root), hung, wall=15)
    process.join(20)


def test_guardian_reaps_native_hang_after_original_parent_dies(tmp_path):
    process = mp.get_context("spawn").Process(target=owner, args=(str(tmp_path),))
    process.start()
    try:
        wait_file(tmp_path / "child/native-ready")
        process.terminate()
        process.join(3)
        terminal = wait_file(tmp_path / "guardian/terminal.json", seconds=5)
        assert terminal["reason"] == "parent_lost"
        assert terminal["worker_reaped"] and terminal["kill_sent"]
        assert terminal["worker_exitcode"] == -signal.SIGKILL
        with pytest.raises(ProcessLookupError):
            os.kill(terminal["worker_pid"], 0)
    finally:
        cleanup(process)


def test_competing_guardians_cannot_enter_second_worker(tmp_path):
    from bimanual.worker_lease import WorkerLease

    lease_path = tmp_path / "worker.lock"
    first, cancel = spawn_guardian(tmp_path / "first", hung, lease_path=lease_path)
    second = None
    try:
        wait_file(tmp_path / "first/child/native-ready")
        second, _ = spawn_guardian(tmp_path / "second", finished, lease_path=lease_path)
        terminal = wait_file(tmp_path / "second/guardian/terminal.json")
        second.join(3)
        assert terminal["reason"] == "failed"
        assert "still holds this lease" in terminal["error"]
        assert terminal["worker_pid"] is None
        assert not (tmp_path / "second/guardian/worker.json").exists()
        cancel.set()
        first_terminal = wait_file(tmp_path / "first/guardian/terminal.json")
        first.join(3)
        assert first_terminal["worker_reaped"]
        with WorkerLease.acquire(lease_path):
            pass
    finally:
        cancel.set()
        first.join(3)
        cleanup(first)
        if second is not None:
            cleanup(second)


def partial_result_then_hung(config, *, store, **kwargs):
    (store.root.parent / "guardian/worker-result.tmp").write_text('{"run_id":')
    hung(config, store=store, **kwargs)


def test_partial_result_write_cannot_block_deadline(tmp_path):
    process, _ = spawn_guardian(tmp_path, partial_result_then_hung, wall=1.5)
    try:
        terminal = wait_file(tmp_path / "guardian/terminal.json")
        process.join(3)
        assert terminal["reason"] == "timed_out"
        assert terminal["kill_sent"] and terminal["worker_reaped"]
        assert terminal["child_message"] is None
        assert (tmp_path / "guardian/worker-result.tmp").exists()
    finally:
        cleanup(process)


def test_result_publisher_rejects_duplicate_and_oversized_messages(tmp_path):
    from bimanual.workflow_guardian import _FileSender

    sender = _FileSender(tmp_path / "result.json")
    with pytest.raises(ValueError, match="size"):
        sender.send({"error": "x" * 65537})
    sender.send({"run_id": "first"})
    with pytest.raises(ValueError, match="multiple"):
        sender.send({"run_id": "second"})
    assert json.loads((tmp_path / "result.json").read_text()) == {"run_id": "first"}
