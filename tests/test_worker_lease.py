"""Real local process exclusion; no simulation or model initialization."""

import multiprocessing as mp
import os

import pytest

from bimanual.worker_lease import WorkerLease


def _hold(exported, ready, release):
    lease = WorkerLease.from_spawn(exported)
    try:
        ready.set()
        if not release.wait(10):
            raise TimeoutError("Test release was not received")
    finally:
        lease.close()


def test_exclusion_and_reacquisition(tmp_path):
    path = tmp_path / "worker.lock"
    first = WorkerLease.acquire(path)
    try:
        with pytest.raises(RuntimeError, match="still holds"):
            WorkerLease.acquire(path)
    finally:
        first.close()
        first.close()
    with WorkerLease.acquire(path):
        assert path.is_file()
    assert path.is_file()  # Never unlink a lock that another contender may have open.
    with pytest.raises(RuntimeError, match="closed"):
        first.export_for_spawn()


def test_refuses_symlink_without_modifying_target(tmp_path):
    target = tmp_path / "source"
    target.write_text("keep")
    link = tmp_path / "lease"
    link.symlink_to(target)
    with pytest.raises(OSError):
        WorkerLease.acquire(link)
    assert target.read_text() == "keep"


def test_spawn_duplicate_retains_exclusion_after_original_closes(tmp_path):
    path = tmp_path / "worker.lock"
    lease = WorkerLease.acquire(path)
    context = mp.get_context("spawn")
    ready, release = context.Event(), context.Event()
    process = context.Process(target=_hold, args=(lease.export_for_spawn(), ready, release))
    process.start()
    try:
        assert ready.wait(10)
        lease.close()
        with pytest.raises(RuntimeError, match="still holds"):
            WorkerLease.acquire(path)
        release.set()
        process.join(10)
        assert process.exitcode == 0
        with WorkerLease.acquire(path):
            pass
    finally:
        lease.close()
        release.set()
        if process.is_alive():
            process.kill()
        process.join(10)
        process.close()


def test_rejects_nonregular_file(tmp_path):
    path = tmp_path / "pipe"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular"):
        WorkerLease.acquire(path)


def test_pending_transfer_rejects_closed_owner(tmp_path):
    lease = WorkerLease.acquire(tmp_path / "lock")
    exported = lease.export_for_spawn()
    lease.close()
    with pytest.raises(RuntimeError, match="closed before spawn"):
        exported.__reduce__()
