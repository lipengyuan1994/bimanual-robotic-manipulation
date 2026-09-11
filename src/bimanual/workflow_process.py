"""Spawned workflow ownership with bounded stop escalation and separate parent evidence."""

from __future__ import annotations

import multiprocessing as mp
import multiprocessing.spawn
import os
import platform
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bimanual.evidence import EvidenceStore, Manifest, canonical, provenance
from bimanual.workflow_execution import WorkflowExecutionConfig, run_workflow_execution
from bimanual.workflow_manifest import WorkflowManifest
from bimanual.workflow_progress import read_progress


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
    This is not an OS-crash supervisor or a process-tree manager. Entry points may
    use threads but must not create independently owned subprocesses.
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
    process = receiver = sender = None
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
        limits="Parent OS crash and independent subprocess trees are outside this supervisor",
    )

    def record(kind, **details):
        with (directory / "process-events.jsonl").open("ab") as stream:
            stream.write(
                canonical(dict(event=kind, elapsed_seconds=time.monotonic() - started, **details))
                + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def stop_child():
        if process is None or process.pid is None:
            return
        cancellation.set()
        process.join(config.cancellation_grace_seconds)
        if process.is_alive():
            metrics.update(forced_interruption=True, terminate_sent=True)
            process.terminate()
            process.join(config.terminate_grace_seconds)
        if process.is_alive():
            metrics["kill_sent"] = True
            process.kill()
            process.join(config.terminate_grace_seconds)
        if process.is_alive():
            # Never publish a seal while a surviving child could still mutate it.
            raise RuntimeError("OS did not reap the killed child; parent evidence remains unsealed")

    try:
        (directory / "config.json").write_bytes(canonical(config.model_dump(mode="json")))
        if cancelled():
            reason = "cancelled"
        else:
            context = mp.get_context("spawn")
            cancellation = context.Event()
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(
                target=_child,
                args=(
                    execution.model_dump(mode="json"),
                    str(child_store.root),
                    str(project_root),
                    cancellation,
                    sender,
                    str(interpreter),
                    _entrypoint,
                ),
                name="bimanual-workflow",
                daemon=True,
            )
            record("spawn_requested")
            process.start()
            sender.close()
            metrics["child_pid"] = process.pid
            record("child_started", pid=process.pid)
            next_progress = 0.0
            while process.is_alive():
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
                # Read while the child is alive to avoid blocking its small result send.
                if receiver.poll():
                    try:
                        incoming = receiver.recv()
                    except EOFError:
                        incoming = None
                    if incoming is not None:
                        if message is not None:
                            raise ValueError("Child sent multiple result messages")
                        message = incoming
                process.join(min(config.poll_interval_seconds, max(0, deadline - time.monotonic())))
            if reason is not None:
                cancellation.set()
                record("stop_requested", reason=reason)
                stop_child()
            else:
                process.join()
                if time.monotonic() >= deadline:
                    reason = "timed_out"
            if message is None and receiver.poll():
                try:
                    message = receiver.recv()
                except EOFError:
                    pass
    except (Exception, KeyboardInterrupt) as error:
        reason = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(error).__name__}: {error}"
        (directory / "parent-error.txt").write_text(traceback.format_exc())
    finally:
        # Even persistence/IPC exceptions cannot leave the simulation running.
        if process is not None and process.pid is not None:
            if process.is_alive():
                stop_child()
            process.join()
            metrics.update(child_reaped=True, child_exitcode=process.exitcode)
            process.close()
        for connection in (receiver, sender):
            if connection is not None:
                connection.close()

    # No child or model thread can write after this point. Only read child artifacts.
    if message is not None:
        (directory / "child-result.json").write_bytes(canonical(message))
    if isinstance(message, dict) and isinstance(message.get("run_id"), str):
        metrics["child_run_id"] = message["run_id"]
        try:
            child = child_store.verify(message["run_id"])
            if child.kind != "dinner_workflow_execution" or child.config != execution.model_dump(
                mode="json"
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
            if reason is None and metrics["child_exitcode"] == 0:
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
    return store.seal(
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
