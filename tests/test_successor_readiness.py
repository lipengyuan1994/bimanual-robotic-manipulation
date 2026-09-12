"""Sealed synthetic source and sampled physics fixtures, never learned manipulation."""

import copy
import json
from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
from types import MappingProxyType

import pytest
from test_contracts import observation
from test_dinner_scoring import LAYOUT, row_for
from test_skill_views import synthetic_export  # noqa: F401

from bimanual.contracts import JointLimits, Observation
from bimanual.skill_outcomes import SkillOutcome
from bimanual.skill_views import create_skill_views
from bimanual.successor_readiness import SuccessorReadinessMonitor, load_successor_reference


@pytest.fixture(scope="module")
def references(synthetic_export, tmp_path_factory):  # noqa: F811
    path = tmp_path_factory.mktemp("readiness") / "views.json"
    create_skill_views(synthetic_export, path)

    @lru_cache
    def load(skill="cup_pick_place", final_parking=False):
        return load_successor_reference(
            synthetic_export, path, skill_id=skill, final_parking=final_parking
        )

    return load


def succeeded():
    return SkillOutcome("succeeded", "Physical fixture passed", MappingProxyType({"actions": 40}))


def setup_monitor(references, skill="cup_pick_place", *, final_parking=False, **kwargs):
    clock = [100]
    reference = references(skill, final_parking)
    monitor = SuccessorReadinessMonitor(
        reference,
        attempt_id="attempt",
        physical_success=succeeded(),
        initial_observation=Observation.model_validate(observation()),
        layout=LAYOUT,
        limits=reference.joint_limits,
        clock_ns=lambda: clock[0],
        **kwargs,
    )
    return monitor, clock


def consume(monitor, clock, *, joint_error=0.0, speed=0.0, change=None):
    seq = monitor.snapshot().counters["actions"]
    q = list(monitor.reference.joint_position_rad)
    q[11] += joint_error  # Include the auxiliary/inactive arm and gripper.
    obs = observation(seq + 1, joint_position_rad=q, joint_velocity_rad_s=[speed] * 12)
    clock[0] = obs["observed_monotonic_ns"]
    action = dict(
        attempt_id="attempt",
        episode_id=obs["episode_id"],
        observation_sequence=seq,
        simulation_seconds_before=seq / 20,
        simulation_seconds_after=(seq + 1) / 20,
        targets_rad=q,
        applied=True,
        partial_physics=False,
    )
    row = row_for("ignored")
    if monitor.reference.skill_id == "handoff_transfer":
        row["objects"]["practice_object"]["forces"]["right"] = [1.0, 1.0]
        row["objects"]["practice_object"]["support"] = []
    if monitor.reference.skill_id in ("drawer_open", "spoon_retrieve_place", "fork_retrieve_place"):
        row["opening"] = 0.1
    batch = []
    for i in range(50):
        sample = copy.deepcopy(row)
        sample["t"] = seq / 20 + (i + 1) / 1000
        sample["joint_position"] = q.copy()
        batch.append(sample)
    if change:
        change(action, batch, obs, clock)
    return monitor.consume(action, batch, Observation.model_validate(obs))


def test_reference_is_measured_entry_not_teacher_action_and_is_immutable(references):
    ref = references()
    assert ref.reference_frame == 2089 and ref.successor_skill_id == "plate_pick_place"
    assert ref.parent_episode_id == "episode-1" and ref.joint_position_rad == (0.0,) * 12
    original = json.loads(
        (ref.dataset_root / "raw_sources/000000/demonstration/episode.json").read_text()
    )
    assert tuple(original["frames"][2089]["action_rad"]) != ref.joint_position_rad
    assert ref.reverify() == ref
    assert ref.report()["operating_action_target"] is False
    with pytest.raises(FrozenInstanceError):
        ref.skill_id = "other"
    forged = replace(ref, joint_position_rad=(0.1,) * 12)
    with pytest.raises(ValueError, match="verified"):
        SuccessorReadinessMonitor(
            forged,
            attempt_id="attempt",
            physical_success=succeeded(),
            initial_observation=Observation.model_validate(observation()),
            layout=LAYOUT,
            limits=ref.joint_limits,
            clock_ns=lambda: 100,
        )


def test_reference_source_change_rejected_before_execution(references, tmp_path):
    ref = references()
    changed_views = tmp_path / "views.json"
    changed_views.write_text(ref.skill_views_path.read_text().replace('"manifest_sha256":', '"x":'))
    with pytest.raises(ValueError):
        load_successor_reference(ref.dataset_root, changed_views, skill_id=ref.skill_id)


def test_ten_new_observations_and_all_five_hundred_samples_required(references):
    monitor, clock = setup_monitor(references)
    for _ in range(9):
        assert consume(monitor, clock).state == "pending"
    result = consume(monitor, clock)
    assert result.state == "ready" and result.counters["physics_rows"] == 500
    assert result.report()["physical_success"] is True
    assert result.report()["successor_start_ready"] is True
    assert result.report()["independent_task_success"] is None
    with pytest.raises(TypeError):
        result.counters["physics_rows"] = 0
    with pytest.raises(RuntimeError, match="terminal"):
        consume(monitor, clock)


@pytest.mark.parametrize("excursion", [dict(joint_error=0.00501), dict(speed=0.02001)])
def test_joint_or_speed_excursion_resets_readiness_count_without_claiming_failure(
    references, excursion
):
    monitor, clock = setup_monitor(references)
    for _ in range(9):
        consume(monitor, clock)
    result = consume(monitor, clock, **excursion)
    assert result.state == "pending" and result.counters["consecutive_observations"] == 0
    for _ in range(9):
        assert consume(monitor, clock).state == "pending"
    assert consume(monitor, clock).state == "ready"


@pytest.mark.parametrize(
    "fault",
    [
        "attempt",
        "episode",
        "revision",
        "sequence",
        "stale",
        "time",
        "partial",
        "missing",
        "extra",
        "sample_gap",
        "sample_limit",
        "action_limit",
        "final_joint",
        "contact_middle",
        "placed_middle",
        "jaw_middle",
        "drawer_middle",
        "reused_pixels",
    ],
)
def test_invalid_evidence_latches_failure_preserving_physical_milestone(references, fault):
    monitor, clock = setup_monitor(references)

    def change(action, rows, obs, now):
        if fault == "attempt":
            action["attempt_id"] = "other"
        elif fault == "episode":
            action["episode_id"] = "other"
        elif fault == "revision":
            obs["instruction_revision"] = 1
        elif fault == "sequence":
            action["observation_sequence"] = 5
        elif fault == "stale":
            now[0] += 2_000_000_001
        elif fault == "time":
            action["simulation_seconds_after"] += 0.001
        elif fault == "partial":
            action["partial_physics"] = True
        elif fault == "missing":
            rows.pop()
        elif fault == "extra":
            rows.append(copy.deepcopy(rows[-1]))
        elif fault == "sample_gap":
            rows[24]["t"] += 0.001
        elif fault == "sample_limit":
            rows[24]["joint_position"][11] = 10.1
        elif fault == "action_limit":
            action["targets_rad"][0] = 10.1
        elif fault == "final_joint":
            rows[-1]["joint_position"][2] += 0.01
        elif fault == "contact_middle":
            rows[24]["bad"] = [["jaw", "table"]]
        elif fault == "placed_middle":
            rows[24]["objects"]["cup"]["pos"][0] += 0.1
        elif fault == "jaw_middle":
            rows[24]["objects"]["fork"]["forces"]["left"] = [1.0, 1.0]
        elif fault == "drawer_middle":
            rows[24]["drawer_forces"] = [1.0, 1.0]
        else:
            for index, frame in enumerate(obs["frames"]):
                frame["artifact"]["path"] = f"frame-0-{index}.png"

    result = consume(monitor, clock, change=change)
    assert result.state == "failed" and result.report()["physical_success"] is True
    assert result.report()["successor_start_ready"] is False
    with pytest.raises(RuntimeError, match="terminal"):
        consume(monitor, clock)


def test_handoff_receiver_grip_loss_between_observations_is_terminal(references):
    monitor, clock = setup_monitor(references, "handoff_transfer")

    def change(action, rows, obs, now):
        rows[24]["objects"]["practice_object"]["forces"]["right"][0] = 0.0

    result = consume(monitor, clock, change=change)
    assert result.state == "failed" and "grip" in result.reason


def test_open_drawer_loss_between_observations_is_terminal(references):
    monitor, clock = setup_monitor(references, "drawer_open")

    def change(action, rows, obs, now):
        rows[24]["opening"] = 0.079

    assert consume(monitor, clock, change=change).state == "failed"


def test_final_parking_is_explicit_and_never_a_successor(references):
    with pytest.raises(ValueError, match="Final fork"):
        references("fork_retrieve_place")
    with pytest.raises(ValueError, match="Final fork"):
        references("cup_pick_place", True)
    monitor, clock = setup_monitor(references, "fork_retrieve_place", final_parking=True)
    for _ in range(10):
        result = consume(monitor, clock)
    assert result.state == "ready"
    assert result.report()["successor_start_ready"] is None
    assert result.report()["final_parking_ready"] is True


def test_cannot_start_without_physical_success_or_changed_limits(references):
    ref = references()
    kwargs = dict(
        attempt_id="attempt",
        initial_observation=Observation.model_validate(observation()),
        layout=LAYOUT,
        limits=ref.joint_limits,
        clock_ns=lambda: 100,
    )
    with pytest.raises(ValueError, match="physical success"):
        SuccessorReadinessMonitor(
            ref, physical_success=SkillOutcome("pending", "pending", {}), **kwargs
        )
    kwargs["limits"] = JointLimits(lower_rad=[-9.0] * 12, upper_rad=[9.0] * 12)
    with pytest.raises(ValueError, match="limits"):
        SuccessorReadinessMonitor(ref, physical_success=succeeded(), **kwargs)


def test_timeout_does_not_erase_physical_success_or_invent_readiness(references):
    monitor, _ = setup_monitor(references)
    result = monitor.fail("Original attempt deadline expired")
    assert result.state == "failed" and result.physical_success
    assert result.report()["successor_start_ready"] is False
