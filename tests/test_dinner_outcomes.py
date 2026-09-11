"""Deterministic physical-summary fixtures, not simulated or learned successes."""

import pytest
from test_dinner_scoring import LAYOUT, row_for

from bimanual.dinner_outcomes import CARRY_SAMPLES, score_dinner_outcomes

META = dict(
    physics_hz=1000, object_state_edits=0, artificial_attachments=0, external_object_force_samples=0
)


def samples(*, fault=None):
    row = row_for("ignored")
    row.pop("phase")
    row["opening"] = 0.0
    tick = 0

    def emit(count):
        nonlocal tick
        for _ in range(count):
            tick += 1
            row["t"] = tick / 1000
            value = dict(row)  # Scorer consumes rows immediately and never mutates them.
            if fault == "gap" and tick == 100:
                value["t"] += 0.001
            elif fault == "nan" and tick == 100:
                value["overlap"] = float("nan")
            elif fault == "forbidden" and tick == 100:
                value["bad"] = [["arm", "table"]]
            elif fault == "labels":
                value["phase"] = "a false success claim"
                value["full_workflow_success"] = True
            yield value

    yield from emit(50)
    bar = row["objects"]["practice_object"]
    bar["pos"][0] -= 0.1
    bar["pos"][2] = 0.48
    bar["support"] = []
    for arms in (("left",), ("left", "right")):
        bar["forces"] = {
            arm: [1.0, 1.0] if arm in arms else [0.0, 0.0] for arm in ("left", "right")
        }
        if fault == "missing_handoff" and len(arms) == 2:
            bar["forces"]["right"] = [0.0, 0.0]
        yield from emit(2000)
    for name in ("practice_object", "cup", "plate", "spoon", "fork"):
        if name == "spoon":
            row["drawer_forces"] = [0.0, 0.0] if fault == "drawer_no_contact" else [1.0, 1.0]
            for i in range(6000):
                row["opening"] = 0.1 * i / 5999
                yield from emit(1)
            yield from emit(2000)
            row["drawer_forces"] = [0.0, 0.0]
            yield from emit(2000)
        obj = row["objects"][name]
        destination = row_for("ignored")["objects"][name]["pos"]
        arm = "right" if name in ("cup", "practice_object") else "left"
        obj["support"] = []
        obj["forces"] = {a: [1.0, 1.0] if a == arm else [0.0, 0.0] for a in ("left", "right")}
        count = CARRY_SAMPLES[name]
        for i in range(count):
            obj["pos"] = [destination[0] - 0.1 + 0.1 * i / (count - 1), destination[1], 0.48]
            if fault == "artificial_placement" and name == "plate":
                obj["forces"][arm] = [0.0, 0.0]
            yield from emit(1)
        obj["pos"] = destination
        obj["support"] = ["workbench"]
        obj["forces"] = {a: [0.0, 0.0] for a in ("left", "right")}
        if fault == "no_release" and name == "cup":
            obj["forces"][arm] = [1.0, 1.0]
        yield from emit(1950 if fault == "short_final" and name == "fork" else 2000)
        if fault == "disturbed" and name == "cup":
            row["objects"]["practice_object"]["pos"][0] += 0.1
    if fault == "short_final":
        return
    yield from emit(50)


# 50 reset + handoff donor/shared + carries + five releases + drawer + 50 trailing hold.
TOTAL = 50 + 4000 + sum(CARRY_SAMPLES.values()) + 10000 + 10000 + 50


def actions(count=TOTAL // 50, fault=None):
    for index in range(count):
        value = dict(
            episode_id="fixture",
            observation_sequence=index,
            simulation_seconds_before=index / 20,
            simulation_seconds_after=(index + 1) / 20,
            targets_rad=[0.0] * 12,
            applied=True,
            partial_physics=False,
        )
        if index == 1:
            if fault in ("applied", "partial_physics"):
                value[fault] = fault == "partial_physics"
            elif fault == "episode_id":
                value[fault] = "other"
            elif fault == "observation_sequence":
                value[fault] += 1
            elif fault == "targets_rad":
                value[fault][0] = float("nan")
        yield value


def score(fault=None, **kwargs):
    return score_dinner_outcomes(
        samples(fault=fault), LAYOUT, metadata=META, actions=kwargs.get("actions", actions())
    )


def test_label_free_positive_contract_and_ignored_labels():
    result = score()
    assert result["independent_task_success"], result["failed_gates"]
    assert result["physics_rows"] == TOTAL and result["handoff_stage"] == 3
    assert result["complete_action_coverage"]
    assert score("labels")["independent_task_success"]


@pytest.mark.parametrize(
    "fault,gate",
    [
        ("missing_handoff", "ordered_contact_handoff"),
        ("artificial_placement", "plate:contact_transport"),
        ("no_release", "cup:released_placement"),
        ("gap", "continuous_1khz"),
        ("nan", "valid_rows"),
        ("forbidden", "zero_forbidden_contacts"),
        ("disturbed", "practice_object:placement_disturbed"),
        ("drawer_no_contact", "drawer_opened_by_contact"),
    ],
)
def test_failed_physics_cannot_be_rescued_by_labels(fault, gate):
    result = score(fault)
    assert not result["independent_task_success"] and gate in result["failed_gates"]


@pytest.mark.parametrize(
    "fault", ["applied", "partial_physics", "episode_id", "observation_sequence", "targets_rad"]
)
def test_action_confirmation_and_identity_required(fault):
    result = score(actions=actions(fault=fault))
    assert not result["independent_task_success"] and not result["valid_actions"]


@pytest.mark.parametrize("count", [0, TOTAL // 50 - 1, TOTAL // 50 + 1])
def test_complete_physics_action_coverage_required(count):
    result = score(actions=actions(count))
    assert not result["independent_task_success"] and not result["complete_action_coverage"]


def test_intervention_metadata_required_even_if_contact_summaries_look_good():
    for key in ("object_state_edits", "artificial_attachments", "external_object_force_samples"):
        result = score_dinner_outcomes([], LAYOUT, metadata=META | {key: 1}, actions=[])
        assert not result["independent_task_success"] and "input_error" in result["failed_gates"]


def test_full_duration_terminal_hold_required_with_complete_actions():
    result = score("short_final", actions=actions(TOTAL // 50 - 2))
    assert result["complete_action_coverage"]
    assert not result["independent_task_success"]
    assert result["terminal_all_placed_samples"] == 1950
    assert "terminal_all_placed_2000" in result["failed_gates"]
