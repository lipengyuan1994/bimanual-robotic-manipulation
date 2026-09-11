"""Actor contract failures must stop and retain auditable partial evidence."""

import gzip
import json
import shutil
from pathlib import Path

import pytest

from bimanual.dinner_teacher import (
    ASSETS,
    DinnerTeacherConfig,
    load_plan,
    phase_permissions,
    run_dinner_teacher,
)
from bimanual.evidence import EvidenceStore


def test_packaged_plan_identity():
    manifest, plan, layout = load_plan()
    assert len(plan["steps"]) == 4819
    assert manifest["source_run"] == "20260911T011032-a9fda4aee41f"
    assert layout["plate_position_tolerance_m"] == 0.02


def test_corrupt_scene_rejected(tmp_path):
    shutil.copytree(ASSETS, tmp_path / "assets")
    with (tmp_path / "assets/scene.xml").open("a") as file:
        file.write("<!-- corrupt -->")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_plan(tmp_path / "assets")


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("plate/transition_home", ({}, None, "left")),
        ("plate/lower", ({"left": {"plate"}}, "plate", "left")),
        (
            "handoff/both_hold",
            ({"left": {"practice_object"}, "right": {"practice_object"}}, None, "left"),
        ),
        ("handoff/bar_transport", ({"right": {"practice_object"}}, "practice_object", "right")),
        ("utensils/fork_clearance", ({"left": {"fork"}}, "fork", "left")),
    ],
)
def test_phase_contact_ownership(phase, expected):
    assert phase_permissions(phase) == expected


def test_cancel_before_initialization_seals_failure(tmp_path):
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False), store, Path.cwd(), cancelled=lambda: True
    )
    assert result.outcome == "interrupted"
    assert not result.claims
    assert not result.metrics["score"]["full_workflow_success"]
    store.verify(result.run_id)


def test_mid_step_cancellation_retains_partial_trace(tmp_path):
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 8

    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False), store, Path.cwd(), cancelled=cancelled
    )
    assert result.outcome == "interrupted", result.metrics["error"]
    assert not result.claims
    assert not result.metrics["score"]["full_workflow_success"]
    run = store.directory(result.run_id)
    actions = [json.loads(line) for line in (run / "actions.jsonl").read_text().splitlines()]
    assert len(actions) == 1 and not actions[0]["applied"]
    with gzip.open(run / "physics.jsonl.gz", "rt") as file:
        rows = [json.loads(line) for line in file]
    assert 0 < len(rows) < 50
    store.verify(result.run_id)


@pytest.fixture
def recorder_environment(monkeypatch):
    """Fake stepping/rendering, real PNG recorder/contracts; no physical success evidence."""
    from types import SimpleNamespace

    import numpy as np

    import bimanual.dinner_scoring as scoring
    import bimanual.dinner_teacher as teacher
    from bimanual.dual_arm import CAMERAS, JOINT_ORDER

    manifest, plan, layout = load_plan()
    short_plan = dict(plan, steps=[dict(phase="handoff/settle", q=[i / 10] * 12) for i in range(3)])
    monkeypatch.setattr(teacher, "load_plan", lambda: (manifest, short_plan, layout))
    monkeypatch.setattr(teacher, "check_joint_path", lambda *args: None)
    options = dict(fail_at=None, score_success=True, observe_failure_at=None, leak_truth=False)
    instances = []

    class FakeEnvironment:
        def __init__(self, xml, trace, cancelled):
            self.lower, self.upper = np.full(12, -1.0), np.full(12, 1.0)
            self.sequence, self.episode_id = 0, "recording-fixture"
            self.data = SimpleNamespace(time=0.0, ctrl=np.zeros(12))
            self.actuator_ids = np.arange(12)
            self.phase = "handoff/settle"
            self.active_contacts = {}
            self.observations, self.applied = [], []
            self.stopped = self.closed = False
            self.trace = trace
            instances.append(self)

        def mapping(self):
            return {"fixture": True}

        def allowed(self, pair):
            return True

        def observe(self, *, render):
            assert render is True
            if self.sequence == options["observe_failure_at"]:
                raise RuntimeError("Fixture camera failure")
            self.observations.append((self.sequence, self.data.time))
            raw = dict(
                schema_version=1,
                episode_id=self.episode_id,
                sequence=self.sequence,
                simulation_seconds=self.data.time,
                observed_monotonic_ns=1_000_000_000 + len(self.observations) * 1_000_000,
                joint_order=list(JOINT_ORDER),
                joint_position_rad=np.full(12, self.sequence / 10),
                joint_velocity_rad_s=np.zeros(12),
                camera_order=list(CAMERAS),
                rgb={
                    camera: np.full((270, 480, 3), self.sequence * 20 + index, np.uint8)
                    for index, camera in enumerate(CAMERAS)
                },
            )
            if options["leak_truth"]:
                raw["object_position"] = [0.0, 0.0, 0.0]
            return raw

        def step(self, target, *, episode_id, sequence):
            assert episode_id == self.episode_id and sequence == self.sequence
            if self.sequence == options["fail_at"]:
                self.data.time += 0.017
                self.trace.write('{"partial_physics_fixture": true}\n')
                raise InterruptedError("Fixture interruption during control interval")
            self.applied.append(target.copy())
            self.data.ctrl[:] = target
            self.sequence += 1
            self.data.time = self.sequence / 20

        def stop(self):
            self.stopped = True

        def close(self):
            self.closed = True

    monkeypatch.setattr(teacher, "DinnerEnvironment", FakeEnvironment)
    monkeypatch.setattr(
        scoring,
        "score_dinner",
        lambda *args: {
            "full_workflow_success": options["score_success"],
            "failed_gates": [] if options["score_success"] else ["fixture_physical_failure"],
        },
    )
    return options, instances


def load_recorded_episode(store, result):
    from bimanual.contracts import DemonstrationEpisode, validate_episode_artifacts

    root = store.directory(result.run_id)
    episode = DemonstrationEpisode.model_validate_json(
        (root / "demonstration/episode.json").read_text()
    )
    validate_episode_artifacts(episode, root)
    store.verify(result.run_id)
    return root, episode


def test_full_rate_recording_is_independent_of_replay_and_keeps_truth_separate(
    tmp_path, recorder_environment
):
    import numpy as np
    from PIL import Image

    options, instances = recorder_environment
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False, record_demonstration=True), store, Path.cwd()
    )
    assert result.outcome == "completed", result.metrics
    root, episode = load_recorded_episode(store, result)
    assert instances[0].observations == [(0, 0.0), (1, 0.05), (2, 0.1), (3, 0.15)]
    assert len(episode.frames) == 4 and episode.frames[-1].action_rad is None
    assert (
        episode.outcome == "success"
        and episode.lineage.seed == 0
        and episode.lineage.split == "train"
    )
    assert len(list((root / "demonstration/frames").glob("*.png"))) == 12
    assert not result.metrics["rendered"] and not (root / "replay.gif").exists()
    for index, frame in enumerate(episode.frames):
        assert frame.observation.sequence == index
        assert frame.observation.simulation_seconds == index / 20
        assert "phase" not in frame.observation.model_dump()
        assert "objects" not in frame.observation.model_dump()
        assert frame.observation.joint_position_rad == tuple([index / 10] * 12)
        if index < 3:
            np.testing.assert_array_equal(frame.action_rad, instances[0].applied[index])
        for camera_index, camera in enumerate(frame.observation.frames):
            image = Image.open(root / camera.artifact.path)
            assert image.size == (480, 270) and image.mode == "RGB"
            assert image.getpixel((0, 0)) == (index * 20 + camera_index,) * 3
    phases = [
        json.loads(row) for row in (root / "demonstration/phases.jsonl").read_text().splitlines()
    ]
    assert [row["observation_sequence"] for row in phases] == [0, 1, 2, 3]
    assert [row["transition_applied"] for row in phases] == [True, True, True, False]
    controller = json.loads((root / "controller.json").read_text())
    assert (
        controller["teacher_uses_simulator_truth"]
        and "no randomization" in controller["seed_semantics"]
    )


@pytest.mark.parametrize("fail_at", [0, 1])
def test_partial_step_records_only_prior_complete_transitions(
    tmp_path, recorder_environment, fail_at
):
    from bimanual.demonstrations import require_successful_training_episode

    options, instances = recorder_environment
    options["fail_at"] = fail_at
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False, record_demonstration=True), store, Path.cwd()
    )
    assert result.outcome == "interrupted", result.metrics
    root, episode = load_recorded_episode(store, result)
    assert episode.outcome == "cancelled" and len(episode.frames) == fail_at + 1
    assert episode.frames[-1].action_rad is None
    assert episode.frames[-1].observation.simulation_seconds == fail_at / 20
    assert instances[0].data.time == pytest.approx(fail_at / 20 + 0.017)
    assert result.metrics["demonstration_terminal_boundary"] == "pre_unconfirmed_action"
    commands = [json.loads(row) for row in (root / "actions.jsonl").read_text().splitlines()]
    assert sum(row["applied"] for row in commands) == fail_at
    assert not commands[-1]["applied"] and not result.claims
    with pytest.raises(ValueError, match="rejects"):
        require_successful_training_episode(episode)


def test_recording_outcome_comes_from_physical_score(tmp_path, recorder_environment):
    options, _ = recorder_environment
    options["score_success"] = False
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False, record_demonstration=True), store, Path.cwd()
    )
    _, episode = load_recorded_episode(store, result)
    assert result.outcome == "failed" and episode.outcome == "failure"
    assert len(episode.frames) == 4 and not result.claims


def test_recording_camera_failure_is_sealed_without_claiming_transition(
    tmp_path, recorder_environment
):
    options, instances = recorder_environment
    options["observe_failure_at"] = 1
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False, record_demonstration=True), store, Path.cwd()
    )
    assert result.outcome == "failed" and "demonstration_error" in result.metrics
    assert len(instances[0].applied) == 1 and not result.claims
    assert instances[0].closed and instances[0].stopped
    assert "demonstration/episode.json" not in result.files
    store.verify(result.run_id)


def test_default_does_not_capture_training_observations(tmp_path, recorder_environment):
    _, instances = recorder_environment
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(DinnerTeacherConfig(render=False), store, Path.cwd())
    assert result.outcome == "completed"
    assert instances[0].observations == []
    assert not any(name.startswith("demonstration/") for name in result.files)


def test_teacher_truth_is_rejected_by_real_recorder(tmp_path, recorder_environment):
    options, _ = recorder_environment
    options["leak_truth"] = True
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False, record_demonstration=True), store, Path.cwd()
    )
    assert result.outcome == "failed" and not result.claims
    assert "truth is forbidden" in result.metrics["error"]
    store.verify(result.run_id)
