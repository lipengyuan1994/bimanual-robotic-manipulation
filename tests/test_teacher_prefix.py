"""Teacher-assisted component setup; never autonomous manipulation evidence."""

import json
from dataclasses import replace

import numpy as np
import pytest
from test_skill_views import synthetic_export_v2  # noqa: F401

from bimanual.dual_arm import CAMERAS
from bimanual.skill_registry import dinner_capability
from bimanual.skill_views import create_skill_views
from bimanual.teacher_prefix import (
    TeacherPreparedDinnerControlWorker,
    load_teacher_prefix,
)


@pytest.fixture(scope="module")
def views(synthetic_export_v2, tmp_path_factory):  # noqa: F811
    path = tmp_path_factory.mktemp("teacher-prefix") / "views.json"
    create_skill_views(synthetic_export_v2, path)
    return synthetic_export_v2, path


def test_verified_prefixes_bind_exact_frozen_skill_starts(views):
    dataset, path = views
    expected = {
        "handoff_transfer": 0,
        "bar_place_and_return": 630,
        "cup_pick_place": 1580,
        "plate_pick_place": 2099,
        "drawer_open": 3081,
        "spoon_retrieve_place": 3641,
        "fork_retrieve_place": 4345,
    }
    for skill, count in expected.items():
        prefix = load_teacher_prefix(dataset, path, skill_id=skill)
        assert prefix.action_count == count and prefix.reverify() == prefix
        report = prefix.report()
        assert report["teacher_actions_used"] == (count > 0)
        assert report["autonomous_workflow_evidence"] is False
        assert report["release_qualified"] is False


def test_forged_prefix_is_rejected_before_worker_allocation(tmp_path, views):
    dataset, path = views
    prefix = load_teacher_prefix(dataset, path, skill_id="bar_place_and_return")
    forged = replace(prefix, plan_steps_sha256="0" * 64)
    with pytest.raises(ValueError, match="verified|changed"):
        TeacherPreparedDinnerControlWorker(
            tmp_path / "worker",
            [dinner_capability(prefix.skill_id)],
            prefix=forged,
            render_capture=lambda env: {},
        )
    assert not (tmp_path / "worker").exists()


def test_real_physics_prefix_reaches_boundary_and_is_disclosed(tmp_path, views):
    dataset, path = views
    prefix = load_teacher_prefix(dataset, path, skill_id="bar_place_and_return")
    worker = TeacherPreparedDinnerControlWorker(
        tmp_path / "worker",
        [dinner_capability(prefix.skill_id)],
        prefix=prefix,
        render_capture=lambda env: {
            name: np.zeros((270, 480, 3), dtype=np.uint8) for name in CAMERAS
        },
    )
    try:
        assert worker._env.sequence == prefix.action_count
        assert worker._env.data.time == pytest.approx(prefix.action_count / 20)
        assert worker.supervisor.snapshot().task is None
        report = json.loads((worker.directory / "worker.json").read_text())
        assert report["teacher_schedule_used"] is True
        assert report["teacher_prefix_actions"] == 630
        assert report["teacher_prefix_sha256"] == prefix.prefix_sha256
        lines = (worker.directory / "teacher-prefix-actions.jsonl").read_text().splitlines()
        assert len(lines) == 630
        observation = worker.capture()
        assert observation.sequence == 630 and observation.simulation_seconds == pytest.approx(31.5)
    finally:
        worker.close()
