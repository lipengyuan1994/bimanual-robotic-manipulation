from types import SimpleNamespace

import pytest

from bimanual.corrective_dataset import CorrectiveDataset, NumericRows, compose_sampling_plan
from bimanual.training import ACTTrainingConfig


def test_corrections_require_verified_handoff():
    for kwargs in ({}, {"skill_id": "plate_place", "skill_views_path": "views.json"}):
        with pytest.raises(ValueError):
            ACTTrainingConfig(
                dataset_path="nominal", corrective_dataset_path="corrections", **kwargs
            )
    config = ACTTrainingConfig(
        dataset_path="nominal",
        corrective_dataset_path="corrections",
        skill_id="handoff_transfer",
        skill_views_path="views.json",
    )
    assert config.corrective_dataset_path.name == "corrections"


def test_plan_keeps_full_nominal_and_original_correction_indices(tmp_path):
    (tmp_path / "export_manifest.json").write_text("{}")
    plan = {
        "profile": "uniform",
        "skill_view": {"skill_id": "handoff_transfer"},
        "frames": [{"dataset_index": i, "source_frame_index": i} for i in range(630)],
        "episodes": [{"episode_id": "nominal", "probability": 1}],
    }
    manifest = {
        "profile": "feedback_approach_corrective_lerobot_v1",
        "episodes": [
            {
                "episode_id": "correction",
                "episode_index": 0,
                "dataset_start": 0,
                "dataset_end": 2,
                "parent_start": 42,
                "episode_sha256": "a" * 64,
                "source_manifest_sha256": "b" * 64,
            }
        ],
    }
    result = compose_sampling_plan(plan, tmp_path, manifest)
    assert len(result["frames"]) == 632
    assert [f["source_frame_index"] for f in result["frames"][-2:]] == [42, 43]
    assert all(f["probability"] == 1 / 632 for f in result["frames"])
    assert len(plan["frames"]) == 630
    assert sum(e["probability"] for e in result["episodes"]) == 1


def test_continuity_profile_gets_distinct_training_region(tmp_path):
    (tmp_path / "export_manifest.json").write_text("{}")
    plan = {
        "profile": "uniform",
        "skill_view": {"skill_id": "handoff_transfer"},
        "frames": [{"dataset_index": 0}],
        "episodes": [{"episode_id": "nominal", "probability": 1}],
    }
    manifest = {
        "profile": "handoff_receiver_continuity_lerobot_v1",
        "episodes": [
            {
                "episode_id": "continuity",
                "episode_index": 0,
                "dataset_start": 0,
                "dataset_end": 1,
                "parent_start": 312,
                "episode_sha256": "a" * 64,
                "source_manifest_sha256": "b" * 64,
            }
        ],
    }
    result = compose_sampling_plan(plan, tmp_path, manifest)
    assert result["frames"][-1]["region"] == "corrective_receiver_continuity"
    assert result["episodes"][-1]["regions"][0]["name"] == ("corrective_receiver_continuity")


class Rows(list):
    def select_columns(self, columns):
        return Rows({k: row[k] for k in columns} for row in self)


def test_numeric_union_includes_both_sources():
    rows = NumericRows((Rows([{"action": 1, "image": "unused"}]), Rows([{"action": 9}])))
    assert list(rows.select_columns(["action"])) == [{"action": 1}, {"action": 9}]


def test_source_intervals_must_cover_dataset():
    class Parent:
        delta_timestamps = None
        hf_dataset = Rows([{"action": 0}])

        def __len__(self):
            return 1

    nominal = SimpleNamespace(meta=SimpleNamespace(stats={}), hf_dataset=Rows())
    with pytest.raises(ValueError, match="partition"):
        CorrectiveDataset(
            nominal,
            Parent(),
            {"frames": 1, "episodes": [{"dataset_start": 1, "dataset_end": 2}]},
            10,
        )


def test_chunks_pad_at_each_corrective_source_boundary():
    torch = pytest.importorskip("torch")
    from bimanual.dataset_export import CAMERA_FEATURES

    class Parent:
        delta_timestamps = None
        hf_dataset = Rows({"action": [float(i)] * 12} for i in range(4))

        def __len__(self):
            return 4

        def __getitem__(self, index):
            return {
                "observation.state": torch.zeros(12),
                **{key: torch.zeros(3, 4, 4) for key in CAMERA_FEATURES.values()},
                "oracle": 42,
            }

    class Nominal:
        meta = SimpleNamespace(stats={})
        hf_dataset = Rows()

        def __len__(self):
            return 0

    union = CorrectiveDataset(
        Nominal(),
        Parent(),
        {
            "frames": 4,
            "episodes": [
                {"dataset_start": 0, "dataset_end": 2},
                {"dataset_start": 2, "dataset_end": 4},
            ],
        },
        3,
    )
    sample = union[1]
    assert sample["action"][:, 0].tolist() == [1, 1, 1]
    assert sample["action_is_pad"].tolist() == [False, True, True]
    assert "oracle" not in sample
    assert union[2]["action"][:, 0].tolist() == [2, 3, 3]
