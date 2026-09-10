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
from pydantic import BaseModel, ConfigDict, Field

from bimanual.contracts import Artifact, DemonstrationEpisode, validate_split_seeds
from bimanual.dataset_export import CAMERA_FEATURES, LEROBOT_VERSION
from bimanual.demonstrations import require_successful_training_episode
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.training_probe import _tensor_digest


class ACTTrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    dataset_path: Path
    device: Literal["cpu", "mps"] = "cpu"
    architecture: Literal["small", "default"] = "small"
    steps: int = Field(default=3, ge=1, le=1_000_000)
    batch_size: int = Field(default=1, ge=1, le=64)
    chunk_size: int = Field(default=10, ge=1, le=100)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    cpu_threads: int = Field(default=4, ge=1, le=32)
    learning_rate: float = Field(default=1e-5, gt=0, le=0.1)
    normalization_std_floor: float = Field(default=1e-4, gt=0, le=1)


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
            delta_timestamps={"action": [i / 20 for i in range(config.chunk_size)]},
        )
        if len(dataset) != dataset_manifest["frames"]:
            raise ValueError("Loaded dataset frame count mismatch")
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
            optimizer_lr=config.learning_rate,
            optimizer_lr_backbone=config.learning_rate,
            **architecture,
        )
        if policy_config.device != config.device:
            raise RuntimeError("LeRobot changed the requested device")
        policy = ACTPolicy(policy_config).to(config.device)
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
            indices = torch.randint(len(dataset), (config.batch_size,), generator=sampler).tolist()
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
            loss, parts = policy(batch)
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
            optimizer.step()
            synchronize()
            item = dict(
                step=step + 1,
                indices=indices,
                loss=float(loss.detach().cpu()),
                loss_parts=parts,
                gradient_norm=norm,
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
                },
                indent=2,
            )
            + "\n"
        )
        torch.save(
            {
                "step": config.steps,
                "optimizer": optimizer.state_dict(),
                "sampler_rng_state": sampler.get_state(),
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
