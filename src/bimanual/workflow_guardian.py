"""Independent worker owner used by the workflow-process supervisor.

The guardian handles root-parent loss even while its worker holds the GIL in a
native call. Guardian loss requires an external process-group cleanup owner; this
module alone does not provide that fallback or certify task success.
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import time
import traceback
from pathlib import Path

from bimanual.evidence import canonical
from bimanual.worker_lease import WorkerLease


def _atomic(path: Path, value: dict):
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class _FileSender:
    """Single worker publishes one bounded result; temporary writes are not messages."""

    def __init__(self, path):
        self.path = Path(path)

    def send(self, value):
        if self.path.exists():
            raise ValueError("Worker sent multiple result messages")
        if len(canonical(value)) > 65536:
            raise ValueError("Worker result exceeds the bounded message size")
        _atomic(self.path, value)

    def close(self):
        pass


# Retain the descriptor through interpreter/thread shutdown, not just _child return.
# A completed entrypoint can leave a non-daemon thread alive; OS exit closes it.
_worker_lease = None


def _leased_child(exported_lease, child_entrypoint, *args):
    global _worker_lease

    if exported_lease is not None:
        _worker_lease = WorkerLease.from_spawn(exported_lease)
    child_entrypoint(*args)


def guardian_entry(
    config_data,
    child_root,
    guardian_root,
    project_root,
    cancellation_event,
    interpreter,
    entrypoint,
    absolute_deadline,
    cancellation_grace,
    terminate_grace,
    poll_interval,
    lease_path=None,
    child_entrypoint=None,
):
    """Own exactly one worker, journal its outcome only after it is reaped.

    Must be a non-daemon spawned process. The caller retains this process unreaped
    when implementing crash fallback. No pipe send to the root can block cleanup.
    """
    root = Path(guardian_root)
    root.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    owner = mp.parent_process()
    worker = None
    lease = None
    message = None
    reason = None
    metrics = dict(
        guardian_pid=os.getpid(),
        worker_pid=None,
        worker_exitcode=None,
        worker_reaped=False,
        forced_interruption=False,
        terminate_sent=False,
        kill_sent=False,
        execution_complete=False,
        independent_task_success=None,
    )

    def record(event, **details):
        with (root / "events.jsonl").open("ab") as stream:
            stream.write(
                canonical(dict(event=event, elapsed_seconds=time.monotonic() - started, **details))
                + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def stop_reason():
        if owner is not None and not owner.is_alive():
            return "parent_lost"
        if cancellation_event.is_set():
            return "cancelled"
        if time.monotonic() >= absolute_deadline:
            return "timed_out"
        return None

    def receive():
        nonlocal message
        path = root / "worker-result.json"
        if message is None and path.exists():
            with path.open("rb") as stream:
                payload = stream.read(65537)
            if len(payload) > 65536:
                raise ValueError("Worker result exceeds the bounded message size")
            value = json.loads(payload)
            if not isinstance(value, dict):
                raise ValueError("Worker result must be an object")
            canonical(value)
            message = value

    def wait_for_exit(seconds):
        deadline = time.monotonic() + seconds
        while worker.is_alive() and time.monotonic() < deadline:
            try:
                receive()
            except Exception as error:
                metrics["ipc_cleanup_error"] = f"{type(error).__name__}: {error}"
            worker.join(min(poll_interval, max(0, deadline - time.monotonic())))

    def stop():
        cancellation_event.set()
        wait_for_exit(cancellation_grace)
        if worker.is_alive():
            metrics.update(forced_interruption=True, terminate_sent=True)
            worker.terminate()
            wait_for_exit(terminate_grace)
        if worker.is_alive():
            metrics["kill_sent"] = True
            worker.kill()
            wait_for_exit(terminate_grace)
        if worker.is_alive():
            raise RuntimeError("Worker remains alive; terminal evidence must not be published")

    try:
        if child_entrypoint is None:
            from bimanual.workflow_process import _child

            child_entrypoint = _child
        if not math.isfinite(absolute_deadline):
            raise ValueError("Guardian deadline must be finite")
        if os.name != "posix":
            raise RuntimeError("Guardian session ownership requires POSIX")
        if (
            not 0 <= cancellation_grace <= 60
            or not 0 < terminate_grace <= 30
            or not 0 < poll_interval <= 1
        ):
            raise ValueError("Invalid guardian stop limits")
        os.setsid()
        _atomic(
            root / "ready.json",
            dict(guardian_pid=os.getpid(), process_group=os.getpgrp(), session=os.getsid(0)),
        )
        reason = stop_reason()
        if reason is None:
            if lease_path is not None:
                lease = WorkerLease.acquire(Path(lease_path))
                record("worker_lease_acquired", path=str(lease_path))
            context = mp.get_context("spawn")
            worker = context.Process(
                target=_leased_child,
                args=(
                    lease.export_for_spawn() if lease is not None else None,
                    child_entrypoint,
                    config_data,
                    child_root,
                    project_root,
                    cancellation_event,
                    _FileSender(root / "worker-result.json"),
                    interpreter,
                    entrypoint,
                    lease_path,
                ),
                daemon=True,
                name="bimanual-guarded-worker",
            )
            worker.start()
            metrics["worker_pid"] = worker.pid
            record("worker_started", pid=worker.pid)
            _atomic(root / "worker.json", dict(worker_pid=worker.pid))
            while worker.is_alive():
                reason = stop_reason()
                if reason is not None:
                    record("stop_requested", reason=reason)
                    break
                receive()
                worker.join(poll_interval)
            if reason is not None:
                stop()
            else:
                worker.join()
                reason = stop_reason()
            receive()
    except BaseException as error:
        reason = "failed"
        metrics["error"] = f"{type(error).__name__}: {error}"
        (root / "error.txt").write_text(traceback.format_exc())
    finally:
        if worker is not None and worker.pid is not None:
            if worker.is_alive():
                stop()
            worker.join()
            metrics.update(worker_reaped=True, worker_exitcode=worker.exitcode)
            worker.close()
        if lease is not None:
            lease.close()
    # No success claim: root must independently verify any returned child manifest.
    metrics.update(
        reason=reason or "worker_exited",
        child_message=message,
        elapsed_seconds=time.monotonic() - started,
    )
    record("guardian_terminal", reason=metrics["reason"], worker_reaped=metrics["worker_reaped"])
    _atomic(root / "terminal.json", metrics)
