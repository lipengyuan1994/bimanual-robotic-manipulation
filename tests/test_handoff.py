import copy
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from bimanual.evidence import EvidenceStore
from bimanual.handoff import (
    HandoffConfig,
    HandoffEnvironment,
    run_handoff,
    score_handoff,
    solve_fixed_roll,
)
from bimanual.teacher import ReachError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def nominal(tmp_path_factory):
    store = EvidenceStore(tmp_path_factory.mktemp("handoff"))
    result = run_handoff(HandoffConfig(render=False), store=store, project_root=ROOT)
    directory = store.directory(result.run_id)
    truth = [json.loads(r) for r in (directory / "scoring-truth.jsonl").read_text().splitlines()]
    return store, result, truth


def test_contact_handoff_is_independently_scored_and_replayable(nominal):
    store, result, truth = nominal
    assert result.outcome == "completed", result.metrics
    assert result.metrics["handoff_success"]
    assert result.metrics["manipulation_success"] is None
    assert result.metrics["donor_only_samples"] == 400
    assert result.metrics["shared_grasp_samples"] == 400
    assert result.metrics["receiver_only_samples"] == 400
    assert result.metrics["max_penetration_m"] <= 0.0025
    assert len(truth) == 6300
    assert store.verify(result.run_id).manifest_sha256 == result.manifest_sha256
    directory = store.directory(result.run_id)
    model = mujoco.MjModel.from_xml_path(str(directory / "scene.xml"))
    assert model.neq == 0 and model.nu == 12
    assert np.all(model.body_gravcomp == 0)
    rows = [json.loads(r) for r in (directory / "observations.jsonl").read_text().splitlines()]
    assert len(rows) == 631
    assert rows[-1]["action_target_rad"] is None
    forbidden_fields = {"object_position_m", "object_orientation_wxyz", "jaw_normal_force_n"}
    assert all(not forbidden_fields.intersection(row) for row in rows)


@pytest.mark.parametrize(
    "fault",
    ["donor_contact", "table", "single_jaw", "short", "timing", "collision", "transition_table"],
)
def test_false_transfer_cannot_pass(nominal, fault):
    _, _, truth = nominal
    altered = copy.deepcopy(truth)
    row = next(r for r in altered if r["stage"] == "receiver_hold")
    if fault == "donor_contact":
        row["jaw_normal_force_n"]["left"][0] = 0.02
    elif fault == "table":
        row["table_contact"] = True
    elif fault == "single_jaw":
        row["jaw_normal_force_n"]["right"][0] = 0
    elif fault == "short":
        altered.pop()
    elif fault == "transition_table":
        next(r for r in altered if r["stage"] == "right_close")["table_contact"] = True
    elif fault == "timing":
        row["simulation_seconds"] += 0.0001
    else:
        altered[0]["forbidden_pairs"] = [["left/fixed_jaw_box1", "workbench"]]
    assert not score_handoff(altered)["handoff_success"]


@pytest.mark.parametrize("fault", ["missing_object", "skip_receiver_close"])
def test_failed_handoff_retains_evidence_and_never_releases_donor(tmp_path, fault):
    store = EvidenceStore(tmp_path)
    result = run_handoff(
        HandoffConfig(render=False, **{fault: True}), store=store, project_root=ROOT
    )
    assert result.outcome == "failed"
    assert not result.metrics["handoff_success"]
    assert result.claims == []
    assert "error.txt" in result.files
    store.verify(result.run_id)
    rows = [
        json.loads(r)
        for r in (store.directory(result.run_id) / "scoring-truth.jsonl").read_text().splitlines()
    ]
    assert not any(r["stage"] == "left_release" for r in rows)
    if fault == "skip_receiver_close":
        assert result.metrics["donor_hold_passed"]
        assert not result.metrics["shared_hold_passed"]


def test_fixed_roll_ik_preserves_live_state_and_inactive_joints():
    env = HandoffEnvironment(HandoffConfig(render=False))
    try:
        before = env.data.qpos.copy()
        initial = env.home.copy()
        initial[[4, 10]] = 1.57
        result = solve_fixed_roll(env, [-0.075, 0, 0.46], initial, arm="left")
        np.testing.assert_array_equal(result[4:], initial[4:])
        np.testing.assert_array_equal(env.data.qpos, before)
        scratch = mujoco.MjData(env.model)
        scratch.qpos[:] = env.data.qpos
        scratch.qpos[env.qadr] = result
        mujoco.mj_forward(env.model, scratch)
        np.testing.assert_allclose(scratch.site("left/pinch").xpos, [-0.075, 0, 0.46], atol=0.0001)
        with pytest.raises(ReachError, match="unreachable"):
            solve_fixed_roll(env, [10, 0, 10], initial, arm="left")
        np.testing.assert_array_equal(env.data.qpos, before)
    finally:
        env.close()


def test_handoff_ownership_and_contact_guards():
    env = HandoffEnvironment(HandoffConfig(render=False))
    try:
        env.stage = "left_lift"
        action = env.home.copy()
        action[6] += 0.1
        before = env.data.qpos.copy()
        with pytest.raises(ValueError, match="does not own"):
            env.step(action, episode_id=env.episode_id, sequence=env.sequence)
        np.testing.assert_array_equal(env.data.qpos, before)
        # Inject table penetration only in test state, never operating code.
        address = env.model.jnt_qposadr[env.model.body_jntadr[env.model.body("practice_object").id]]
        env.data.qpos[address + 2] = 0.37
        with pytest.raises(RuntimeError, match="penetration"):
            env.step(env.home, episode_id=env.episode_id, sequence=env.sequence)
        assert not env.active and len(env.contact_trace) == 1
    finally:
        env.close()


def test_interrupted_handoff_seals_partial_attempt(tmp_path, monkeypatch):
    original = HandoffEnvironment.after_physics_step

    def interrupt(env):
        original(env)
        if len(env.contact_trace) == 20:
            raise KeyboardInterrupt()

    monkeypatch.setattr(HandoffEnvironment, "after_physics_step", interrupt)
    store = EvidenceStore(tmp_path)
    result = run_handoff(HandoffConfig(render=False), store=store, project_root=ROOT)
    assert result.outcome == "interrupted"
    assert result.claims == [] and not result.metrics["handoff_success"]
    assert result.metrics["simulation_seconds"] == pytest.approx(0.1)
    store.verify(result.run_id)
