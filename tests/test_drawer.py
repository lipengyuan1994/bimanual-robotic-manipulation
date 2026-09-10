import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.drawer import DrawerConfig, DrawerEnvironment, run_drawer, score_drawer
from bimanual.evidence import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def nominal(tmp_path_factory):
    store = EvidenceStore(tmp_path_factory.mktemp("drawer"))
    result = run_drawer(DrawerConfig(render=False), store=store, project_root=ROOT)
    truth = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    return store, result, truth


def test_open_and_release_real_drawer_with_free_utensils(nominal):
    store, result, trace = nominal
    assert result.outcome == "completed", result.metrics
    assert result.metrics["drawer_success"]
    assert result.metrics["manipulation_success"] is None
    assert result.metrics["open_grasp_samples"] == 400
    assert result.metrics["released_open_samples"] == 400
    assert result.metrics["pull_grasp_samples"] == 1200
    assert result.metrics["utensils_retained"]
    assert 0.08 < result.metrics["final_opening_m"] < 0.11
    assert len(trace) == 4800
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    slide = model.joint("drawer/slide").id
    assert model.nu == 12 and model.neq == 0
    assert slide not in model.actuator_trnid[:, 0]
    assert model.jnt_type[slide] == mujoco.mjtJoint.mjJNT_SLIDE
    assert np.all(model.body_gravcomp == 0)
    for name in ("spoon/free", "fork/free"):
        assert model.joint(name).type[0] == mujoco.mjtJoint.mjJNT_FREE
    for name in ("cabinet_roof", "cabinet_floor", "drawer/floor", "drawer/back", "drawer/front"):
        assert model.geom(name).id >= 0
    rows = [json.loads(r) for r in (directory / "observations.jsonl").read_text().splitlines()]
    assert len(rows) == 481 and rows[-1]["action_target_rad"] is None
    assert all(
        not {"opening_m", "utensil_positions_m", "jaw_normal_force_n"}.intersection(row)
        for row in rows
    )
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault",
    ["short", "shut", "supported", "missing_utensil", "lost_grip", "collision", "limit", "timing"],
)
def test_false_drawer_success_rejected(nominal, fault):
    _, _, trace = nominal
    altered = copy.deepcopy(trace)
    row = next(r for r in altered if r["stage"] == "released_hold")
    if fault == "short":
        altered.pop()
    elif fault == "shut":
        row["opening_m"] = 0.07
    elif fault == "supported":
        row["jaw_normal_force_n"][0] = 0.1
    elif fault == "missing_utensil":
        row["utensil_positions_m"].pop("spoon")
    elif fault == "lost_grip":
        next(r for r in altered if r["stage"] == "pull")["jaw_normal_force_n"][0] = 0
    elif fault == "collision":
        altered[0]["forbidden_pairs"] = [["left/gripper", "cabinet_roof"]]
    elif fault == "limit":
        altered[0]["joint_limit_overtravel_m"] = 0.003
    else:
        row["simulation_seconds"] += 0.0001
    assert not score_drawer(altered)["drawer_success"]


@pytest.mark.parametrize("fault", ["missing_handle", "skip_close"])
def test_failed_attempt_stops_before_pull_and_is_sealed(tmp_path, fault):
    store = EvidenceStore(tmp_path)
    result = run_drawer(DrawerConfig(render=False, **{fault: True}), store=store, project_root=ROOT)
    assert result.outcome == "failed" and not result.metrics["drawer_success"]
    assert result.claims == [] and "error.txt" in result.files
    rows = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    assert not any(r["stage"] == "pull" for r in rows)
    store.verify(result.run_id)


def test_contact_and_right_arm_guards():
    env = DrawerEnvironment(DrawerConfig(render=False))
    try:
        action = env.home.copy()
        action[6] += 0.1
        with pytest.raises(ValueError, match="does not own"):
            env.step(action, episode_id=env.episode_id, sequence=env.sequence)
        assert env.sequence == 0
        assert env.allowed(("drawer/stem", next(iter(env.fingers[0]))))
        assert env.allowed(("spoon/shaft", "drawer/floor"))
        assert not env.allowed(("spoon/shaft", "cabinet_roof"))
        assert not env.allowed((next(iter(env.fingers[0])), "drawer/front"))
        # Test-only fault injection: disturb the passive drawer beyond its limit.
        env.data.joint("drawer/slide").qpos[0] = -0.02
        with pytest.raises(RuntimeError, match="Forbidden|overtravel"):
            env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
        assert not env.active and len(env.contact_trace) == 1
    finally:
        env.close()


def test_interrupted_drawer_preserves_partial_physics(tmp_path, monkeypatch):
    original = DrawerEnvironment.after_physics_step

    def interrupt(env):
        original(env)
        if len(env.contact_trace) == 10:
            raise KeyboardInterrupt()

    monkeypatch.setattr(DrawerEnvironment, "after_physics_step", interrupt)
    store = EvidenceStore(tmp_path)
    result = run_drawer(DrawerConfig(render=False), store=store, project_root=ROOT)
    assert result.outcome == "interrupted"
    assert not result.metrics["drawer_success"] and result.claims == []
    assert result.metrics["simulation_seconds"] == pytest.approx(0.05)
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "fault", ["initially_open", "net_short", "phase_order", "nonterminal", "pull_gap"]
)
def test_drawer_requires_closed_start_ordered_phases_and_terminal_release(nominal, fault):
    _, _, truth = nominal
    trace = copy.deepcopy(truth)
    if fault == "initially_open":
        trace[0]["opening_m"] = 0.002
    elif fault == "net_short":
        # Within the closed tolerance, but exactly8cm later is less than8cm net.
        trace[0]["opening_m"] = 0.001
        for row in trace:
            if row["stage"] in {"open_hold", "released_hold"}:
                row["opening_m"] = 0.08
    elif fault == "phase_order":
        early = [
            r
            for r in trace
            if r["stage"] not in {"pull", "open_hold", "release", "retreat", "released_hold"}
        ]
        held = [r for r in trace if r["stage"] == "open_hold"]
        pulled = [r for r in trace if r["stage"] == "pull"]
        late = [r for r in trace if r["stage"] in {"release", "retreat", "released_hold"}]
        trace = early + held + pulled + late
        for i, row in enumerate(trace):
            row["simulation_seconds"] = (i + 1) * 0.005
    elif fault == "nonterminal":
        row = copy.deepcopy(trace[-1])
        row["stage"] = "retreat"
        row["simulation_seconds"] += 0.005
        trace.append(row)
    else:
        next(r for r in reversed(trace) if r["stage"] == "close")["stage"] = "pull"
        [r for r in trace if r["stage"] == "pull"][500]["stage"] = "outside"
    assert not score_drawer(trace)["drawer_success"]
