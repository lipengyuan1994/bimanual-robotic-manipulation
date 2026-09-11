"""Bounded local skill execution with separate physical outcome monitoring."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from bimanual.dinner_teacher import ASSETS
from bimanual.evidence import digest_file
from bimanual.skill_outcomes import SkillOutcomeMonitor


@dataclass(frozen=True)
class SkillExecutionResult:
    attempt_id: str
    state: str
    reason: str
    applied_actions: int


class DinnerSkillExecutor:
    """Serialized actor driver; a preloaded policy receives cameras and joints only.

    Physical truth is read from the worker's append-only evidence by the outcome
    monitor. Only its outcome/reason reaches the supervisor. This is an explicit
    simulation termination instrument, not visual recognition or full-task scoring.
    Call tick regularly; inference is synchronous and worker cancellation/expiry
    is checked again before any action. No teacher actions or fallback are loaded.
    """

    def __init__(self, worker, policy, *, max_actions: int = 2000):
        if type(max_actions) is not int or not 1 <= max_actions <= 20000:
            raise ValueError("Skill action budget must be between one and 20000")
        manifest = json.loads((ASSETS / "manifest.json").read_text())
        if digest_file(ASSETS / "layout.json") != manifest["files"]["layout.json"]:
            raise ValueError("Frozen scoring layout integrity mismatch")
        self._layout = json.loads((ASSETS / "layout.json").read_text())
        if digest_file(worker.directory / "scene.xml") != self._layout["scene_sha256"]:
            raise ValueError("Physical outcome layout does not match worker scene")
        self.worker, self.policy, self.max_actions = worker, policy, max_actions
        self._attempt = self._monitor = self._result = None
        self._count = 0
        self._trace_offset = None
        self._next_observation = None

    def start(self, attempt_id, observation, *, temporal_ensemble_coefficient=None):
        if self._attempt is not None:
            raise RuntimeError("Executor is single-attempt; create another for a supervisor retry")
        active = self.worker.supervisor.snapshot().active
        if active is None or active.attempt_id != attempt_id:
            raise ValueError("Executor requires the canonical active attempt")
        if observation.episode_id != active.request.episode_id:
            raise ValueError("Executor observation belongs to another episode")
        # The worker validates current observation and exact capability/checkpoint binding.
        self.worker.policy_inputs(observation)
        self.worker.bind_skill(
            self.policy,
            attempt_id,
            execute_chunk_steps=1,
            temporal_ensemble_coefficient=temporal_ensemble_coefficient,
        )
        self._attempt = attempt_id
        self._next_observation = observation
        try:
            self._monitor = SkillOutcomeMonitor(
                self.policy.binding.view.skill_id,
                episode_id=observation.episode_id,
                initial_sequence=observation.sequence,
                initial_simulation_seconds=observation.simulation_seconds,
                layout=self._layout,
            )
            self.worker.flush_physics_trace()
            self._trace_offset = (self.worker.directory / "physics.jsonl").stat().st_size
            self._write(
                "started",
                {
                    "skill_id": self.policy.binding.view.skill_id,
                    "max_actions": self.max_actions,
                    "physical_truth_consumer": "independent_skill_outcome_monitor",
                },
            )
        except (Exception, KeyboardInterrupt) as error:
            self._fail(error, observation)
            raise

    def _write(self, event, details):
        with (self.worker.directory / "skill-execution.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "attempt_id": self._attempt,
                        "event": event,
                        "applied_actions": self._count,
                        **details,
                    },
                    allow_nan=False,
                )
                + "\n"
            )

    def _rows(self):
        self.worker.flush_physics_trace()
        with (self.worker.directory / "physics.jsonl").open("rb") as stream:
            stream.seek(self._trace_offset)
            lines = [stream.readline() for _ in range(51)]
            if any(not line.endswith(b"\n") for line in lines[:50]) or lines[50]:
                raise ValueError("A confirmed action must own exactly50 complete physical samples")
            self._trace_offset = stream.tell()
        return [json.loads(line) for line in lines[:50]]

    def _finish(self, state, reason, observation):
        result = SkillExecutionResult(self._attempt, state, reason, self._count)
        self._write("termination_requested", asdict(result))
        self.worker.finish(self._attempt, observation, executor_outcome=state, reason=reason)
        self._result = result
        return self._result

    def _fail(self, error, observation):
        reason = f"Skill executor rejected operation: {type(error).__name__}: {error}"[:2048]
        active = self.worker.supervisor.snapshot().active
        if active is not None and active.attempt_id == self._attempt:
            self.worker._abort(self._attempt, observation, error)
        self._result = SkillExecutionResult(self._attempt, "failed", reason, self._count)
        self._write("error", asdict(self._result))

    def tick(self) -> SkillExecutionResult:
        if self._attempt is None:
            raise RuntimeError("Start the executor before advancing it")
        if self._result is not None:
            return self._result
        observation = None
        try:
            snapshot = self.worker.supervisor.snapshot()
            if snapshot.active is None or snapshot.active.attempt_id != self._attempt:
                # A cancelled/replaced task must not cancel or finish its replacement.
                self._result = SkillExecutionResult(
                    self._attempt, "failed", "Attempt authority was revoked", self._count
                )
                self._write("revoked", asdict(self._result))
                return self._result
            observation = self._next_observation or self.worker.capture()
            self._next_observation = None
            if self._count >= self.max_actions:
                return self._finish(
                    "failed", "Physical completion not reached within action budget", observation
                )
            if not self.worker.control.pending:
                start = time.perf_counter()
                prediction = self.policy.predict(self.worker.policy_inputs(observation))
                self.worker.offer(self._attempt, prediction, observation)
                self._write("forecast", {"inference_seconds": time.perf_counter() - start})
            action = self.worker.step(self._attempt, observation)
            self._count += 1
            outcome = self._monitor.consume(action, self._rows())
            self._write("physical_outcome", outcome.report())
            if outcome.state != "pending":
                return self._finish(outcome.state, outcome.reason, self.worker.capture())
            return SkillExecutionResult(self._attempt, "pending", outcome.reason, self._count)
        except (Exception, KeyboardInterrupt) as error:
            self._fail(error, observation)
            raise
