"""Real, bounded ACT imitation training from verified local LeRobot exports."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import time
import traceback
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bimanual.contracts import Artifact, DemonstrationEpisode, validate_split_seeds
from bimanual.dataset_export import CAMERA_FEATURES, LEROBOT_VERSION
from bimanual.demonstrations import require_successful_training_episode
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.training_loss import act_training_loss, temporal_loss_definition
from bimanual.training_probe import _tensor_digest


class ACTTrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    dataset_path: Path
    corrective_dataset_path: Path | None = None
    device: Literal["cpu", "mps"] = "cpu"
    architecture: Literal["small", "default"] = "small"
    steps: int = Field(default=3, ge=1, le=1_000_000)
    batch_size: int = Field(default=1, ge=1, le=64)
    chunk_size: int = Field(default=10, ge=1, le=100)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    cpu_threads: int = Field(default=4, ge=1, le=32)
    learning_rate: float = Field(default=1e-5, gt=0, le=0.1)
    learning_rate_schedule: Literal["constant", "terminal_linear"] = "constant"
    temporal_loss_profile: Literal["uniform", "first_action_half_v1"] = "uniform"
    normalization_std_floor: float = Field(default=1e-4, gt=0, le=1)
    sampling_profile: Literal["uniform", "approach_regions_v1", "approach_nominal_launch_v1"] = (
        "uniform"
    )
    sampling_protocol_run: Path | None = None
    use_vae: bool = True
    dropout: float = Field(default=0.1, ge=0, lt=1)
    skill_views_path: Path | None = None
    skill_id: str | None = None
    reference_initial_state_sha256: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def sampling_configuration(self):
        temporal_loss_definition(self.temporal_loss_profile, self.chunk_size, use_vae=self.use_vae)
        if self.learning_rate_schedule == "terminal_linear" and self.steps < 4:
            raise ValueError("Terminal linear decay requires at least four updates")
        if (self.skill_views_path is None) != (self.skill_id is None):
            raise ValueError("Skill training requires both a verified view manifest and skill id")
        if self.skill_id is not None and self.sampling_profile != "uniform":
            raise ValueError("Skill views currently support uniform sampling only")
        if (self.sampling_profile == "uniform") != (self.sampling_protocol_run is None):
            raise ValueError(
                "Nonuniform profiles require a sampling protocol run; uniform forbids it"
            )
        if self.corrective_dataset_path is not None and (
            self.skill_id != "handoff_transfer"
            or self.skill_views_path is None
            or self.sampling_profile != "uniform"
        ):
            raise ValueError(
                "Corrective training requires verified handoff_transfer views and uniform sampling"
            )
        return self


def learning_rate_for_step(config: ACTTrainingConfig, step: int) -> float:
    """Learning rate used by this one-based optimizer update, before optimizer.step()."""
    if type(step) is not int or not 1 <= step <= config.steps:
        raise ValueError("Learning-rate step must be a one-based update within the budget")
    if config.learning_rate_schedule == "constant":
        return config.learning_rate
    if config.learning_rate_schedule != "terminal_linear" or config.steps < 4:
        raise ValueError("Unsupported learning-rate schedule")
    hold = 3 * config.steps // 4
    factor = 1.0 if step <= hold else 0.1 + 0.9 * (config.steps - step) / (config.steps - hold)
    return config.learning_rate * factor


def learning_rate_schedule_definition(config: ACTTrainingConfig) -> dict:
    """Portable schedule metadata; optimizer group order matches saved optimizer state."""
    learning_rate_for_step(config, 1)
    hold = config.steps if config.learning_rate_schedule == "constant" else 3 * config.steps // 4
    return dict(
        schema_version=1,
        profile=config.learning_rate_schedule,
        total_updates=config.steps,
        base_learning_rate=config.learning_rate,
        hold_updates=hold,
        first_decay_update=None if hold == config.steps else hold + 1,
        final_factor=1.0 if hold == config.steps else 0.1,
        indexing="one_based_before_optimizer_step",
        applies_to="all_optimizer_parameter_groups",
    )


def apply_learning_rate(optimizer, config: ACTTrainingConfig, step: int) -> list[float]:
    """Set every group, including the visual backbone, and return the actual rates."""
    value = learning_rate_for_step(config, step)
    groups = optimizer.param_groups
    if not groups or any(not isinstance(group, dict) or "lr" not in group for group in groups):
        raise ValueError("Optimizer must expose learning rates for every parameter group")
    for group in groups:
        group["lr"] = value
    return [group["lr"] for group in groups]


def build_sampling_plan(
    dataset_root: Path, manifest: dict, config: ACTTrainingConfig, *, project_root: Path
) -> dict:
    """Build probabilities from verified training boundaries, never evaluation outcomes.

    The caller must first run verify_training_dataset. Weighted compatibility is
    checked against the sealed collection schedule and copied source configs.
    """
    protocol = None
    if config.sampling_profile != "uniform":
        path = config.sampling_protocol_run
        if not path.is_absolute():
            path = project_root / path
        path = path.resolve(strict=True)
        protocol = EvidenceStore(path.parent.parent).verify(path.name)
        if protocol.kind != "approach_collection_protocol" or protocol.outcome != "completed":
            raise ValueError("Sampling requires a completed approach collection protocol")
        schedule = json.loads((path / "protocol.json").read_text())
        if schedule != protocol.config or schedule.get("skill") != "left_open_hand_pregrasp":
            raise ValueError("Sampling protocol/config mismatch")
        motion, settle = schedule.get("motion_steps"), schedule.get("settle_steps")
        if (
            type(motion) is not int
            or type(settle) is not int
            or motion <= 10
            or settle < 1
            or schedule.get("control_hz") != 20
        ):
            raise ValueError("Sampling requires nonempty declared start/middle/settled regions")
    frame_sources, episode_plans, nominal_candidates = [], [], []
    count = len(manifest["episodes"])
    for source in manifest["episodes"]:
        raw = dataset_root / source["raw_root"]
        reference = Artifact(path="demonstration/episode.json", sha256=source["episode_sha256"])
        episode = DemonstrationEpisode.model_validate_json(reference.verify(raw).read_bytes())
        require_successful_training_episode(episode)
        length = len(episode.frames) - 1
        if config.sampling_profile == "uniform":
            regions = [("all", 0, length, 1.0)]
            episode_probability = length / manifest["frames"]
        else:
            source_config = json.loads(episode.lineage.config.verify(raw).read_text())
            case = [
                episode.lineage.seed,
                "train",
                source_config.get("left_joint_offset_rad"),
            ]
            if (
                source_config.get("skill") != schedule["skill"]
                or source_config.get("protocol_run") != protocol.run_id
                or source_config.get("case_seed") != episode.lineage.seed
                or source_config.get("split") != "train"
                or source_config.get("target_m") != schedule.get("target_m")
                or case not in schedule.get("cases", [])
                or length != motion + settle
            ):
                raise ValueError("Approach episode/config does not match the sampling protocol")
            if config.sampling_profile == "approach_nominal_launch_v1":
                offsets = source_config.get("left_joint_offset_rad")
                if (
                    not isinstance(offsets, list)
                    or len(offsets) != 5
                    or any(type(value) not in (int, float) for value in offsets)
                    or not np.isfinite(offsets).all()
                ):
                    raise ValueError("Nominal launch requires five finite numeric joint offsets")
                if all(value == 0 for value in offsets):
                    nominal_candidates.append(
                        dict(
                            episode_id=episode.episode_id,
                            episode_index=source["episode_index"],
                            raw_root=source["raw_root"],
                            source_episode_sha256=source["episode_sha256"],
                            source_config=episode.lineage.config.model_dump(mode="json"),
                            left_joint_offset_rad=offsets,
                        )
                    )
            regions = [
                ("start", 0, 10, 1 / 3),
                ("middle", 10, motion, 1 / 3),
                ("settled", motion, motion + settle, 1 / 3),
            ]
            episode_probability = 1 / count
        episode_plans.append(
            dict(
                episode_id=episode.episode_id,
                episode_index=source["episode_index"],
                probability=episode_probability,
                regions=[
                    dict(name=name, start=start, end=end, conditional_probability=probability)
                    for name, start, end, probability in regions
                ],
            )
        )
        for name, start, end, probability in regions:
            for index in range(start, end):
                frame_sources.append(
                    dict(
                        dataset_index=len(frame_sources),
                        episode_id=episode.episode_id,
                        episode_index=source["episode_index"],
                        source_frame_index=episode.frames[index].observation.sequence,
                        source_episode_sha256=source["episode_sha256"],
                        region=name,
                        probability=episode_probability * probability / (end - start),
                    )
                )
    nominal_launch = None
    if config.sampling_profile == "approach_nominal_launch_v1":
        if len(nominal_candidates) != 1:
            raise ValueError(
                "Nominal launch requires exactly one zero-offset nominal training episode"
            )
        nominal = nominal_candidates[0]
        groups = {"nominal_launch": [], "settled": [], "remaining": []}
        for frame in frame_sources:
            if frame["region"] == "settled":
                group = "settled"
            elif frame["episode_index"] == nominal["episode_index"] and frame["region"] == "start":
                group = "nominal_launch"
            else:
                group = "remaining"
            frame["region"] = group
            groups[group].append(frame)
        for frames in groups.values():
            if not frames:
                raise ValueError("Nominal launch sampling groups must be nonempty")
            for frame in frames:
                frame["probability"] = 1 / (3 * len(frames))
        for episode in episode_plans:
            frames = [f for f in frame_sources if f["episode_index"] == episode["episode_index"]]
            probability = sum(f["probability"] for f in frames)
            episode["probability"] = probability
            regions = []
            for index, frame in enumerate(frames):
                if not regions or regions[-1]["name"] != frame["region"]:
                    regions.append(dict(name=frame["region"], start=index, end=index, mass=0.0))
                regions[-1]["end"] = index + 1
                regions[-1]["mass"] += frame["probability"]
            for region in regions:
                region["conditional_probability"] = region.pop("mass") / probability
            episode["regions"] = regions
        nominal_launch = dict(
            nominal_episode=nominal,
            groups=[
                dict(name=name, frame_count=len(frames), probability=1 / 3)
                for name, frames in groups.items()
            ],
        )
    probabilities = np.array([frame["probability"] for frame in frame_sources])
    if len(frame_sources) != manifest["frames"] or not np.isclose(probabilities.sum(), 1):
        raise ValueError("Sampling plan does not cover the verified dataset")
    plan = dict(
        schema_version=1,
        profile=config.sampling_profile,
        algorithm="torch.randint" if protocol is None else "torch.multinomial_float64",
        replacement=True,
        episodes=episode_plans,
        frames=frame_sources,
        collection_protocol=protocol.model_dump(mode="json") if protocol else None,
    )
    if nominal_launch is not None:
        plan["nominal_launch"] = nominal_launch
    return plan


def restrict_sampling_plan(plan: dict, view, views_digest: str) -> dict:
    """Map local samples to their unchanged parent recording indices."""
    if plan["profile"] != "uniform" or len(plan["episodes"]) != 1:
        raise ValueError("Skill sampling requires one uniform parent episode")
    selected = plan["frames"][view.start : view.end]
    if len(selected) != view.end - view.start or any(
        frame["episode_id"] != view.parent_episode_id
        or frame["source_frame_index"] != view.start + offset
        for offset, frame in enumerate(selected)
    ):
        raise ValueError("Skill sampling does not match parent recording boundaries")
    result = copy.deepcopy(plan)
    result["frames"] = [
        dict(
            frame,
            dataset_index=index,
            parent_dataset_index=frame["dataset_index"],
            probability=1 / len(selected),
            region="skill",
        )
        for index, frame in enumerate(selected)
    ]
    result["episodes"][0]["regions"] = [
        dict(name="skill", start=0, end=len(selected), conditional_probability=1.0)
    ]
    result["skill_view"] = view.model_dump(mode="json")
    result["skill_views_file_sha256"] = views_digest
    return result


def initialize_act_policy(torch, policy_class, policy_config, *, use_vae: bool):
    """Match shared initial weights when removing the optional VAE training branch.

    Construct the standard model first, as previous runs did. The no-VAE model
    receives every shared parameter/buffer from that model; its extra construction
    does not advance the training CPU RNG. No trained weights or targets enter here.
    """
    if not policy_config.use_vae:
        raise ValueError("Initialization reference must be standard ACT with VAE")
    reference = policy_class(policy_config)
    reference_state = reference.state_dict()
    reference_digest = _tensor_digest(reference_state)
    if use_vae:
        return reference, dict(
            use_vae=True,
            initialization="standard_seeded_act",
            reference_initial_state_sha256=reference_digest,
        )
    rng = torch.get_rng_state()
    disabled_config = copy.deepcopy(policy_config)
    disabled_config.use_vae = False
    policy = policy_class(disabled_config)
    target = policy.state_dict()
    if any(
        name not in reference_state or value.shape != reference_state[name].shape
        for name, value in target.items()
    ):
        raise RuntimeError("No-VAE ACT has incompatible shared state")
    shared = {name: reference_state[name] for name in target}
    policy.load_state_dict(shared, strict=True)
    torch.set_rng_state(rng)
    shared_digest = _tensor_digest(shared)
    if _tensor_digest(policy.state_dict()) != shared_digest:
        raise RuntimeError("No-VAE shared initialization differs from standard ACT")
    return policy, dict(
        use_vae=False,
        initialization="shared_state_from_standard_seeded_act",
        reference_initial_state_sha256=reference_digest,
        shared_initial_state_sha256=shared_digest,
        removed_state_keys=sorted(set(reference_state) - set(target)),
        cpu_rng_restored_after_ablation_construction=True,
    )


def sample_training_indices(torch, generator, plan: dict, batch_size: int) -> list[int]:
    """Uniform preserves the original RNG call; weighted draws use the same CPU RNG."""
    if plan["profile"] == "uniform":
        return torch.randint(len(plan["frames"]), (batch_size,), generator=generator).tolist()
    probabilities = torch.tensor(
        [frame["probability"] for frame in plan["frames"]], dtype=torch.float64, device="cpu"
    )
    return torch.multinomial(
        probabilities, batch_size, replacement=True, generator=generator
    ).tolist()


def verify_training_dataset(root: Path) -> dict:
    """Verify the complete export, copied source contracts and train-only eligibility."""
    root = root.resolve(strict=True)
    payload = json.loads((root / "export_manifest.json").read_text())
    declared = payload.get("manifest_sha256")
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if hashlib.sha256(canonical(body)).hexdigest() != declared:
        raise ValueError("Dataset export manifest digest mismatch")
    if (
        payload.get("schema_version"),
        payload.get("format"),
        payload.get("split"),
        payload.get("fps"),
        payload.get("lerobot_version"),
    ) != (1, "lerobot_v3", "train", 20, LEROBOT_VERSION):
        raise ValueError("Unsupported dataset format, split, cadence or library version")
    if not payload.get("files") or not payload.get("episodes"):
        raise ValueError("Dataset export is empty")
    for relative, expected in payload["files"].items():
        Artifact(path=relative, sha256=expected).verify(root)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != root / "export_manifest.json"
    }
    if actual_files != set(payload["files"]):
        raise ValueError("Unsealed files in exported dataset")
    episodes = []
    for index, source in enumerate(payload["episodes"]):
        if source.get("split") != "train" or source.get("episode_index") != index:
            raise ValueError("Dataset source split/index mismatch")
        relative = f"{source['raw_root']}/demonstration/episode.json"
        episode_path = Artifact(path=relative, sha256=source["episode_sha256"]).verify(root)
        episode = DemonstrationEpisode.model_validate_json(episode_path.read_bytes())
        require_successful_training_episode(episode)
        if source["episode_id"] != episode.episode_id or source["seed"] != episode.lineage.seed:
            raise ValueError("Dataset episode identity mismatch")
        if source["exported_transitions"] != len(episode.frames) - 1:
            raise ValueError("Dataset transition count mismatch")
        episodes.append(episode)
    validate_split_seeds(tuple(episodes))
    if payload["frames"] != sum(len(ep.frames) - 1 for ep in episodes):
        raise ValueError("Dataset total frame count mismatch")
    return payload


def stable_numeric_stats(values: np.ndarray, *, std_floor: float) -> dict:
    """Compute training-only state/action statistics without float32 cancellation."""
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 12 or len(values) < 1:
        raise ValueError("Expected N x 12 numeric training values")
    if not np.isfinite(values).all() or not np.isfinite(std_floor) or std_floor <= 0:
        raise ValueError("Statistics require finite values and a positive std floor")
    return {
        "mean": values.mean(axis=0).tolist(),
        "std": np.maximum(values.std(axis=0), std_floor).tolist(),
    }


def run_train(config: ACTTrainingConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    """Train actual ACT; seal success/failure without claiming physical task completion."""
    dataset_root = config.dataset_path.resolve()
    if store.root.is_relative_to(dataset_root):
        raise ValueError("Training evidence store must be outside the immutable dataset")
    directory = store.new_run()
    source = provenance(project_root)
    metrics = {
        "requested_device": config.device,
        "actual_device": None,
        "initialization": "random_no_pretrained_weights",
        "training_completed": False,
        "manipulation_success": None,
        "learned_policy_quality": None,
        "steps": [],
        "learning_rate_schedule": learning_rate_schedule_definition(config),
        "temporal_loss": temporal_loss_definition(
            config.temporal_loss_profile, config.chunk_size, use_vae=config.use_vae
        ),
    }
    started = time.perf_counter()
    torch = None
    old_threads = None
    try:
        dataset_manifest = verify_training_dataset(dataset_root)
        dataset_digest = digest_file(dataset_root / "export_manifest.json")
        (directory / "dataset_manifest.json").write_bytes(
            (dataset_root / "export_manifest.json").read_bytes()
        )
        (directory / "training_config.json").write_text(config.model_dump_json(indent=2) + "\n")
        sampling_plan = build_sampling_plan(
            dataset_root, dataset_manifest, config, project_root=project_root
        )
        skill_view = None
        if config.skill_views_path is not None:
            from bimanual.skill_views import load_skill_views

            view_path = config.skill_views_path
            if not view_path.is_absolute():
                view_path = project_root / view_path
            view_digest = digest_file(view_path)
            views = load_skill_views(view_path, dataset_root=dataset_root)
            matches = [view for view in views.views if view.skill_id == config.skill_id]
            if len(matches) != 1:
                raise ValueError("Unknown or ambiguous skill view")
            skill_view = matches[0]
            sampling_plan = restrict_sampling_plan(sampling_plan, skill_view, view_digest)
            (directory / "skill_views.json").write_bytes(view_path.read_bytes())
            if digest_file(directory / "skill_views.json") != view_digest:
                raise ValueError("Skill view manifest changed during training setup")
            metrics["skill_view"] = skill_view.model_dump(mode="json")
            metrics["skill_views_file_sha256"] = view_digest
        corrective_manifest = None
        corrective_root = None
        if config.corrective_dataset_path is not None:
            from bimanual.corrective_dataset import compose_sampling_plan
            from bimanual.corrective_export import verify_corrective_dataset

            corrective_root = config.corrective_dataset_path
            if not corrective_root.is_absolute():
                corrective_root = project_root / corrective_root
            corrective_root = corrective_root.resolve(strict=True)
            if store.root.resolve().is_relative_to(corrective_root):
                raise ValueError("Training evidence must be outside the corrective dataset")
            corrective_manifest = verify_corrective_dataset(corrective_root)
            (directory / "corrective_views.json").write_bytes(
                (corrective_root / "corrective_views.json").read_bytes()
            )
            metrics["corrective_dataset_root"] = str(corrective_root)
            metrics["corrective_config_base"] = str(project_root.resolve())
            metrics["corrective_views_sha256"] = digest_file(
                corrective_root / "corrective_views.json"
            )
            if (
                digest_file(directory / "corrective_views.json")
                != metrics["corrective_views_sha256"]
            ):
                raise ValueError("Corrective views changed during setup")
            sampling_plan = compose_sampling_plan(
                sampling_plan, corrective_root, corrective_manifest
            )
            (directory / "corrective_dataset_manifest.json").write_bytes(
                (corrective_root / "export_manifest.json").read_bytes()
            )
        (directory / "sampling-plan.json").write_bytes(canonical(sampling_plan))
        sampling_digest = digest_file(directory / "sampling-plan.json")
        metrics["sampling_profile"] = config.sampling_profile
        metrics["sampling_plan_sha256"] = sampling_digest
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            raise RuntimeError("Local training requires native Apple Silicon Python")
        if config.device == "mps" and os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0":
            raise RuntimeError("Start a fresh process with PYTORCH_ENABLE_MPS_FALLBACK=0")
        if importlib.metadata.version("lerobot") != LEROBOT_VERSION:
            raise RuntimeError(f"Expected LeRobot {LEROBOT_VERSION}")
        import torch
        from lerobot.configs.types import FeatureType, PolicyFeature
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        from lerobot.policies.act.configuration_act import ACTConfig
        from lerobot.policies.act.modeling_act import ACTPolicy
        from lerobot.policies.act.processor_act import make_act_pre_post_processors
        from lerobot.processor import PolicyProcessorPipeline
        from lerobot.processor.converters import (
            policy_action_to_transition,
            transition_to_policy_action,
        )
        from torch.utils.data import default_collate

        if config.device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("Requested MPS unavailable; no fallback")
        old_threads = torch.get_num_threads()
        torch.set_num_threads(config.cpu_threads)
        torch.manual_seed(config.seed)
        np.random.seed(config.seed)
        random.seed(config.seed)
        if config.device == "mps":
            torch.mps.manual_seed(config.seed)
        sampler = torch.Generator(device="cpu").manual_seed(config.seed)
        dataset = LeRobotDataset(
            repo_id=dataset_manifest["repo_id"],
            root=dataset_root,
            delta_timestamps=(
                None
                if skill_view is not None
                else {"action": [i / 20 for i in range(config.chunk_size)]}
            ),
        )
        if len(dataset) != dataset_manifest["frames"]:
            raise ValueError("Loaded dataset frame count mismatch")
        metrics["parent_dataset_frames"] = len(dataset)
        if skill_view is not None:
            from bimanual.skill_dataset import SkillDatasetView

            dataset = SkillDatasetView(dataset, skill_view, config.chunk_size)
        if corrective_manifest is not None:
            from bimanual.corrective_dataset import CorrectiveDataset

            corrective = LeRobotDataset(
                repo_id=corrective_manifest["repo_id"], root=corrective_root, delta_timestamps=None
            )
            dataset = CorrectiveDataset(dataset, corrective, corrective_manifest, config.chunk_size)
        architecture = (
            dict(
                dim_model=128,
                n_heads=4,
                dim_feedforward=512,
                n_encoder_layers=1,
                n_decoder_layers=1,
                n_vae_encoder_layers=1,
                latent_dim=16,
            )
            if config.architecture == "small"
            else {}
        )
        input_features = {
            "observation.state": PolicyFeature(type=FeatureType.STATE, shape=(12,)),
            **{
                key: PolicyFeature(type=FeatureType.VISUAL, shape=(3, 270, 480))
                for key in CAMERA_FEATURES.values()
            },
        }
        policy_config = ACTConfig(
            input_features=input_features,
            output_features={"action": PolicyFeature(type=FeatureType.ACTION, shape=(12,))},
            chunk_size=config.chunk_size,
            n_action_steps=config.chunk_size,
            device=config.device,
            pretrained_backbone_weights=None,
            push_to_hub=False,
            use_amp=False,
            dropout=config.dropout,
            optimizer_lr=config.learning_rate,
            optimizer_lr_backbone=config.learning_rate,
            **architecture,
        )
        if policy_config.device != config.device:
            raise RuntimeError("LeRobot changed the requested device")
        policy, initialization = initialize_act_policy(
            torch, ACTPolicy, policy_config, use_vae=config.use_vae
        )
        metrics["act_initialization"] = initialization
        if (
            config.reference_initial_state_sha256 is not None
            and initialization["reference_initial_state_sha256"]
            != config.reference_initial_state_sha256
        ):
            raise RuntimeError("ACT reference initialization differs from declared experiment")
        policy_config = policy.config
        policy = policy.to(config.device)
        devices = {str(parameter.device) for parameter in policy.parameters()}
        expected_device = "cpu" if config.device == "cpu" else "mps:0"
        if devices != {expected_device}:
            raise RuntimeError(f"Unexpected parameter devices: {devices}")
        stats = copy.deepcopy(dataset.meta.stats)
        numeric_stats = {}
        columns = dataset.hf_dataset.select_columns(["observation.state", "action"])
        for key in ("observation.state", "action"):
            values = np.asarray([row[key] for row in columns], dtype=np.float64)
            numeric_stats[key] = stable_numeric_stats(
                values, std_floor=config.normalization_std_floor
            )
            stats[key].update(numeric_stats[key])
        preprocessor, postprocessor = make_act_pre_post_processors(policy_config, stats)
        optimizer_config = policy_config.get_optimizer_preset()
        optimizer = optimizer_config.build(policy.get_optim_params())
        metrics.update(
            {
                "actual_device": config.device,
                "precision": "float32",
                "parameter_count": sum(p.numel() for p in policy.parameters()),
                "initial_state_sha256": _tensor_digest(policy.state_dict()),
                "dataset_manifest_sha256": dataset_digest,
                "dataset_frames": len(dataset),
                "versions": {
                    name: importlib.metadata.version(name)
                    for name in ("torch", "torchvision", "lerobot", "numpy", "datasets", "pyarrow")
                },
                "optimizer_weight_decay": optimizer_config.weight_decay,
                "gradient_clip_norm": optimizer_config.grad_clip_norm,
                "deterministic_algorithms_enabled": torch.are_deterministic_algorithms_enabled(),
            }
        )

        def synchronize():
            if config.device == "mps":
                torch.mps.synchronize()

        for step in range(config.steps):
            step_start = time.perf_counter()
            indices = sample_training_indices(torch, sampler, sampling_plan, config.batch_size)
            allowed = set(input_features) | {"action", "action_is_pad"}
            items = [
                {key: value for key, value in dataset[index].items() if key in allowed}
                for index in indices
            ]
            raw_batch = default_collate(items)
            batch = preprocessor(raw_batch)
            if tuple(batch["action"].shape) != (config.batch_size, config.chunk_size, 12):
                raise ValueError("ACT batch action chunk shape mismatch")
            if batch["action_is_pad"].all().item():
                raise ValueError("ACT batch contains no real action targets")
            policy.train()
            optimizer.zero_grad(set_to_none=True)
            loss, parts = act_training_loss(policy, batch, profile=config.temporal_loss_profile)
            if not torch.isfinite(loss).item():
                raise RuntimeError("Non-finite ACT loss")
            loss.backward()
            gradients = [p.grad for p in policy.parameters() if p.grad is not None]
            if not gradients or not all(torch.isfinite(g).all().item() for g in gradients):
                raise RuntimeError("Missing or non-finite ACT gradients")
            norm = float(
                torch.nn.utils.clip_grad_norm_(policy.parameters(), optimizer_config.grad_clip_norm)
            )
            if not np.isfinite(norm) or norm <= 0:
                raise RuntimeError("Invalid ACT gradient norm")
            actual_learning_rates = apply_learning_rate(optimizer, config, step + 1)
            optimizer.step()
            synchronize()
            item = dict(
                step=step + 1,
                indices=indices,
                sampled_frames=[sampling_plan["frames"][index] for index in indices],
                loss=float(loss.detach().cpu()),
                loss_parts=parts,
                gradient_norm=norm,
                learning_rates=actual_learning_rates,
                seconds=time.perf_counter() - step_start,
            )
            metrics["steps"].append(item)
            with (directory / "steps.jsonl").open("a") as stream:
                stream.write(json.dumps(item, allow_nan=False) + "\n")
        metrics["updated_state_sha256"] = _tensor_digest(policy.state_dict())
        if metrics["updated_state_sha256"] == metrics["initial_state_sha256"]:
            raise RuntimeError("Optimizer did not change model parameters")
        checkpoint = directory / "checkpoint"
        policy.save_pretrained(checkpoint)
        (checkpoint / "training_sampling.json").write_bytes(canonical(sampling_plan))
        schedule_metadata = dict(
            definition=metrics["learning_rate_schedule"],
            completed_updates=config.steps,
            final_learning_rates=list(actual_learning_rates),
        )
        (checkpoint / "training_schedule.json").write_bytes(canonical(schedule_metadata))
        (checkpoint / "training_loss.json").write_bytes(canonical(metrics["temporal_loss"]))
        preprocessor.save_pretrained(checkpoint, config_filename="policy_preprocessor.json")
        postprocessor.save_pretrained(checkpoint, config_filename="policy_postprocessor.json")
        (directory / "normalization.json").write_text(
            json.dumps(
                {
                    "mapping": {
                        key: value.value
                        for key, value in policy_config.normalization_mapping.items()
                    },
                    "dataset_stats_sha256": digest_file(dataset_root / "meta" / "stats.json"),
                    "images": "original RGB decoded to float32 [0,1], then dataset mean/std",
                    "state_action": "dataset mean/std; inverse action processor saved",
                    "resize": None,
                    "numeric_stats": numeric_stats,
                    "numeric_statistics_method": "float64 training rows; population std",
                    "numeric_std_floor_rad": config.normalization_std_floor,
                    "numeric_scope": (
                        "selected_skill_and_corrective"
                        if corrective_manifest is not None
                        else "selected_skill"
                        if skill_view
                        else "full_training_dataset"
                    ),
                    "image_statistics_scope": "full_parent_training_dataset",
                },
                indent=2,
            )
            + "\n"
        )
        torch.save(
            {
                "step": config.steps,
                "optimizer": optimizer.state_dict(),
                "learning_rate_schedule": schedule_metadata,
                "temporal_loss": metrics["temporal_loss"],
                "sampler_rng_state": sampler.get_state(),
                "sampling_plan": sampling_plan,
                "sampling_plan_sha256": sampling_digest,
                "torch_rng_state": torch.get_rng_state(),
                "mps_rng_state": torch.mps.get_rng_state() if config.device == "mps" else None,
                "python_rng_state": random.getstate(),
                "numpy_rng_state": {
                    "kind": np.random.get_state()[0],
                    "keys": np.random.get_state()[1].tolist(),
                    "position": np.random.get_state()[2],
                    "has_gauss": np.random.get_state()[3],
                    "cached_gaussian": np.random.get_state()[4],
                },
                "dataset_manifest_sha256": dataset_digest,
            },
            directory / "trainer_state.pt",
        )
        restored_state = torch.load(
            directory / "trainer_state.pt", map_location="cpu", weights_only=True
        )
        if (
            restored_state["sampling_plan"] != sampling_plan
            or restored_state["sampling_plan_sha256"] != sampling_digest
        ):
            raise RuntimeError("Saved sampling plan differs from the training plan")
        if (
            restored_state["learning_rate_schedule"] != schedule_metadata
            or [group["lr"] for group in restored_state["optimizer"]["param_groups"]]
            != actual_learning_rates
            or json.loads((checkpoint / "training_schedule.json").read_text()) != schedule_metadata
        ):
            raise RuntimeError("Saved optimizer learning rates or schedule metadata differ")
        metrics["learning_rate_reload_verified"] = True
        if (
            restored_state["temporal_loss"] != metrics["temporal_loss"]
            or json.loads((checkpoint / "training_loss.json").read_text())
            != metrics["temporal_loss"]
        ):
            raise RuntimeError("Saved temporal loss profile differs from the training objective")
        metrics["temporal_loss_reload_verified"] = True
        restored_sampler = torch.Generator(device="cpu")
        restored_sampler.set_state(restored_state["sampler_rng_state"])
        saved_sampler_state = sampler.get_state()
        expected_next = sample_training_indices(torch, sampler, sampling_plan, config.batch_size)
        restored_next = sample_training_indices(
            torch, restored_sampler, restored_state["sampling_plan"], config.batch_size
        )
        sampler.set_state(saved_sampler_state)
        if expected_next != restored_next:
            raise RuntimeError("Saved sampler RNG did not reproduce the next batch")
        metrics["sampler_reload_verified"] = True
        del restored_state
        policy.eval()
        with torch.inference_mode():
            observation = {key: batch[key] for key in input_features}
            prediction = policy.predict_action_chunk(observation)
            if not torch.isfinite(prediction).all().item():
                raise RuntimeError("Trained checkpoint produced non-finite actions")
            reloaded = ACTPolicy.from_pretrained(checkpoint, local_files_only=True).to(
                config.device
            )
            reloaded.eval()
            replayed = reloaded.predict_action_chunk(observation)
            torch.testing.assert_close(prediction, replayed, rtol=1e-5, atol=1e-6)
            loaded_pre = PolicyProcessorPipeline.from_pretrained(
                checkpoint,
                config_filename="policy_preprocessor.json",
                local_files_only=True,
            )
            loaded_post = PolicyProcessorPipeline.from_pretrained(
                checkpoint,
                config_filename="policy_postprocessor.json",
                local_files_only=True,
                to_transition=policy_action_to_transition,
                to_output=transition_to_policy_action,
            )
            fresh = {
                key: value.clone() for key, value in raw_batch.items() if key in input_features
            }
            loaded_observation = loaded_pre(fresh)
            for key in input_features:
                torch.testing.assert_close(loaded_observation[key], observation[key])
            restored_prediction = reloaded.predict_action_chunk(loaded_observation)
            physical_action = postprocessor(prediction)
            restored_action = loaded_post(restored_prediction)
            torch.testing.assert_close(physical_action, restored_action, rtol=1e-5, atol=1e-6)
            if not torch.isfinite(physical_action).all().item():
                raise RuntimeError("Unnormalized checkpoint output is non-finite")
        if verify_training_dataset(dataset_root) != dataset_manifest or (
            digest_file(dataset_root / "export_manifest.json") != dataset_digest
        ):
            raise ValueError("Dataset changed during training")
        if corrective_manifest is not None:
            if (
                verify_corrective_dataset(corrective_root) != corrective_manifest
                or (
                    digest_file(corrective_root / "export_manifest.json")
                    != sampling_plan["corrective_dataset"]["export_manifest_sha256"]
                )
                or digest_file(corrective_root / "corrective_views.json")
                != metrics["corrective_views_sha256"]
            ):
                raise ValueError("Corrective dataset changed during training")
        metrics["checkpoint_reload_verified"] = True
        metrics["processor_reload_verified"] = True
        metrics["training_completed"] = True
        metrics["total_seconds"] = time.perf_counter() - started
        (directory / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        return store.seal(
            directory,
            kind="act_training",
            outcome="completed",
            config=config.model_dump(mode="json"),
            metrics=metrics,
            source=source,
            claims=["ACT updated from verified demonstration images/actions"],
        )
    except (Exception, KeyboardInterrupt) as exc:
        metrics["interrupted"] = isinstance(exc, KeyboardInterrupt)
        (directory / "error.txt").write_text(traceback.format_exc())
        metrics["total_seconds"] = time.perf_counter() - started
        (directory / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        store.seal(
            directory,
            kind="act_training",
            outcome="failed",
            config=config.model_dump(mode="json"),
            metrics=metrics,
            source=source,
            claims=[],
        )
        raise
    finally:
        if torch is not None and old_threads is not None:
            torch.set_num_threads(old_threads)
