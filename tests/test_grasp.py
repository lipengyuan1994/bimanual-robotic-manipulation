import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.contracts import DemonstrationEpisode, validate_episode_artifacts
from bimanual.demonstrations import require_successful_training_episode
from bimanual.evidence import EvidenceStore
from bimanual.grasp import GraspConfig, GraspEnvironment, run_grasp, score_grasp
from bimanual.teacher import ReachError, check_joint_path, solve_downward

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.render
@pytest.mark.parametrize("fault", [None, "missing", "partial"])
def test_recorded_physical_transitions(tmp_path, monkeypatch, fault):
    if fault == "partial":
        original = GraspEnvironment.after_physics_step

        def interrupted_step(self):
            original(self)
            raise RuntimeError("Injected partial physics failure")

        monkeypatch.setattr(GraspEnvironment, "after_physics_step", interrupted_step)
    store = EvidenceStore(tmp_path)
    result = run_grasp(
        GraspConfig(
            record_demo=True, destination_xy=(-0.15, 0.08), missing_object=fault == "missing"
        ),
        store=store,
        project_root=ROOT,
    )
    directory = store.directory(result.run_id)
    episode = DemonstrationEpisode.model_validate_json(
        (directory / "demonstration/episode.json").read_text()
    )
    validate_episode_artifacts(episode, directory)
    assert episode.frames[-1].action_rad is None
    assert all("object_position" not in frame.observation.model_dump() for frame in episode.frames)
    if fault is None:
        assert result.outcome == "completed", result.metrics
        assert len(episode.frames) == 461
        assert episode.frames[-1].observation.simulation_seconds == pytest.approx(23)
        require_successful_training_episode(episode)
    else:
        assert result.outcome == "failed"
        assert episode.outcome == "failure"
        assert len(episode.frames) == 1
        assert episode.frames[0].observation.simulation_seconds == 0
        with pytest.raises(ValueError, match="rejects"):
            require_successful_training_episode(episode)
        if fault == "partial":
            assert result.metrics["simulation_seconds"] == pytest.approx(0.005)
    store.verify(result.run_id)


def test_recording_requires_cameras():
    with pytest.raises(ValueError, match="cameras"):
        GraspConfig(record_demo=True, render=False)


@pytest.fixture
def env():
    environment = GraspEnvironment(GraspConfig(render=False))
    yield environment
    environment.close()


def test_ik_is_bounded_and_does_not_edit_live_state(env):
    before = env.data.qpos.copy()
    target = np.array([-0.15, -0.08, 0.404])
    solution = solve_downward(env, target, env.home)
    assert np.all(solution >= env.lower) and np.all(solution <= env.upper)
    np.testing.assert_array_equal(env.data.qpos, before)
    np.testing.assert_array_equal(solution[5:], env.home[5:])
    scratch = mujoco.MjData(env.model)
    scratch.qpos[:] = env.data.qpos
    scratch.qpos[env.qadr] = solution
    mujoco.mj_forward(env.model, scratch)
    np.testing.assert_allclose(scratch.site("left/pinch").xpos, target, atol=0.0001)
    axis = scratch.site("left/pinch").xmat.reshape(3, 3)[:, 0]
    np.testing.assert_allclose(axis, [0, 0, -1], atol=0.001)
    with pytest.raises(ReachError, match="unreachable"):
        solve_downward(env, np.array([10, 0, 10]), env.home)
    np.testing.assert_array_equal(env.data.qpos, before)


def test_collision_guard_stops_at_physics_step(env):
    # Fault injection is test-only. Operating teacher never writes object qpos.
    body = env.model.body("practice_object").id
    address = env.model.jnt_qposadr[env.model.body_jntadr[body]]
    env.data.qpos[address + 2] = 0.37
    with pytest.raises(RuntimeError, match="penetration"):
        env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
    assert not env.active
    assert len(env.contact_trace) == 1


def test_collision_path_rejection_preserves_live_state(env):
    env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
    before = env.data.qpos.copy()
    # After settling starts, an empty allow-list rejects object-table contact.
    with pytest.raises(ReachError, match="forbidden"):
        check_joint_path(env, env.home, env.home, lambda pair: False)
    np.testing.assert_array_equal(env.data.qpos, before)


def test_contact_only_episode_and_scoring_negative_controls(tmp_path):
    store = EvidenceStore(tmp_path)
    result = run_grasp(GraspConfig(render=False), store=store, project_root=ROOT)
    assert result.outcome == "completed", result.metrics
    assert result.metrics["grasp_success"] is True
    assert result.metrics["manipulation_success"] is None
    assert result.metrics["airborne_bilateral_hold_samples"] == 400
    assert result.metrics["settled_release_samples"] == 400
    assert result.metrics["max_penetration_m"] <= 0.0025
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    assert model.neq == 0  # No welded or other equality attachment.
    assert model.nu == 12  # No object actuator.
    assert np.all(model.body_gravcomp == 0)
    rows = [json.loads(r) for r in (directory / "observations.jsonl").read_text().splitlines()]
    assert len(rows) == 401
    assert rows[-1]["action_target_rad"] is None
    assert all("object_position_m" not in row for row in rows)
    truth = [json.loads(r) for r in (directory / "scoring-truth.jsonl").read_text().splitlines()]
    assert len(truth) == 4000
    assert store.verify(result.run_id).manifest_sha256 == result.manifest_sha256
    initial = np.array([-0.15, -0.08, 0.391])
    # A height spike, single-jaw contact, collision, or unfinished release cannot pass.
    for mutation in ["one_jaw", "supported", "collision", "penetration", "short"]:
        altered = copy.deepcopy(truth)
        row = next(r for r in altered if r["stage"] == "hold")
        if mutation == "one_jaw":
            row["moving_jaw_normal_force_n"] = 0
        elif mutation == "supported":
            row["table_contact"] = True
        elif mutation == "collision":
            row["forbidden_pairs"] = [["left/fixed_jaw_box1", "workbench"]]
        elif mutation == "penetration":
            row["max_penetration_m"] = 0.01
        else:
            altered.pop()
        assert not score_grasp(altered, initial)["grasp_success"]


@pytest.mark.parametrize("fault", ["missing_object", "skip_close"])
def test_faults_are_failed_and_sealed(tmp_path, fault):
    store = EvidenceStore(tmp_path)
    result = run_grasp(GraspConfig(render=False, **{fault: True}), store=store, project_root=ROOT)
    assert result.outcome == "failed"
    assert result.metrics["grasp_success"] is False
    assert result.claims == []
    assert "error.txt" in result.files
    store.verify(result.run_id)


@pytest.mark.parametrize("arm,x,y", [("left", -0.15, 0.08), ("right", 0.15, -0.08)])
def test_transport_requires_sustained_grip_and_destination(tmp_path, arm, x, y):
    store = EvidenceStore(tmp_path)
    config = GraspConfig(render=False, arm=arm, destination_xy=(x, y))
    result = run_grasp(config, store=store, project_root=ROOT)
    assert result.outcome == "completed", result.metrics
    assert result.kind == "contact_placement_teacher"
    assert result.metrics["placement_success"] is True
    assert result.metrics["airborne_transport_samples"] == 600
    assert result.metrics["final_position_error_m"] < 0.02
    store.verify(result.run_id)
    directory = store.directory(result.run_id)
    truth = [json.loads(r) for r in (directory / "scoring-truth.jsonl").read_text().splitlines()]
    initial = np.array([config.object_x, config.object_y, 0.391])
    destination = np.array([x, y, 0.391])
    assert not score_grasp(truth, initial, initial)["placement_success"]
    repeated = []
    for name, count in [("hold", 400), ("transport", 600), ("settled", 400)]:
        repeated.extend([next(r for r in truth if r["stage"] == name)] * count)
    assert not score_grasp(repeated, initial, destination)["placement_success"]
    for fault in ("gap", "duplicate", "order", "nonterminal", "interleaved"):
        altered = copy.deepcopy(truth)
        if fault == "gap":
            altered[100]["simulation_seconds"] += 0.001
        elif fault == "duplicate":
            altered[100]["simulation_seconds"] = altered[99]["simulation_seconds"]
        elif fault == "order":
            # Preserve valid cadence and samples, but put released settling before hold.
            phases = [r for r in altered if r["stage"] == "settled"]
            altered = phases + [r for r in altered if r["stage"] != "settled"]
            for index, sample in enumerate(altered):
                sample["simulation_seconds"] = (index + 1) * 0.005
        elif fault == "nonterminal":
            last = copy.deepcopy(altered[-1])
            last.update(stage="retreat", simulation_seconds=last["simulation_seconds"] + 0.005)
            altered.append(last)
        else:
            a = next(i for i, r in enumerate(altered) if r["stage"] == "hold")
            b = next(i for i, r in enumerate(altered) if r["stage"] == "transport")
            altered[a]["stage"], altered[b]["stage"] = altered[b]["stage"], altered[a]["stage"]
        assert not score_grasp(altered, initial, destination)["placement_success"], fault
    row = next(r for r in truth if r["stage"] == "transport")
    row["fixed_jaw_normal_force_n"] = 0
    assert not score_grasp(truth, initial, destination)["placement_success"]


@pytest.mark.parametrize("arm", ["left", "right"])
def test_single_arm_ownership(arm):
    env = GraspEnvironment(GraspConfig(arm=arm, render=False))
    try:
        values = env.home.copy()
        values[6 if arm == "left" else 0] += 0.1
        before = env.data.qpos.copy()
        with pytest.raises(ValueError, match="does not own"):
            env.step(values, episode_id=env.episode_id, sequence=env.sequence)
        np.testing.assert_array_equal(env.data.qpos, before)
        assert env.sequence == 0
    finally:
        env.close()


def test_placement_config_rejects_ambiguous_or_nonfinite_destination():
    for xy in [(-0.15, -0.08), (float("nan"), 0), (float("inf"), 0), (0.6, 0)]:
        with pytest.raises(ValueError):
            GraspConfig(destination_xy=xy)
