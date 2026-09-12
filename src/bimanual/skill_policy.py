"""Local ACT inference tied to a verified development dinner skill binding."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from bimanual.contracts import JointLimits
from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.policy_rollout import _load_policy
from bimanual.skill_registry import load_skill_checkpoint
from bimanual.supervised_control import SupervisedPolicyControl


class DinnerSkillPolicy:
    """Load before capture/dispatch; inference accepts only normalized RGB and joints.

    Checkpoint integrity is not manipulation quality. This adapter neither chooses
    a step nor reports success, and provides no teacher or remote fallback.
    """

    def __init__(
        self,
        training_run: Path,
        *,
        skill_id: str,
        dataset_root: Path,
        device="cpu",
        corrective_dataset_root: Path | None = None,
    ):
        if device not in {"cpu", "mps"}:
            raise ValueError("Supported local policy devices are cpu and mps")
        relocation = (
            {}
            if corrective_dataset_root is None
            else {"corrective_dataset_root": corrective_dataset_root}
        )
        self.binding = load_skill_checkpoint(
            training_run, skill_id=skill_id, dataset_root=dataset_root, **relocation
        )
        self._torch, self._policy, self._pre, self._post = _load_policy(
            self.binding.checkpoint_path, device
        )
        # Loading must not race an artifact replacement, including processor state.
        self.binding.reverify()
        self.device = device

    def bind_control(
        self,
        control: SupervisedPolicyControl,
        attempt_id: str,
        *,
        hold_targets: np.ndarray,
        limits: JointLimits,
        execute_chunk_steps: int = 1,
        temporal_ensemble_coefficient: float | None = None,
    ):
        snapshot = control.supervisor.snapshot()
        active = snapshot.active
        if active is None or active.attempt_id != attempt_id:
            raise ValueError("Policy binding requires the active attempt")
        step = next(step for step in snapshot.task.steps if step.step_id == active.step_id)
        registered = control.supervisor.registry[step.capability_id]
        if registered != self.binding.capability:
            raise ValueError("Checkpoint skill does not match the registered attempt")
        self._policy.reset()
        return control.bind(
            attempt_id,
            hold_targets=hold_targets,
            limits=limits,
            policy_sha256=self.binding.checkpoint_sha256,
            chunk_size=self.binding.chunk_size,
            execute_chunk_steps=execute_chunk_steps,
            temporal_ensemble_coefficient=temporal_ensemble_coefficient,
        )

    def predict(self, inputs: dict[str, np.ndarray]) -> np.ndarray:
        shapes = {"observation.state": (12,)} | {
            feature: (3, 270, 480) for feature in CAMERA_FEATURES.values()
        }
        if set(inputs) != set(shapes):
            raise ValueError("Policy accepts only measured joints and three camera images")
        copied = {}
        for key, shape in shapes.items():
            value = inputs[key]
            if (
                not isinstance(value, np.ndarray)
                or value.dtype != np.float32
                or value.shape != shape
                or not np.isfinite(value).all()
            ):
                raise ValueError(f"Malformed policy input: {key}")
            if key != "observation.state" and (np.any(value < 0) or np.any(value > 1)):
                raise ValueError("Policy RGB values must be in [0, 1]")
            copied[key] = self._torch.from_numpy(value.copy())
        with self._torch.inference_mode():
            result = self._post(self._policy.predict_action_chunk(self._pre(copied)))
            values = result.detach().cpu().numpy()
        if values.shape != (1, self.binding.chunk_size, 12) or not np.isfinite(values).all():
            raise ValueError("ACT returned an invalid action forecast")
        return values[0].copy()
