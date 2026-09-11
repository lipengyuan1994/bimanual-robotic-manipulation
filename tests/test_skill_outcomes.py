"""Synthetic physical evidence fixtures; these tests do not execute a robot or policy."""

import copy

import pytest
from test_dinner_scoring import LAYOUT, row_for

from bimanual.dinner_outcomes import CARRY_SAMPLES
from bimanual.skill_outcomes import SkillOutcomeMonitor


def monitor(skill="cup_pick_place", **kwargs):
    return SkillOutcomeMonitor(
        skill,
        episode_id="episode",
        initial_sequence=0,
        initial_simulation_seconds=0.0,
        layout=LAYOUT,
        **kwargs,
    )


def action(sequence=0):
    return dict(
        episode_id="episode",
        observation_sequence=sequence,
        simulation_seconds_before=sequence / 20,
        simulation_seconds_after=(sequence + 1) / 20,
        targets_rad=[0.0] * 12,
        applied=True,
        partial_physics=False,
    )


def base(target="cup"):
    row = row_for("ignored")
    row.pop("phase")
    row["objects"][target]["pos"][0] -= 0.1
    return row


def consume(monitor, row, *, change=None):
    seq = monitor.snapshot().counters["actions"]
    batch = []
    for i in range(50):
        sample = copy.deepcopy(row)
        sample["t"] = seq / 20 + (i + 1) / 1000
        batch.append(sample)
    proposal = action(seq)
    if change:
        change(proposal, batch)
    return monitor.consume(proposal, batch)


@pytest.mark.parametrize(
    "skill,target",
    [
        ("cup_pick_place", "cup"),
        ("plate_pick_place", "plate"),
        ("spoon_retrieve_place", "spoon"),
        ("fork_retrieve_place", "fork"),
        ("bar_place_and_return", "practice_object"),
    ],
)
def test_contact_carry_and_two_seconds_release_required(skill, target):
    m, row = monitor(skill), base(target)
    destination = row_for("ignored")["objects"][target]["pos"]
    arm = "right" if target in ("cup", "practice_object") else "left"
    obj = row["objects"][target]
    obj["support"] = []
    obj["forces"][arm] = [1.0, 1.0]
    obj["pos"][2] = 0.48
    if target in ("spoon", "fork"):
        row["opening"] = 0.1
    count = 12000 if target == "practice_object" else CARRY_SAMPLES[target]
    for tick in range(count // 50):
        obj["pos"][0] = destination[0] - 0.1 + 0.1 * tick / (count // 50 - 1)
        assert consume(m, row).state == "pending"
    obj["pos"] = destination
    obj["forces"][arm] = [0.0, 0.0]
    obj["support"] = ["workbench"]
    for _ in range(39):
        assert consume(m, row).state == "pending"
    result = consume(m, row)
    assert result.state == "succeeded" and result.counters["released_samples"] == 2000
    assert result.report()["successor_start_ready"] is None
    assert result.report()["independent_task_success"] is None
    with pytest.raises(TypeError):
        result.counters["actions"] = 0
    with pytest.raises(RuntimeError, match="terminal"):
        consume(m, row)


def test_handoff_requires_ordered_donor_shared_receiver_holds():
    m, row = monitor("handoff_transfer"), base("practice_object")
    bar = row["objects"]["practice_object"]
    bar["support"] = []
    for arms in (("left",), ("left", "right"), ("right",)):
        bar["forces"] = {
            arm: [1.0, 1.0] if arm in arms else [0.0, 0.0] for arm in ("left", "right")
        }
        for _ in range(40):
            result = consume(m, row)
    assert result.state == "succeeded" and result.counters["handoff_stage"] == 3
    assert result.counters["receiver_samples"] == 2000


def test_drawer_requires_driven_open_and_released_hold():
    m, row = monitor("drawer_open"), row_for("labels do not matter")
    row["drawer_forces"] = [1.0, 1.0]
    for i in range(120):
        row["opening"] = 0.1 * i / 119
        assert consume(m, row).state == "pending"
    for _ in range(40):
        assert consume(m, row).state == "pending"
    row["drawer_forces"] = [0.0, 0.0]
    for _ in range(39):
        assert consume(m, row).state == "pending"
    assert consume(m, row).state == "succeeded"


@pytest.mark.parametrize(
    "change",
    [
        lambda a, b: a.update(episode_id="other"),
        lambda a, b: a.update(observation_sequence=1),
        lambda a, b: a.update(applied=False),
        lambda a, b: a.update(partial_physics=True),
        lambda a, b: a.update(simulation_seconds_after=0.1),
        lambda a, b: b.pop(),
        lambda a, b: b.append(copy.deepcopy(b[-1])),
        lambda a, b: b[20].update(t=0.9),
        lambda a, b: b[20].update(overlap=float("nan")),
        lambda a, b: b[20]["objects"]["cup"].update(vel=[0.0]),
        lambda a, b: b[-1].update(bad=[["arm", "table"]]),
    ],
)
def test_bad_physics_or_actions_latch_failure(change):
    m = monitor()
    assert consume(m, base(), change=change).state == "failed"
    with pytest.raises(RuntimeError, match="terminal"):
        consume(m, base())


@pytest.mark.parametrize("fault", ["preplaced", "protected", "wrong_arm", "foreign_object"])
def test_prerequisites_and_ownership_cannot_be_inferred(fault):
    m, row = monitor(), base()
    if fault == "preplaced":
        row = row_for("model says complete")
    elif fault == "protected":
        row["objects"]["practice_object"]["pos"][0] += 0.2
    elif fault == "wrong_arm":
        row["objects"]["cup"]["forces"]["left"] = [1.0, 1.0]
    else:
        row["objects"]["fork"]["forces"]["right"] = [1.0, 1.0]
    assert consume(m, row).state == "failed"


def test_time_and_model_labels_cannot_claim_success():
    m, row = monitor(max_actions=2), base()
    row["phase"], row["success"] = "cup/settled", True
    assert consume(m, row).state == "pending"
    result = consume(m, row)
    assert result.state == "failed" and "budget" in result.reason


def test_open_drawer_retry_and_unavailable_handoff_history_are_not_successes():
    row = row_for("ignored")
    row["opening"] = 0.1
    assert consume(monitor("drawer_open"), row).state == "failed"
    assert consume(monitor("bar_place_and_return"), row).state == "failed"
    row["opening"] = 0
    assert consume(monitor("spoon_retrieve_place"), row).state == "failed"


def test_inactive_command_cannot_change_after_first_confirmed_action():
    m, row = monitor(), base()
    assert consume(m, row).state == "pending"
    result = consume(m, row, change=lambda a, b: a["targets_rad"].__setitem__(0, 0.2))
    assert result.state == "failed" and "unowned arm" in result.reason


def test_nonzero_episode_origin_requires_matching_sequence_and_time():
    with pytest.raises(ValueError):
        SkillOutcomeMonitor(
            "cup_pick_place",
            episode_id="e",
            initial_sequence=100,
            initial_simulation_seconds=0.0,
            layout=LAYOUT,
        )
    with pytest.raises(ValueError):
        monitor(max_actions=True)


def test_handoff_cannot_reuse_hold_after_loss_inside_final_control_step():
    m, row = monitor("handoff_transfer"), base("practice_object")
    bar = row["objects"]["practice_object"]
    bar["support"] = []
    for arms in (("left",), ("left", "right")):
        bar["forces"] = {
            arm: [1.0, 1.0] if arm in arms else [0.0, 0.0] for arm in ("left", "right")
        }
        for _ in range(40):
            assert consume(m, row).state == "pending"
    bar["forces"] = dict(left=[0.0, 0.0], right=[1.0, 1.0])

    def initial_shared(a, batch):
        for sample in batch[:10]:
            sample["objects"]["practice_object"]["forces"]["left"] = [1.0, 1.0]

    assert consume(m, row, change=initial_shared).state == "pending"
    for _ in range(39):
        assert consume(m, row).state == "pending"

    def lose_last(a, batch):
        batch[-1]["objects"]["practice_object"]["forces"]["right"] = [0.0, 0.0]

    result = consume(m, row, change=lose_last)
    assert result.state == "failed" and "Receiver grip lost" in result.reason
