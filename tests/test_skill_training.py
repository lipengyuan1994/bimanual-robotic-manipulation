import copy
import json
import os
from pathlib import Path

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.skill_views import SkillView
from bimanual.training import ACTTrainingConfig, restrict_sampling_plan, run_train


def test_skill_configuration_requires_paired_uniform_selection():
    with pytest.raises(ValueError, match="both"):
        ACTTrainingConfig(dataset_path=Path("unused"), skill_id="cup_pick_place")
    with pytest.raises(ValueError, match="both"):
        ACTTrainingConfig(dataset_path=Path("unused"), skill_views_path=Path("views"))
    with pytest.raises(ValueError, match="uniform"):
        ACTTrainingConfig(
            dataset_path=Path("unused"),
            skill_id="cup_pick_place",
            skill_views_path=Path("views"),
            sampling_profile="approach_regions_v1",
            sampling_protocol_run=Path("protocol"),
        )


def test_skill_sampler_retains_parent_identity_and_uses_local_indices():
    view = SkillView(
        skill_id="bar_place_and_return",
        parent_episode_id="parent",
        start=630,
        end=1570,
        terminal_parent_frame=1570,
    )
    plan = {
        "profile": "uniform",
        "episodes": [{"probability": 1.0, "regions": []}],
        "frames": [
            dict(
                dataset_index=i,
                source_frame_index=i,
                episode_id="parent",
                probability=1 / 4819,
                region="all",
            )
            for i in range(4819)
        ],
    }
    original = copy.deepcopy(plan)
    selected = restrict_sampling_plan(plan, view, "a" * 64)
    assert plan == original
    assert len(selected["frames"]) == 940
    assert selected["frames"][0]["dataset_index"] == 0
    assert selected["frames"][0]["parent_dataset_index"] == 630
    assert selected["frames"][-1]["source_frame_index"] == 1569
    assert sum(f["probability"] for f in selected["frames"]) == pytest.approx(1)
    plan["frames"][630]["episode_id"] = "different"
    with pytest.raises(ValueError, match="boundaries"):
        restrict_sampling_plan(plan, view, "a" * 64)


@pytest.mark.skipif(
    not (os.environ.get("BIMANUAL_DINNER_DATASET") and os.environ.get("BIMANUAL_DINNER_VIEWS")),
    reason="Requires verified full dinner dataset/views and native LeRobot environment",
)
def test_real_skill_training_checkpoint_preserves_selected_scope(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    result = run_train(
        ACTTrainingConfig(
            dataset_path=Path(os.environ["BIMANUAL_DINNER_DATASET"]),
            skill_views_path=Path(os.environ["BIMANUAL_DINNER_VIEWS"]),
            skill_id="bar_place_and_return",
            steps=1,
            device="cpu",
            use_vae=False,
            dropout=0.0,
        ),
        store=store,
        project_root=Path.cwd(),
    )
    verified = store.verify(result.run_id)
    assert verified.outcome == "completed"
    assert verified.metrics["dataset_frames"] == 940
    assert verified.metrics["parent_dataset_frames"] == 4819
    assert verified.metrics["checkpoint_reload_verified"] is True
    assert verified.metrics["sampler_reload_verified"] is True
    assert verified.metrics["skill_view"]["start"] == 630
    sampled = verified.metrics["steps"][0]["sampled_frames"][0]
    assert sampled["parent_dataset_index"] == sampled["dataset_index"] + 630
    root = store.directory(result.run_id)
    norm = json.loads((root / "normalization.json").read_text())
    assert norm["numeric_scope"] == "selected_skill"
    assert norm["image_statistics_scope"] == "full_parent_training_dataset"
    assert (root / "skill_views.json").is_file()
