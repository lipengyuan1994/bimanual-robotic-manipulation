import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.cup import CupConfig, CupEnvironment, run_cup, score_cup
from bimanual.evidence import EvidenceStore
from bimanual.teacher import ReachError, check_carried_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def nominal(tmp_path_factory):
    store = EvidenceStore(tmp_path_factory.mktemp("cup"))
    result = run_cup(CupConfig(render=False), store=store, project_root=ROOT)
    trace = [
        json.loads(row)
        for row in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    return store, result, trace


def test_hollow_cup_physically_moves_and_settles_upright(nominal):
    store, result, trace = nominal
    assert result.outcome == "completed", result.metrics
    assert result.metrics["cup_success"] and result.metrics["released_upright"]
    assert result.metrics["manipulation_success"] is None
    assert result.metrics["actual_displacement_xy_m"] >= 0.06
    assert result.metrics["airborne_bilateral_hold_samples"] == 400
    assert result.metrics["airborne_transport_samples"] == 600
    assert result.metrics["settled_release_samples"] == 400
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    assert model.nu == 12 and model.neq == 0 and np.all(model.body_gravcomp == 0)
    assert model.joint("cup/free").type[0] == mujoco.mjtJoint.mjJNT_FREE
    assert model.body("cup").mass[0] == pytest.approx(0.06)
    assert model.geom("cup/wall15").id >= 0
    assert model.geom("cup/handle_outer").id >= 0
    rows = [json.loads(r) for r in (directory / "observations.jsonl").read_text().splitlines()]
    assert rows[-1]["action_target_rad"] is None
    assert rows[-1]["simulation_seconds"] == pytest.approx(trace[-1]["simulation_seconds"])
    assert all(not {"object_position_m", "upright_cosine"}.intersection(row) for row in rows)
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault", ["tilt", "short", "support", "moving", "collision", "gap", "grip"]
)
def test_false_cup_success_rejected(nominal, fault):
    _, _, truth = nominal
    trace = copy.deepcopy(truth)
    row = next(r for r in trace if r["stage"] == "settled")
    if fault == "tilt":
        row["upright_cosine"] = 0.9
    elif fault == "short":
        trace.pop()
    elif fault == "support":
        row["fixed_jaw_normal_force_n"] = 0.1
    elif fault == "moving":
        row["object_velocity"][0] = 0.02
    elif fault == "collision":
        trace[0]["forbidden_pairs"] = [["left/gripper", "right/gripper"]]
    elif fault == "gap":
        row["simulation_seconds"] += 0.001
    else:
        next(r for r in trace if r["stage"] == "transport")["moving_jaw_normal_force_n"] = 0
    assert not score_cup(trace)["cup_success"]


@pytest.mark.parametrize("fault", ["missing_object", "skip_close"])
def test_fault_stops_before_transport_with_preserved_failure(tmp_path, fault):
    store = EvidenceStore(tmp_path)
    result = run_cup(CupConfig(render=False, **{fault: True}), store=store, project_root=ROOT)
    assert result.outcome == "failed" and not result.metrics["cup_success"]
    assert not result.claims and "error.txt" in result.files
    trace = (store.directory(result.run_id) / "scoring-truth.jsonl").read_text()
    assert '"stage": "transport"' not in trace
    store.verify(result.run_id)


def test_unowned_arm_and_live_collision_stop():
    env = CupEnvironment(CupConfig(render=False))
    try:
        action = env.home.copy()
        action[6] += 0.1
        with pytest.raises(ValueError, match="does not own"):
            env.step(action, episode_id=env.episode_id, sequence=env.sequence)
        assert env.sequence == 0
        # Test-only disturbance: cup deeply overlaps the table. Production never does this.
        env.data.joint("cup/free").qpos[2] -= 0.015
        with pytest.raises(RuntimeError, match="penetration"):
            env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
        assert not env.active and len(env.contact_trace) == 1
    finally:
        env.close()


def test_carried_prediction_cannot_edit_live_object_or_skip_forbidden_contact():
    env = CupEnvironment(CupConfig(render=False))
    try:
        env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
        before = (env.data.qpos.copy(), env.data.qvel.copy(), env.data.ctrl.copy(), env.data.time)
        end = env.home.copy()
        end[0] += 0.03
        check_carried_path(env, env.home, end, env.allowed, body_name="cup", site_name="left/pinch")
        with pytest.raises(ReachError, match="forbidden geometry"):
            check_carried_path(
                env, env.home, env.home, lambda pair: False, body_name="cup", site_name="left/pinch"
            )
        for actual, expected in zip(
            (env.data.qpos, env.data.qvel, env.data.ctrl, env.data.time), before, strict=True
        ):
            np.testing.assert_array_equal(actual, expected)
        with pytest.raises(ReachError, match="free joint"):
            check_carried_path(
                env,
                env.home,
                env.home,
                env.allowed,
                body_name="left/gripper",
                site_name="left/pinch",
            )
        with pytest.raises(ReachError, match="finite"):
            check_carried_path(
                env,
                env.home,
                np.full(12, np.nan),
                env.allowed,
                body_name="cup",
                site_name="left/pinch",
            )
    finally:
        env.close()


def test_interrupted_cup_preserves_partial_run(tmp_path, monkeypatch):
    original = CupEnvironment.after_physics_step

    def interrupt(env):
        original(env)
        if len(env.contact_trace) == 7:
            raise KeyboardInterrupt()

    monkeypatch.setattr(CupEnvironment, "after_physics_step", interrupt)
    store = EvidenceStore(tmp_path)
    result = run_cup(CupConfig(render=False), store=store, project_root=ROOT)
    assert result.outcome == "interrupted" and result.metrics[
        "simulation_seconds"
    ] == pytest.approx(0.035)
    assert not result.metrics["cup_success"] and not result.claims
    store.verify(result.run_id)


@pytest.mark.render
def test_three_camera_cup_replay(tmp_path):
    from PIL import Image

    store = EvidenceStore(tmp_path)
    result = run_cup(CupConfig(), store=store, project_root=ROOT)
    assert result.outcome == "completed", result.metrics
    with Image.open(store.directory(result.run_id) / "preview.png") as image:
        assert image.size == (1440, 300)
    with Image.open(store.directory(result.run_id) / "replay.gif") as image:
        assert image.n_frames > 50
    store.verify(result.run_id)


def test_right_arm_cup_placement_and_mirrored_evidence(tmp_path):
    store = EvidenceStore(tmp_path)
    result = run_cup(CupConfig(render=False, arm="right"), store=store, project_root=ROOT)
    assert result.outcome == "completed", result.metrics
    assert result.metrics["cup_success"]
    assert result.metrics["destination_position_m"] == [0.066, 0.153, 0.378]
    trace = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    assert score_cup(trace, arm="right")["cup_success"]
    assert not score_cup(trace, arm="left")["cup_success"]
    rows = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "observations.jsonl").read_text().splitlines()
    ]
    for row in rows:
        if row["action_target_rad"] is not None:
            assert row["action_target_rad"][:6] == [0.0, -1.0, 0.8, 1.2, 0.0, 0.8]
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault",
    [
        "nan_overlap",
        "negative_force",
        "pose_shape",
        "velocity_shape",
        "nonfinite_velocity",
        "invalid_support",
        "nan_upright",
        "missing_stage",
    ],
)
def test_review_rejects_malformed_cup_trace(nominal, fault):
    _, _, original = nominal
    trace = list(original)
    row = copy.deepcopy(trace[1])
    trace[1] = row
    if fault == "nan_overlap":
        row["max_penetration_m"] = float("nan")
    elif fault == "negative_force":
        row["fixed_jaw_normal_force_n"] = -1
    elif fault == "pose_shape":
        row["object_position_m"].pop()
    elif fault == "velocity_shape":
        row["object_velocity"].pop()
    elif fault == "nonfinite_velocity":
        row["object_velocity"][0] = float("inf")
    elif fault == "invalid_support":
        row["table_contact"] = "false"
    elif fault == "nan_upright":
        row["upright_cosine"] = float("nan")
    elif fault == "missing_stage":
        row.pop("stage")
    result = score_cup(trace)
    assert not result["cup_success"] and not result["trace_valid"]
    assert result["invalid_trace_row"] == 1
