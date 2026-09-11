"""Single local workflow job ownership; finished execution is not task success."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Literal
from uuid import uuid4

from bimanual.evidence import EvidenceStore
from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process


@dataclass(frozen=True)
class OperatorJob:
    job_id: str
    state: Literal["active", "stopping", "finished", "failed", "cancelled", "needs_clarification"]
    instruction: str
    run_id: str | None = None
    run_outcome: str | None = None
    error: str | None = None
    independent_task_success: None = None
    progress: dict | None = None

    def report(self) -> dict:
        return asdict(self)


class OperatorJobs:
    """Server-owned settings; callers can submit instructions and stop their job.

    The background thread owns the existing bounded process runner. Stop requests
    are acknowledged as stopping until that runner returns and its evidence is
    verified. Closing permanently prevents new work. Guardian cleanup covers parent
    loss; reconstructing interrupted jobs and OS crashes remains unsupported.
    """

    def __init__(
        self,
        config: WorkflowProcessConfig,
        *,
        store: EvidenceStore,
        project_root: Path,
        _runner=run_workflow_process,
    ):
        self._config = WorkflowProcessConfig.model_validate(config.model_dump())
        self._store = store
        self._root = project_root.resolve()
        self._runner = _runner
        self._lock = Lock()
        self._job: OperatorJob | None = None
        self._thread: Thread | None = None
        self._cancel: Event | None = None
        self._closed = False

    def snapshot(self) -> OperatorJob | None:
        with self._lock:
            return self._job

    def start(self, instruction: str) -> OperatorJob:
        # Validate through the execution contract rather than bypassing model_copy.
        data = self._config.model_dump()
        data["execution"]["instruction"] = instruction
        config = WorkflowProcessConfig.model_validate(data)
        with self._lock:
            if self._closed:
                raise RuntimeError("Operator controller is closed")
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("A workflow job is already active")
            event = Event()
            job = OperatorJob(uuid4().hex, "active", config.execution.instruction)
            thread = Thread(
                target=self._execute,
                args=(job, config, event),
                name=f"bimanual-operator-{job.job_id}",
                daemon=False,
            )
            self._job, self._cancel, self._thread = job, event, thread
            try:
                thread.start()
            except BaseException:
                self._thread, self._cancel = None, None
                self._job = replace(job, state="failed", error="Could not start workflow job")
                raise
            return job

    def stop(self, job_id: str) -> OperatorJob:
        with self._lock:
            if self._job is None or self._job.job_id != job_id:
                raise KeyError("No matching operator job")
            if self._job.state in {"active", "stopping"}:
                self._cancel.set()
                self._job = replace(self._job, state="stopping")
            return self._job

    def _execute(self, job: OperatorJob, config: WorkflowProcessConfig, event: Event):
        def progress(value):
            with self._lock:
                if self._job is not None and self._job.job_id == job.job_id:
                    self._job = replace(self._job, progress=value)

        try:
            result = self._runner(
                config,
                store=self._store,
                project_root=self._root,
                cancelled=event.is_set,
                on_progress=progress,
            )
            verified = self._store.verify(result.run_id)
            if verified != result or result.kind != "dinner_workflow_process":
                raise ValueError("Unverified workflow process result")
            states = {
                "completed": "finished",
                "cancelled": "cancelled",
                "failed": "failed",
                "timed_out": "failed",
                "needs_clarification": "needs_clarification",
                "recovery_required": "failed",
                "replaced": "cancelled",
                "closed": "cancelled",
            }
            if result.outcome not in states:
                raise ValueError("Unsupported workflow process outcome")
            # A late stop cannot erase completed evidence or invent a cancelled run.
            state = states[result.outcome]
            reason = None
            if state in {"failed", "needs_clarification"}:
                reason = "Workflow time limit reached; inspect the recorded run before retrying."
                if result.outcome != "timed_out":
                    reason = next(
                        (
                            value[:2048]
                            for key in ("error", "child_verification_error", "child_reason")
                            if isinstance(value := result.metrics.get(key), str) and value.strip()
                        ),
                        "Workflow did not complete. Inspect the recorded run for details.",
                    )
            final = replace(
                job, state=state, run_id=result.run_id, run_outcome=result.outcome, error=reason
            )
        except BaseException as error:
            final = replace(job, state="failed", error=f"{type(error).__name__}: {error}")
        with self._lock:
            self._job = replace(final, progress=self._job.progress)

    def close(self, timeout: float | None = None) -> None:
        with self._lock:
            self._closed = True
            thread = self._thread
            if self._job is not None and self._job.state in {"active", "stopping"}:
                self._cancel.set()
                self._job = replace(self._job, state="stopping")
        if thread is not None:
            if timeout is None:
                timeout = (
                    self._config.cancellation_grace_seconds
                    # Guardian cancellation, then possible group exit and lease release.
                    + 4 * self._config.terminate_grace_seconds
                    + 10
                )
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("Workflow is still stopping; shutdown is not confirmed")
