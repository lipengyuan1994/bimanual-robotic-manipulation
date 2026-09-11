"""Serialized orchestration; completion is not independent dinner-task success."""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from bimanual.evidence import canonical
from bimanual.skill_executor import DinnerSkillExecutor
from bimanual.skill_registry import dinner_capability
from bimanual.supervisor import TaskSpec

_TERMINAL = {
    "execution_complete",
    "failed",
    "cancelled",
    "replaced",
    "needs_clarification",
    "recovery_required",
    "closed",
}


@dataclass(frozen=True)
class WorkflowSnapshot:
    workflow_id: str
    task_id: str | None
    state: str
    reason: str
    supervisor_state: str
    completed_steps: tuple[str, ...]
    attempt_count: int
    active_attempt_id: str | None
    planning_job_id: str | None
    execution_complete: bool
    independent_task_success: None = None
    recovery_implemented: bool = True


class DinnerWorkflowRunner:
    """Call every public method on one owning thread; no internal simulation thread.

    Factories construct fresh single-attempt executors *before* planning capture;
    model loading is forbidden in factories. A factory may reverify preloaded
    references there. The planner's own model thread remains external to physics.
    Owned incomplete-skill boundaries permit at most two camera-grounded retries.
    Other failures terminate or require explicit recovery.
    """

    def __init__(
        self,
        worker,
        planner_runner,
        executors: Mapping[str, Callable[[], DinnerSkillExecutor]],
        *,
        directory: Path | None = None,
    ):
        if planner_runner._session.worker is not worker:
            raise ValueError("Planner and executors must share one physical worker")
        if (
            not isinstance(executors, Mapping)
            or not executors
            or any(
                key not in worker.supervisor.registry or not callable(factory)
                for key, factory in executors.items()
            )
        ):
            raise ValueError("Executor factories must map registered capabilities")
        self.worker, self.planner_runner = worker, planner_runner
        self.executors = MappingProxyType(dict(executors))
        self.directory = Path(directory) if directory is not None else worker.directory / "workflow"
        self.directory.mkdir(parents=True, exist_ok=False)
        self.workflow_id = uuid.uuid4().hex
        self._owner = threading.get_ident()
        self._busy = self._closed = False
        self._task = self._task_digest = None
        self._prepared = self._executor = None
        self._job_id = self._attempt_id = None
        self._used_executors = []  # Keep strong references; object IDs cannot be recycled.
        self._state, self._reason = "idle", "No workflow task loaded"
        self._event_index = 0
        self._write("created", {"capabilities": list(self.executors)})

    def _thread(self):
        if threading.get_ident() != self._owner or self._busy:
            raise RuntimeError("Workflow operations must be serialized on their owning thread")

    def _write(self, event, details):
        row = {
            "index": self._event_index,
            "workflow_id": self.workflow_id,
            "task_id": self._task.task_id if self._task else None,
            "event": event,
            "at_ns": self.worker._clock(),
            "details": details,
            "independent_task_success": None,
        }
        with (self.directory / "events.jsonl").open("ab") as stream:
            stream.write(canonical(row) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._event_index += 1

    def snapshot(self) -> WorkflowSnapshot:
        self._thread()
        return self._snapshot()

    def _snapshot(self):
        current = self.worker.supervisor.snapshot()
        same = self._same_task(current)
        return WorkflowSnapshot(
            self.workflow_id,
            self._task.task_id if self._task else None,
            self._state,
            self._reason,
            current.state,
            current.completed_steps if same else (),
            sum(r.attempt.task_id == self._task.task_id for r in current.attempts)
            + int(bool(same and current.active))
            if self._task
            else 0,
            current.active.attempt_id if same and current.active else None,
            self._job_id,
            self._state == "execution_complete" and same and current.state == "execution_complete",
        )

    def _same_task(self, snapshot):
        return (
            snapshot.task is not None
            and self._task_digest
            == hashlib.sha256(canonical(snapshot.task.model_dump(mode="json"))).hexdigest()
        )

    def _stop_error(self, error):
        # This is also the disk-failure path: do not depend on another write to stop.
        self._state, self._reason = "failed", f"Workflow stopped: {type(error).__name__}: {error}"
        self._prepared = self._executor = None
        self._job_id = self._attempt_id = None
        try:
            self.planner_runner.cancel(self._reason)
        finally:
            if self._same_task(self.worker.supervisor.snapshot()):
                self.worker.cancel(self._reason[:2048])

    def start(self, task: TaskSpec) -> WorkflowSnapshot:
        """Load or explicitly replace a task without replacing its physical episode."""
        self._thread()
        if self._closed:
            raise RuntimeError("Workflow is closed")
        if not isinstance(task, TaskSpec) or task.episode_id != self.worker.episode_id:
            raise ValueError("Task must belong to this continuous physical episode")
        if any(step.capability_id not in self.executors for step in task.steps):
            raise ValueError("Task requires an unavailable preloaded executor")
        current = self.worker.supervisor.snapshot()
        if any(old.task_id == task.task_id for old in current.tasks) or (
            current.task is not None
            and current.task.episode_id == task.episode_id
            and task.instruction_revision <= current.task.instruction_revision
        ):
            raise ValueError("Replacement requires a new task ID and newer instruction revision")
        self.worker._available()
        self._busy = True
        try:
            self._write("task_load_requested", {"task": task.model_dump(mode="json")})
            self.worker.supervisor.load_task(task)
            # Load replacement first, so cancelling the old planner cannot stop it.
            self._task, self._task_digest = (
                task,
                hashlib.sha256(canonical(task.model_dump(mode="json"))).hexdigest(),
            )
            self.planner_runner.cancel("Task explicitly replaced")
            self._prepared = self._executor = None
            self._job_id = self._attempt_id = None
            self._state, self._reason = "ready", "Task ready for visual planning"
            self._write("task_loaded", {})
            return self._snapshot()
        except BaseException as error:
            self._stop_error(error)
            raise
        finally:
            self._busy = False

    def _terminal(self, state, reason):
        self._write("workflow_terminal", {"state": state, "reason": reason})
        self._state, self._reason = state, reason
        self._prepared = self._executor = None
        self._job_id = self._attempt_id = None

    def tick(self) -> WorkflowSnapshot:
        self._thread()
        if self._closed or self._state in _TERMINAL or self._task is None:
            return self._snapshot()
        self._busy = True
        try:
            snapshot = self.worker.supervisor.tick()
            if not self._same_task(snapshot):
                self.planner_runner.cancel("Old workflow task was replaced externally")
                self._terminal("replaced", "Task authority replaced; replacement task preserved")
                return self._snapshot()
            if snapshot.state in {
                "failed",
                "cancelled",
                "needs_clarification",
                "execution_complete",
            }:
                self.planner_runner.cancel("Workflow reached a supervisor terminal state")
                self._terminal(snapshot.state, "Supervisor reached " + snapshot.state)
                return self._snapshot()
            if snapshot.state == "awaiting_observation" and not self.worker.recovery_available():
                self.planner_runner.cancel("Owned recovery boundary is required")
                last = snapshot.attempts[-1]
                self._terminal(
                    "recovery_required",
                    last.reason + "; no eligible owned recovery boundary",
                )
                return self._snapshot()
            if self._executor is not None:
                if snapshot.active is None or snapshot.active.attempt_id != self._attempt_id:
                    raise ValueError("Executor authority changed outside the workflow")
                self._write("execution_tick_requested", {"attempt_id": self._attempt_id})
                result = self._executor.tick()
                after = self.worker.supervisor.snapshot()
                if not self._same_task(after):
                    self._terminal("replaced", "Task replaced during execution; output discarded")
                    return self._snapshot()
                self._write("execution_result", result.__dict__)
                if result.attempt_id != self._attempt_id:
                    raise ValueError("Executor returned another attempt identity")
                if result.state == "pending":
                    if after.active is None or after.active.attempt_id != self._attempt_id:
                        raise ValueError("Pending executor lost canonical attempt authority")
                    self._state, self._reason = "executing", result.reason
                else:
                    matching = [
                        r for r in after.attempts if r.attempt.attempt_id == self._attempt_id
                    ]
                    if after.active is not None or len(matching) != 1:
                        raise ValueError("Executor result lacks canonical supervisor termination")
                    if (result.state == "succeeded") != (matching[0].outcome == "succeeded"):
                        raise ValueError("Executor and supervisor termination disagree")
                    self._executor = None
                    self._attempt_id = None
                    self._state, self._reason = "ready", "Execution outcome recorded"
                return self._snapshot()
            if self._job_id is not None:
                self._write("planner_poll_requested", {"job_id": self._job_id})
                result = self.planner_runner.poll()
                if result is None:
                    return self._snapshot()
                if result.job_id != self._job_id:
                    raise ValueError("Planner returned another planning job")
                dispatch = result.dispatch
                self._write(
                    "planner_result",
                    {
                        "job_id": result.job_id,
                        "supervisor_state": dispatch.supervisor_state,
                        "attempt_id": dispatch.attempt.attempt_id if dispatch.attempt else None,
                    },
                )
                self._job_id = None
                if dispatch.attempt is None:
                    self._prepared = None
                    current = self.worker.supervisor.snapshot()
                    if current.active is not None or current.state not in {
                        "cancelled",
                        "needs_clarification",
                    }:
                        raise ValueError("Nonactionable planner result has unexpected authority")
                    self._terminal(current.state, "Planner requested " + current.state)
                    return self._snapshot()
                current = self.worker.supervisor.snapshot()
                if not self._same_task(current) or current.active != dispatch.attempt:
                    raise ValueError("Planner dispatch no longer owns this task")
                if self._prepared is None:
                    raise ValueError("No executor was prepared before planning")
                self._write("executor_start_requested", {"attempt_id": dispatch.attempt.attempt_id})
                self._prepared.start(dispatch.attempt.attempt_id, dispatch.execution_observation)
                self._executor, self._prepared = self._prepared, None
                self._attempt_id = dispatch.attempt.attempt_id
                self._state, self._reason = "executing", "Registered skill executing"
                self._write("executor_started", {"attempt_id": self._attempt_id})
                return self._snapshot()
            if (
                snapshot.state not in {"ready", "awaiting_observation"}
                or snapshot.active is not None
            ):
                raise ValueError("Workflow cannot adopt unowned active execution")
            step = snapshot.task.steps[len(snapshot.completed_steps)]
            self._write("executor_prepare_requested", {"capability_id": step.capability_id})
            prepared = self.executors[step.capability_id]()
            if not isinstance(prepared, DinnerSkillExecutor) or prepared.worker is not self.worker:
                raise ValueError("Factory must return a DinnerSkillExecutor for this worker")
            if not self._same_task(self.worker.supervisor.snapshot()):
                raise ValueError("Task replaced during executor preparation")
            if (
                dinner_capability(prepared.policy.binding.view.skill_id)
                != (self.worker.supervisor.registry[step.capability_id])
            ):
                raise ValueError("Prepared policy does not match the registered capability")
            if prepared._attempt is not None or any(
                prepared is old for old in self._used_executors
            ):
                raise ValueError("Each workflow attempt requires a fresh single-attempt executor")
            self._used_executors.append(prepared)
            self._prepared = prepared
            self._write("planner_submit_requested", {"step_id": step.step_id})
            job = self.planner_runner.submit()
            self._job_id = job.job_id
            self._state, self._reason = "planning", "Waiting for camera-grounded proposal"
            self._write("planner_submitted", {"job_id": self._job_id})
            return self._snapshot()
        except BaseException as error:
            # Retain failures closed by lower layers; no implicit retry or queue reuse.
            self._stop_error(error)
            raise
        finally:
            self._busy = False

    def cancel(self, reason="Operator cancelled workflow") -> WorkflowSnapshot:
        self._thread()
        try:
            self._write("cancel_requested", {"reason": reason})
        finally:
            try:
                self.planner_runner.cancel(reason)
            finally:
                if self._same_task(self.worker.supervisor.snapshot()):
                    self.worker.cancel(reason)
                self._prepared = self._executor = None
                self._job_id = self._attempt_id = None
                self._state, self._reason = "cancelled", reason
        return self._snapshot()

    def close(self):
        self._thread()
        if self._closed:
            return
        try:
            if self._state not in _TERMINAL:
                self.cancel("Workflow runner closed")
        finally:
            self.planner_runner.close()
            self._closed = True
