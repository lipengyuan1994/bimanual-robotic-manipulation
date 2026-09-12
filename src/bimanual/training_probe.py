"""Real ACT execution on synthetic inputs; never a manipulation-quality evaluation."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import json
import os
import platform
import time
import traceback
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from bimanual.evidence import EvidenceStore, Manifest, provenance

CAMERA_KEYS = (
    "observation.images.overhead",
    "observation.images.left_wrist",
    "observation.images.right_wrist",
)


class TrainingProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    device: Literal["cpu", "mps"] = "cpu"
    architecture: Literal["small", "default"] = "small"
    image_height: int = Field(default=270, ge=32, le=540)
    image_width: int = Field(default=480, ge=32, le=960)
    chunk_size: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=1, ge=1, le=4)
    train_steps: int = Field(default=1, ge=1, le=10)
    inference_samples: int = Field(default=3, ge=1, le=100)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    cpu_threads: int = Field(default=4, ge=1, le=32)


def _tensor_digest(tensors) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(tensors.items()):
        array = tensor.detach().cpu().contiguous().numpy()
        hasher.update(name.encode())
        hasher.update(str((array.shape, array.dtype)).encode())
        hasher.update(array.tobytes())
    return hasher.hexdigest()


def run_training_probe(
    config: TrainingProbeConfig, *, store: EvidenceStore, project_root: Path
) -> Manifest:
    """Seal success or failure of real loss/backprop/AdamW/inference, with no network I/O.

    Synthetic tensors exercise the runtime only. They are never issued to a robot,
    interpreted as demonstrations, or promoted to an inference checkpoint.
    """
    directory = store.new_run()
    source = provenance(project_root)
    metrics = {
        "requested_device": config.device,
        "actual_device": None,
        "precision": "float32",
        "input_kind": "synthetic_seeded_uniform",
        "initialization": "random_no_pretrained_weights",
        "runtime_success": False,
        "manipulation_success": None,
        "learned_policy_quality": None,
        "versions": {},
        "train_steps": [],
    }
    started = time.perf_counter()
    old_threads = None
    torch = None
    try:
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            raise RuntimeError("Local macOS training requires a native arm64 interpreter")
        # PyTorch reads fallback at process initialization; changing it now cannot
        # prove that unsupported GPU operations did not silently execute on CPU.
        if config.device == "mps" and os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0":
            raise RuntimeError("Start a fresh process with PYTORCH_ENABLE_MPS_FALLBACK=0")
        import torch
        from lerobot.configs.types import FeatureType, PolicyFeature
        from lerobot.policies.act.configuration_act import ACTConfig
        from lerobot.policies.act.modeling_act import ACTPolicy

        metrics["versions"] = {
            package: importlib.metadata.version(package)
            for package in ("torch", "torchvision", "lerobot", "numpy")
        }
        if config.device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("Requested MPS is unavailable; no CPU fallback was attempted")
        old_threads = torch.get_num_threads()
        torch.set_num_threads(config.cpu_threads)
        torch.manual_seed(config.seed)
        if config.device == "mps":
            torch.mps.manual_seed(config.seed)
        features = {
            "observation.state": PolicyFeature(type=FeatureType.STATE, shape=(12,)),
            **{
                key: PolicyFeature(
                    type=FeatureType.VISUAL,
                    shape=(3, config.image_height, config.image_width),
                )
                for key in CAMERA_KEYS
            },
        }
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
        act_config = ACTConfig(
            input_features=features,
            output_features={"action": PolicyFeature(type=FeatureType.ACTION, shape=(12,))},
            chunk_size=config.chunk_size,
            n_action_steps=config.chunk_size,
            device=config.device,
            pretrained_backbone_weights=None,
            push_to_hub=False,
            use_amp=False,
            **architecture,
        )
        if act_config.device != config.device:
            raise RuntimeError(f"LeRobot changed requested device to {act_config.device}")
        (directory / "act_config.json").write_text(
            json.dumps(dataclasses.asdict(act_config), indent=2, default=str) + "\n"
        )
        policy = ACTPolicy(act_config).to(config.device)
        parameter_devices = sorted({str(p.device) for p in policy.parameters()})
        if parameter_devices != [config.device if config.device == "cpu" else "mps:0"]:
            raise RuntimeError(f"Unexpected model parameter devices: {parameter_devices}")
        metrics["actual_device"] = config.device
        metrics["parameter_devices"] = parameter_devices
        metrics["parameter_count"] = sum(p.numel() for p in policy.parameters())
        metrics["initial_state_sha256"] = _tensor_digest(policy.state_dict())
        # Generate on CPU so seed input identity is comparable across devices.
        generator = torch.Generator(device="cpu").manual_seed(config.seed)
        batch = {
            "observation.state": torch.rand(config.batch_size, 12, generator=generator) * 2 - 1,
            "action": torch.rand(config.batch_size, config.chunk_size, 12, generator=generator) * 2
            - 1,
            "action_is_pad": torch.zeros(config.batch_size, config.chunk_size, dtype=torch.bool),
            **{
                key: torch.rand(
                    config.batch_size,
                    3,
                    config.image_height,
                    config.image_width,
                    generator=generator,
                )
                for key in CAMERA_KEYS
            },
        }
        metrics["input_sha256"] = _tensor_digest(batch)
        batch = {key: value.to(config.device) for key, value in batch.items()}
        optimizer = act_config.get_optimizer_preset().build(policy.get_optim_params())
        metrics["deterministic_algorithms_enabled"] = torch.are_deterministic_algorithms_enabled()
        metrics["optimizer"] = dataclasses.asdict(act_config.get_optimizer_preset())

        def synchronize():
            if config.device == "mps":
                torch.mps.synchronize()

        synchronize()
        metrics["initialization_seconds"] = time.perf_counter() - started
        for _ in range(config.train_steps):
            policy.train()
            optimizer.zero_grad(set_to_none=True)
            synchronize()
            step_start = time.perf_counter()
            loss, loss_parts = policy(batch)
            if not torch.isfinite(loss).item():
                raise RuntimeError("ACT loss is non-finite")
            loss.backward()
            gradients = [p.grad for p in policy.parameters() if p.grad is not None]
            if not gradients or not all(torch.isfinite(g).all().item() for g in gradients):
                raise RuntimeError("Missing or non-finite ACT gradients")
            gradient_norm = float(
                torch.nn.utils.clip_grad_norm_(
                    policy.parameters(), act_config.get_optimizer_preset().grad_clip_norm
                )
            )
            if not np.isfinite(gradient_norm) or gradient_norm <= 0:
                raise RuntimeError("ACT gradient norm is non-finite or zero")
            optimizer.step()
            synchronize()
            metrics["train_steps"].append(
                {
                    "seconds": time.perf_counter() - step_start,
                    "loss": float(loss.detach().cpu()),
                    "loss_parts": loss_parts,
                    "finite_gradient_tensors": len(gradients),
                    "gradient_norm_before_clipping": gradient_norm,
                }
            )
        metrics["updated_state_sha256"] = _tensor_digest(policy.state_dict())
        if metrics["initial_state_sha256"] == metrics["updated_state_sha256"]:
            raise RuntimeError("Optimizer did not update model parameters")
        observation = {key: value for key, value in batch.items() if key.startswith("observation.")}
        policy.eval()
        latencies = []
        with torch.inference_mode():
            for _ in range(config.inference_samples + 1):
                synchronize()
                inference_start = time.perf_counter()
                actions = policy.predict_action_chunk(observation)
                synchronize()
                latencies.append(time.perf_counter() - inference_start)
                if tuple(actions.shape) != (config.batch_size, config.chunk_size, 12):
                    raise RuntimeError(f"Unexpected ACT output shape: {actions.shape}")
                if not torch.isfinite(actions).all().item():
                    raise RuntimeError("Non-finite inferred actions")
        metrics["inference_cold_seconds"] = latencies[0]
        metrics["inference_warm_seconds"] = latencies[1:]
        metrics["inference_warm_p50_seconds"] = float(np.percentile(latencies[1:], 50))
        metrics["inference_warm_p95_seconds"] = float(np.percentile(latencies[1:], 95))
        metrics["inference_chunks_per_second"] = config.batch_size / float(np.mean(latencies[1:]))
        metrics["output_shape"] = list(actions.shape)
        metrics["output_sha256"] = _tensor_digest({"action": actions})
        np.save(directory / "synthetic_action_chunk.npy", actions.detach().cpu().numpy())
        metrics["runtime_success"] = True
    except Exception as exc:
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        (directory / "failure.txt").write_text(traceback.format_exc())
    finally:
        if old_threads is not None and torch is not None:
            torch.set_num_threads(old_threads)
    metrics["wall_seconds"] = time.perf_counter() - started
    metrics = json.loads(json.dumps(metrics, allow_nan=False))
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    return store.seal(
        directory,
        kind="act_runtime_probe",
        outcome="completed" if metrics["runtime_success"] else "failed",
        config=config.model_dump(mode="json"),
        metrics=metrics,
        source=source,
        claims=["act_synthetic_training_and_inference"] if metrics["runtime_success"] else [],
    )
