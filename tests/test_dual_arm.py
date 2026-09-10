import json

import mujoco
import numpy as np
import pytest

from bimanual.dual_arm import (
    CAMERAS,
    JOINT_ORDER,
    MODEL_DIR,
    DualArm,
    FoundationConfig,
    run_foundation,
)
from bimanual.evidence import EvidenceStore


@pytest.fixture
def env():
    robot = DualArm()
    yield robot
    robot.close()


def test_upstream_joint_actuator_and_inertia_preserved(env):
    upstream = mujoco.MjModel.from_xml_path(str(MODEL_DIR / "so101.xml"))
    assert env.model.nu == env.model.nq == env.model.nv == 12
    assert env.model.opt.timestep == upstream.opt.timestep == 0.005
    for name in JOINT_ORDER:
        original = name.split("/")[1]
        j, a = env.model.joint(name).id, env.model.actuator(name).id
        uj, ua = upstream.joint(original).id, upstream.actuator(original).id
        np.testing.assert_equal(env.model.jnt_range[j], upstream.jnt_range[uj])
        assert env.model.actuator_trnid[a, 0] == j
        for field in (
            "actuator_ctrlrange",
            "actuator_forcerange",
            "actuator_gainprm",
            "actuator_biasprm",
        ):
            np.testing.assert_equal(getattr(env.model, field)[a], getattr(upstream, field)[ua])
    for arm in ("left", "right"):
        for i in range(1, upstream.nbody):
            j = env.model.body(f"{arm}/{upstream.body(i).name}").id
            np.testing.assert_allclose(env.model.body_mass[j], upstream.body_mass[i])
            np.testing.assert_allclose(env.model.body_inertia[j], upstream.body_inertia[i])


@pytest.mark.parametrize("channel", range(12))
def test_each_action_channel_drives_its_named_joint(env, channel):
    action = env.home.copy()
    action[channel] += 0.02
    env.step(action, episode_id=env.episode_id, sequence=0)
    assert env.data.qpos[env.qadr[channel]] > env.home[channel] + 0.005
    assert env.data.time == pytest.approx(0.05)
    assert env.max_contacts == 0


@pytest.mark.parametrize(
    "bad", [np.zeros(11), np.full(12, np.nan), np.full(12, np.inf), np.full(12, 10)]
)
def test_invalid_actions_do_not_mutate_state(env, bad):
    before, control = env.data.qpos.copy(), env.data.ctrl.copy()
    with pytest.raises(ValueError):
        env.step(bad, episode_id=env.episode_id, sequence=0)
    np.testing.assert_array_equal(env.data.qpos, before)
    np.testing.assert_array_equal(env.data.ctrl, control)
    assert env.data.time == 0


def test_wrist_range_intersection_and_lifecycle(env):
    action = env.home.copy()
    action[4] = 2.80  # Legal upstream ctrlrange, illegal physical joint range.
    with pytest.raises(ValueError, match="bounds"):
        env.step(action, episode_id=env.episode_id, sequence=0)
    episode = env.episode_id
    env.step(env.home, episode_id=episode, sequence=0)
    with pytest.raises(ValueError, match="Stale"):
        env.step(env.home, episode_id=episode, sequence=0)
    env.stop()
    with pytest.raises(ValueError, match="stopped"):
        env.step(env.home, episode_id=episode, sequence=1)
    env.reset()
    with pytest.raises(ValueError, match="Stale"):
        env.step(env.home, episode_id=episode, sequence=0)
    assert env.sequence == 0 and env.data.time == 0


def test_deterministic_reset_and_observation_boundary(env):
    def rollout():
        for index in range(20):
            env.step(env.home, episode_id=env.episode_id, sequence=index)
        return env.observe(render=False)

    a = rollout()
    env.reset()
    b = rollout()
    np.testing.assert_array_equal(a["joint_position_rad"], b["joint_position_rad"])
    assert a["episode_id"] != b["episode_id"]
    assert set(a) == {
        "schema_version",
        "episode_id",
        "sequence",
        "simulation_seconds",
        "observed_monotonic_ns",
        "joint_order",
        "joint_position_rad",
        "joint_velocity_rad_s",
        "rgb",
        "camera_order",
    }


def test_failed_run_is_retained(tmp_path, monkeypatch):
    def fail(self, *args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(DualArm, "step", fail)
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(RuntimeError, match="injected"):
        run_foundation(
            FoundationConfig(seconds=1, render=False), store=store, project_root=tmp_path
        )
    run = store.list_runs()[0]
    assert run["integrity"] == "verified" and run["outcome"] == "failed"
    assert not run["claims"] and run["metrics"]["manipulation_success"] is None


@pytest.mark.render
def test_camera_freshness_and_self_contained_scene(env, tmp_path):
    before = env.observe()
    targets = env.home.copy()
    targets[[0, 6]] += [0.10, -0.10]
    env.step(targets, episode_id=before["episode_id"], sequence=before["sequence"])
    after = env.observe()
    assert after["sequence"] == before["sequence"] + 1
    assert after["simulation_seconds"] > before["simulation_seconds"]
    assert after["observed_monotonic_ns"] > before["observed_monotonic_ns"]
    assert tuple(after["rgb"]) == CAMERAS
    for camera in CAMERAS:
        assert after["rgb"][camera].shape == (270, 480, 3)
        assert after["rgb"][camera].dtype == np.uint8
        assert np.std(after["rgb"][camera]) > 10
        assert not np.array_equal(before["rgb"][camera], after["rgb"][camera])
    store = EvidenceStore(tmp_path / "evidence")
    result = run_foundation(FoundationConfig(seconds=1), store=store, project_root=tmp_path)
    bundle = store.directory(result.run_id)
    loaded = mujoco.MjModel.from_xml_path(str(bundle / "scene.xml"))
    assert loaded.nu == 12
    assert store.verify(result.run_id).metrics["max_contacts_per_physics_step"] == 0
    rows = [json.loads(line) for line in (bundle / "observations.jsonl").read_text().splitlines()]
    assert len(rows) == 21 and rows[-1]["action_target_rad"] is None
