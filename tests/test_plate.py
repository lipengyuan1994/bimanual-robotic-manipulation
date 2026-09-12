import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.evidence import EvidenceStore
from bimanual.plate import PlateConfig, PlateEnvironment, run_plate, score_plate
from bimanual.teacher import ReachError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def nominal(tmp_path_factory):
    store = EvidenceStore(tmp_path_factory.mktemp("plate"))
    result = run_plate(PlateConfig(render=False), store=store, project_root=ROOT)
    trace = [
        json.loads(row)
        for row in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    return store, result, trace


def test_rimmed_plate_physically_moves_and_settles_upright(nominal):
    store, result, trace = nominal
    assert result.outcome == "completed", result.metrics
    assert result.metrics["plate_success"] and result.metrics["released_upright"]
    assert result.metrics["manipulation_success"] is None
    assert result.metrics["actual_displacement_xy_m"] >= 0.06
    assert result.metrics["airborne_bilateral_hold_samples"] == 2000
    assert result.metrics["airborne_transport_samples"] == 3000
    assert result.metrics["settled_release_samples"] == 2000
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    assert model.nu == 12 and model.neq == 0 and np.all(model.body_gravcomp == 0)
    assert model.joint("plate/free").type[0] == mujoco.mjtJoint.mjJNT_FREE
    assert model.body("plate").mass[0] == pytest.approx(0.08)
    assert model.geom("plate/rim23").id >= 0
    assert model.geom("plate_rack").id >= 0
    assert model.opt.timestep == pytest.approx(0.001)
    assert model.geom("plate/base").size[0] == pytest.approx(0.065)
    assert not any(model.geom(i).name == "placement_trivet" for i in range(model.ngeom))
    rows = [json.loads(r) for r in (directory / "observations.jsonl").read_text().splitlines()]
    assert rows[-1]["action_target_rad"] is None
    assert rows[-1]["simulation_seconds"] == pytest.approx(trace[-1]["simulation_seconds"])
    assert all(not {"object_position_m", "upright_cosine"}.intersection(row) for row in rows)
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault",
    [
        "tilt",
        "short",
        "support",
        "moving",
        "collision",
        "gap",
        "grip",
        "rack",
        "mixed_support",
        "light_support",
    ],
)
def test_false_plate_success_rejected(nominal, fault):
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
    elif fault == "rack":
        row["bare_table_contact"] = False
    elif fault == "mixed_support":
        row["rack_contact"] = True
    elif fault == "light_support":
        next(r for r in trace if r["stage"] == "transport")["any_support_contact"] = True
    else:
        next(r for r in trace if r["stage"] == "transport")["moving_jaw_normal_force_n"] = 0
    assert not score_plate(trace)["plate_success"]


@pytest.mark.parametrize("fault", ["missing_object", "skip_close"])
def test_fault_stops_before_transport_with_preserved_failure(tmp_path, fault):
    store = EvidenceStore(tmp_path)
    result = run_plate(PlateConfig(render=False, **{fault: True}), store=store, project_root=ROOT)
    assert result.outcome == "failed" and not result.metrics["plate_success"]
    assert not result.claims and "error.txt" in result.files
    trace = (store.directory(result.run_id) / "scoring-truth.jsonl").read_text()
    assert '"stage": "transport"' not in trace
    store.verify(result.run_id)


def test_unowned_arm_and_live_collision_stop():
    env = PlateEnvironment(PlateConfig(render=False))
    try:
        env.stage = "approach"
        action = env.parked.copy()
        action[6] += 0.1
        with pytest.raises(ValueError, match="does not own"):
            env.step(action, episode_id=env.episode_id, sequence=env.sequence)
        assert env.sequence == 0
        # Test-only disturbance: plate deeply overlaps the table. Production never does this.
        env.data.joint("plate/free").qpos[2] -= 0.055
        with pytest.raises(RuntimeError, match="penetration"):
            env.step(env.parked, episode_id=env.episode_id, sequence=env.sequence)
        assert not env.active and len(env.contact_trace) == 1
    finally:
        env.close()


def test_axis_solver_is_scratch_only_and_rejects_invalid_or_unreachable():
    from bimanual.plate import solve_axis

    env = PlateEnvironment(PlateConfig(render=False))
    try:
        before = env.data.qpos.copy()
        q = env.parked.copy()
        q[5] = 0.3
        solved = solve_axis(env, np.array([0.1, -0.08, 0.424]), q, [0, 0, 1])
        assert np.all(solved >= env.lower) and np.all(solved <= env.upper)
        np.testing.assert_array_equal(env.data.qpos, before)
        with pytest.raises(ReachError, match="finite"):
            solve_axis(env, np.array([np.nan, 0, 0]), q, [0, 0, 1])
        with pytest.raises(ReachError, match="shapes"):
            solve_axis(env, np.array([0, 0]), q, [0, 0, 1])
        bad = q.copy()
        bad[6] = env.upper[6] + 0.1
        with pytest.raises(ReachError, match="limits"):
            solve_axis(env, np.zeros(3), bad, [0, 0, 1])
        with pytest.raises(ReachError, match="column"):
            solve_axis(env, np.zeros(3), q, [0, 0, 1], column=3)
        with pytest.raises(ReachError, match="unreachable"):
            solve_axis(env, np.array([4, 4, 4]), q, [0, 0, 1])
    finally:
        env.close()


def test_interrupted_plate_preserves_partial_run(tmp_path, monkeypatch):
    original = PlateEnvironment.after_physics_step

    def interrupt(env):
        original(env)
        if len(env.contact_trace) == 7:
            raise KeyboardInterrupt()

    monkeypatch.setattr(PlateEnvironment, "after_physics_step", interrupt)
    store = EvidenceStore(tmp_path)
    result = run_plate(PlateConfig(render=False), store=store, project_root=ROOT)
    assert result.outcome == "interrupted" and result.metrics[
        "simulation_seconds"
    ] == pytest.approx(0.007)
    assert not result.metrics["plate_success"] and not result.claims
    store.verify(result.run_id)


@pytest.mark.render
def test_three_camera_plate_replay(tmp_path):
    from PIL import Image

    store = EvidenceStore(tmp_path)
    result = run_plate(PlateConfig(), store=store, project_root=ROOT)
    assert result.outcome == "completed", result.metrics
    with Image.open(store.directory(result.run_id) / "preview.png") as image:
        assert image.size == (1440, 300)
    with Image.open(store.directory(result.run_id) / "replay.gif") as image:
        assert image.n_frames > 50
    store.verify(result.run_id)


def test_unsupported_right_arm_is_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PlateConfig(arm="right")


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
def test_review_rejects_malformed_plate_trace(nominal, fault):
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
    result = score_plate(trace)
    assert not result["plate_success"] and not result["trace_valid"]
    assert result["invalid_trace_row"] == 1
