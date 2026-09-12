"""Guardian-owned process boundary for one learned physical component evaluation."""

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
from bimanual.skill_physical_evaluation import (
    SkillPhysicalEvaluationConfig,
    run_skill_physical_evaluation,
)
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease
from bimanual.workflow_process import _PinnedGuardian

EVALUATION_KIND = "learned_skill_teacher_prepared_physical_evaluation"
PROCESS_KIND = "learned_skill_teacher_prepared_physical_evaluation_process"


class SkillPhysicalProcessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    evaluation: SkillPhysicalEvaluationConfig
    cancellation_grace_seconds: float = Field(default=2.0, ge=0, le=60)
    terminate_grace_seconds: float = Field(default=1.0, gt=0, le=30)
    poll_interval_seconds: float = Field(default=0.05, gt=0, le=1)


def _owner_cancelled(event, parent) -> bool:
    return event.is_set() or (parent is not None and not parent.is_alive())


def _physical_child(
    config_data,
    child_root,
    project_root,
    event,
    sender,
    interpreter,
    entrypoint,
    lease_path,
):
    """Run the evaluator under the guardian's inherited model-job lease."""

    def notify(message):
        try:
            sender.send(message)
        except (BrokenPipeError, EOFError):
            pass

    try:
        os.dup2(2, 1)
        sys.stdout = sys.stderr
        if Path(sys.executable).resolve() != Path(interpreter).resolve():
            raise RuntimeError("Spawned interpreter differs from the verified parent")
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            raise RuntimeError("Spawned local runtime must be native ARM64")
        config = SkillPhysicalEvaluationConfig.model_validate(config_data)
        from bimanual.workflow_guardian import _worker_lease

        if _worker_lease is None or lease_path is None:
            raise RuntimeError("Physical evaluator requires the guardian model-job lease")
        result = entrypoint(
            config,
            store=EvidenceStore(Path(child_root)),
            project_root=Path(project_root),
            cancelled=lambda: _owner_cancelled(event, mp.parent_process()),
            model_job_lease=_worker_lease,
            model_job_lease_path=Path(lease_path),
        )
        notify({"run_id": result.run_id})
    except BaseException:
        notify({"error": traceback.format_exc()[-8192:]})
    finally:
        sender.close()


def _resolve(config: SkillPhysicalProcessConfig, project_root: Path):
    evaluation = config.evaluation.model_copy(
        update={
            "training_run": (project_root / config.evaluation.training_run).resolve(),
            "dataset_root": (project_root / config.evaluation.dataset_root).resolve(),
            "skill_views_path": (project_root / config.evaluation.skill_views_path).resolve(),
        }
    )
    return config.model_copy(update={"evaluation": evaluation})


def _confine(config: SkillPhysicalProcessConfig, store: EvidenceStore):
    if any(
        store.root.is_relative_to(source)
        for source in (
            config.evaluation.training_run,
            config.evaluation.dataset_root,
            config.evaluation.skill_views_path,
        )
    ):
        raise ValueError("Process evidence must be outside immutable evaluation sources")


def run_skill_physical_process(
    config: SkillPhysicalProcessConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
    _entrypoint: Callable = run_skill_physical_evaluation,
) -> Manifest:
    """Run one evaluation with bounded cancellation, timeout and parent-loss cleanup."""

    config = SkillPhysicalProcessConfig.model_validate(config.model_dump(mode="json"))
    project_root = Path(project_root).resolve()
    config = _resolve(config, project_root)
    interpreter = Path(sys.executable)
    if (
        not interpreter.is_file()
        or Path(os.fsdecode(mp.spawn.get_executable())).resolve() != interpreter.resolve()
        or platform.system() == "Darwin"
        and platform.machine() != "arm64"
    ):
        raise RuntimeError("Spawn requires the current verified native interpreter")
    _confine(config, store)
    store.root.mkdir(parents=True, exist_ok=True)
    lease_path = store.root / MODEL_JOB_LEASE
    prestart_cancelled = cancelled()
    # A busy worker is not an evaluation attempt. Reserve the shared lease before
    # allocating evidence, then transfer the same descriptor through the guardian.
    parent_lease = None if prestart_cancelled else WorkerLease.acquire(lease_path)
    try:
        directory = store.new_run()
        source = provenance(project_root)
    except BaseException:
        if parent_lease is not None:
            parent_lease.close()
        raise
    started = time.monotonic()
    deadline = started + config.evaluation.wall_timeout_seconds
    guardian_root = directory / "guardian"
    cleanup_lease = None
    cancellation = None
    process = None
    message = None
    reason = None
    metrics = {
        "state": "initializing",
        "process_complete": False,
        "component_passed": False,
        "independent_task_success": None,
        "autonomous_workflow_success": None,
        "release_qualified": False,
        "forced_interruption": False,
        "terminate_sent": False,
        "kill_sent": False,
        "child_reaped": False,
        "child_pid": None,
        "child_exitcode": None,
        "child_run_id": None,
        "child_manifest_verified": False,
        "child_manifest_sha256": None,
        "child_outcome": None,
        "interpreter": str(interpreter),
        "start_method": "spawn",
        "guardian_pid": None,
        "guardian_exitcode": None,
        "guardian_reaped": False,
        "guardian_terminal_verified": False,
        "guardian_group_cleanup": False,
    }

    def record(kind, **details):
        with (directory / "process-events.jsonl").open("ab") as stream:
            stream.write(
                canonical({"event": kind, "elapsed_seconds": time.monotonic() - started, **details})
                + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def exited(timeout=0):
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
            try:
                ready = read_json(guardian_root / "ready.json")
                return ready == {
                    "guardian_pid": process.pid,
                    "process_group": process.pid,
                    "session": process.pid,
                }
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
            if not group_owned():
                if not exited():
                    process.kill()
                    if not exited(config.terminate_grace_seconds):
                        raise RuntimeError(
                            "Guardian cleanup unconfirmed; evidence remains unsealed"
                        )
                raise RuntimeError(
                    "Guardian group ownership unconfirmed; evidence remains unsealed"
                )
            metrics.update(forced_interruption=True, kill_sent=True)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as error:
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

    from bimanual.workflow_guardian import guardian_entry

    try:
        if os.name != "posix":
            raise RuntimeError("Physical evaluation guardian requires POSIX")
        (directory / "config.json").write_bytes(canonical(config.model_dump(mode="json")))
        if prestart_cancelled or cancelled():
            reason = "cancelled"
        else:
            context = mp.get_context("spawn")
            cancellation = context.Event()
            process = _PinnedGuardian(
                target=guardian_entry,
                args=(
                    config.evaluation.model_dump(mode="json"),
                    str(store.root),
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
                    _physical_child,
                    parent_lease.export_for_spawn(),
                ),
                name="bimanual-skill-physical-guardian",
                daemon=False,
            )
            record("spawn_requested")
            process.start()
            # spawn serialization has transferred a duplicate to the guardian.
            parent_lease.close()
            parent_lease = None
            metrics["guardian_pid"] = process.pid
            record("guardian_started", pid=process.pid)
            while not exited(config.poll_interval_seconds):
                if cancelled():
                    reason = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    reason = "timed_out"
                    break
            if reason is not None:
                record("stop_requested", reason=reason)
    except (Exception, KeyboardInterrupt) as error:
        reason = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(error).__name__}: {error}"
        (directory / "parent-error.txt").write_text(traceback.format_exc())
    finally:
        if process is not None and process.pid is not None:
            settle_guardian()
        if parent_lease is not None:
            parent_lease.close()

    try:
        if message is not None:
            (directory / "child-result.json").write_bytes(canonical(message))
        if isinstance(message, dict) and isinstance(message.get("run_id"), str):
            metrics["child_run_id"] = message["run_id"]
            try:
                child = store.verify(message["run_id"])
                if child.kind != EVALUATION_KIND or child.config != config.evaluation.model_dump(
                    mode="json"
                ):
                    raise ValueError("Child manifest kind/config does not match evaluation")
                if (
                    child.metrics.get("independent_task_success", "missing") is not None
                    or child.metrics.get("autonomous_workflow_success", "missing") is not None
                    or child.metrics.get("release_qualified") is not False
                ):
                    raise ValueError("Child physical result exceeds its component scope")
                passed = child.metrics.get("component_passed") is True
                if (child.outcome == "completed") != passed:
                    raise ValueError("Child outcome contradicts component result")
                metrics.update(
                    child_manifest_verified=True,
                    child_manifest_sha256=child.manifest_sha256,
                    child_outcome=child.outcome,
                    component_passed=passed,
                )
                if (
                    reason is None
                    and metrics["child_exitcode"] == 0
                    and metrics["guardian_terminal_verified"]
                    and metrics["guardian_reaped"]
                    and metrics["guardian_exitcode"] == 0
                    and metrics["child_reaped"]
                    and not metrics["forced_interruption"]
                ):
                    metrics.update(state=child.outcome, process_complete=True)
            except (ValueError, OSError, KeyError, TypeError) as error:
                reason = reason or "failed"
                metrics["child_verification_error"] = f"{type(error).__name__}: {error}"
        else:
            reason = reason or "failed"
        if reason is not None or metrics["child_exitcode"] not in (None, 0):
            metrics.update(state=reason or "failed", process_complete=False, component_passed=False)
        if metrics["forced_interruption"]:
            metrics.update(process_complete=False, component_passed=False)
        metrics["total_seconds"] = time.monotonic() - started
        record(
            "parent_terminal", state=metrics["state"], process_complete=metrics["process_complete"]
        )
        (directory / "metrics.json").write_bytes(canonical(metrics))
        return store.seal(
            directory,
            kind=PROCESS_KIND,
            outcome=metrics["child_outcome"] if metrics["process_complete"] else metrics["state"],
            config=config.model_dump(mode="json"),
            metrics=metrics,
            source=source,
            claims=(
                ["Verified bounded process completion for one component evaluation"]
                if metrics["process_complete"]
                else []
            ),
        )
    finally:
        if cleanup_lease is not None:
            cleanup_lease.close()
