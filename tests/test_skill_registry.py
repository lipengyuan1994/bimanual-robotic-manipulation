"""Synthetic metadata fixtures exercise intake only, never model execution or quality."""

import json
import shutil
import struct
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from test_skill_views import seal_fixture, synthetic_export, write_json  # noqa: F401

from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_registry import dinner_capability, load_skill_checkpoint
from bimanual.skill_views import INTERVALS, create_skill_views
from bimanual.training import ACTTrainingConfig, build_sampling_plan, restrict_sampling_plan


@pytest.fixture(scope="module")
def dataset(tmp_path_factory, synthetic_export):  # noqa: F811
    root = tmp_path_factory.mktemp("registry-data") / "dataset"
    shutil.copytree(synthetic_export, root)
    (root / "meta").mkdir()
    stats = {
        f"observation.images.{camera}": {"mean": [[[0.5]]] * 3, "std": [[[0.2]]] * 3}
        for camera in ("overhead", "left_wrist", "right_wrist")
    }
    write_json(root / "meta/stats.json", stats)
    seal_fixture(root)
    views = root.parent / "views.json"
    return root, views, create_skill_views(root, views)


def save_tensors(path, tensors):
    header, payload = {}, bytearray()
    for key, values in tensors.items():
        values = np.asarray(values, dtype="<f4")
        start = len(payload)
        payload.extend(values.tobytes())
        header[key] = dict(
            dtype="F32", shape=list(values.shape), data_offsets=[start, len(payload)]
        )
    raw = canonical(header)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + payload)


def training_fixture(tmp_path, dataset, *, skill="bar_place_and_return", mutate=None):
    data, views_path, views = dataset
    store = EvidenceStore(tmp_path)
    root = store.new_run()
    checkpoint = root / "checkpoint"
    checkpoint.mkdir()
    config = ACTTrainingConfig(dataset_path=data, skill_views_path=views_path, skill_id=skill)
    view = next(view for view in views.views if view.skill_id == skill)
    shutil.copyfile(views_path, root / "skill_views.json")
    shutil.copyfile(data / "export_manifest.json", root / "dataset_manifest.json")
    manifest = json.loads((data / "export_manifest.json").read_text())
    view_hash = digest_file(views_path)
    plan = restrict_sampling_plan(
        build_sampling_plan(data, manifest, config, project_root=data.parent), view, view_hash
    )
    for name in ("sampling-plan.json", "checkpoint/training_sampling.json"):
        (root / name).write_bytes(canonical(plan))
    write_json(root / "training_config.json", config.model_dump(mode="json"))
    metrics = dict(
        training_completed=True,
        sampler_reload_verified=True,
        checkpoint_reload_verified=True,
        processor_reload_verified=True,
        versions={"lerobot": "0.6.1"},
        skill_view=view.model_dump(mode="json"),
        skill_views_file_sha256=view_hash,
        dataset_manifest_sha256=digest_file(data / "export_manifest.json"),
        sampling_plan_sha256=digest_file(root / "sampling-plan.json"),
        sampling_profile="uniform",
        learned_policy_quality=None,
        manipulation_success=None,
        synthetic_fixture_only=True,
    )
    write_json(root / "metrics.json", metrics)
    inputs = {"observation.state": {"type": "STATE", "shape": [12]}} | {
        f"observation.images.{camera}": {"type": "VISUAL", "shape": [3, 270, 480]}
        for camera in ("overhead", "left_wrist", "right_wrist")
    }
    outputs = {"action": {"type": "ACTION", "shape": [12]}}
    mapping = dict(VISUAL="MEAN_STD", STATE="MEAN_STD", ACTION="MEAN_STD")
    write_json(
        checkpoint / "config.json",
        dict(
            type="act",
            input_features=inputs,
            output_features=outputs,
            n_obs_steps=1,
            chunk_size=10,
            n_action_steps=10,
            normalization_mapping=mapping,
        ),
    )
    numeric = {
        key: dict(mean=[0.0] * 12, std=[1.0] * 12) for key in ("observation.state", "action")
    }
    normalization = dict(
        mapping=mapping,
        numeric_scope="selected_skill",
        image_statistics_scope="full_parent_training_dataset",
        resize=None,
        numeric_stats=numeric,
        numeric_std_floor_rad=config.normalization_std_floor,
        dataset_stats_sha256=digest_file(data / "meta/stats.json"),
    )
    write_json(root / "normalization.json", normalization)
    stats = json.loads((data / "meta/stats.json").read_text()) | numeric
    tensors = {
        f"{key}.{kind}": value[kind] for key, value in stats.items() for kind in ("mean", "std")
    }
    for kind in ("preprocessor", "postprocessor"):
        filename = f"{kind}.safetensors"
        save_tensors(checkpoint / filename, tensors)
        normalizer = dict(
            registry_name="normalizer_processor"
            if kind == "preprocessor"
            else "unnormalizer_processor",
            config=dict(
                features=inputs | outputs if kind == "preprocessor" else outputs, norm_map=mapping
            ),
            state_file=filename,
        )
        steps = (
            [
                dict(registry_name="rename_observations_processor", config={"rename_map": {}}),
                dict(registry_name="to_batch_processor", config={}),
                dict(registry_name="device_processor", config={}),
                normalizer,
            ]
            if kind == "preprocessor"
            else [normalizer, dict(registry_name="device_processor", config={})]
        )
        write_json(checkpoint / f"policy_{kind}.json", dict(steps=steps))
    # Opaque fixture bytes are not claimed to be a loadable ACT checkpoint.
    (checkpoint / "model.safetensors").write_bytes(b"synthetic-model-intake-fixture")
    (root / "trainer_state.pt").write_bytes(b"never-unpickle-this-fixture")
    if mutate:
        mutate(root, metrics)
    write_json(root / "metrics.json", metrics)
    store.seal(
        root,
        kind="act_training",
        outcome="completed",
        config=config.model_dump(mode="json"),
        metrics=metrics,
        source={"fixture_only": True},
        claims=["synthetic metadata fixture only"],
    )
    return root


def change(root, filename, mutate):
    value = json.loads((root / filename).read_text())
    mutate(value)
    write_json(root / filename, value)


@pytest.mark.parametrize(
    "skill,arms",
    [
        (name, arms)
        for (name, _, _), arms in zip(
            INTERVALS,
            [
                ("left", "right"),
                ("left", "right"),
                ("right",),
                ("left", "right"),
                ("left", "right"),
                ("left",),
                ("left",),
            ],
            strict=True,
        )
    ],
)
def test_fixed_capability_ownership(skill, arms):
    assert dinner_capability(skill).execution_arms == arms


def test_verified_development_binding_and_reverify(tmp_path, dataset):
    root = training_fixture(tmp_path, dataset)
    binding = load_skill_checkpoint(root, skill_id="bar_place_and_return", dataset_root=dataset[0])
    assert binding.reverify() == binding
    assert binding.release_available is False and binding.learned_quality is None
    assert binding.capability.arm == "right" and binding.capability.auxiliary_arms == ("left",)
    assert binding.policy_sha256 == digest_file(root / "checkpoint/model.safetensors")
    assert binding.chunk_size == 10
    assert json.loads(json.dumps(binding.report()))["release_available"] is False
    with pytest.raises(FrozenInstanceError):
        binding.chunk_size = 20
    (root / "checkpoint/model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        binding.reverify()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r, m: m.update(training_completed=False),
        lambda r, m: m.update(processor_reload_verified=False),
        lambda r, m: m.update(skill_views_file_sha256="0" * 64),
        lambda r, m: change(r, "checkpoint/config.json", lambda v: v.update(chunk_size=20)),
        lambda r, m: change(
            r, "checkpoint/config.json", lambda v: v["input_features"].update(truth={})
        ),
        lambda r, m: change(
            r,
            "checkpoint/training_sampling.json",
            lambda v: v["frames"][0].update(source_frame_index=0),
        ),
        lambda r, m: change(
            r, "normalization.json", lambda v: v.update(numeric_scope="full_training_dataset")
        ),
        lambda r, m: change(
            r,
            "normalization.json",
            lambda v: v["numeric_stats"]["action"]["mean"].__setitem__(0, 42),
        ),
        lambda r, m: change(
            r,
            "checkpoint/policy_postprocessor.json",
            lambda v: v["steps"][0].update(state_file="../trainer_state.pt"),
        ),
    ],
)
def test_resealed_inconsistent_metadata_rejected(tmp_path, dataset, mutation):
    root = training_fixture(tmp_path, dataset, mutate=mutation)
    with pytest.raises(ValueError):
        load_skill_checkpoint(root, skill_id="bar_place_and_return", dataset_root=dataset[0])


def test_wrong_skill_failed_run_and_unsealed_artifacts(tmp_path, dataset):
    root = training_fixture(tmp_path, dataset)
    with pytest.raises(ValueError, match="different"):
        load_skill_checkpoint(root, skill_id="plate_pick_place", dataset_root=dataset[0])
    with pytest.raises(ValueError, match="Unknown"):
        load_skill_checkpoint(root, skill_id="invented", dataset_root=dataset[0])
    (root / "checkpoint/unsealed.json").write_text("{}")
    with pytest.raises(ValueError, match="Unsealed"):
        load_skill_checkpoint(root, skill_id="bar_place_and_return", dataset_root=dataset[0])
    (root / "checkpoint/unsealed.json").unlink()
    original = json.loads((root / "manifest.json").read_text())
    (root / "manifest.json").unlink()
    (tmp_path / "runs.sqlite3").unlink()  # Synthetic resealing must not warn about its old index.
    EvidenceStore(tmp_path).seal(
        root,
        kind="act_training",
        outcome="failed",
        config=original["config"],
        metrics=original["metrics"],
        source={},
        claims=[],
    )
    with pytest.raises(ValueError, match="completed"):
        load_skill_checkpoint(root, skill_id="bar_place_and_return", dataset_root=dataset[0])
