"""Guarded ACT execution in the training placement scene, without teacher actions."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import time
import traceback
from collections import deque
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field

from bimanual.contracts import ActionChunk, Artifact, CameraFrame, JointLimits, Observation
from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.dual_arm import CAMERAS, JOINT_ORDER, MODEL_DIR
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.grasp import GraspConfig, GraspEnvironment, score_grasp

_RAW_KEYS = {
    "schema_version",
    "episode_id",
    "sequence",
    "simulation_seconds",
    "observed_monotonic_ns",
    "joint_order",
    "joint_position_rad",
    "joint_velocity_rad_s",
    "rgb",
    "camera_order",
}
_PHASES = (
    (20, "settle"),
    (60, "approach"),
    (100, "descend"),
    (130, "close"),
    (190, "lift"),
    (230, "hold"),
    (290, "transport"),
    (350, "lower"),
    (380, "release"),
    (420, "retreat"),
    (460, "settled"),
)


class PolicyRolloutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    training_run: Path
    device: Literal["cpu", "mps"] = "cpu"
    max_seconds: float = Field(default=23, ge=0.05, le=23)
    max_observation_age_seconds: float = Field(default=2, gt=0, le=10)
    replay: bool = True
    cpu_threads: int = Field(default=4, ge=1, le=32)
    execute_chunk_steps: int = Field(default=10, ge=1, le=100, strict=True)


def policy_inputs(raw: dict) -> dict[str, np.ndarray]:
    """Explicit perception boundary: only RGB and measured robot joint positions."""
    if set(raw) != _RAW_KEYS or raw["schema_version"] != 1:
        raise ValueError("Unexpected observation fields; simulator truth is forbidden")
    if tuple(raw["joint_order"]) != JOINT_ORDER or tuple(raw["camera_order"]) != CAMERAS:
        raise ValueError("Unexpected joint/camera order")
    if tuple(raw["rgb"]) != CAMERAS:
        raise ValueError("All three fresh cameras are required")
    state = np.asarray(raw["joint_position_rad"], dtype=np.float32)
    if state.shape != (12,) or not np.isfinite(state).all():
        raise ValueError("Invalid observed joint positions")
    result = {"observation.state": state.copy()}
    for camera, feature in CAMERA_FEATURES.items():
        pixels = raw["rgb"][camera]
        if (
            not isinstance(pixels, np.ndarray)
            or pixels.dtype != np.uint8
            or pixels.shape != (270, 480, 3)
        ):
            raise ValueError("Expected uint8 RGB camera images")
        result[feature] = pixels.transpose(2, 0, 1).astype(np.float32) / 255
    return result


def save_observation(raw: dict, directory: Path, *, prefix: str = "observations") -> Observation:
    policy_inputs(raw)
    capture = {key: raw[key] for key in ("sequence", "simulation_seconds", "observed_monotonic_ns")}
    frames = []
    for index, camera in enumerate(CAMERAS):
        relative = f"{prefix}/{raw['sequence']:06d}-{index}.png"
        target = directory / relative
        with target.open("xb") as stream:
            Image.fromarray(raw["rgb"][camera]).save(stream, format="PNG")
        frames.append(
            CameraFrame(
                camera=camera,
                **capture,
                artifact=Artifact(path=relative, sha256=digest_file(target)),
            )
        )
    return Observation(
        episode_id=raw["episode_id"],
        instruction_revision=0,
        **capture,
        joint_position_rad=np.asarray(raw["joint_position_rad"]).tolist(),
        joint_velocity_rad_s=np.asarray(raw["joint_velocity_rad_s"]).tolist(),
        frames=tuple(frames),
    )


class GuardedActionQueue:
    """All proposal bounds checked before enqueue; right arm explicitly owned by supervisor."""

    def __init__(
        self,
        limits: JointLimits,
        home: np.ndarray,
        policy_sha256: str,
        max_age_ns: int,
        *,
        execute_chunk_steps: int = 10,
    ):
        if type(execute_chunk_steps) is not int or not 1 <= execute_chunk_steps <= 100:
            raise ValueError("Execution prefix must contain between one and 100 steps")
        self.execute_chunk_steps = execute_chunk_steps
        self.limits, self.home = limits, home.copy()
        self.policy_sha256, self.max_age_ns = policy_sha256, max_age_ns
        self.clear()

    def clear(self):
        self.pending = deque()
        self.chunk = self.anchor = None
        self.consumed = 0

    def offer(self, targets: np.ndarray, observation: Observation, *, now_ns: int) -> dict:
        self.clear()
        values = np.asarray(targets, dtype=float)
        if values.ndim != 2 or values.shape[1] != 12:
            raise ValueError("Expected action chunk shape N x 12")
        raw = ActionChunk(
            episode_id=observation.episode_id,
            instruction_revision=observation.instruction_revision,
            observation_sequence=observation.sequence,
            observed_monotonic_ns=observation.observed_monotonic_ns,
            generated_monotonic_ns=now_ns,
            expires_monotonic_ns=observation.observed_monotonic_ns + self.max_age_ns,
            policy_sha256=self.policy_sha256,
            targets_rad=values.tolist(),
        )
        raw.validate_for(
            observation,
            self.limits,
            now_monotonic_ns=now_ns,
            max_observation_age_ns=self.max_age_ns,
            expected_policy_sha256=self.policy_sha256,
        )
        accepted = values.copy()
        accepted[:, 6:] = self.home[6:]
        chunk = ActionChunk.model_validate(raw.model_dump() | {"targets_rad": accepted.tolist()})
        chunk.validate_for(
            observation,
            self.limits,
            now_monotonic_ns=now_ns,
            max_observation_age_ns=self.max_age_ns,
            expected_policy_sha256=self.policy_sha256,
        )
        self.chunk, self.anchor = chunk, observation
        prefix_length = min(self.execute_chunk_steps, len(chunk.targets_rad))
        self.pending.extend(chunk.targets_rad[:prefix_length])
        return {
            "raw_chunk": raw.model_dump(mode="json"),
            "accepted_chunk": chunk.model_dump(mode="json"),
            "ownership_mask": "right six joints held at reset; left six unchanged",
            "prediction_horizon_steps": len(chunk.targets_rad),
            "execution_prefix_steps": prefix_length,
            "discarded_forecast_steps": len(chunk.targets_rad) - prefix_length,
        }

    def take(self, current: Observation, *, now_ns: int, cancelled: bool = False) -> np.ndarray:
        try:
            if cancelled:
                raise InterruptedError("Operator cancelled rollout")
            if not self.pending:
                raise ValueError("No accepted action queued")
            if (current.episode_id, current.instruction_revision, current.sequence) != (
                self.anchor.episode_id,
                self.anchor.instruction_revision,
                self.anchor.sequence + self.consumed,
            ):
                raise ValueError("Action queue no longer matches current episode/sequence")
            if not 0 <= now_ns - current.observed_monotonic_ns <= self.max_age_ns:
                raise ValueError("Current observation is stale or from the future")
            self.chunk.validate_for(
                self.anchor,
                self.limits,
                now_monotonic_ns=now_ns,
                max_observation_age_ns=self.max_age_ns,
                expected_policy_sha256=self.policy_sha256,
            )
            value = np.asarray(self.pending.popleft())
            self.consumed += 1
            return value
        except Exception:
            self.clear()
            raise


def _load_policy(checkpoint: Path, device: str):
    if importlib.metadata.version("lerobot") != "0.6.1":
        raise RuntimeError("Rollout requires pinned LeRobot 0.6.1")
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.processor import PolicyProcessorPipeline
    from lerobot.processor.converters import (
        policy_action_to_transition,
        transition_to_policy_action,
    )

    if platform.system() == "Darwin" and platform.machine() != "arm64":
        raise RuntimeError("Local rollout requires native arm64 Python")
    if device == "mps" and (
        not torch.backends.mps.is_available()
        or os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0"
    ):
        raise RuntimeError("MPS unavailable or CPU fallback enabled")
    config = PreTrainedConfig.from_pretrained(checkpoint, local_files_only=True)
    config.device = device
    expected = {
        "observation.state": (12,),
        **{name: (3, 270, 480) for name in CAMERA_FEATURES.values()},
    }
    if {key: value.shape for key, value in config.input_features.items()} != expected:
        raise ValueError("Checkpoint input interface mismatch")
    if config.type != "act" or config.output_features["action"].shape != (12,):
        raise ValueError("Expected twelve-joint ACT policy")
    if config.pretrained_backbone_weights is not None:
        raise ValueError("Checkpoint must not require downloaded backbone initialization")
    with redirect_stdout(sys.stderr):
        policy = ACTPolicy.from_pretrained(checkpoint, config=config, local_files_only=True).to(
            device
        )
    devices = {str(p.device) for p in policy.parameters()}
    if devices != {"mps:0" if device == "mps" else "cpu"}:
        raise RuntimeError(f"Unexpected policy device: {devices}")
    pre = PolicyProcessorPipeline.from_pretrained(
        checkpoint,
        config_filename="policy_preprocessor.json",
        local_files_only=True,
        overrides={"device_processor": {"device": device}},
    )
    post = PolicyProcessorPipeline.from_pretrained(
        checkpoint,
        config_filename="policy_postprocessor.json",
        local_files_only=True,
        to_transition=policy_action_to_transition,
        to_output=transition_to_policy_action,
    )
    policy.eval()
    policy.reset()
    return torch, policy, pre, post


def run_policy_rollout(
    config: PolicyRolloutConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] | None = None,
) -> Manifest:
    """Run one declared training-scene diagnostic; return sealed physical failure honestly."""
    cancelled = cancelled or (lambda: False)
    directory = store.new_run()
    source = provenance(project_root)
    metrics = {
        "evaluation_split": "training_scene_diagnostic",
        "teacher_assistance": False,
        "requested_device": config.device,
        "actual_device": None,
        "placement_success": False,
        "manipulation_success": None,
        "inference_seconds": [],
    }
    env = policy = queue = torch_runtime = old_threads = None
    outcome = "failed"
    started = time.perf_counter()
    frames, chunks, observations, actions = [], [], [], []
    try:
        if cancelled():
            raise InterruptedError("Operator cancelled before checkpoint loading")
        training_root = (
            config.training_run
            if config.training_run.is_absolute()
            else project_root / config.training_run
        ).resolve(strict=True)
        training_manifest = EvidenceStore(training_root.parent.parent).verify(training_root.name)
        if training_manifest.kind != "act_training" or training_manifest.outcome != "completed":
            raise ValueError("Only sealed completed ACT training runs may supply a checkpoint")
        if not training_manifest.metrics.get(
            "checkpoint_reload_verified"
        ) or not training_manifest.metrics.get("processor_reload_verified"):
            raise ValueError("Training run did not verify checkpoint and processors")
        shutil.copytree(training_root / "checkpoint", directory / "checkpoint")
        (directory / "training_manifest.json").write_bytes(
            (training_root / "manifest.json").read_bytes()
        )
        for name, expected in training_manifest.files.items():
            if name.startswith("checkpoint/") and digest_file(directory / name) != expected:
                raise ValueError("Checkpoint changed during copy")
        checkpoint_digest = hashlib.sha256(
            canonical(
                {
                    name: value
                    for name, value in training_manifest.files.items()
                    if name.startswith("checkpoint/")
                }
            )
        ).hexdigest()
        metrics["checkpoint_sha256"] = checkpoint_digest
        metrics["training_run_id"] = training_root.name
        metrics["training_manifest_sha256"] = training_manifest.manifest_sha256
        (directory / "config.json").write_text(config.model_dump_json(indent=2) + "\n")
        torch, policy, pre, post = _load_policy(directory / "checkpoint", config.device)
        torch_runtime = torch
        old_threads = torch.get_num_threads()
        torch.set_num_threads(config.cpu_threads)
        metrics["actual_device"] = config.device
        metrics["cpu_threads"] = config.cpu_threads
        metrics["prediction_horizon_steps"] = policy.config.chunk_size
        metrics["execution_prefix_limit"] = config.execute_chunk_steps
        metrics["precision"] = "float32"
        metrics["torch_version"] = torch.__version__
        env = GraspEnvironment(GraspConfig(destination_xy=(-0.15, 0.08)))
        dataset_manifest = json.loads((training_root / "dataset_manifest.json").read_text())
        if digest_file(training_root / "dataset_manifest.json") != training_manifest.metrics.get(
            "dataset_manifest_sha256"
        ):
            raise ValueError("Training dataset identity mismatch")
        scene_digest = hashlib.sha256(env.xml.encode()).hexdigest()
        dataset_root = Path(training_manifest.config["dataset_path"])
        if not dataset_root.is_absolute():
            dataset_root = project_root / dataset_root
        compatible_configs = []
        for item in dataset_manifest["episodes"]:
            if item["lineage"]["scene"]["sha256"] != scene_digest:
                raise ValueError("Checkpoint was trained with a different scene")
            reference = Artifact(
                path=f"{item['raw_root']}/config.json", sha256=item["lineage"]["config"]["sha256"]
            )
            teacher_config = GraspConfig.model_validate_json(
                reference.verify(dataset_root).read_text()
            )
            if (
                teacher_config.arm != "left"
                or teacher_config.destination_xy != (-0.15, 0.08)
                or teacher_config.object_x != -0.15
                or teacher_config.object_y != -0.08
                or teacher_config.mass_kg != 0.025
                or teacher_config.missing_object
                or teacher_config.skip_close
            ):
                raise ValueError(
                    "Checkpoint demonstration task differs from the declared placement"
                )
            compatible_configs.append(teacher_config.model_dump(mode="json"))
        if not compatible_configs:
            raise ValueError("Checkpoint has no declared training episodes")
        (directory / "training_scene_configs.json").write_text(
            json.dumps(compatible_configs, indent=2)
        )
        metrics["training_scene_sha256"] = scene_digest
        (directory / "scene.xml").write_text(env.xml)
        shutil.copytree(MODEL_DIR / "assets", directory / "assets")
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "observations").mkdir()
        queue = GuardedActionQueue(
            JointLimits(lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist()),
            env.home,
            checkpoint_digest,
            int(config.max_observation_age_seconds * 1e9),
            execute_chunk_steps=config.execute_chunk_steps,
        )
        maximum_steps = min(460, int(config.max_seconds * 20))
        for step in range(maximum_steps):
            if cancelled():
                raise InterruptedError("Operator cancelled rollout")
            env.stage = next(stage for end, stage in _PHASES if step < end)
            raw = env.observe(render=True)
            observation = save_observation(raw, directory)
            observations.append(observation.model_dump(mode="json"))
            if config.replay and step % 2 == 0:
                frame = Image.new("RGB", (1440, 300), "#14202b")
                for column, camera in enumerate(CAMERAS):
                    frame.paste(Image.fromarray(raw["rgb"][camera]), (column * 480, 30))
                ImageDraw.Draw(frame).text(
                    (12, 8),
                    f"LEARNED ACT DIAGNOSTIC | {env.stage} | {env.data.time:.2f}s",
                    fill="white",
                )
                frames.append(frame)
            if not queue.pending:
                inference_start = time.perf_counter()
                with torch.inference_mode():
                    batch = pre(
                        {key: torch.from_numpy(value) for key, value in policy_inputs(raw).items()}
                    )
                    prediction = post(policy.predict_action_chunk(batch)).detach().cpu().numpy()
                metrics["inference_seconds"].append(time.perf_counter() - inference_start)
                raw_proposal = prediction.tolist()
                # Preserve non-finite rejected proposals as explicit strings in strict JSON.
                raw_proposal = json.loads(
                    json.dumps(raw_proposal), parse_constant=lambda value: value
                )
                record = {
                    "observation_sequence": step,
                    "raw_proposal_rad": raw_proposal,
                    "accepted": False,
                }
                chunks.append(record)
                if cancelled():
                    raise InterruptedError("Operator cancelled during inference")
                if prediction.ndim != 3 or prediction.shape[0] != 1:
                    raise ValueError("Expected ACT chunk shape 1 x N x 12")
                record.update(queue.offer(prediction[0], observation, now_ns=time.monotonic_ns()))
                record["accepted"] = True
            target = queue.take(observation, now_ns=time.monotonic_ns(), cancelled=cancelled())
            applied = {
                "observation_sequence": step,
                "targets_rad": target.tolist(),
                "applied": False,
            }
            actions.append(applied)
            env.step(target, episode_id=observation.episode_id, sequence=observation.sequence)
            applied["applied"] = True
            if (
                env.sequence == 230
                and not score_grasp(
                    env.contact_trace,
                    np.array([-0.15, -0.08, 0.391]),
                    np.array([-0.15, 0.08, 0.391]),
                )["hold_passed"]
            ):
                raise RuntimeError("Learned policy failed the two-second airborne hold")
        metrics.update(
            score_grasp(
                env.contact_trace, np.array([-0.15, -0.08, 0.391]), np.array([-0.15, 0.08, 0.391])
            )
        )
        if not metrics["placement_success"]:
            raise RuntimeError("Learned placement did not pass the declared physical checks")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        outcome = (
            "interrupted" if isinstance(exc, (KeyboardInterrupt, InterruptedError)) else "failed"
        )
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        (directory / "error.txt").write_text(traceback.format_exc())
    finally:
        if queue:
            queue.clear()
        if policy:
            policy.reset()
        if env:
            if (directory / "observations").is_dir():
                try:
                    (directory / "terminal").mkdir()
                    terminal = save_observation(
                        env.observe(render=True), directory, prefix="terminal"
                    )
                    (directory / "terminal-observation.json").write_text(
                        terminal.model_dump_json(indent=2) + "\n"
                    )
                except Exception as exc:
                    metrics["terminal_observation_error"] = f"{type(exc).__name__}: {exc}"
            metrics.update(
                score_grasp(
                    env.contact_trace,
                    np.array([-0.15, -0.08, 0.391]),
                    np.array([-0.15, 0.08, 0.391]),
                )
            )
            metrics["simulation_seconds"] = float(env.data.time)
            (directory / "scoring-truth.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in env.contact_trace)
            )
            env.close()
        for name, rows in (
            ("observations", observations),
            ("action-chunks", chunks),
            ("actions", actions),
        ):
            (directory / f"{name}.jsonl").write_text(
                "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows)
            )
        if frames:
            frames[0].save(directory / "preview.png")
            frames[0].save(
                directory / "replay.gif",
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
            )
        if torch_runtime is not None and old_threads is not None:
            torch_runtime.set_num_threads(old_threads)
        metrics["wall_seconds"] = time.perf_counter() - started
        metrics["control_steps_applied"] = sum(row["applied"] for row in actions)
        (directory / "metrics.json").write_text(
            json.dumps(metrics, indent=2, allow_nan=False) + "\n"
        )
    return store.seal(
        directory,
        kind="act_policy_rollout",
        outcome=outcome,
        config=config.model_dump(mode="json"),
        metrics=metrics,
        source=source,
        claims=["learned_contact_placement_training_scene"] if outcome == "completed" else [],
    )
