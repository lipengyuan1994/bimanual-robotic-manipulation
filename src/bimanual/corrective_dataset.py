"""Training-only composition preserving nominal and corrective source boundaries."""

from __future__ import annotations

import copy
from pathlib import Path

from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.evidence import digest_file


class NumericRows:
    """Small column-only union; never materializes camera data for statistics."""

    def __init__(self, parts, columns=None):
        self.parts = tuple(parts)
        self.columns = columns

    def select_columns(self, columns):
        return NumericRows(self.parts, tuple(columns))

    def __iter__(self):
        for part in self.parts:
            yield from (part.select_columns(self.columns) if self.columns else part)


class CorrectiveDataset:
    """Union of a complete nominal skill and independently padded correction sources."""

    def __init__(self, nominal, corrective, manifest, chunk_size):
        if getattr(corrective, "delta_timestamps", None) is not None:
            raise ValueError("Corrective dataset must have no delta timestamps")
        if not 1 <= chunk_size <= 100:
            raise ValueError("Invalid action horizon")
        if len(corrective) != manifest["frames"]:
            raise ValueError("Corrective dataset length mismatch")
        self.nominal, self.corrective = nominal, corrective
        self.episodes = manifest["episodes"]
        self.chunk_size = chunk_size
        self.meta = nominal.meta
        self.hf_dataset = NumericRows((nominal.hf_dataset, corrective.hf_dataset))
        self.actions = corrective.hf_dataset.select_columns(["action"])
        cursor = 0
        for source in self.episodes:
            if source["dataset_start"] != cursor or source["dataset_end"] <= cursor:
                raise ValueError("Corrective intervals must partition their dataset")
            cursor = source["dataset_end"]
        if cursor != len(corrective):
            raise ValueError("Corrective intervals do not cover the dataset")

    def __len__(self):
        return len(self.nominal) + len(self.corrective)

    def __getitem__(self, index):
        import torch

        if type(index) is not int or not 0 <= index < len(self):
            raise IndexError(index)
        if index < len(self.nominal):
            return self.nominal[index]
        local = index - len(self.nominal)
        source = next(s for s in self.episodes if s["dataset_start"] <= local < s["dataset_end"])
        current = self.corrective[local]
        result = {key: current[key] for key in ("observation.state", *CAMERA_FEATURES.values())}
        state = result["observation.state"]
        if (
            not isinstance(state, torch.Tensor)
            or tuple(state.shape) != (12,)
            or not torch.isfinite(state).all()
        ):
            raise ValueError("Invalid corrective joint observation")
        for key in CAMERA_FEATURES.values():
            image = result[key]
            if not isinstance(image, torch.Tensor) or image.ndim != 3 or image.shape[0] != 3:
                raise ValueError("Invalid corrective RGB observation")
        indices = [
            min(local + offset, source["dataset_end"] - 1) for offset in range(self.chunk_size)
        ]
        actions = [torch.as_tensor(self.actions[i]["action"]) for i in indices]
        if any(
            tuple(action.shape) != (12,)
            or not action.is_floating_point()
            or not torch.isfinite(action).all()
            for action in actions
        ):
            raise ValueError("Invalid corrective joint targets")
        result["action"] = torch.stack(actions)
        result["action_is_pad"] = torch.tensor(
            [local + offset >= source["dataset_end"] for offset in range(self.chunk_size)],
            dtype=torch.bool,
        )
        return result


def compose_sampling_plan(
    plan: dict, root: Path, manifest: dict, *, recorded_root: str | None = None
) -> dict:
    """Bind every uniformly sampled row to its immutable source and original index."""
    if (
        plan["profile"] != "uniform"
        or plan.get("skill_view", {}).get("skill_id") != "handoff_transfer"
    ):
        raise ValueError("Corrections require the complete verified handoff skill")
    if recorded_root is not None and not Path(recorded_root).is_absolute():
        raise ValueError("Recorded corrective identity must be an absolute path")
    regions = {
        "feedback_approach_corrective_lerobot_v1": "corrective_approach",
        "handoff_receiver_continuity_lerobot_v1": "corrective_receiver_continuity",
    }
    try:
        corrective_region = regions[manifest["profile"]]
    except (KeyError, TypeError) as error:
        raise ValueError("Unsupported corrective dataset profile") from error
    result = copy.deepcopy(plan)
    identity = digest_file(root / "export_manifest.json")
    result["corrective_dataset"] = {
        "root": str(root.resolve()) if recorded_root is None else recorded_root,
        "export_manifest_sha256": identity,
        "manifest": manifest,
    }
    for frame in result["frames"]:
        frame["dataset_source"] = "nominal"
    for source in manifest["episodes"]:
        for index in range(source["dataset_start"], source["dataset_end"]):
            result["frames"].append(
                dict(
                    dataset_index=len(result["frames"]),
                    dataset_source="corrective",
                    parent_dataset_index=index,
                    episode_id=source["episode_id"],
                    episode_index=source["episode_index"],
                    source_frame_index=source["parent_start"] + index - source["dataset_start"],
                    source_episode_sha256=source["episode_sha256"],
                    source_manifest_sha256=source["source_manifest_sha256"],
                    region=corrective_region,
                )
            )
    count = len(result["frames"])
    for frame in result["frames"]:
        frame["probability"] = 1 / count
    # Episode identities are namespaced because both datasets start at episode zero.
    result["episodes"] = [dict(source="nominal", **episode) for episode in result["episodes"]]
    nominal_count = sum(f["dataset_source"] == "nominal" for f in result["frames"])
    for episode in result["episodes"]:
        episode["probability"] = nominal_count / count
    result["episodes"].extend(
        dict(
            source="corrective",
            episode_id=s["episode_id"],
            episode_index=s["episode_index"],
            probability=(s["dataset_end"] - s["dataset_start"]) / count,
            regions=[
                dict(
                    name=corrective_region,
                    start=0,
                    end=s["dataset_end"] - s["dataset_start"],
                    conditional_probability=1.0,
                )
            ],
        )
        for s in manifest["episodes"]
    )
    return result
