import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.evidence import EvidenceStore
from bimanual.utensils import (
    UtensilConfig,
    UtensilEnvironment,
    run_utensils,
    score_utensils,
    solve_utensil_tip,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def nominal(tmp_path_factory):
    store = EvidenceStore(tmp_path_factory.mktemp("utensils"))
    result = run_utensils(UtensilConfig(render=False), store=store, project_root=ROOT)
    truth = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    return store, result, truth


def test_drawer_and_both_utensils_share_continuous_physics(nominal):
    store, result, truth = nominal
    assert result.outcome == "completed", result.metrics
    assert result.metrics["utensils_success"] and result.metrics["drawer_opened"]
    assert result.metrics["manipulation_success"] is None
    assert result.metrics["physics_hz"] == 1000 and result.metrics["control_hz"] == 20
    assert result.metrics["scene_variant"] == "ergonomic_flush_roof_v1"
    assert len(truth) == 94400
    for obj in ("spoon", "fork"):
        assert result.metrics[obj + "_placed"]
        assert result.metrics[obj + "_hold_samples"] == 2000
        assert result.metrics[obj + "_transport_samples"] == 7200
        assert result.metrics[obj + "_settled_samples"] == 2000
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    assert model.nu == 12 and model.neq == 0
    assert model.opt.timestep == 0.001
    assert model.joint("drawer/slide").id not in model.actuator_trnid[:, 0]
    assert np.all(model.body_gravcomp == 0)
    assert model.nmocap == 0
    assert np.allclose(model.geom("spoon/shaft").size, [0.006, 0.02, 0.006])
    assert np.allclose(model.geom("cabinet_roof").pos, [-0.014, -0.18, 0.433])
    for obj in ("spoon", "fork"):
        assert model.joint(obj + "/free").type[0] == mujoco.mjtJoint.mjJNT_FREE
    observations = [
        json.loads(r) for r in (directory / "observations.jsonl").read_text().splitlines()
    ]
    assert len(observations) == 1889 and observations[-1]["action_target_rad"] is None
    assert all(
        not {"objects", "opening_m", "jaw_normal_force_n"}.intersection(r) for r in observations
    )
    assert all(r["episode_id"] == observations[0]["episode_id"] for r in observations)
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault",
    [
        "gap",
        "phase_order",
        "nonterminal",
        "start_open",
        "drawer_closed",
        "lost_spoon",
        "supported_fork",
        "premature_lower_release",
        "not_released",
        "destination",
        "collision",
        "overlap",
        "missing_object",
    ],
)
def test_independent_scorer_rejects_false_completion(nominal, fault):
    _, _, original = nominal
    trace = list(original)
    stage = "fork_settled"
    if fault == "lost_spoon":
        stage = "spoon_transport"
    elif fault == "supported_fork":
        stage = "fork_transport"
    elif fault == "premature_lower_release":
        stage = "fork_lower"
    elif fault in {"start_open", "collision", "overlap"}:
        stage = "settle"
    index = next(i for i, row in enumerate(trace) if row["stage"] == stage)
    row = copy.deepcopy(trace[index])
    trace[index] = row
    if fault == "gap":
        trace.pop(index)
    elif fault == "phase_order":
        row["stage"] = "spoon_hold"
    elif fault == "nonterminal":
        row = copy.deepcopy(trace[-1])
        row["simulation_seconds"] += 0.001
        row["stage"] = "fork_retreat"
        trace.append(row)
    elif fault == "start_open":
        row["opening_m"] = 0.002
    elif fault == "drawer_closed":
        row["opening_m"] = 0.07
    elif fault == "lost_spoon":
        row["objects"]["spoon"]["jaw_normal_force_n"][0] = 0
    elif fault == "supported_fork":
        row["objects"]["fork"]["support"] = ["spoon/shaft"]
    elif fault == "premature_lower_release":
        row["objects"]["fork"]["jaw_normal_force_n"][0] = 0
    elif fault == "not_released":
        row["objects"]["fork"]["jaw_normal_force_n"][0] = 0.1
    elif fault == "destination":
        row["objects"]["fork"]["position_m"][0] = 0.2
    elif fault == "collision":
        row["forbidden_pairs"] = [["left/gripper", "cabinet_roof"]]
    elif fault == "overlap":
        row["max_penetration_m"] = 0.003
    elif fault == "missing_object":
        row["objects"].pop("spoon")
    assert not score_utensils(trace)["utensils_success"]


@pytest.mark.parametrize("name", ["spoon", "fork"])
def test_missing_object_is_absent_and_attempt_is_sealed(tmp_path, name):
    store = EvidenceStore(tmp_path)
    result = run_utensils(
        UtensilConfig(render=False, missing_object=name), store=store, project_root=ROOT
    )
    assert result.outcome == "failed" and not result.metrics["utensils_success"]
    assert result.claims == []
    assert "missing" in result.metrics["error"]
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) == -1
    assert (directory / "scoring-truth.jsonl").read_text() == ""
    store.verify(result.run_id)


@pytest.mark.parametrize("name", ["spoon", "fork"])
def test_skipped_closure_cannot_claim_placement(tmp_path, name):
    store = EvidenceStore(tmp_path)
    result = run_utensils(
        UtensilConfig(render=False, skip_close=name), store=store, project_root=ROOT
    )
    assert result.outcome == "failed" and not result.metrics["utensils_success"]
    assert result.metrics["drawer_opened"] and result.claims == []
    assert "grasp not established" in result.metrics["error"]
    rows = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    assert rows[-1]["stage"] == name + "_close"
    assert not any(r["stage"] == name + "_lift" for r in rows)
    store.verify(result.run_id)


def test_guards_and_inverse_kinematics_do_not_mutate_live_objects():
    env = UtensilEnvironment(UtensilConfig(render=False))
    try:
        action = env.home.copy()
        action[6] += 0.1
        with pytest.raises(ValueError, match="does not own"):
            env.step(action, episode_id=env.episode_id, sequence=env.sequence)
        assert env.sequence == 0
        qpos = env.data.qpos.copy()
        with pytest.raises(ValueError):
            solve_utensil_tip(env, [9, 9, 9], env.home, arm="left")
        assert np.array_equal(qpos, env.data.qpos)
        assert not np.any(env.data.qfrc_applied) and not np.any(env.data.xfrc_applied)
        env.active_utensil = "spoon"
        assert env.allowed((next(iter(env.fingers[0])), "spoon/shaft"))
        assert not env.allowed((next(iter(env.fingers[0])), "fork/shaft"))
        env.data.joint("drawer/slide").qpos[0] = -0.02
        with pytest.raises(RuntimeError, match="Forbidden|overtravel"):
            env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
        assert not env.active and len(env.contact_trace) == 1
    finally:
        env.close()


def test_interruption_retains_partial_physics(tmp_path, monkeypatch):
    original = UtensilEnvironment.after_physics_step

    def interrupt(env):
        original(env)
        if len(env.contact_trace) == 10:
            raise KeyboardInterrupt()

    monkeypatch.setattr(UtensilEnvironment, "after_physics_step", interrupt)
    store = EvidenceStore(tmp_path)
    result = run_utensils(UtensilConfig(render=False), store=store, project_root=ROOT)
    assert result.outcome == "interrupted" and not result.metrics["utensils_success"]
    assert result.metrics["simulation_seconds"] == pytest.approx(0.01)
    assert not result.claims
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_idle_object",
        "nan_force",
        "nan_overlap",
        "negative_force",
        "negative_overlap",
        "negative_overtravel",
        "pose_shape",
        "velocity_shape",
        "quaternion_shape",
        "jaw_shape",
        "nonfinite_velocity",
        "nonnumeric_time",
        "spoon_moved_after_fork",
        "spoon_supported_after_fork",
    ],
)
def test_review_rejects_incomplete_or_nonfinite_evidence(nominal, fault):
    _, _, original = nominal
    trace = list(original)
    final_spoon = fault in {"spoon_moved_after_fork", "spoon_supported_after_fork"}
    index = next(
        i
        for i, row in enumerate(trace)
        if row["stage"] == ("fork_settled" if final_spoon else "spoon_transport")
    )
    row = copy.deepcopy(trace[index])
    trace[index] = row
    obj = row["objects"]["spoon"]
    if fault == "missing_idle_object":
        row["objects"].pop("fork")
    elif fault == "nan_force":
        obj["jaw_normal_force_n"][1] = float("nan")
    elif fault == "nan_overlap":
        row["max_penetration_m"] = float("nan")
    elif fault == "negative_force":
        row["objects"]["fork"]["jaw_normal_force_n"][1] = -1
    elif fault == "negative_overlap":
        row["max_penetration_m"] = -0.001
    elif fault == "negative_overtravel":
        row["joint_limit_overtravel_m"] = -0.001
    elif fault == "pose_shape":
        obj["position_m"].pop()
    elif fault == "velocity_shape":
        obj["velocity"].pop()
    elif fault == "quaternion_shape":
        obj["quaternion_wxyz"].pop()
    elif fault == "jaw_shape":
        obj["jaw_normal_force_n"].append(0)
    elif fault == "nonfinite_velocity":
        obj["velocity"][4] = float("inf")
    elif fault == "nonnumeric_time":
        row["simulation_seconds"] = "invalid"
    elif fault == "spoon_moved_after_fork":
        obj["position_m"][0] = 0.2
    elif fault == "spoon_supported_after_fork":
        obj["support"].append("fork/shaft")
    result = score_utensils(trace)
    assert not result["utensils_success"]
    if not final_spoon:
        assert not result["trace_valid"] and result["invalid_trace_row"] == index
