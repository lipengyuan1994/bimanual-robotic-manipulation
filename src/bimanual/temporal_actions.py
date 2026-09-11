"""Guarded one-step temporal ACT execution; optional LeRobot loads only after validation."""

from __future__ import annotations

import importlib.metadata
import math

import numpy as np

from bimanual.contracts import JointLimits, Observation
from bimanual.policy_rollout import GuardedActionQueue


class _OfficialEnsembler:
    def __init__(self, chunk_size: int, coefficient: float):
        if importlib.metadata.version("lerobot") != "0.6.1":
            raise RuntimeError("Temporal execution requires pinned LeRobot 0.6.1")
        import torch
        from lerobot.policies.act.modeling_act import ACTTemporalEnsembler

        self.torch = torch
        self.ensemble = ACTTemporalEnsembler(coefficient, chunk_size)
        if any(
            not bool(torch.isfinite(value).all()) or not bool((value > 0).all())
            for value in (
                self.ensemble.ensemble_weights,
                self.ensemble.ensemble_weights_cumsum,
            )
        ):
            raise ValueError("Temporal coefficient produces invalid float32 weights")

    def update(self, values: np.ndarray) -> np.ndarray:
        with self.torch.inference_mode():
            tensor = self.torch.tensor(values, dtype=self.torch.float32, device="cpu").unsqueeze(0)
            result = self.ensemble.update(tensor)
            if result.device.type != "cpu":
                raise RuntimeError("Temporal ensemble must run on CPU")
            return result.detach().numpy().copy()

    def reset(self):
        self.ensemble.reset()


def _make_ensembler(chunk_size: int, coefficient: float):
    return _OfficialEnsembler(chunk_size, coefficient)


class GuardedTemporalActionQueue:
    """Validate raw forecasts, average with official ACT, validate again, execute one.

    The right arm remains held by the underlying ownership mask. Ensembling sees
    the original *validated* twelve-joint forecast, before that mask is applied.
    Every next forecast must follow consumption of the prior queued action and
    advance exactly one sequence. A task identity change starts a fresh history.
    This synchronous queue requires one caller; it does not own worker threads.
    """

    execute_chunk_steps = 1

    def __init__(
        self,
        limits: JointLimits,
        home: np.ndarray,
        policy_sha256: str,
        max_age_ns: int,
        *,
        chunk_size: int,
        coefficient: float,
    ):
        if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
            raise ValueError("Temporal horizon must contain between one and 100 steps")
        if (
            type(coefficient) not in (int, float)
            or not math.isfinite(coefficient)
            or not 0 <= coefficient <= 1
        ):
            raise ValueError("Temporal coefficient must be finite and between zero and one")
        if type(max_age_ns) is not int or max_age_ns <= 0:
            raise ValueError("Observation maximum age must be a positive integer")
        values = np.asarray(home, dtype=float)
        if values.shape != (12,) or not np.isfinite(values).all():
            raise ValueError("Reset home must contain twelve finite targets")
        limits.validate_targets(tuple(values))
        self.chunk_size, self.coefficient = chunk_size, float(coefficient)
        self._raw_guard = GuardedActionQueue(
            limits, values, policy_sha256, max_age_ns, execute_chunk_steps=1
        )
        self._action_guard = GuardedActionQueue(
            limits, values, policy_sha256, max_age_ns, execute_chunk_steps=1
        )
        self._ensembler = None
        self._last_observation = None
        self._forecast_count = 0

    @property
    def pending(self) -> tuple:
        """Read-only queued target snapshot; mutate state only through offer/take/clear."""
        return tuple(self._action_guard.pending)

    def clear(self):
        previous, self._ensembler = self._ensembler, None
        self._raw_guard.clear()
        self._action_guard.clear()
        self._last_observation = None
        self._forecast_count = 0
        if previous is not None:
            previous.reset()

    def offer(self, targets: np.ndarray, observation: Observation, *, now_ns: int) -> dict:
        try:
            # Revalidate even constructed/updated Pydantic objects before using their identity.
            current = Observation.model_validate(observation.model_dump(mode="json"))
            previous = self._last_observation
            if previous is not None:
                if (current.episode_id, current.instruction_revision) != (
                    previous.episode_id,
                    previous.instruction_revision,
                ):
                    self.clear()
                elif self.pending:
                    raise ValueError("An unconsumed temporal action is still queued")
                elif current.sequence != previous.sequence + 1:
                    raise ValueError("Temporal observations must advance exactly one sequence")
                elif (
                    current.observed_monotonic_ns <= previous.observed_monotonic_ns
                    or current.simulation_seconds <= previous.simulation_seconds
                ):
                    raise ValueError(
                        "Temporal observations must advance capture and simulation time"
                    )
            values = np.asarray(targets, dtype=float)
            if values.shape != (self.chunk_size, 12):
                raise ValueError(
                    "Temporal forecast has the wrong configured horizon or joint shape"
                )
            # ENTIRE forecast must pass before any weight allocation or history update.
            raw_evidence = self._raw_guard.offer(values, current, now_ns=now_ns)
            self._raw_guard.clear()
            if self._ensembler is None:
                self._ensembler = _make_ensembler(self.chunk_size, self.coefficient)
            averaged = self._ensembler.update(values.copy())
            if np.asarray(averaged).shape != (1, 12):
                raise ValueError("Temporal ensemble did not return one twelve-joint target")
            # Includes raw averaged right-arm bounds before the final ownership mask.
            accepted = self._action_guard.offer(averaged, current, now_ns=now_ns)
            self._last_observation = current
            self._forecast_count += 1
            return {
                "raw_chunk": raw_evidence["raw_chunk"],
                "averaged_raw_chunk": accepted["raw_chunk"],
                "accepted_chunk": accepted["accepted_chunk"],
                "ownership_mask": accepted["ownership_mask"],
                "prediction_horizon_steps": self.chunk_size,
                "execution_prefix_steps": 1,
                "discarded_forecast_steps": 0,
                "retained_for_temporal_ensemble_steps": self.chunk_size - 1,
                "temporal_ensemble": {
                    "implementation": "lerobot.policies.act.modeling_act.ACTTemporalEnsembler",
                    "lerobot_version": "0.6.1",
                    "device": "cpu",
                    "dtype": "float32",
                    "coefficient": self.coefficient,
                    "chunk_size": self.chunk_size,
                    "forecasts_since_reset": self._forecast_count,
                    "maximum_overlapping_forecasts": min(self._forecast_count, self.chunk_size),
                    "positive_coefficient_favors": "older forecasts",
                },
            }
        except (Exception, KeyboardInterrupt):
            self.clear()
            raise

    def take(self, current: Observation, *, now_ns: int, cancelled: bool = False) -> np.ndarray:
        try:
            if type(now_ns) is not int or now_ns < 0:
                raise ValueError("Current time must be a monotonic integer timestamp")
            if current != self._last_observation:
                raise ValueError("Queued temporal action requires its exact source observation")
            return self._action_guard.take(current, now_ns=now_ns, cancelled=cancelled)
        except (Exception, KeyboardInterrupt):
            self.clear()
            raise
