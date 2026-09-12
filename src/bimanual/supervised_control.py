"""Serial lifecycle bridge between registered attempts and guarded policy actions."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
from pydantic import TypeAdapter

from bimanual.contracts import Digest, JointLimits, Observation
from bimanual.policy_rollout import GuardedActionQueue
from bimanual.supervisor import Attempt, Capability, TaskSupervisor
from bimanual.temporal_actions import GuardedTemporalActionQueue


@dataclass(frozen=True)
class ControlBinding:
    attempt_id: str
    controlled_arms: tuple[str, ...]
    shared_workspace: bool
    policy_sha256: str
    chunk_size: int
    hold_targets: tuple[float, ...]


class SupervisedPolicyControl:
    """One serialized worker, one canonical attempt, and one guarded queue.

    This registers no capabilities itself and performs no inference or physics.
    The worker calls ``supervisor`` lifecycle methods and applies only successful
    ``take`` results. Its actor must serialize these calls with physical stepping.
    Invalid operations fail the attempt; retry authorization belongs exclusively
    to the supervisor. A binding cannot be replaced inside an active attempt.
    """

    def __init__(
        self,
        registry: Iterable[Capability],
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        max_observation_age_ns: int = 2_000_000_000,
    ):
        self._clock = clock_ns
        self._max_age = max_observation_age_ns
        self._queue = None
        self._binding = None
        self._last_consumed: Observation | None = None
        self._used_attempts: set[str] = set()
        self.supervisor = TaskSupervisor(
            registry,
            clear_actions=self.clear,
            clock_ns=clock_ns,
            max_observation_age_ns=max_observation_age_ns,
        )

    @property
    def binding(self) -> ControlBinding | None:
        return self._binding

    @property
    def pending(self) -> tuple:
        return tuple(self._queue.pending) if self._queue is not None else ()

    def clear(self):
        """Lifecycle callback: discard both the queue and temporal history."""
        previous, self._queue = self._queue, None
        self._binding = None
        self._last_consumed = None
        if previous is not None:
            previous.clear()

    def _authorize(self, attempt_id: str, observation: Observation) -> Attempt:
        # authorize itself ticks deadlines, validates identity/freshness, and clears
        # on stale attempts. Do not trust a caller-provided Attempt or arm list.
        active = self.supervisor.authorize(attempt_id, observation)
        for arm in active.arms:
            active = self.supervisor.authorize(
                attempt_id, observation, arm=arm, shared_workspace=active.shared_workspace
            )
        return active

    def _fail(self, attempt_id: str, observation: Observation, error: BaseException):
        active = self.supervisor.snapshot().active
        if active is not None and active.attempt_id == attempt_id:
            try:
                self.supervisor.finish(
                    attempt_id,
                    observation,
                    executor_outcome="failed",
                    reason=f"Policy control rejected operation: {type(error).__name__}: {error}"[
                        :2048
                    ],
                )
            except (Exception, KeyboardInterrupt):
                # Invalid context/clock/queue cleanup already closes the attempt in
                # the supervisor. Preserve that original outcome, not a fake retry.
                self.clear()
        else:
            self.clear()

    def bind(
        self,
        attempt_id: str,
        *,
        hold_targets: np.ndarray,
        limits: JointLimits,
        policy_sha256: str,
        chunk_size: int,
        execute_chunk_steps: int = 10,
        temporal_ensemble_coefficient: float | None = None,
    ) -> ControlBinding:
        active = self.supervisor.tick().active
        if active is None or type(attempt_id) is not str or active.attempt_id != attempt_id:
            raise RuntimeError("Binding requires the canonical active attempt ID")
        observation = active.observation
        try:
            active = self._authorize(attempt_id, observation)
            if self._binding is not None or attempt_id in self._used_attempts:
                raise RuntimeError("Cannot rebind an active or previously bound attempt")
            if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
                raise ValueError("Policy horizon must contain between one and 100 steps")
            policy_sha256 = TypeAdapter(Digest).validate_python(policy_sha256)
            limits = JointLimits.model_validate(limits.model_dump(mode="json"))
            hold = np.asarray(hold_targets, dtype=float).copy()
            if hold.shape != (12,) or not np.isfinite(hold).all():
                raise ValueError("Hold targets require twelve finite joint targets")
            limits.validate_targets(tuple(hold))
            if temporal_ensemble_coefficient is None:
                queue = GuardedActionQueue(
                    limits,
                    hold,
                    policy_sha256,
                    self._max_age,
                    execute_chunk_steps=execute_chunk_steps,
                    controlled_arms=active.arms,
                )
            else:
                if type(execute_chunk_steps) is not int or execute_chunk_steps != 1:
                    raise ValueError("Temporal execution requires a one-step prefix")
                queue = GuardedTemporalActionQueue(
                    limits,
                    hold,
                    policy_sha256,
                    self._max_age,
                    chunk_size=chunk_size,
                    coefficient=temporal_ensemble_coefficient,
                    controlled_arms=active.arms,
                )
            self._binding = ControlBinding(
                attempt_id=attempt_id,
                controlled_arms=active.arms,
                shared_workspace=active.shared_workspace,
                policy_sha256=policy_sha256,
                chunk_size=chunk_size,
                hold_targets=tuple(hold),
            )
            self._queue = queue
            self._used_attempts.add(attempt_id)
            return self._binding
        except (Exception, KeyboardInterrupt) as error:
            self._fail(attempt_id, observation, error)
            raise

    def _bound_queue(self, attempt_id: str, observation: Observation):
        active = self._authorize(attempt_id, observation)
        if self._binding is None or self._binding.attempt_id != attempt_id or self._queue is None:
            raise RuntimeError("Active attempt has no policy control binding")
        if (active.arms, active.shared_workspace) != (
            self._binding.controlled_arms,
            self._binding.shared_workspace,
        ):
            raise RuntimeError("Canonical attempt ownership changed after binding")
        return self._queue

    def _operation_time(self, attempt_id: str) -> int:
        """Recheck the deadline at the actual queue timestamp, after authorization."""
        now = self._clock()
        active = self.supervisor.snapshot().active
        if active is None or active.attempt_id != attempt_id:
            raise RuntimeError("No matching active attempt at queue operation")
        if now >= active.deadline_ns:
            # Let the supervisor own the timeout record and retry accounting.
            self.supervisor.tick()
            raise TimeoutError("Attempt deadline reached before queue operation")
        return now

    def offer(self, attempt_id: str, targets: np.ndarray, observation: Observation) -> dict:
        try:
            queue = self._bound_queue(attempt_id, observation)
            if queue.pending:
                raise ValueError("Cannot replace an unconsumed policy forecast")
            previous = self._last_consumed
            if previous is not None and not (
                observation.sequence == previous.sequence + 1
                and observation.observed_monotonic_ns > previous.observed_monotonic_ns
                and observation.simulation_seconds > previous.simulation_seconds
            ):
                raise ValueError("Next forecast requires the next fresh post-action observation")
            if np.asarray(targets).shape != (self._binding.chunk_size, 12):
                raise ValueError("Forecast does not match the bound policy horizon")
            report = queue.offer(targets, observation, now_ns=self._operation_time(attempt_id))
            return report | {"attempt_id": attempt_id}
        except (Exception, KeyboardInterrupt) as error:
            self._fail(attempt_id, observation, error)
            raise

    def take(self, attempt_id: str, observation: Observation) -> np.ndarray:
        try:
            queue = self._bound_queue(attempt_id, observation)
            target = queue.take(observation, now_ns=self._operation_time(attempt_id))
            self._last_consumed = observation
            return target
        except (Exception, KeyboardInterrupt) as error:
            self._fail(attempt_id, observation, error)
            raise
