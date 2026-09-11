import copy
import hashlib
import importlib.metadata
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from bimanual.contracts import EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.training import (
    ACTTrainingConfig,
    build_sampling_plan,
    initialize_act_policy,
    run_train,
    sample_training_indices,
    stable_numeric_stats,
    verify_training_dataset,
)
from bimanual.training_probe import CAMERA_KEYS, _tensor_digest


def write_manifest(root, payload):
    payload = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    (root / "export_manifest.json").write_text(json.dumps(payload))


@pytest.fixture
def manifest_dataset(tmp_path):
    # A structural manifest fixture only; real LeRobot compatibility has a separate test.
    root = tmp_path / "dataset"
    raw = root / "raw_sources" / "000000"
    raw.mkdir(parents=True)
    (raw / "source.txt").write_text("fixture")
    ref = dict(path="source.txt", sha256=digest_file(raw / "source.txt"))
    lineage = EpisodeLineage(
        code_revision="a" * 40,
        source_sha256="b" * 64,
        scene=ref,
        config=ref,
        controller=ref,
        controller_kind="scripted_teacher",
        seed=3,
        split="train",
    )
    recorder = DemonstrationRecorder(
        raw,
        instruction="Pick block",
        instruction_revision=0,
        lineage=lineage,
        joint_limits=JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
    )
    for seq in range(2):
        recorder.record(
            dict(
                schema_version=1,
                episode_id="fixture",
                sequence=seq,
                simulation_seconds=seq / 20,
                observed_monotonic_ns=100 + seq * 50_000_000,
                joint_order=list(JOINT_ORDER),
                joint_position_rad=np.zeros(12),
                joint_velocity_rad_s=np.zeros(12),
                camera_order=list(CAMERAS),
                rgb={name: np.zeros((270, 480, 3), dtype=np.uint8) for name in CAMERAS},
            ),
            [0.1] * 12 if seq == 0 else None,
        )
    episode = recorder.finalize(outcome="success", outcome_reason="Synthetic fixture")
    files = {
        path.relative_to(root).as_posix(): digest_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    payload = dict(
        schema_version=1,
        format="lerobot_v3",
        split="train",
        fps=20,
        lerobot_version="0.6.1",
        frames=1,
        files=files,
        episodes=[
            dict(
                split="train",
                episode_index=0,
                raw_root="raw_sources/000000",
                episode_sha256=digest_file(episode),
                episode_id="fixture",
                seed=3,
                exported_transitions=1,
            )
        ],
    )
    write_manifest(root, payload)
    return root


def test_verified_dataset_manifest_and_raw_episode(manifest_dataset):
    result = verify_training_dataset(manifest_dataset)
    assert result["frames"] == 1 and result["episodes"][0]["seed"] == 3


@pytest.mark.parametrize(
    "field,value", [("split", "test"), ("fps", 30), ("frames", 2), ("lerobot_version", "0.5.0")]
)
def test_semantic_dataset_mismatch_rejected_even_with_valid_digest(manifest_dataset, field, value):
    payload = json.loads((manifest_dataset / "export_manifest.json").read_text())
    payload[field] = value
    write_manifest(manifest_dataset, payload)
    with pytest.raises(ValueError):
        verify_training_dataset(manifest_dataset)


def test_manifest_tampering_and_extra_files_rejected(manifest_dataset):
    path = manifest_dataset / "export_manifest.json"
    original = path.read_text()
    payload = json.loads(original)
    payload["frames"] = 5
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_training_dataset(manifest_dataset)
    path.write_text(original)
    (manifest_dataset / "unexpected").write_text("extra")
    with pytest.raises(ValueError, match="Unsealed"):
        verify_training_dataset(manifest_dataset)


def test_source_artifact_corruption_prevents_training(manifest_dataset):
    (manifest_dataset / "raw_sources" / "000000" / "source.txt").write_text("changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_training_dataset(manifest_dataset)


def test_invalid_dataset_seals_failure_without_optional_import(manifest_dataset, tmp_path):
    (manifest_dataset / "raw_sources" / "000000" / "source.txt").write_text("changed")
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(ValueError, match="digest mismatch"):
        run_train(
            ACTTrainingConfig(dataset_path=manifest_dataset), store=store, project_root=tmp_path
        )
    (result,) = store.list_runs()
    assert result["integrity"] == "verified" and result["outcome"] == "failed"
    assert result["metrics"]["training_completed"] is False and result["claims"] == []
    assert "error.txt" in result["files"]


def test_wrong_library_version_is_sealed_failure(manifest_dataset, tmp_path, monkeypatch):
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.0.0")
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(RuntimeError, match="Expected LeRobot"):
        run_train(
            ACTTrainingConfig(dataset_path=manifest_dataset), store=store, project_root=tmp_path
        )
    assert store.list_runs()[0]["outcome"] == "failed"


def test_mps_fallback_is_rejected_before_torch_import(manifest_dataset, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(RuntimeError, match="fresh process"):
        run_train(
            ACTTrainingConfig(dataset_path=manifest_dataset, device="mps"),
            store=store,
            project_root=tmp_path,
        )
    assert store.list_runs()[0]["metrics"]["actual_device"] is None


def test_training_cannot_write_inside_dataset(manifest_dataset):
    with pytest.raises(ValueError, match="outside"):
        run_train(
            ACTTrainingConfig(dataset_path=manifest_dataset),
            store=EvidenceStore(manifest_dataset / "training"),
            project_root=manifest_dataset,
        )
    assert not (manifest_dataset / "training").exists()


@pytest.mark.skipif(
    not os.environ.get("BIMANUAL_TRAIN_TEST_DATASET"),
    reason="Requires explicit real ACT dataset and native training environment",
)
@pytest.mark.parametrize(
    "use_vae,dropout",
    [(True, 0.1), (False, 0.1), (False, 0.0)],
    ids=["vae", "no_vae", "no_dropout"],
)
def test_real_one_step_training_and_reload(tmp_path, use_vae, dropout):
    dataset = Path(os.environ["BIMANUAL_TRAIN_TEST_DATASET"])
    store = EvidenceStore(tmp_path / "evidence")
    manifest = run_train(
        ACTTrainingConfig(
            dataset_path=dataset, steps=1, device="cpu", use_vae=use_vae, dropout=dropout
        ),
        store=store,
        project_root=Path.cwd(),
    )
    verified = store.verify(manifest.run_id)
    assert verified.metrics["training_completed"] is True
    assert verified.metrics["checkpoint_reload_verified"] is True
    assert verified.metrics["sampler_reload_verified"] is True
    assert len(verified.metrics["steps"]) == 1
    assert verified.metrics["initial_state_sha256"] != verified.metrics["updated_state_sha256"]
    assert verified.metrics["manipulation_success"] is None
    assert "checkpoint/model.safetensors" in verified.files
    assert "checkpoint/policy_preprocessor.json" in verified.files
    assert "checkpoint/policy_postprocessor.json" in verified.files
    assert "checkpoint/training_sampling.json" in verified.files
    assert verified.metrics["sampling_profile"] == "uniform"
    assert len(verified.metrics["steps"][0]["sampled_frames"]) == 1
    assert "trainer_state.pt" in verified.files
    checkpoint_config = json.loads(
        (store.root / "runs" / manifest.run_id / "checkpoint/config.json").read_text()
    )
    assert checkpoint_config["use_vae"] is use_vae
    assert checkpoint_config["dropout"] == dropout
    assert verified.metrics["act_initialization"]["use_vae"] is use_vae
    if not use_vae:
        assert set(verified.metrics["steps"][0]["loss_parts"]) == {"l1_loss"}
        assert verified.metrics["steps"][0]["loss"] == pytest.approx(
            verified.metrics["steps"][0]["loss_parts"]["l1_loss"]
        )
        assert verified.metrics["act_initialization"]["removed_state_keys"]


@pytest.mark.parametrize("use_vae", [True, False], ids=["vae", "no_vae"])
def test_real_act_initializer_preserves_shared_tensors_and_rng(use_vae):
    torch = pytest.importorskip("torch")
    types = pytest.importorskip("lerobot.configs.types")
    ACTConfig = pytest.importorskip("lerobot.policies.act.configuration_act").ACTConfig
    ACTPolicy = pytest.importorskip("lerobot.policies.act.modeling_act").ACTPolicy
    config = ACTConfig(
        input_features={
            "observation.state": types.PolicyFeature(type=types.FeatureType.STATE, shape=(12,)),
            **{
                key: types.PolicyFeature(type=types.FeatureType.VISUAL, shape=(3, 270, 480))
                for key in CAMERA_KEYS
            },
        },
        output_features={"action": types.PolicyFeature(type=types.FeatureType.ACTION, shape=(12,))},
        device="cpu",
        pretrained_backbone_weights=None,
        push_to_hub=False,
        chunk_size=10,
        n_action_steps=10,
        dim_model=128,
        n_heads=4,
        dim_feedforward=512,
        n_encoder_layers=1,
        n_decoder_layers=1,
        n_vae_encoder_layers=1,
        latent_dim=16,
    )
    assert config.use_vae is True
    torch.manual_seed(0)
    reference = ACTPolicy(copy.deepcopy(config))
    reference_state = reference.state_dict()
    reference_rng = torch.get_rng_state().clone()
    expected_next_random = torch.randn(8)
    torch.manual_seed(0)
    actual, metadata = initialize_act_policy(torch, ACTPolicy, config, use_vae=use_vae)
    assert config.use_vae is True  # The supplied standard config remains reusable.
    assert actual.config.use_vae is use_vae
    assert torch.equal(torch.get_rng_state(), reference_rng)
    assert torch.equal(torch.randn(8), expected_next_random)
    assert metadata["reference_initial_state_sha256"] == _tensor_digest(reference_state)
    actual_state = actual.state_dict()
    assert all(torch.equal(value, reference_state[key]) for key, value in actual_state.items())
    removed = sorted(set(reference_state) - set(actual_state))
    if use_vae:
        assert not removed
        assert _tensor_digest(actual_state) == _tensor_digest(reference_state)
        assert metadata["initialization"] == "standard_seeded_act"
        assert ACTTrainingConfig(dataset_path=Path("unused")).use_vae is True
    else:
        assert removed and all(key.startswith("model.vae_encoder") for key in removed)
        assert metadata["removed_state_keys"] == removed
        assert metadata["shared_initial_state_sha256"] == _tensor_digest(actual_state)
        assert metadata["cpu_rng_restored_after_ablation_construction"] is True


def test_float64_statistics_do_not_amplify_constant_joint_roundoff():
    values = np.full((460, 12), np.float32(1.2), dtype=np.float32)
    stats = stable_numeric_stats(values, std_floor=1e-4)
    np.testing.assert_allclose(stats["std"], 1e-4)
    normalized = (values - np.asarray(stats["mean"])) / np.asarray(stats["std"])
    np.testing.assert_array_equal(normalized, np.zeros_like(values))


def test_keyboard_interrupt_seals_failure(manifest_dataset, tmp_path, monkeypatch):
    def interrupted(*_):
        raise KeyboardInterrupt()

    monkeypatch.setattr(importlib.metadata, "version", interrupted)
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(KeyboardInterrupt):
        run_train(
            ACTTrainingConfig(dataset_path=manifest_dataset), store=store, project_root=tmp_path
        )
    (result,) = store.list_runs()
    assert result["outcome"] == "failed" and result["metrics"]["interrupted"] is True
    assert "metrics.json" in result["files"]


@pytest.fixture
def approach_sampling_dataset(manifest_dataset, tmp_path, request):
    root = manifest_dataset
    store = EvidenceStore(tmp_path / "protocol-evidence")
    directory = store.new_run()
    protocol = dict(
        skill="left_open_hand_pregrasp",
        motion_steps=60,
        settle_steps=20,
        control_hz=20,
        target_m=[-0.15, -0.08, 0.46],
        cases=[
            [3 + index, "train", offsets]
            for index, offsets in enumerate(getattr(request, "param", [[0] * 5, [0.1] * 5]))
        ],
    )
    (directory / "protocol.json").write_text(json.dumps(protocol))
    store.seal(
        directory,
        kind="approach_collection_protocol",
        outcome="completed",
        config=protocol,
        metrics={},
        source={},
        claims=[],
    )
    template = json.loads((root / "raw_sources/000000/demonstration/episode.json").read_text())
    shutil.copytree(root / "raw_sources/000000", root / "raw_sources/000001")
    sources = []
    for index in range(2):
        raw = root / "raw_sources" / f"{index:06d}"
        cfg = dict(
            skill=protocol["skill"],
            protocol_run=directory.name,
            case_seed=3 + index,
            split="train",
            target_m=protocol["target_m"],
            left_joint_offset_rad=protocol["cases"][index][2],
        )
        (raw / "config.json").write_text(json.dumps(cfg))
        episode = copy.deepcopy(template)
        episode["episode_id"] = f"approach-{index}"
        episode["lineage"]["seed"] = 3 + index
        episode["lineage"]["config"] = dict(
            path="config.json", sha256=digest_file(raw / "config.json")
        )
        episode["frames"] = []
        for sequence in range(81):
            frame = copy.deepcopy(template["frames"][0])
            frame["action_rad"] = [0.1] * 12 if sequence < 80 else None
            capture = dict(
                sequence=sequence,
                simulation_seconds=sequence / 20,
                observed_monotonic_ns=100 + sequence * 50_000_000,
            )
            frame["observation"].update(capture, episode_id=episode["episode_id"])
            for camera in frame["observation"]["frames"]:
                camera.update(capture)
            episode["frames"].append(frame)
        (raw / "demonstration/episode.json").write_text(json.dumps(episode))
        sources.append(
            dict(
                split="train",
                episode_index=index,
                raw_root=raw.relative_to(root).as_posix(),
                episode_sha256=digest_file(raw / "demonstration/episode.json"),
                episode_id=episode["episode_id"],
                seed=3 + index,
                exported_transitions=80,
            )
        )
    payload = json.loads((root / "export_manifest.json").read_text())
    payload.update(frames=160, episodes=sources)
    payload["files"] = {
        path.relative_to(root).as_posix(): digest_file(path)
        for path in root.rglob("*")
        if path.is_file() and path.name != "export_manifest.json"
    }
    write_manifest(root, payload)
    return root, directory


def sampling_plan_fixture(dataset, profile="approach_regions_v1"):
    root, protocol = dataset
    config = ACTTrainingConfig(
        dataset_path=root,
        sampling_profile=profile,
        sampling_protocol_run=protocol if profile != "uniform" else None,
    )
    return build_sampling_plan(root, verify_training_dataset(root), config, project_root=root)


def test_approach_sampling_balances_episodes_and_regions(approach_sampling_dataset):
    plan = sampling_plan_fixture(approach_sampling_dataset)
    assert len(plan["frames"]) == 160
    for episode_index in range(2):
        rows = [r for r in plan["frames"] if r["episode_index"] == episode_index]
        assert sum(r["probability"] for r in rows) == pytest.approx(0.5)
        for name, expected_indices in (
            ("start", range(10)),
            ("middle", range(10, 60)),
            ("settled", range(60, 80)),
        ):
            region = [r for r in rows if r["region"] == name]
            assert [r["source_frame_index"] for r in region] == list(expected_indices)
            assert sum(r["probability"] for r in region) == pytest.approx(1 / 6)
    assert [r["dataset_index"] for r in plan["frames"]] == list(range(160))
    assert all(r["probability"] > 0 and r["source_episode_sha256"] for r in plan["frames"])


@pytest.mark.parametrize(
    "profile", ["uniform", "approach_regions_v1", "approach_nominal_launch_v1"]
)
def test_sampler_rng_save_restore_and_uniform_compatibility(approach_sampling_dataset, profile):
    torch = pytest.importorskip("torch")
    plan = sampling_plan_fixture(approach_sampling_dataset, profile)
    sampler = torch.Generator(device="cpu").manual_seed(24)
    original = torch.Generator(device="cpu").manual_seed(24)
    for _ in range(5):
        actual = sample_training_indices(torch, sampler, plan, 8)
        if profile == "uniform":
            assert actual == torch.randint(160, (8,), generator=original).tolist()
    state = sampler.get_state()
    expected = [sample_training_indices(torch, sampler, plan, 8) for _ in range(3)]
    restored = torch.Generator(device="cpu")
    restored.set_state(state)
    reloaded_plan = json.loads(json.dumps(plan))
    assert [
        sample_training_indices(torch, restored, reloaded_plan, 8) for _ in range(3)
    ] == expected


@pytest.mark.parametrize("profile", ["approach_regions_v1", "approach_nominal_launch_v1"])
def test_profile_requires_explicit_compatible_protocol(manifest_dataset, tmp_path, profile):
    with pytest.raises(ValueError, match="sampling protocol"):
        ACTTrainingConfig(dataset_path=manifest_dataset, sampling_profile=profile)
    with pytest.raises(ValueError, match="sampling protocol"):
        ACTTrainingConfig(dataset_path=manifest_dataset, sampling_protocol_run=tmp_path)


@pytest.mark.parametrize("profile", ["approach_regions_v1", "approach_nominal_launch_v1"])
def test_profile_rejects_changed_protocol(approach_sampling_dataset, profile):
    _, protocol = approach_sampling_dataset
    (protocol / "protocol.json").write_text("{}")
    with pytest.raises(ValueError, match="digest|mismatch"):
        sampling_plan_fixture(approach_sampling_dataset, profile)


@pytest.mark.parametrize("field,value", [("motion_steps", 10), ("settle_steps", 0)])
def test_profile_rejects_empty_regions(approach_sampling_dataset, tmp_path, field, value):
    root, original = approach_sampling_dataset
    body = json.loads((original / "protocol.json").read_text())
    body[field] = value
    store = EvidenceStore(tmp_path / "alternative")
    directory = store.new_run()
    (directory / "protocol.json").write_text(json.dumps(body))
    store.seal(
        directory,
        kind="approach_collection_protocol",
        outcome="completed",
        config=body,
        metrics={},
        source={},
        claims=[],
    )
    with pytest.raises(ValueError, match="nonempty"):
        sampling_plan_fixture((root, directory))


@pytest.mark.parametrize("profile", ["approach_regions_v1", "approach_nominal_launch_v1"])
def test_profile_rejects_unrelated_protocol_identity(approach_sampling_dataset, tmp_path, profile):
    root, original = approach_sampling_dataset
    body = json.loads((original / "protocol.json").read_text())
    store = EvidenceStore(tmp_path / "alternative")
    directory = store.new_run()
    (directory / "protocol.json").write_text(json.dumps(body))
    store.seal(
        directory,
        kind="approach_collection_protocol",
        outcome="completed",
        config=body,
        metrics={"held_out_success": True},
        source={},
        claims=[],
    )
    with pytest.raises(ValueError, match="episode/config"):
        sampling_plan_fixture((root, directory), profile)


@pytest.mark.parametrize(
    "approach_sampling_dataset,nominal_index",
    [([[0] * 5, [0.1] * 5], 0), ([[0.1] * 5, [0] * 5], 1)],
    indirect=["approach_sampling_dataset"],
)
def test_nominal_launch_masses_coverage_and_lineage(approach_sampling_dataset, nominal_index):
    root, protocol = approach_sampling_dataset
    plan = sampling_plan_fixture(approach_sampling_dataset, "approach_nominal_launch_v1")
    frames = plan["frames"]
    assert [f["dataset_index"] for f in frames] == list(range(160))
    assert [(f["episode_index"], f["source_frame_index"]) for f in frames] == [
        (episode, frame) for episode in range(2) for frame in range(80)
    ]
    assert all(f["probability"] > 0 for f in frames)
    for name, count in [("nominal_launch", 10), ("settled", 40), ("remaining", 110)]:
        rows = [f for f in frames if f["region"] == name]
        assert len(rows) == count
        assert sum(f["probability"] for f in rows) == pytest.approx(1 / 3)
        assert all(f["probability"] == pytest.approx(1 / (3 * count)) for f in rows)
    launch = [f for f in frames if f["region"] == "nominal_launch"]
    assert {f["episode_index"] for f in launch} == {nominal_index}
    assert [f["source_frame_index"] for f in launch] == list(range(10))
    for episode in plan["episodes"]:
        rows = [f for f in frames if f["episode_index"] == episode["episode_index"]]
        mass = sum(f["probability"] for f in rows)
        assert episode["probability"] == pytest.approx(mass)
        assert mass != pytest.approx(0.5)  # This profile intentionally changes episode balance.
        for region in episode["regions"]:
            subset = rows[region["start"] : region["end"]]
            assert {f["region"] for f in subset} == {region["name"]}
            assert region["conditional_probability"] == pytest.approx(
                sum(f["probability"] for f in subset) / mass
            )
    nominal = plan["nominal_launch"]["nominal_episode"]
    assert nominal["episode_index"] == nominal_index
    assert nominal["left_joint_offset_rad"] == [0] * 5
    assert nominal["source_config"]["sha256"] == digest_file(
        root / nominal["raw_root"] / nominal["source_config"]["path"]
    )
    assert nominal["source_episode_sha256"] == launch[0]["source_episode_sha256"]
    assert plan["collection_protocol"]["run_id"] == protocol.name


@pytest.mark.parametrize(
    "approach_sampling_dataset",
    [[[0.1] * 5, [0.2] * 5], [[0] * 5, [0] * 5]],
    indirect=True,
)
def test_nominal_launch_rejects_missing_or_ambiguous_nominal(approach_sampling_dataset):
    with pytest.raises(ValueError, match="exactly one zero-offset"):
        sampling_plan_fixture(approach_sampling_dataset, "approach_nominal_launch_v1")


@pytest.mark.parametrize(
    "approach_sampling_dataset",
    [[[], [0.1] * 5], [[False] * 5, [0.1] * 5], [["0"] * 5, [0.1] * 5]],
    indirect=True,
)
def test_nominal_launch_rejects_malformed_offsets(approach_sampling_dataset):
    with pytest.raises(ValueError, match="offsets|episode/config"):
        sampling_plan_fixture(approach_sampling_dataset, "approach_nominal_launch_v1")


@pytest.mark.skipif(
    not os.environ.get("BIMANUAL_TRAIN_TEST_DATASET"),
    reason="Requires explicit real ACT dataset and native training environment",
)
def test_initialization_reference_mismatch_stops_before_training(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(RuntimeError, match="reference initialization"):
        run_train(
            ACTTrainingConfig(
                dataset_path=Path(os.environ["BIMANUAL_TRAIN_TEST_DATASET"]),
                steps=1,
                device="cpu",
                use_vae=False,
                reference_initial_state_sha256="0" * 64,
            ),
            store=store,
            project_root=Path.cwd(),
        )
    (run,) = store.list_runs()
    assert run["outcome"] == "failed"
    assert run["metrics"]["steps"] == []
    assert run["metrics"]["act_initialization"]["reference_initial_state_sha256"] != "0" * 64
    assert "checkpoint/model.safetensors" not in run["files"]


def test_constant_learning_rate_default_preserves_every_update():
    from bimanual.training import learning_rate_for_step, learning_rate_schedule_definition

    config = ACTTrainingConfig(dataset_path=Path("unused"), steps=20, learning_rate=2e-5)
    assert config.learning_rate_schedule == "constant"
    assert [learning_rate_for_step(config, step) for step in range(1, 21)] == [2e-5] * 20
    definition = learning_rate_schedule_definition(config)
    assert definition["hold_updates"] == 20 and definition["first_decay_update"] is None
    assert definition["final_factor"] == 1.0


@pytest.mark.parametrize(
    "step,expected", [(1, 1e-5), (15000, 1e-5), (15001, 9.9982e-6), (17500, 5.5e-6), (20000, 1e-6)]
)
def test_terminal_linear_one_based_boundaries(step, expected):
    from bimanual.training import learning_rate_for_step

    config = ACTTrainingConfig(
        dataset_path=Path("unused"), steps=20000, learning_rate_schedule="terminal_linear"
    )
    assert learning_rate_for_step(config, step) == pytest.approx(expected, rel=1e-13)


@pytest.mark.parametrize("steps", [4, 5, 6, 7, 20, 20000])
def test_terminal_schedule_has_fixed_plateau_monotone_decay_and_endpoint(steps):
    from bimanual.training import learning_rate_for_step, learning_rate_schedule_definition

    config = ACTTrainingConfig(
        dataset_path=Path("unused"), steps=steps, learning_rate_schedule="terminal_linear"
    )
    rates = [learning_rate_for_step(config, step) for step in range(1, steps + 1)]
    hold = 3 * steps // 4
    assert rates[:hold] == [config.learning_rate] * hold
    assert all(a > b for a, b in zip(rates[hold - 1 : -1], rates[hold:], strict=True))
    assert rates[-1] == config.learning_rate * 0.1
    assert learning_rate_schedule_definition(config)["first_decay_update"] == hold + 1


@pytest.mark.parametrize("step", [0, -1, 20001, True, 1.0, "1"])
@pytest.mark.parametrize("profile", ["constant", "terminal_linear"])
def test_learning_rate_rejects_invalid_update_indices(profile, step):
    from bimanual.training import learning_rate_for_step

    config = ACTTrainingConfig(
        dataset_path=Path("unused"), steps=20000, learning_rate_schedule=profile
    )
    with pytest.raises(ValueError, match="one-based"):
        learning_rate_for_step(config, step)


@pytest.mark.parametrize("steps", [1, 2, 3])
def test_terminal_linear_requires_at_least_four_updates(steps):
    with pytest.raises(ValueError, match="four updates"):
        ACTTrainingConfig(
            dataset_path=Path("unused"), steps=steps, learning_rate_schedule="terminal_linear"
        )
    assert ACTTrainingConfig(dataset_path=Path("unused"), steps=steps).steps == steps


def test_schedule_applies_to_all_optimizer_groups_before_update():
    from types import SimpleNamespace

    from bimanual.training import apply_learning_rate

    config = ACTTrainingConfig(
        dataset_path=Path("unused"), steps=4, learning_rate_schedule="terminal_linear"
    )
    optimizer = SimpleNamespace(
        param_groups=[dict(lr=1e-5, params="model"), dict(lr=1e-5, params="backbone")]
    )
    assert apply_learning_rate(optimizer, config, 3) == [1e-5, 1e-5]
    assert apply_learning_rate(optimizer, config, 4) == [1e-5 * 0.1, 1e-5 * 0.1]
    assert [group["params"] for group in optimizer.param_groups] == ["model", "backbone"]
    with pytest.raises(ValueError):
        apply_learning_rate(optimizer, config, 5)
    assert [group["lr"] for group in optimizer.param_groups] == [1e-5 * 0.1, 1e-5 * 0.1]
    malformed = SimpleNamespace(param_groups=[dict(lr=1e-5), {}])
    with pytest.raises(ValueError, match="every parameter group"):
        apply_learning_rate(malformed, config, 4)
    assert malformed.param_groups[0]["lr"] == 1e-5


@pytest.mark.skipif(
    not os.environ.get("BIMANUAL_TRAIN_TEST_DATASET"),
    reason="Requires explicit real ACT dataset and native training environment",
)
def test_real_four_step_terminal_schedule_and_reload(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    manifest = run_train(
        ACTTrainingConfig(
            dataset_path=Path(os.environ["BIMANUAL_TRAIN_TEST_DATASET"]),
            steps=4,
            device="cpu",
            use_vae=False,
            dropout=0.0,
            learning_rate_schedule="terminal_linear",
        ),
        store=store,
        project_root=Path.cwd(),
    )
    verified = store.verify(manifest.run_id)
    assert verified.metrics["training_completed"] is True
    assert verified.metrics["learning_rate_reload_verified"] is True
    assert verified.metrics["checkpoint_reload_verified"] is True
    assert verified.metrics["processor_reload_verified"] is True
    assert verified.metrics["sampler_reload_verified"] is True
    assert [step["learning_rates"] for step in verified.metrics["steps"]] == [
        [1e-5, 1e-5],
        [1e-5, 1e-5],
        [1e-5, 1e-5],
        [1e-5 * 0.1, 1e-5 * 0.1],
    ]
    definition = verified.metrics["learning_rate_schedule"]
    assert definition["hold_updates"] == 3 and definition["final_factor"] == 0.1
    saved = json.loads(
        (store.directory(manifest.run_id) / "checkpoint/training_schedule.json").read_text()
    )
    assert saved == dict(
        definition=definition, completed_updates=4, final_learning_rates=[1e-5 * 0.1, 1e-5 * 0.1]
    )
    assert verified.metrics["manipulation_success"] is None


@pytest.mark.parametrize("profile", ["uniform", "first_action_half_v1"])
def test_cli_forwards_declared_temporal_loss_without_training(tmp_path, monkeypatch, profile):
    from types import SimpleNamespace

    from bimanual.cli import main

    seen = []

    def fake_train(config, **kwargs):
        seen.append(config)
        return SimpleNamespace(outcome="completed", model_dump=lambda **kw: {"fixture": True})

    monkeypatch.setattr("bimanual.training.run_train", fake_train)
    assert (
        main(
            [
                "--artifacts",
                str(tmp_path / "artifacts"),
                "train",
                "--dataset",
                str(tmp_path),
                "--no-vae",
                "--temporal-loss-profile",
                profile,
            ]
        )
        == 0
    )
    assert len(seen) == 1 and seen[0].temporal_loss_profile == profile
    assert seen[0].use_vae is False
