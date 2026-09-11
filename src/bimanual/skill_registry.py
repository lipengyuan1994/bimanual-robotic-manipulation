"""Verified development checkpoint bindings; training never establishes release quality."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_views import SkillView, load_skill_views
from bimanual.supervisor import Capability
from bimanual.training import ACTTrainingConfig, build_sampling_plan, restrict_sampling_plan

_SPECS = {
    "handoff_transfer": ("handoff", "both", "practice_block", "right_gripper", ()),
    "bar_place_and_return": ("place", "right", "practice_block", "table", ("left",)),
    "cup_pick_place": ("place", "right", "cup", "table", ()),
    "plate_pick_place": ("place", "left", "plate", "table", ("right",)),
    "drawer_open": ("open_drawer", "left", "drawer", None, ("right",)),
    "spoon_retrieve_place": ("place", "left", "spoon", "table", ()),
    "fork_retrieve_place": ("place", "left", "fork", "table", ()),
}
_MAPPING = {"VISUAL": "MEAN_STD", "STATE": "MEAN_STD", "ACTION": "MEAN_STD"}
_INPUTS = {"observation.state": {"type": "STATE", "shape": [12]}} | {
    name: {"type": "VISUAL", "shape": [3, 270, 480]} for name in CAMERA_FEATURES.values()
}
_OUTPUTS = {"action": {"type": "ACTION", "shape": [12]}}


def dinner_capability(skill_id: str) -> Capability:
    """Fixed host registration; a model cannot request auxiliary ownership."""
    if skill_id not in _SPECS:
        raise ValueError("Unknown dinner skill")
    skill, arm, target, destination, auxiliary = _SPECS[skill_id]
    return Capability(
        capability_id=f"dinner_v1_{skill_id}",
        skill=skill,
        arm=arm,
        target=target,
        destination=destination,
        auxiliary_arms=auxiliary,
    )


@dataclass(frozen=True)
class SkillCheckpointBinding:
    training_run: Path
    dataset_root: Path
    capability: Capability
    view: SkillView
    training_manifest_sha256: str
    checkpoint_path: Path
    policy_sha256: str
    checkpoint_sha256: str
    chunk_size: int
    profile: Literal["dinner_development_registry_v1"] = "dinner_development_registry_v1"
    release_available: Literal[False] = False
    learned_quality: None = None

    def report(self) -> dict:
        return {
            "profile": self.profile,
            "release_available": False,
            "learned_quality": None,
            "capability": self.capability.model_dump(mode="json"),
            "execution_arms": list(self.capability.execution_arms),
            "view": self.view.model_dump(mode="json"),
            "training_run": str(self.training_run),
            "dataset_root": str(self.dataset_root),
            "training_manifest_sha256": self.training_manifest_sha256,
            "checkpoint_path": str(self.checkpoint_path),
            "policy_sha256": self.policy_sha256,
            "checkpoint_sha256": self.checkpoint_sha256,
            "chunk_size": self.chunk_size,
        }

    def reverify(self) -> SkillCheckpointBinding:
        current = load_skill_checkpoint(
            self.training_run, skill_id=self.view.skill_id, dataset_root=self.dataset_root
        )
        if current != self:
            raise ValueError("Checkpoint binding changed after registration")
        return current


def _read(path: Path) -> dict:
    value = json.loads(path.read_text())
    canonical(value)  # Reject NaN/Infinity even where fields are otherwise unused.
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def _stats(path: Path, expected: dict):
    """Inspect only small float32 processor tensors, without torch or pickle loads."""
    if path.stat().st_size > 1_000_000:
        raise ValueError("Oversized normalization state")
    data = path.read_bytes()
    if len(data) < 8:
        raise ValueError("Truncated normalization state")
    size = struct.unpack("<Q", data[:8])[0]
    if size > len(data) - 8:
        raise ValueError("Truncated normalization header")
    header, payload = json.loads(data[8 : 8 + size]), data[8 + size :]
    for name, values in expected.items():
        values = np.asarray(values, dtype="<f4")
        entry = header.get(name, {})
        offsets = entry.get("data_offsets", [])
        if (
            entry.get("dtype") != "F32"
            or entry.get("shape") != list(values.shape)
            or len(offsets) != 2
            or any(type(x) is not int for x in offsets)
            or not 0 <= offsets[0] <= offsets[1] <= len(payload)
            or offsets[1] - offsets[0] != values.nbytes
        ):
            raise ValueError(f"Invalid normalization tensor: {name}")
        actual = np.frombuffer(payload[offsets[0] : offsets[1]], dtype="<f4")
        if not np.isfinite(actual).all() or not np.array_equal(actual, values.reshape(-1)):
            raise ValueError(f"Normalization tensor mismatch: {name}")


def _processors(root: Path, normalization: dict, dataset_root: Path):
    stats = _read(dataset_root / "meta/stats.json")
    expected = {}
    numeric = normalization.get("numeric_stats", {})
    if set(numeric) != {"observation.state", "action"}:
        raise ValueError("Missing selected-skill numeric normalization")
    for feature in _INPUTS | _OUTPUTS:
        for statistic in ("mean", "std"):
            source = numeric if feature in numeric else stats
            values = np.asarray(source[feature][statistic], dtype=float)
            shape = (12,) if feature in numeric else (3, 1, 1)
            if values.shape != shape or not np.isfinite(values).all():
                raise ValueError("Malformed normalization statistics")
            if statistic == "std" and np.any(values <= 0):
                raise ValueError("Normalization standard deviation must be positive")
            expected[f"{feature}.{statistic}"] = values
    for kind, names, features in (
        (
            "preprocessor",
            [
                "rename_observations_processor",
                "to_batch_processor",
                "device_processor",
                "normalizer_processor",
            ],
            _INPUTS | _OUTPUTS,
        ),
        ("postprocessor", ["unnormalizer_processor", "device_processor"], _OUTPUTS),
    ):
        config = _read(root / f"policy_{kind}.json")
        steps = config.get("steps", [])
        if [step.get("registry_name") for step in steps] != names:
            raise ValueError("Unsupported checkpoint processor sequence")
        step = steps[3 if kind == "preprocessor" else 0]
        if step["config"].get("features") != features or step["config"].get("norm_map") != _MAPPING:
            raise ValueError("Processor feature/normalization mismatch")
        if kind == "preprocessor" and steps[0]["config"].get("rename_map") != {}:
            raise ValueError("Unexpected observation renaming")
        filename = step.get("state_file")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("Invalid processor state path")
        # LeRobot stores all dataset statistics in both processor state files.
        _stats(root / filename, expected)


def load_skill_checkpoint(
    training_run: Path, *, skill_id: str, dataset_root: Path
) -> SkillCheckpointBinding:
    """Reverify sealed training, full source dataset, selection and local ACT artifacts.

    This performs no model construction, deserialization of trainer_state.pt, inference,
    upload or task dispatch. Call reverify immediately before loading/binding a model;
    the serialized worker must keep these files immutable through model loading.
    """
    capability = dinner_capability(skill_id)
    root, dataset_root = training_run.resolve(strict=True), dataset_root.resolve(strict=True)
    manifest = EvidenceStore(root.parent.parent).verify(root.name)
    if manifest.kind != "act_training" or manifest.outcome != "completed":
        raise ValueError("Registry requires completed ACT training evidence")
    config = ACTTrainingConfig.model_validate(manifest.config)
    metrics = manifest.metrics
    if config.skill_id != skill_id or config.skill_views_path is None:
        raise ValueError("Training selected a different or absent skill")
    if _read(root / "training_config.json") != manifest.config:
        raise ValueError("Training config disagrees with seal")
    if _read(root / "metrics.json") != metrics:
        raise ValueError("Training metrics disagree with seal")
    for key in (
        "training_completed",
        "sampler_reload_verified",
        "checkpoint_reload_verified",
        "processor_reload_verified",
    ):
        if metrics.get(key) is not True:
            raise ValueError(f"Missing successful training check: {key}")
    if metrics.get("versions", {}).get("lerobot") != "0.6.1":
        raise ValueError("Unsupported training library version")
    views = load_skill_views(root / "skill_views.json", dataset_root=dataset_root)
    view = next(view for view in views.views if view.skill_id == skill_id)
    view_digest = digest_file(root / "skill_views.json")
    if (metrics.get("skill_view"), metrics.get("skill_views_file_sha256")) != (
        view.model_dump(mode="json"),
        view_digest,
    ):
        raise ValueError("Selected skill metadata mismatch")
    dataset = _read(root / "dataset_manifest.json")
    dataset_digest = digest_file(dataset_root / "export_manifest.json")
    if (
        digest_file(root / "dataset_manifest.json") != dataset_digest
        or metrics.get("dataset_manifest_sha256") != dataset_digest
    ):
        raise ValueError("Training dataset identity mismatch")
    plan = restrict_sampling_plan(
        build_sampling_plan(dataset_root, dataset, config, project_root=root), view, view_digest
    )
    if (
        _read(root / "sampling-plan.json") != plan
        or _read(root / "checkpoint/training_sampling.json") != plan
        or metrics.get("sampling_plan_sha256") != digest_file(root / "sampling-plan.json")
        or metrics.get("sampling_profile") != "uniform"
    ):
        raise ValueError("Sampler does not preserve the selected skill boundary")
    checkpoint = root / "checkpoint"
    act = _read(checkpoint / "config.json")
    if (
        act.get("type") != "act"
        or act.get("input_features") != _INPUTS
        or act.get("output_features") != _OUTPUTS
        or act.get("n_obs_steps") != 1
        or type(act.get("chunk_size")) is not int
        or act["chunk_size"] != config.chunk_size
        or act.get("n_action_steps") != config.chunk_size
        or act.get("normalization_mapping") != _MAPPING
    ):
        raise ValueError("Checkpoint observation/action/horizon contract mismatch")
    normalization = _read(root / "normalization.json")
    if (
        normalization.get("mapping") != _MAPPING
        or normalization.get("numeric_scope") != "selected_skill"
        or normalization.get("image_statistics_scope") != "full_parent_training_dataset"
        or normalization.get("resize") is not None
        or normalization.get("numeric_std_floor_rad") != config.normalization_std_floor
        or normalization.get("dataset_stats_sha256")
        != digest_file(dataset_root / "meta/stats.json")
    ):
        raise ValueError("Normalization lineage or scope mismatch")
    _processors(checkpoint, normalization, dataset_root)
    required = {"checkpoint/model.safetensors", "trainer_state.pt"}
    if not required <= manifest.files.keys() or any(
        (root / name).stat().st_size == 0 for name in required
    ):
        raise ValueError("Missing model or trainer-state artifact")
    checkpoint_files = {
        name: digest for name, digest in manifest.files.items() if name.startswith("checkpoint/")
    }
    return SkillCheckpointBinding(
        training_run=root,
        dataset_root=dataset_root,
        capability=capability,
        view=view,
        training_manifest_sha256=manifest.manifest_sha256,
        checkpoint_path=checkpoint,
        policy_sha256=manifest.files["checkpoint/model.safetensors"],
        checkpoint_sha256=hashlib.sha256(canonical(checkpoint_files)).hexdigest(),
        chunk_size=config.chunk_size,
    )
