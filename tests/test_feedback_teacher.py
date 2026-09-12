"""Feedback collection must retain failed attempts and never claim a hand-off."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from bimanual import feedback_teacher as module
from bimanual.evidence import EvidenceStore


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_delta_rad", 0),
        ("max_delta_rad", float("nan")),
        ("max_delta_rad", 0.031),
        ("position_tolerance_rad", float("inf")),
        ("max_actions_per_goal", True),
        ("max_actions_per_goal", 0),
        ("record_demonstration", "yes"),
    ],
)
def test_invalid_config(field, value):
    with pytest.raises(ValidationError):
        module.FeedbackApproachConfig(**{field: value})


def test_feedback_direction_and_bound():
    measured = np.zeros(12)
    goal = np.arange(12, dtype=float) / 10
    result = module.feedback_target(measured, goal, 0.03)
    assert np.max(np.abs(result - measured)) == pytest.approx(0.03)
    assert result == pytest.approx(goal * (0.03 / 1.1))
    assert np.array_equal(measured, np.zeros(12))
    with pytest.raises(ValueError):
        module.feedback_target(np.full(12, np.nan), goal, 0.03)


@pytest.fixture
def fake_environment(monkeypatch):
    instances = []
    _, plan, _ = module.load_plan(module.ASSETS.with_name("dinner_teacher_v2"))
    first = np.asarray(plan["steps"][59]["q"])

    class Environment:
        def __init__(self, xml, trace, cancelled):
            self.data = SimpleNamespace(qpos=first.copy(), qvel=np.zeros(12))
            self.qadr = self.vadr = np.arange(12)
            self.lower, self.upper = np.full(12, -10.0), np.full(12, 10.0)
            self.sequence, self.episode_id = 0, "fake"
            self.stopped = self.closed = False
            instances.append(self)

        def allowed(self, pair):
            return True

        def step(self, action, **kwargs):
            self.data.qpos[:] = action
            self.sequence += 1

        def stop(self):
            self.stopped = True

        def close(self):
            self.closed = True

    monkeypatch.setattr(module, "DinnerEnvironment", Environment)
    monkeypatch.setattr(module, "check_joint_path", lambda *args: None)
    return instances


def run(tmp_path, **kwargs):
    store = EvidenceStore(tmp_path)
    result = module.run_feedback_approach(
        kwargs.pop("config", module.FeedbackApproachConfig()),
        store=store,
        project_root=Path.cwd(),
        **kwargs,
    )
    assert store.verify(result.run_id).manifest_sha256 == result.manifest_sha256
    return result


def test_success_is_only_approach(tmp_path, fake_environment):
    result = run(tmp_path)
    assert result.outcome == "completed"
    assert result.metrics["goals_reached"] == 3
    assert result.metrics["actions"] > 0
    assert result.metrics["physical_handoff_success"] is None
    assert not result.metrics["learned_execution"]
    assert fake_environment[0].closed and fake_environment[0].stopped


def test_cancel_before_initialization(tmp_path, fake_environment):
    result = run(tmp_path, cancelled=lambda: True)
    assert result.outcome == "interrupted"
    assert result.metrics["actions"] == 0
    assert not fake_environment


def test_budget_failure_closes_and_seals(tmp_path, fake_environment):
    result = run(tmp_path, config=module.FeedbackApproachConfig(max_actions_per_goal=1))
    assert result.outcome == "failed"
    assert "timeout" in result.metrics["error"]
    assert result.metrics["actions"] == 1
    assert fake_environment[0].closed and fake_environment[0].stopped


def test_collision_failure_never_applies_action(tmp_path, fake_environment, monkeypatch):
    def reject(*args):
        raise ValueError("collision")

    monkeypatch.setattr(module, "check_joint_path", reject)
    result = run(tmp_path)
    assert result.outcome == "failed"
    assert result.metrics["actions"] == 0
    assert fake_environment[0].closed


def test_cleanup_error_still_seals(tmp_path, fake_environment, monkeypatch):
    def reject(self):
        raise RuntimeError("renderer cleanup")

    monkeypatch.setattr(module.DinnerEnvironment, "close", reject)
    result = run(tmp_path)
    assert result.outcome == "failed"
    assert result.metrics["cleanup_errors"] == ["RuntimeError: renderer cleanup"]
    assert fake_environment[0].stopped


def test_recording_boundaries_and_partial_step(tmp_path, fake_environment, monkeypatch):
    records = []

    class Recorder:
        def __init__(self, directory, **kwargs):
            self.directory, self.frames = directory, records

        def record(self, observation, action):
            records.append((observation["sequence"], action is None))

        def finalize(self, **kwargs):
            assert kwargs["outcome"] == "failure"
            destination = self.directory / "fake-episode.json"
            destination.write_text("{}")
            return destination

    monkeypatch.setattr(module, "DemonstrationRecorder", Recorder)
    monkeypatch.setattr(
        module.DinnerEnvironment,
        "observe",
        lambda self, **kwargs: {"sequence": self.sequence},
        raising=False,
    )
    original = module.DinnerEnvironment.step

    def step(self, action, **kwargs):
        original(self, action, **kwargs)
        if self.sequence == 2:
            raise ValueError("partial physics")

    monkeypatch.setattr(module.DinnerEnvironment, "step", step)
    result = run(tmp_path, config=module.FeedbackApproachConfig(record_demonstration=True))
    assert result.outcome == "failed"
    assert result.metrics["actions"] == 1
    # Only confirmed action 0 is recorded; failed action 1 becomes a terminal boundary.
    assert records == [(0, False), (1, True)]
    assert fake_environment[0].closed


def test_cancel_between_actions(tmp_path, fake_environment):
    result = run(
        tmp_path, cancelled=lambda: bool(fake_environment and fake_environment[0].sequence)
    )
    assert result.outcome == "interrupted"
    assert result.metrics["actions"] == 1
    assert fake_environment[0].closed


def test_acquisition_is_preserved_and_excluded(tmp_path, fake_environment):
    import json

    result = run(
        tmp_path,
        config=module.FeedbackApproachConfig(variation_seed=7, acquisition_offset_rad=0.06),
    )
    assert result.outcome == "completed"
    start = result.metrics["correction_start_action"]
    assert start == result.metrics["acquisition_actions"] > 0
    rows = [
        json.loads(line)
        for line in (tmp_path / "runs" / result.run_id / "actions.jsonl").read_text().splitlines()
    ]
    assert all(row["training_eligible"] is False for row in rows[:start])
    assert all(row["training_eligible"] is True for row in rows[start:])
    assert result.metrics["goals_reached"] == 3
    target = result.config["acquisition"][0]["q"]
    nominal = result.config["goals"][0]["q"]
    assert np.max(np.abs(np.asarray(target) - nominal)) <= 0.06
    assert target[4:] == nominal[4:]
