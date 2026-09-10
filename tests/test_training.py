import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import numpy as np
import pytest

from bimanual.contracts import EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.training import (
    ACTTrainingConfig,
    run_train,
    stable_numeric_stats,
    verify_training_dataset,
)


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
def test_real_one_step_training_and_reload(tmp_path):
    dataset = Path(os.environ["BIMANUAL_TRAIN_TEST_DATASET"])
    store = EvidenceStore(tmp_path / "evidence")
    manifest = run_train(
        ACTTrainingConfig(dataset_path=dataset, steps=1, device="cpu"),
        store=store,
        project_root=Path.cwd(),
    )
    verified = store.verify(manifest.run_id)
    assert verified.metrics["training_completed"] is True
    assert verified.metrics["checkpoint_reload_verified"] is True
    assert len(verified.metrics["steps"]) == 1
    assert verified.metrics["initial_state_sha256"] != verified.metrics["updated_state_sha256"]
    assert verified.metrics["manipulation_success"] is None
    assert "checkpoint/model.safetensors" in verified.files
    assert "checkpoint/policy_preprocessor.json" in verified.files
    assert "checkpoint/policy_postprocessor.json" in verified.files
    assert "trainer_state.pt" in verified.files


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
