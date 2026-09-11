"""Spawned workflow ownership with bounded stop escalation and separate parent evidence."""

from __future__ import annotations

import json
import multiprocessing as mp
import multiprocessing.spawn
import os
import platform
import signal
import sys
import time
import traceback
from collections.abc import Callable
from multiprocessing.connection import wait
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bimanual.evidence import EvidenceStore, Manifest, canonical, provenance
from bimanual.workflow_execution import WorkflowExecutionConfig, run_workflow_execution
from bimanual.workflow_manifest import WorkflowManifest
from bimanual.workflow_progress import read_progress


class _PinnedGuardian(mp.context.SpawnProcess):
    """Python 3.12 spawn owner immune to multiprocessing's implicit child reaping.

    Install suppression before BaseProcess.start registers the child. Detachment
    alone has a race with another thread's already-created _cleanup iterator.
    """

    @staticmethod
    def _Popen(process_obj):
        if sys.version_info[:2] != (3, 12):
            raise RuntimeError("Guardian PID pin requires validated Python 3.12 multiprocessing")
        popen = mp.context.SpawnProcess._Popen(process_obj)
        if not callable(getattr(popen, "poll", None)):
            raise RuntimeError("Unsupported spawn process handle")
        popen._guardian_original_poll = popen.poll
        popen.poll = lambda flag=os.WNOHANG: None
        return popen

    def start(self):
        super().start()
        mp.process._children.discard(self)

    def authorize_reap(self):
        self._popen.poll = self._popen._guardian_original_poll


class WorkflowProcessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    execution: WorkflowExecutionConfig
    cancellation_grace_seconds: float = Field(default=2.0, ge=0, le=60)
    terminate_grace_seconds: float = Field(default=1.0, gt=0, le=30)
    poll_interval_seconds: float = Field(default=0.05, gt=0, le=1)


def _owner_cancelled(event, parent) -> bool:
    """Use the spawn parent's process handle, not a potentially reused PID."""
    return event.is_set() or (parent is not None and not parent.is_alive())


def _child(config_data, child_root, project_root, event, sender, interpreter, entrypoint):
    """Only this child owns the simulation. Pipe messages never constitute success."""

    def notify(message):
        try:
            sender.send(message)
        except (BrokenPipeError, EOFError):
            # Parent loss must not prevent preservation of the child's sealed result.
            pass

    try:
        # Spawn does not inherit Python redirect_stdout. Redirect the descriptor
        # too, so native library progress cannot mix with the parent's CLI JSON.
        os.dup2(2, 1)
        sys.stdout = sys.stderr
        if Path(sys.executable).resolve() != Path(interpreter).resolve():
            raise RuntimeError("Spawned interpreter differs from the verified parent")
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            raise RuntimeError("Spawned local runtime must be native ARM64")
        config = WorkflowExecutionConfig.model_validate(config_data)
        parent = mp.parent_process()
        result = entrypoint(
            config,
            store=EvidenceStore(Path(child_root)),
            project_root=Path(project_root),
            cancelled=lambda: _owner_cancelled(event, parent),
        )
        notify({"run_id": result.run_id})
    except BaseException:
        notify({"error": traceback.format_exc()[-8192:]})
    finally:
        sender.close()


def _confine(execution: WorkflowExecutionConfig, root: Path):
    """Check immutable declarations before allocating parent or child output."""
    roots = [execution.planner_model_directory]
    try:
        manifest = WorkflowManifest.model_validate_json(execution.workflow_manifest.read_bytes())
    except (OSError, ValueError):
        manifest = None
    if manifest is not None:
        base = execution.workflow_manifest.parent
        roots += [(base / manifest.dataset_root).resolve()]
        roots += [(base / item.training_run).resolve() for item in manifest.checkpoints]
        roots += [
            (base / item.corrective_dataset_root).resolve()
            for item in manifest.checkpoints
            if getattr(item, "corrective_dataset_root", None) is not None
        ]
    if any(root.is_relative_to(path) for path in roots):
        raise ValueError(
            "Process evidence store must be outside immutable model/dataset/checkpoint sources"
        )


def run_workflow_process(
    config: WorkflowProcessConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
    on_progress: Callable[[dict], None] | None = None,
    _entrypoint: Callable = run_workflow_execution,
) -> Manifest:
    """Synchronous supervisor suitable for an API background job or CLI.

    Cancellation/overall deadline has bounded grace in addition to the requested
    wall budget; parent evidence hashing/sealing occurs after the child is reaped.
    A killed native call cannot finish worker cleanup, so partial files are retained
    as interrupted evidence. The parent never edits a child manifest or artifacts.
    A separate guardian handles root loss; independent process trees remain unsupported.
    Entry points may use threads but must not create independently owned subprocesses.
    """
    # Revalidate even model_construct/model_copy inputs before any child/output.
    config = WorkflowProcessConfig.model_validate(config.model_dump(mode="json"))
    project_root = Path(project_root).resolve()
    execution = config.execution.model_copy(
        update={
            "workflow_manifest": (project_root / config.execution.workflow_manifest).resolve(),
            "planner_model_directory": (
                project_root / config.execution.planner_model_directory
            ).resolve(),
        }
    )
    config = config.model_copy(update={"execution": execution})
    interpreter = Path(sys.executable)
    if (
        not interpreter.is_file()
        or Path(os.fsdecode(mp.spawn.get_executable())).resolve() != interpreter.resolve()
        or platform.system() == "Darwin"
        and platform.machine() != "arm64"
    ):
        raise RuntimeError("Spawn requires the current verified native interpreter")
    _confine(execution, store.root)
    directory = store.new_run()
    source = provenance(project_root)
    started = time.monotonic()
    deadline = started + execution.wall_timeout_seconds
    child_store = EvidenceStore(directory / "child-evidence")
    process = None
    guardian_root = directory / "guardian"
    from bimanual.worker_lease import MODEL_JOB_LEASE

    lease_path = store.root / MODEL_JOB_LEASE
    cleanup_lease = None
    cancellation = None
    message = None
    reason = None
    metrics = dict(
        state="initializing",
        execution_complete=False,
        independent_task_success=None,
        forced_interruption=False,
        terminate_sent=False,
        kill_sent=False,
        child_reaped=False,
        child_pid=None,
        child_exitcode=None,
        child_run_id=None,
        child_manifest_verified=False,
        child_manifest_sha256=None,
        child_outcome=None,
        interpreter=str(interpreter),
        start_method="spawn",
        child_stdout_redirected_to_stderr=True,
        backend="workflow_execution"
        if _entrypoint is run_workflow_execution
        else "injected_test_entrypoint",
        guardian_pid=None,
        guardian_exitcode=None,
        guardian_reaped=False,
        guardian_terminal_verified=False,
        guardian_group_cleanup=False,
        limits="POSIX guardian covers root loss; independent subprocess trees are unsupported",
    )

    def record(kind, **details):
        with (directory / "process-events.jsonl").open("ab") as stream:
            stream.write(
                canonical(dict(event=kind, elapsed_seconds=time.monotonic() - started, **details))
                + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def exited(timeout=0):
        # Process.is_alive/exitcode/join can reap the guardian and release its PID.
        # Keep it unreaped until fallback process-group cleanup is complete.
        return bool(wait([process.sentinel], timeout=timeout))

    def read_json(path):
        with path.open("rb") as stream:
            payload = stream.read(65537)
        if len(payload) > 65536:
            raise ValueError("Oversized guardian journal")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Guardian journal must be an object")
        canonical(value)
        return value

    def group_owned():
        try:
            return os.getpgid(process.pid) == process.pid and os.getsid(process.pid) == process.pid
        except ProcessLookupError:
            # Unreaped direct-child PID cannot have been reused. Readiness was
            # written only after setsid, before any worker could be started.
            try:
                ready = read_json(guardian_root / "ready.json")
                return ready == dict(
                    guardian_pid=process.pid, process_group=process.pid, session=process.pid
                )
            except (OSError, ValueError):
                return False

    def settle_guardian():
        nonlocal cleanup_lease, message, reason
        cancellation.set()
        grace = config.cancellation_grace_seconds + 2 * config.terminate_grace_seconds + 1.0
        exited(grace)
        terminal = None
        if exited():
            try:
                terminal = read_json(guardian_root / "terminal.json")
                worker_pid = terminal.get("worker_pid")
                if (
                    type(terminal.get("guardian_pid")) is not int
                    or terminal["guardian_pid"] != process.pid
                    or any(
                        type(terminal.get(key)) is not bool
                        for key in (
                            "worker_reaped",
                            "forced_interruption",
                            "terminate_sent",
                            "kill_sent",
                        )
                    )
                    or terminal.get("reason")
                    not in {"worker_exited", "cancelled", "timed_out", "parent_lost", "failed"}
                    or (
                        worker_pid is not None
                        and (
                            type(worker_pid) is not int
                            or worker_pid <= 0
                            or terminal.get("worker_reaped") is not True
                            or type(terminal.get("worker_exitcode")) is not int
                            or read_json(guardian_root / "worker.json").get("worker_pid")
                            != worker_pid
                        )
                    )
                ):
                    raise ValueError("Guardian did not certify worker reap")
            except (OSError, ValueError):
                terminal = None
        if terminal is None:
            # A crash or stuck guardian must not strand its native worker. Group
            # signal is safe only while this direct-child leader is unreaped.
            if not group_owned():
                if not exited():
                    # Before setsid there is no worker; signal only our direct child.
                    process.kill()
                    if not exited(config.terminate_grace_seconds):
                        raise RuntimeError(
                            "Guardian cleanup unconfirmed; evidence remains unsealed"
                        )
                # Without proven dedicated group ownership, readiness absence
                # does not prove that a worker was never started.
                raise RuntimeError(
                    "Guardian group ownership unconfirmed; evidence remains unsealed"
                )
            metrics.update(forced_interruption=True, kill_sent=True)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as error:
                # Some kernels/sandboxes reject signaling an already-dead group.
                # This is not cleanup proof: require the guardian sentinel and
                # exclusive worker lease below, or leave the run unsealed.
                metrics["group_signal_error"] = str(error)
            if not exited(config.terminate_grace_seconds):
                raise RuntimeError("Guardian group exit unconfirmed; evidence remains unsealed")
            until = time.monotonic() + config.terminate_grace_seconds
            while True:
                try:
                    cleanup_lease = WorkerLease.acquire(lease_path)
                    break
                except RuntimeError:
                    if time.monotonic() >= until:
                        raise RuntimeError(
                            "Worker lease remains held; evidence remains unsealed"
                        ) from None
                    time.sleep(config.poll_interval_seconds)
            metrics["guardian_group_cleanup"] = True
            reason = reason or "failed"
            try:
                metrics["child_pid"] = read_json(guardian_root / "worker.json").get("worker_pid")
            except (OSError, ValueError):
                pass
            try:
                message = read_json(guardian_root / "worker-result.json")
            except (OSError, ValueError):
                pass
        else:
            metrics.update(
                guardian_terminal_verified=True,
                child_pid=terminal.get("worker_pid"),
                child_reaped=terminal.get("worker_reaped") is True,
                child_exitcode=terminal.get("worker_exitcode"),
                forced_interruption=terminal.get("forced_interruption") is True,
                terminate_sent=terminal.get("terminate_sent") is True,
                kill_sent=terminal.get("kill_sent") is True,
            )
            message = terminal.get("child_message")
            if terminal.get("reason") != "worker_exited":
                reason = reason or terminal.get("reason", "failed")
        process.authorize_reap()
        process.join()
        metrics.update(guardian_reaped=True, guardian_exitcode=process.exitcode)
        if process.exitcode != 0:
            reason = reason or "failed"
        process.close()

    from bimanual.worker_lease import WorkerLease
    from bimanual.workflow_guardian import guardian_entry

    try:
        if os.name != "posix":
            raise RuntimeError("Workflow guardian requires POSIX")
        (directory / "config.json").write_bytes(canonical(config.model_dump(mode="json")))
        if cancelled():
            reason = "cancelled"
        else:
            context = mp.get_context("spawn")
            cancellation = context.Event()
            process = _PinnedGuardian(
                target=guardian_entry,
                args=(
                    execution.model_dump(mode="json"),
                    str(child_store.root),
                    str(guardian_root),
                    str(project_root),
                    cancellation,
                    str(interpreter),
                    _entrypoint,
                    deadline,
                    config.cancellation_grace_seconds,
                    config.terminate_grace_seconds,
                    config.poll_interval_seconds,
                    str(lease_path),
                ),
                name="bimanual-workflow-guardian",
                daemon=False,
            )
            record("spawn_requested")
            process.start()
            metrics["guardian_pid"] = process.pid
            record("guardian_started", pid=process.pid)
            next_progress = 0.0
            while not exited(config.poll_interval_seconds):
                if cancelled():
                    reason = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    reason = "timed_out"
                    break
                if on_progress is not None and time.monotonic() >= next_progress:
                    next_progress = time.monotonic() + 0.25
                    progress = read_progress(child_store.root)
                    if progress is not None:
                        on_progress(progress)
            if reason is not None:
                record("stop_requested", reason=reason)
    except (Exception, KeyboardInterrupt) as error:
        reason = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(error).__name__}: {error}"
        (directory / "parent-error.txt").write_text(traceback.format_exc())
    finally:
        if process is not None and process.pid is not None:
            settle_guardian()

    try:
        # No child or model thread can write after this point. Only read child artifacts.
        if message is not None:
            (directory / "child-result.json").write_bytes(canonical(message))
        if isinstance(message, dict) and isinstance(message.get("run_id"), str):
            metrics["child_run_id"] = message["run_id"]
            try:
                child = child_store.verify(message["run_id"])
                if (
                    child.kind != "dinner_workflow_execution"
                    or child.config != execution.model_dump(mode="json")
                ):
                    raise ValueError("Child manifest kind/config does not match requested workflow")
                if child.metrics.get("independent_task_success", "missing") is not None:
                    raise ValueError("Child cannot supply independent task certification")
                metrics.update(
                    child_manifest_verified=True,
                    child_manifest_sha256=child.manifest_sha256,
                    child_outcome=child.outcome,
                )
                child_reason = child.metrics.get("reason")
                if isinstance(child_reason, str):
                    metrics["child_reason"] = child_reason[:2048]
                if (
                    reason is None
                    and metrics["child_exitcode"] == 0
                    and metrics["guardian_terminal_verified"]
                    and metrics["guardian_reaped"]
                    and metrics["guardian_exitcode"] == 0
                    and metrics["child_reaped"]
                    and not metrics["forced_interruption"]
                ):
                    complete = (
                        child.outcome == "completed"
                        and child.metrics.get("execution_complete") is True
                        and child.metrics.get("state") == "execution_complete"
                    )
                    if child.outcome == "completed" and not complete:
                        raise ValueError("Child completion contradicts execution state")
                    metrics.update(
                        state="execution_complete" if complete else child.outcome,
                        execution_complete=complete,
                    )
            except (ValueError, OSError, KeyError, TypeError) as error:
                reason = reason or "failed"
                metrics["child_verification_error"] = f"{type(error).__name__}: {error}"
        else:
            reason = reason or "failed"
        if reason is not None or metrics["child_exitcode"] not in (None, 0):
            metrics.update(state=reason or "failed", execution_complete=False)
        if metrics["forced_interruption"]:
            metrics["execution_complete"] = False
        metrics["total_seconds"] = time.monotonic() - started
        record(
            "parent_terminal",
            state=metrics["state"],
            forced_interruption=metrics["forced_interruption"],
        )
        (directory / "metrics.json").write_bytes(canonical(metrics))
        result = store.seal(
            directory,
            kind="dinner_workflow_process",
            outcome="completed" if metrics["execution_complete"] else metrics["state"],
            config=config.model_dump(mode="json"),
            metrics=metrics,
            source=source,
            claims=["Verified child execution completion; independent dinner task scoring not run"]
            if metrics["execution_complete"]
            else [],
        )
        return result
    finally:
        if cleanup_lease is not None:
            cleanup_lease.close()
