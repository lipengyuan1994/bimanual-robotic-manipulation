import hashlib
import importlib.metadata
import json
import os

import numpy as np
import pytest

from bimanual.contracts import EpisodeLineage, JointLimits
from bimanual.dataset_export import (
    CAMERA_FEATURES,
    export_lerobot_dataset,
    iter_export_frames,
    lerobot_features,
    preflight_sources,
    validate_export_timestamp,
)
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import EvidenceStore


@pytest.mark.parametrize("index", [0, 1, 641, 2561, 4818, 99999])
def test_timestamp_checks_storage_precision_without_accepting_wrong_frames(index):
    stored = float(np.float32(index / 20))
    validate_export_timestamp(stored, index)
    with pytest.raises(ValueError, match="timestamp"):
        validate_export_timestamp(float(np.float32((index + 1) / 20)), index)
    with pytest.raises(ValueError, match="timestamp"):
        validate_export_timestamp(
            float(np.nextafter(np.float32(stored), np.float32(np.inf))), index
        )


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), -float("inf")])
def test_timestamp_rejects_nonfinite_values(timestamp):
    with pytest.raises(ValueError, match="timestamp"):
        validate_export_timestamp(timestamp, 4818)


@pytest.mark.skipif(
    os.environ.get("BIMANUAL_TEST_LEROBOT") != "1",
    reason="Requires real native LeRobot timestamp storage",
)
def test_real_long_episode_timestamp_representation(tmp_path):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    dataset = LeRobotDataset.create(
        repo_id="local/long-timestamp-test",
        root=tmp_path / "dataset",
        fps=20,
        robot_type="dual_so101_sim",
        use_videos=False,
        features={"action": {"dtype": "float32", "shape": (12,), "names": list(JOINT_ORDER)}},
    )
    for _ in range(4819):
        dataset.add_frame({"action": np.zeros(12, dtype=np.float32), "task": "Storage test"})
    dataset.save_episode()
    dataset.finalize()
    for index in (0, 1, 641, 2561, 4818):
        actual = float(dataset[index]["timestamp"].item())
        validate_export_timestamp(actual, index)
    assert abs(float(dataset[4818]["timestamp"].item()) - 4818 / 20) > 1e-6


@pytest.fixture
def source_factory(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")

    def make(*, split="train", seed=3, outcome="success", interventions=0, manifest_outcome=None):
        root = store.new_run()
        artifact = root / "source.txt"
        artifact.write_text("fixture source")
        ref = dict(path=artifact.name, sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
        lineage = EpisodeLineage(
            code_revision="a" * 40,
            source_sha256="b" * 64,
            scene=ref,
            config=ref,
            controller=ref,
            controller_kind="scripted_teacher",
            seed=seed,
            split=split,
        )
        recorder = DemonstrationRecorder(
            root,
            instruction="Place the practice block",
            instruction_revision=0,
            lineage=lineage,
            joint_limits=JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        )
        for seq in range(3):
            observation = dict(
                schema_version=1,
                episode_id=root.name,
                sequence=seq,
                simulation_seconds=seq / 20,
                observed_monotonic_ns=100 + seq * 50_000_000,
                joint_order=list(JOINT_ORDER),
                joint_position_rad=np.full(12, seq / 10),
                joint_velocity_rad_s=np.full(12, 0.4),
                camera_order=list(CAMERAS),
                rgb={
                    name: np.full((270, 480, 3), i * 30 + seq, dtype=np.uint8)
                    for i, name in enumerate(CAMERAS)
                },
            )
            recorder.record(observation, None if seq == 2 else np.full(12, seq / 5))
        recorder.finalize(
            outcome=outcome, outcome_reason="Synthetic fixture", interventions=interventions
        )
        store.seal(
            root,
            kind="contact_grasp",
            outcome=manifest_outcome or ("completed" if outcome == "success" else outcome),
            config={},
            metrics={},
            claims=[],
            source={
                "git_revision": lineage.code_revision,
                "source_sha256": lineage.source_sha256,
            },
        )
        return root

    return make


def test_preflight_and_exact_frame_mapping_without_optional_library(source_factory):
    root = source_factory()
    (source,) = preflight_sources((root,))
    frames = list(iter_export_frames(source))
    assert len(frames) == 2  # The third observation has no action.
    assert frames[1]["task"] == "Place the practice block"
    np.testing.assert_array_equal(frames[1]["action"], np.full(12, 0.2, dtype=np.float32))
    np.testing.assert_array_equal(
        frames[1]["observation.state"], np.full(12, 0.1, dtype=np.float32)
    )
    for i, feature in enumerate(CAMERA_FEATURES.values()):
        assert frames[1][feature].shape == (270, 480, 3)
        assert frames[1][feature].dtype == np.uint8
        assert np.unique(frames[1][feature]).tolist() == [i * 30 + 1]
    assert "timestamp" not in frames[0] and "frame_index" not in frames[0]
    assert lerobot_features()["action"]["names"] == list(JOINT_ORDER)


@pytest.mark.parametrize(
    "options",
    [
        {"outcome": "failure"},
        {"outcome": "cancelled"},
        {"interventions": 1},
        {"split": "test"},
    ],
)
def test_training_intake_rejects_ineligible_sources(source_factory, options):
    with pytest.raises(ValueError):
        preflight_sources((source_factory(**options),))


def test_compare_heldout_seeds_and_reject_duplicate_episodes(source_factory):
    train = source_factory(seed=7)
    heldout = source_factory(seed=7, split="validation")
    with pytest.raises(ValueError, match="Seed leakage"):
        preflight_sources((train,), comparison_run_roots=(heldout,))
    with pytest.raises(ValueError, match="Duplicate"):
        preflight_sources((train, train))
    different = source_factory(seed=8, split="validation")
    assert len(preflight_sources((train,), comparison_run_roots=(different,))) == 1


@pytest.mark.parametrize(
    "record_outcome,manifest_outcome", [("failure", "failed"), ("cancelled", "interrupted")]
)
def test_failed_heldout_records_still_participate_in_leakage_checks(
    source_factory, record_outcome, manifest_outcome
):
    train = source_factory(seed=7)
    failed = source_factory(
        seed=8, split="test", outcome=record_outcome, manifest_outcome=manifest_outcome
    )
    assert len(preflight_sources((train,), comparison_run_roots=(failed,))) == 1
    leaked = source_factory(
        seed=7, split="test", outcome=record_outcome, manifest_outcome=manifest_outcome
    )
    with pytest.raises(ValueError, match="Seed leakage"):
        preflight_sources((train,), comparison_run_roots=(leaked,))
    mismatch = source_factory(
        seed=9, split="test", outcome=record_outcome, manifest_outcome="completed"
    )
    with pytest.raises(ValueError, match="outcomes disagree"):
        preflight_sources((train,), comparison_run_roots=(mismatch,))


def test_preflight_integrity_and_frame_budget(source_factory):
    root = source_factory()
    with pytest.raises(ValueError, match="frame limit"):
        preflight_sources((root,), max_frames=1)
    (root / "source.txt").write_text("modified")
    with pytest.raises(ValueError, match="digest mismatch"):
        preflight_sources((root,))


def test_existing_destination_never_overwritten(source_factory, tmp_path):
    root = source_factory()
    destination = tmp_path / "keep"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        export_lerobot_dataset((root,), destination, repo_id="local/example")
    assert (destination / "keep.txt").read_text() == "keep"


def test_missing_optional_dependency_does_not_create_output(source_factory, tmp_path, monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    destination = tmp_path / "dataset"
    with pytest.raises(RuntimeError, match="native training environment"):
        export_lerobot_dataset((source_factory(),), destination, repo_id="local/example")
    assert not destination.exists()


def test_output_cannot_pollute_source(source_factory):
    root = source_factory()
    with pytest.raises(ValueError, match="sealed source"):
        export_lerobot_dataset((root,), root / "dataset", repo_id="local/example")


@pytest.mark.skipif(
    os.environ.get("BIMANUAL_TEST_LEROBOT") != "1",
    reason="Requires explicit real native LeRobot 0.6.1 training environment",
)
def test_real_lerobot_v3_export_and_readback(source_factory, tmp_path):
    # No fake dataset class: this test must create and reopen actual LeRobot files.
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    source = source_factory()
    output = export_lerobot_dataset((source,), tmp_path / "dataset", repo_id="local/test")
    manifest = json.loads((output / "export_manifest.json").read_text())
    assert manifest["frames"] == 2 and manifest["lerobot_version"] == "0.6.1"
    dataset = LeRobotDataset(repo_id="local/test", root=output)
    assert len(dataset) == 2 and dataset.num_episodes == 1
    assert dataset[1]["timestamp"].item() == pytest.approx(0.05)
    assert dataset[1]["action"].shape == (12,)
    assert dataset[1]["observation.images.overhead"].shape == (3, 270, 480)
    raw = output / "raw_sources" / "000000" / "demonstration" / "episode.json"
    assert raw.read_bytes() == (source / "demonstration" / "episode.json").read_bytes()
