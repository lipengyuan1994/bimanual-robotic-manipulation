"""Deterministic execution lifecycle; physical evaluation remains a separate authority."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Counter, Identifier, Observation, SkillRequest

PositiveNS = Annotated[int, Field(strict=True, gt=0)]
TaskState = Literal[
    "idle",
    "ready",
    "running",
    "awaiting_observation",
    "needs_clarification",
    "execution_complete",
    "failed",
    "cancelled",
    "replaced",
]
Outcome = Literal[
    "succeeded", "failed", "unreachable", "timed_out", "cancelled", "queue_clear_failed"
]


class Capability(Contract):
    """An explicitly registered executor capability, never inferred from a planner."""

    capability_id: Identifier
    skill: Literal["open_drawer", "pick", "place", "handoff"]
    arm: Literal["left", "right", "both"]
    target: Literal["drawer", "spoon", "fork", "plate", "cup", "practice_block"]
    destination: Literal["table", "drawer", "left_gripper", "right_gripper"] | None = None
    shared_workspace: bool = True
    auxiliary_arms: tuple[Literal["left", "right"], ...] = Field(default=(), max_length=1)

    @model_validator(mode="after")
    def supported_arguments(self):
        self.request("capability-validation", 0, 0)
        primary = ("left", "right") if self.arm == "both" else (self.arm,)
        if any(arm in primary for arm in self.auxiliary_arms):
            raise ValueError("Auxiliary ownership cannot repeat a primary arm")
        if self.auxiliary_arms and not self.shared_workspace:
            raise ValueError("Auxiliary arm control requires shared workspace ownership")
        return self

    @property
    def execution_arms(self) -> tuple[Literal["left", "right"], ...]:
        primary = ("left", "right") if self.arm == "both" else (self.arm,)
        return tuple(arm for arm in ("left", "right") if arm in primary + self.auxiliary_arms)

    def request(self, episode_id: str, revision: int, sequence: int) -> SkillRequest:
        return SkillRequest(
            episode_id=episode_id,
            instruction_revision=revision,
            observation_sequence=sequence,
            skill=self.skill,
            arm=self.arm,
            target=self.target,
            destination=self.destination,
            explanation="Executor capability selected by the task supervisor",
        )


class StepSpec(Contract):
    step_id: Identifier
    capability_id: Identifier
    prerequisites: tuple[Identifier, ...] = ()
    timeout_ns: PositiveNS = 30_000_000_000
    max_retries: Annotated[int, Field(strict=True, ge=0, le=2)] = 2


class TaskSpec(Contract):
    task_id: Identifier
    episode_id: Identifier
    instruction_revision: Counter
    instruction: Annotated[str, Field(min_length=1, max_length=8192)]
    steps: Annotated[tuple[StepSpec, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def ordered_dependencies(self):
        previous = set()
        for step in self.steps:
            if step.step_id in previous or len(set(step.prerequisites)) != len(step.prerequisites):
                raise ValueError("Step IDs and prerequisites must be unique")
            if not set(step.prerequisites) <= previous:
                raise ValueError("Prerequisites must name earlier steps in this serial plan")
            previous.add(step.step_id)
        return self


class VisibleAssessment(Contract):
    """Advisory visual evidence, never an executor result or independent score."""

    state: Literal["apparently_complete", "incomplete", "uncertain"]
    explanation: Annotated[str, Field(min_length=1, max_length=2048)]


class Attempt(Contract):
    attempt_id: Identifier
    task_id: Identifier
    step_id: Identifier
    number: Annotated[int, Field(strict=True, ge=1, le=3)]
    request: SkillRequest
    observation: Observation
    started_ns: Counter
    deadline_ns: PositiveNS
    arms: tuple[Literal["left", "right"], ...]
    shared_workspace: bool


class AttemptResult(Contract):
    attempt: Attempt
    ended_ns: Counter
    observation: Observation | None = None
    outcome: Outcome
    reason: Annotated[str, Field(min_length=1, max_length=2048)]
    visible_assessment: VisibleAssessment | None = None


class Event(Contract):
    index: Counter
    at_ns: Counter
    task_id: str | None
    attempt_id: str | None
    kind: str
    reason: str


class Snapshot(Contract):
    task: TaskSpec | None
    tasks: tuple[TaskSpec, ...]
    state: TaskState
    completed_steps: tuple[str, ...]
    active: Attempt | None
    attempts: tuple[AttemptResult, ...]
    events: tuple[Event, ...]
    # Executed steps are not an independent evaluator's full-task success finding.
    evaluation_success: None = None


class TaskSupervisor:
    """One serial executor per worker; call authorize before every action and tick while idle."""

    def __init__(
        self,
        registry: Iterable[Capability],
        *,
        clear_actions: Callable[[], None],
        clock_ns: Callable[[], int] = time.monotonic_ns,
        max_observation_age_ns: int = 2_000_000_000,
    ):
        capabilities = tuple(registry)
        if any(not isinstance(c, Capability) for c in capabilities):
            raise TypeError("Registry must contain validated Capability records")
        if len({c.capability_id for c in capabilities}) != len(capabilities):
            raise ValueError("Duplicate capability ID")
        if type(max_observation_age_ns) is not int or max_observation_age_ns <= 0:
            raise ValueError("Observation age limit must be positive nanoseconds")
        self.registry = MappingProxyType({c.capability_id: c for c in capabilities})
        self._clear_actions, self._clock = clear_actions, clock_ns
        self._max_age = max_observation_age_ns
        self._task: TaskSpec | None = None
        self._tasks: tuple[TaskSpec, ...] = ()
        self._state: TaskState = "idle"
        self._active: Attempt | None = None
        self._completed: tuple[str, ...] = ()
        self._attempts: tuple[AttemptResult, ...] = ()
        self._events: tuple[Event, ...] = ()
        self._used_tasks: set[str] = set()
        self._last_now = 0
        self._last_observation: Observation | None = None
        self._fresh_after: int | None = None
        self._fresh_anchor: Observation | None = None

    def snapshot(self) -> Snapshot:
        return Snapshot(
            task=self._task,
            tasks=self._tasks,
            state=self._state,
            completed_steps=self._completed,
            active=self._active,
            attempts=self._attempts,
            events=self._events,
        )

    def _event(self, kind: str, reason: str, now: int):
        self._events += (
            Event(
                index=len(self._events),
                at_ns=now,
                task_id=self._task.task_id if self._task else None,
                attempt_id=self._active.attempt_id if self._active else None,
                kind=kind,
                reason=reason,
            ),
        )

    def _now(self) -> int:
        now = self._clock()
        if type(now) is not int or now < self._last_now:
            self._clear("Invalid or regressing monotonic clock", self._last_now)
            if self._active:
                self._close(
                    "failed",
                    "Invalid or regressing monotonic clock",
                    self._last_now,
                    self._last_observation,
                )
            self._state = "failed"
            raise RuntimeError("Invalid or regressing monotonic clock")
        self._last_now = now
        return now

    def _clear(self, reason: str, now: int):
        try:
            self._clear_actions()
        except (Exception, KeyboardInterrupt) as exc:
            if self._active:
                self._attempts += (
                    AttemptResult(
                        attempt=self._active,
                        ended_ns=now,
                        outcome="queue_clear_failed",
                        reason=reason,
                    ),
                )
            self._event("queue_clear_failed", f"{reason}: {type(exc).__name__}", now)
            self._active = None
            self._state = "failed"
            raise RuntimeError("Action-queue clearing failed; worker must stop") from exc

    def load_task(self, task: TaskSpec) -> Snapshot:
        if not isinstance(task, TaskSpec):
            raise TypeError("Expected a validated TaskSpec")
        if task.task_id in self._used_tasks:
            raise ValueError("Task IDs cannot be reused")
        if any(step.capability_id not in self.registry for step in task.steps):
            raise ValueError("Task requires an unregistered executor capability")
        if (
            self._task
            and task.episode_id == self._task.episode_id
            and task.instruction_revision <= self._task.instruction_revision
        ):
            raise ValueError("Task change in an episode requires a newer instruction revision")
        now = self._now()
        self._clear("Task change", now)
        if self._active:
            self._close("cancelled", "Task replaced", now, self._last_observation)
        if self._task:
            self._event("task_replaced", "A new task supersedes this task", now)
        self._task, self._state = task, "ready"
        self._tasks += (task,)
        self._used_tasks.add(task.task_id)
        self._completed, self._last_observation = (), None
        self._fresh_after, self._fresh_anchor = None, None
        self._event("task_loaded", "Validated plan and executor registry", now)
        return self.snapshot()

    def _observation(self, observation: Observation, now: int):
        if not isinstance(observation, Observation):
            raise TypeError("Only validated camera/joint Observation records are accepted")
        if not self._task or (observation.episode_id, observation.instruction_revision) != (
            self._task.episode_id,
            self._task.instruction_revision,
        ):
            raise ValueError("Observation has stale task identity")
        if not 0 <= now - observation.observed_monotonic_ns <= self._max_age:
            raise ValueError("Observation is stale or from the future")
        previous = self._last_observation
        if previous:
            if observation.sequence == previous.sequence:
                if observation != previous:
                    raise ValueError(
                        "Observation sequence was reused with different capture or content"
                    )
            elif not (
                observation.sequence > previous.sequence
                and observation.observed_monotonic_ns > previous.observed_monotonic_ns
                and observation.simulation_seconds > previous.simulation_seconds
            ):
                raise ValueError("Observation identity did not advance consistently")

    def dispatch(
        self, observation: Observation, *, proposal: SkillRequest | None = None
    ) -> Attempt | None:
        return self._dispatch(observation, proposal=proposal)

    def dispatch_stationary(
        self,
        observation: Observation,
        *,
        previous_observation: Observation,
        proposal: SkillRequest | None = None,
    ) -> Attempt | None:
        """Trusted paused worker only: newly rendered images, unchanged physical state.

        This does not authorize retimestamping old pixels. The worker must own the
        pause, verify its complete simulator state and write fresh image artifacts.
        Only a successful step boundary qualifies; recovery retains normal rules.
        """
        return self._dispatch(observation, proposal=proposal, stationary=previous_observation)

    def dispatch_recovery(
        self,
        observation: Observation,
        *,
        previous_observation: Observation,
        failed_attempt_id: str,
        proposal: SkillRequest | None = None,
    ) -> Attempt | None:
        """Trusted worker only: recapture an explicitly eligible failed boundary."""
        if not isinstance(failed_attempt_id, str) or not failed_attempt_id:
            raise ValueError("Recovery requires a failed attempt identity")
        return self._dispatch(
            observation,
            proposal=proposal,
            stationary=previous_observation,
            recovery_attempt_id=failed_attempt_id,
        )

    def _stationary_observation(self, observation, previous, now, recovery_attempt_id=None):
        if not isinstance(observation, Observation) or not isinstance(previous, Observation):
            raise TypeError("Stationary transition requires validated observations")
        if (
            self._state != ("awaiting_observation" if recovery_attempt_id else "ready")
            or not self._attempts
            or self._attempts[-1].outcome != ("failed" if recovery_attempt_id else "succeeded")
            or (
                recovery_attempt_id is not None
                and self._attempts[-1].attempt.attempt_id != recovery_attempt_id
            )
            or self._attempts[-1].attempt.task_id != self._task.task_id
            or self._attempts[-1].observation != previous
            or self._fresh_anchor != previous
            or self._last_observation != previous
        ):
            raise ValueError("Stationary transition requires its exact predecessor terminal")
        if (
            observation.episode_id != previous.episode_id
            or observation.instruction_revision != previous.instruction_revision
            or observation.sequence != previous.sequence
            or observation.simulation_seconds != previous.simulation_seconds
            or observation.joint_position_rad != previous.joint_position_rad
            or observation.joint_velocity_rad_s != previous.joint_velocity_rad_s
            or not self._fresh_after < observation.observed_monotonic_ns <= now
            or not 0 <= now - observation.observed_monotonic_ns <= self._max_age
            or tuple((f.camera, f.artifact.sha256) for f in observation.frames)
            != tuple((f.camera, f.artifact.sha256) for f in previous.frames)
            or any(
                a.artifact.path == b.artifact.path
                for a, b in zip(observation.frames, previous.frames, strict=True)
            )
        ):
            raise ValueError("Stationary transition requires fresh artifacts and unchanged state")

    def _dispatch(self, observation, *, proposal=None, stationary=None, recovery_attempt_id=None):
        now = self._now()
        self._expire(now)
        if self._state not in {"ready", "awaiting_observation"} or self._active:
            raise RuntimeError("Task is not ready to dispatch a step")
        if stationary is None:
            self._observation(observation, now)
        else:
            self._stationary_observation(observation, stationary, now, recovery_attempt_id)
        step = self._task.steps[len(self._completed)]
        if not set(step.prerequisites) <= set(self._completed):
            raise RuntimeError("Step prerequisites are incomplete")
        request = self.registry[step.capability_id].request(
            self._task.episode_id, self._task.instruction_revision, observation.sequence
        )
        if proposal is not None:
            if not isinstance(proposal, SkillRequest):
                raise TypeError("Expected validated SkillRequest, not planner text")
            if (
                proposal.episode_id,
                proposal.instruction_revision,
                proposal.observation_sequence,
            ) != (observation.episode_id, observation.instruction_revision, observation.sequence):
                raise ValueError("Planner proposal has stale observation identity")
            if proposal.skill == "stop":
                self.cancel(proposal.explanation)
                return None
            if proposal.skill == "clarify":
                self._clear("Clarification requested", now)
                self._state = "needs_clarification"
                self._event("clarification_requested", proposal.explanation, now)
                return None
            if proposal.model_dump(exclude={"explanation"}) != request.model_dump(
                exclude={"explanation"}
            ):
                raise ValueError("Planner proposal does not match the next registered step")
        if self._fresh_after is not None and stationary is None:
            anchor = self._fresh_anchor
            if not (
                observation.observed_monotonic_ns > self._fresh_after
                and observation.sequence > anchor.sequence
                and observation.simulation_seconds > anchor.simulation_seconds
            ):
                raise ValueError(
                    "Next attempt requires a new observation captured "
                    "after the previous attempt ended"
                )
        self._clear("Starting a new attempt", now)
        number = 1 + sum(
            r.attempt.task_id == self._task.task_id and r.attempt.step_id == step.step_id
            for r in self._attempts
        )
        if number > 1 + step.max_retries:
            raise RuntimeError("Retry budget exhausted")
        capability = self.registry[step.capability_id]
        self._active = Attempt(
            attempt_id=uuid.uuid4().hex,
            task_id=self._task.task_id,
            step_id=step.step_id,
            number=number,
            request=request,
            observation=observation,
            started_ns=now,
            deadline_ns=now + step.timeout_ns,
            arms=capability.execution_arms,
            shared_workspace=capability.shared_workspace,
        )
        self._last_observation, self._state = observation, "running"
        self._fresh_after, self._fresh_anchor = None, None
        if stationary is not None:
            self._event(
                "stationary_recapture",
                f"{'Recovery' if recovery_attempt_id else 'Successful'} stationary boundary; "
                f"fresh capture at sequence {observation.sequence}",
                now,
            )
        self._event("attempt_started", f"Attempt {number}", now)
        return self._active

    def authorize(
        self,
        attempt_id: str,
        observation: Observation,
        *,
        arm: Literal["left", "right"] | None = None,
        shared_workspace: bool = False,
    ) -> Attempt:
        now = self._now()
        self._expire(now)
        if not self._active or self._active.attempt_id != attempt_id:
            self._clear("Stale executor attempt", now)
            raise RuntimeError("No matching active attempt")
        try:
            self._observation(observation, now)
            if arm is not None and arm not in self._active.arms:
                raise ValueError("Executor does not own that arm")
            if shared_workspace and not self._active.shared_workspace:
                raise ValueError("Executor does not own the shared workspace")
        except (ValueError, TypeError) as exc:
            self._clear("Rejected execution context", now)
            self._close("failed", f"Rejected execution context: {exc}", now, self._last_observation)
            raise
        self._last_observation = observation
        return self._active

    def _close(
        self,
        outcome: Outcome,
        reason: str,
        now: int,
        observation: Observation | None,
        assessment: VisibleAssessment | None = None,
    ):
        active = self._active
        self._attempts += (
            AttemptResult(
                attempt=active,
                ended_ns=now,
                observation=observation,
                outcome=outcome,
                reason=reason,
                visible_assessment=assessment,
            ),
        )
        self._event("attempt_finished", f"{outcome}: {reason}", now)
        self._active = None
        self._fresh_after = now
        self._fresh_anchor = observation or active.observation
        if outcome == "succeeded":
            self._completed += (active.step_id,)
            self._state = (
                "execution_complete" if len(self._completed) == len(self._task.steps) else "ready"
            )
        elif outcome in {"failed", "timed_out"}:
            step = self._task.steps[len(self._completed)]
            self._state = "awaiting_observation" if active.number <= step.max_retries else "failed"
            self._fresh_after = now
            self._fresh_anchor = observation or active.observation
        else:
            self._state = "cancelled" if outcome == "cancelled" else "failed"

    def _expire(self, now: int):
        if self._active and now >= self._active.deadline_ns:
            self._clear("Step deadline reached", now)
            self._close("timed_out", "Monotonic step deadline reached", now, self._last_observation)

    def tick(self) -> Snapshot:
        self._expire(self._now())
        return self.snapshot()

    def finish(
        self,
        attempt_id: str,
        observation: Observation,
        *,
        executor_outcome: Literal["succeeded", "failed", "unreachable"],
        reason: str,
        visible_assessment: VisibleAssessment | None = None,
    ) -> Snapshot:
        self.authorize(attempt_id, observation)
        now = self._last_now
        try:
            if executor_outcome not in {"succeeded", "failed", "unreachable"}:
                raise ValueError("Only explicit executor outcomes can finish a step")
            if not isinstance(reason, str) or not 1 <= len(reason) <= 2048:
                raise ValueError("Expected a bounded executor explanation")
            if visible_assessment is not None and not isinstance(
                visible_assessment, VisibleAssessment
            ):
                raise TypeError("Expected validated advisory visual assessment")
            anchor = self._active.observation
            if executor_outcome == "succeeded" and not (
                observation.sequence > anchor.sequence
                and observation.observed_monotonic_ns > anchor.observed_monotonic_ns
                and observation.simulation_seconds > anchor.simulation_seconds
            ):
                raise ValueError("Executor completion requires a fresh post-action observation")
        except (ValueError, TypeError) as exc:
            self._clear("Rejected executor result", now)
            self._close("failed", f"Rejected executor result: {exc}", now, self._last_observation)
            raise
        self._clear("Attempt finished", now)
        self._close(executor_outcome, reason, now, observation, visible_assessment)
        return self.snapshot()

    def cancel(self, reason: str = "Operator cancelled") -> Snapshot:
        if not isinstance(reason, str) or not 1 <= len(reason) <= 2048:
            raise ValueError("Expected a bounded cancellation reason")
        now = self._now()
        self._clear("Task cancelled", now)
        if self._active:
            self._close("cancelled", reason, now, self._last_observation)
        elif self._state not in {"execution_complete", "failed", "cancelled", "replaced", "idle"}:
            self._state = "cancelled"
        self._event("cancel_requested", reason, now)
        return self.snapshot()
