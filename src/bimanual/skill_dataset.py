"""Runtime ACT samples restricted to a verified view of a parent dinner dataset."""

from __future__ import annotations

from types import MappingProxyType

from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.skill_views import SkillView, action_window


class SkillDatasetView:
    """Keep current sensor inputs and pad action targets at the skill boundary.

    The caller must verify the parent export and its SkillViews manifest before
    selecting the view. The parent must be loaded without delta timestamps. Its
    metadata/image statistics remain the parent training dataset's; numeric
    statistics must be computed from this object's selected ``hf_dataset`` rows.
    No phase, time, evaluator state, or next-skill sensor input is returned.
    """

    def __init__(self, parent, view: SkillView, chunk_size: int):
        if not isinstance(view, SkillView):
            raise TypeError("Expected a verified SkillView")
        self.view = SkillView.model_validate(view.model_dump(mode="json"))
        action_window(self.view, 0, chunk_size)  # Validate the requested horizon.
        if getattr(parent, "delta_timestamps", None) is not None:
            raise ValueError("Parent dataset must be loaded without delta_timestamps")
        if len(parent) < self.view.end:
            raise ValueError("Parent dataset does not contain the complete skill interval")
        self.parent = parent
        self.chunk_size = chunk_size
        self.hf_dataset = parent.hf_dataset.select(range(self.view.start, self.view.end))
        self.meta = parent.meta
        # Future targets use only the numeric action column, never parent image decoding.
        self._actions = self.hf_dataset.select_columns(["action"])
        self.normalization_provenance = MappingProxyType(
            {
                "image_statistics": "parent_training_dataset",
                "numeric_statistics": "selected_skill_view_rows",
                "parent_episode_id": self.view.parent_episode_id,
                "skill_id": self.view.skill_id,
                "parent_frame_range": (self.view.start, self.view.end),
            }
        )

    def __len__(self):
        return self.view.end - self.view.start

    def __getitem__(self, index: int):
        import torch

        window = action_window(self.view, index, self.chunk_size)
        current = self.parent[window.parent_observation_index]
        keys = ("observation.state", *CAMERA_FEATURES.values())
        if any(key not in current for key in keys):
            raise ValueError("Parent observation is missing a required joint or camera input")
        result = {key: current[key] for key in keys}
        state = result["observation.state"]
        if not isinstance(state, torch.Tensor) or tuple(state.shape) != (12,):
            raise ValueError("Expected a single twelve-joint parent observation")
        for key in CAMERA_FEATURES.values():
            image = result[key]
            if not isinstance(image, torch.Tensor) or image.ndim != 3 or image.shape[0] != 3:
                raise ValueError("Expected a single CHW RGB image for each parent camera")
        targets = []
        # Reuse repeated padding targets without reading their row multiple times.
        raw_actions = {}
        for parent_index in window.parent_action_indices:
            if parent_index not in raw_actions:
                value = torch.as_tensor(self._actions[parent_index - self.view.start]["action"])
                if tuple(value.shape) != (12,) or not value.is_floating_point():
                    raise ValueError("Expected an unchunked floating twelve-joint parent action")
                if not torch.isfinite(value).all().item():
                    raise ValueError("Parent action contains non-finite targets")
                raw_actions[parent_index] = value
            targets.append(raw_actions[parent_index])
        result["action"] = torch.stack(targets)
        result["action_is_pad"] = torch.tensor(window.action_is_pad, dtype=torch.bool)
        return result
