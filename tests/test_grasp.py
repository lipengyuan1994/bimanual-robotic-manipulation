import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.evidence import EvidenceStore
from bimanual.grasp import GraspConfig, GraspEnvironment, run_grasp, score_grasp
from bimanual.teacher import ReachError, check_joint_path, solve_downward

ROOT = Path(__file__).resolve().parents[1]


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
