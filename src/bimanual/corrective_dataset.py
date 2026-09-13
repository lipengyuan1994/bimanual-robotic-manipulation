"""Training-only composition preserving nominal and corrective source boundaries."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.evidence import digest_file

SKILL_CORRECTIVE_PROFILE = "six_skill_corrective_lerobot_v1"
BAR_OVERLAP_PROFILE = "bar_overlap_corrective_lerobot_v1"


def select_corrective_episodes(root: Path, manifest: dict, skill_id: str) -> tuple[dict, ...]:
    """Return one skill's replay intervals, preserving their source indices.

    The all-skill corrective export is an immutable archival dataset.  A policy
    must never consume another skill's actions merely because those rows share
    that archive, so selection is derived from the sealed source view rather
    than from task text or a caller-provided index.
    """
    if manifest.get("profile") == BAR_OVERLAP_PROFILE:
        if skill_id != "bar_place_and_return":
            raise ValueError("Bar-overlap archive is restricted to bar_place_and_return")
        episodes = manifest.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            raise ValueError("Bar-overlap archive has no replay episodes")
        selected, cursor = [], 0
        for episode in episodes:
            start, end = episode.get("dataset_start"), episode.get("dataset_end")
            if type(start) is not int or type(end) is not int or end <= start:
                raise ValueError("Bar-overlap source interval is invalid")
            selected.append(
                dict(
                    episode,
                    source_dataset_start=start,
                    source_dataset_end=end,
                    dataset_start=cursor,
                    dataset_end=cursor + end - start,
                )
            )
            cursor += end - start
        return tuple(selected)
    if manifest.get("profile") != SKILL_CORRECTIVE_PROFILE:
        return tuple(manifest["episodes"])
    from bimanual.skill_corrective_views import load_skill_corrective_views_binding

    root = Path(root).resolve(strict=True)
    views = load_skill_corrective_views_binding(root / "skill_corrective_views.json")
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != len(views.sources):
        raise ValueError("Corrective source/view episode count mismatch")
    selected, cursor = [], 0
    for episode, source in zip(episodes, views.sources, strict=True):
        required = {
            "episode_id": source.episode_id,
            "run_id": source.run_id,
            "parent_start": source.start,
            "parent_end": source.end,
            "source_manifest_sha256": source.source_manifest_sha256,
            "episode_sha256": source.episode.sha256,
        }
        if any(episode.get(key) != value for key, value in required.items()):
            raise ValueError("Corrective source/view lineage mismatch")
        start, end = episode.get("dataset_start"), episode.get("dataset_end")
        if type(start) is not int or type(end) is not int or end <= start:
            raise ValueError("Corrective source interval is invalid")
        if source.skill_id == skill_id:
            selected.append(
                dict(
                    episode,
                    source_dataset_start=start,
                    source_dataset_end=end,
                    dataset_start=cursor,
                    dataset_end=cursor + end - start,
                )
            )
            cursor += end - start
    if not selected:
        raise ValueError("Corrective archive has no replay for selected skill")
    return tuple(selected)


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

    def __init__(self, nominal, corrective, manifest, chunk_size, *, episodes=None):
        if getattr(corrective, "delta_timestamps", None) is not None:
            raise ValueError("Corrective dataset must have no delta timestamps")
        if not 1 <= chunk_size <= 100:
            raise ValueError("Invalid action horizon")
        if len(corrective) != manifest["frames"]:
            raise ValueError("Corrective dataset length mismatch")
        self.nominal, self.corrective = nominal, corrective
        self.episodes = tuple(manifest["episodes"] if episodes is None else episodes)
        self.chunk_size = chunk_size
        self.meta = nominal.meta
        self.source_indices = []
        cursor = 0
        for source in self.episodes:
            if source["dataset_start"] != cursor or source["dataset_end"] <= cursor:
                raise ValueError("Corrective intervals must partition their dataset")
            source_start = source.get("source_dataset_start", source["dataset_start"])
            source_end = source.get("source_dataset_end", source["dataset_end"])
            if (
                type(source_start) is not int
                or type(source_end) is not int
                or source_end - source_start != source["dataset_end"] - source["dataset_start"]
                or not 0 <= source_start < source_end <= len(corrective)
            ):
                raise ValueError("Corrective source index mapping is invalid")
            self.source_indices.extend(range(source_start, source_end))
            cursor = source["dataset_end"]
        if not self.source_indices:
            raise ValueError("Corrective selection is empty")
        # The complete, unfiltered archive needs no dataset-library-specific
        # selection method.  This also keeps the small contract fixtures
        # independent from Hugging Face Dataset internals.
        selected_rows = (
            corrective.hf_dataset
            if self.source_indices == list(range(len(corrective)))
            else corrective.hf_dataset.select(self.source_indices)
        )
        self.hf_dataset = NumericRows((nominal.hf_dataset, selected_rows))
        self.actions = selected_rows.select_columns(["action"])

    def __len__(self):
        return len(self.nominal) + len(self.source_indices)

    def __getitem__(self, index):
        import torch

        if type(index) is not int or not 0 <= index < len(self):
            raise IndexError(index)
        if index < len(self.nominal):
            return self.nominal[index]
        local = index - len(self.nominal)
        source = next(s for s in self.episodes if s["dataset_start"] <= local < s["dataset_end"])
        current = self.corrective[self.source_indices[local]]
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
    plan: dict, root: Path, manifest: dict, *, recorded_root: str | None = None, episodes=None
) -> dict:
    """Bind every uniformly sampled row to its immutable source and original index."""
    selected_skill = plan.get("skill_view", {}).get("skill_id")
    if plan["profile"] != "uniform" or not isinstance(selected_skill, str):
        raise ValueError("Corrections require a selected uniform skill view")
    if manifest.get("profile") not in {SKILL_CORRECTIVE_PROFILE, BAR_OVERLAP_PROFILE} and (
        selected_skill != "handoff_transfer"
    ):
        raise ValueError("This corrective profile requires the complete verified handoff skill")
    if recorded_root is not None and not Path(recorded_root).is_absolute():
        raise ValueError("Recorded corrective identity must be an absolute path")
    regions = {
        "feedback_approach_corrective_lerobot_v1": "corrective_approach",
        "handoff_receiver_continuity_lerobot_v1": "corrective_receiver_continuity",
        SKILL_CORRECTIVE_PROFILE: "corrective_skill_replay",
        BAR_OVERLAP_PROFILE: "corrective_bar_overlap_replay",
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
    selected_episodes = tuple(manifest["episodes"] if episodes is None else episodes)
    if manifest.get("profile") in {SKILL_CORRECTIVE_PROFILE, BAR_OVERLAP_PROFILE}:
        expected_episodes = select_corrective_episodes(root, manifest, selected_skill)
        if selected_episodes != expected_episodes:
            raise ValueError("Corrective selection does not match the selected skill")
    for source in selected_episodes:
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
        for s in selected_episodes
    )
    return result


def emphasize_bar_transport_placement(
    plan: dict,
    *,
    emphasis_start: int,
    emphasis_end: int,
    sampling_profile: str = "bar_transport_placement_v1",
) -> dict:
    """Give each bar corrective replay equal mass to transport and its remainder.

    Nominal selected-skill frames retain one half of total mass. The other half is
    divided equally among every corrective source's emphasis and remainder groups.
    This makes the correction auditable without turning the archive into a generic
    task mixture.
    """
    if plan.get("profile") != "uniform" or plan.get("skill_view", {}).get("skill_id") != (
        "bar_place_and_return"
    ):
        raise ValueError("Bar transport emphasis requires a uniform selected bar skill")
    if (
        type(emphasis_start) is not int
        or type(emphasis_end) is not int
        or emphasis_start >= emphasis_end
    ):
        raise ValueError("Bar transport emphasis interval is invalid")
    result = copy.deepcopy(plan)
    nominal = [frame for frame in result["frames"] if frame.get("dataset_source") == "nominal"]
    corrective = [
        frame for frame in result["frames"] if frame.get("dataset_source") == "corrective"
    ]
    if not nominal or not corrective:
        raise ValueError("Bar transport emphasis requires nominal and corrective frames")
    groups = {}
    for frame in corrective:
        source = frame.get("episode_id")
        index = frame.get("source_frame_index")
        if not isinstance(source, str) or type(index) is not int:
            raise ValueError("Bar corrective frame lacks immutable source identity")
        region = "transport_to_placement" if emphasis_start <= index < emphasis_end else "remainder"
        frame["region"] = region
        groups.setdefault((source, region), []).append(frame)
    required_regions = (
        ("transport_to_placement",)
        if sampling_profile == "bar_placement_progress_sampling_v3"
        else ("transport_to_placement", "remainder")
    )
    expected_groups = {
        (episode["episode_id"], region)
        for episode in result["episodes"]
        if episode.get("source") == "corrective"
        for region in required_regions
    }
    if set(groups) != expected_groups or any(not frames for frames in groups.values()):
        raise ValueError("Selected bar replay does not match required sampling regions")
    for frame in nominal:
        frame["probability"] = 0.5 / len(nominal)
    group_mass = 0.5 / len(groups)
    for frames in groups.values():
        for frame in frames:
            frame["probability"] = group_mass / len(frames)
    probabilities = [frame["probability"] for frame in result["frames"]]
    if not np.isclose(sum(probabilities), 1.0):
        raise ValueError("Bar transport sampling probabilities do not sum to one")
    for episode in result["episodes"]:
        episode_frames = [
            frame
            for frame in result["frames"]
            if frame.get("episode_id") == episode["episode_id"]
            and frame.get("dataset_source") == episode.get("source")
        ]
        episode["probability"] = sum(frame["probability"] for frame in episode_frames)
        if episode.get("source") == "corrective":
            regions = []
            for region in required_regions:
                frames = [frame for frame in episode_frames if frame["region"] == region]
                regions.append(
                    dict(
                        name=region,
                        start=min(frame["parent_dataset_index"] for frame in frames),
                        end=max(frame["parent_dataset_index"] for frame in frames) + 1,
                        conditional_probability=sum(frame["probability"] for frame in frames)
                        / episode["probability"],
                    )
                )
            episode["regions"] = regions
    if sampling_profile == "bar_transport_placement_v1":
        metadata_key, emphasis_name = "bar_transport_placement", "transport_to_placement"
    elif sampling_profile == "bar_entry_contact_sampling_v2":
        metadata_key, emphasis_name = "bar_entry_contact", "policy_entry"
    elif sampling_profile == "bar_placement_contact_sampling_v4":
        metadata_key, emphasis_name = "bar_placement_contact", "placement_contact_entry"
    elif sampling_profile == "bar_placement_progress_sampling_v3":
        metadata_key, emphasis_name = "bar_placement_progress", "placement_release_retreat"
    else:
        raise ValueError("Unsupported bar sampling profile")
    for frame in corrective:
        if frame["region"] == "transport_to_placement":
            frame["region"] = emphasis_name
    for episode in result["episodes"]:
        if episode.get("source") == "corrective":
            for region in episode["regions"]:
                if region["name"] == "transport_to_placement":
                    region["name"] = emphasis_name
    result.update(
        profile=sampling_profile,
        algorithm="torch.multinomial_float64",
        **{
            metadata_key: dict(
                emphasis_source_interval=[emphasis_start, emphasis_end],
                nominal_probability=0.5,
                corrective_group_probability=group_mass,
                groups=[
                    dict(
                        episode_id=episode_id,
                        region=emphasis_name if region == "transport_to_placement" else region,
                        frame_count=len(frames),
                        probability=group_mass,
                    )
                    for (episode_id, region), frames in sorted(groups.items())
                ],
            )
        },
    )
    return result
