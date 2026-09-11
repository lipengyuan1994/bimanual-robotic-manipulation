import copy
import itertools

import pytest

from bimanual.dinner_scoring import score_dinner

LAYOUT = {
    "bar_destination_m": [0.025, 0.21, 0.391],
    "plate_destination_m": [0.14, -0.015, 0.378],
    "plate_source_m": [0.0, 0.3, 0.413],
    "plate_transport_clearance_tool_m": [0.04, 0.02, 0.48],
}
PHASES = [
    ("handoff/left_hold", 2000),
    ("handoff/both_hold", 2000),
    ("handoff/receiver_hold", 2000),
    ("handoff/bar_transport", 12000),
    ("handoff/bar_settled", 2000),
    ("cup/hold", 2000),
    ("cup/transport", 3000),
    ("cup/settled", 2000),
    ("plate/hold", 2000),
    ("plate/transport_clearance", 2000),
    ("plate/transport", 3000),
    ("plate/settled", 2000),
    ("utensils/pull", 6000),
    ("utensils/open_hold", 2000),
    ("utensils/released_hold", 2000),
    *[
        (f"utensils/{name}_{phase}", count)
        for name in ("spoon", "fork")
        for phase, count in (
            ("hold", 2000),
            ("clearance", 3000),
            ("transport", 7200),
            ("lower", 3000),
            ("settled", 2000),
        )
    ],
]
TOTAL = sum(count for _, count in PHASES)


def row_for(phase, t=0.001):
    positions = {
        "spoon": [-0.12, 0.045, 0.391],
        "fork": [-0.06, 0.062, 0.391],
        "cup": [0.066, 0.153, 0.378],
        "plate": [0.14, -0.015, 0.378],
        "practice_object": [0.025, 0.21, 0.391],
    }
    objects = {
        name: {
            "pos": pos,
            "quat": [1.0, 0.0, 0.0, 0.0],
            "vel": [0.0] * 6,
            "upright": 1.0,
            "forces": {"left": [0.0, 0.0], "right": [0.0, 0.0]},
            "support": ["workbench"],
        }
        for name, pos in positions.items()
    }
    active = None
    arms = []
    if phase in (
        "handoff/left_hold",
        "handoff/both_hold",
        "handoff/receiver_hold",
        "handoff/bar_transport",
    ):
        active = "practice_object"
        arms = ["left"] if phase.endswith("left_hold") else ["right"]
        if phase.endswith("both_hold"):
            arms = ["left", "right"]
    elif phase in ("cup/hold", "cup/transport"):
        active, arms = "cup", ["right"]
    elif phase in ("plate/hold", "plate/transport_clearance", "plate/transport"):
        active, arms = "plate", ["left"]
    elif phase.startswith(("utensils/spoon_", "utensils/fork_")) and not phase.endswith("settled"):
        active, arms = phase.split("/")[1].split("_")[0], ["left"]
    if active:
        objects[active]["support"] = []
        objects[active]["pos"][2] = 0.48
        for arm in arms:
            objects[active]["forces"][arm] = [1.0, 1.0]
    return {
        "t": t,
        "phase": phase,
        "opening": 0.1 if phase.startswith("utensils/") else 0.0,
        "overtravel": 0.0,
        "contacts": [],
        "bad": [],
        "overlap": 0.0,
        "drawer_forces": [1.0, 1.0]
        if phase in ("utensils/pull", "utensils/open_hold")
        else [0.0, 0.0],
        "objects": objects,
        "joint_position": [0.0] * 12,
    }


def rows():
    index = 0
    for phase, count in PHASES:
        row = row_for(phase)
        for _ in range(count):
            index += 1
            row["t"] = index / 1000
            yield row


def actions():
    index = 0
    for phase, count in PHASES:
        for _ in range(count // 50):
            yield {"t": index / 20, "phase": phase, "q": [0.0] * 12, "episode_id": "fixture"}
            index += 1


def score(physics=None, commands=None, layout=None):
    return score_dinner(
        rows() if physics is None else physics,
        actions() if commands is None else commands,
        LAYOUT if layout is None else layout,
    )


def test_complete_raw_trace_satisfies_physical_gates():
    result = score()
    assert result["full_workflow_success"], result["failed_gates"]
    assert result["physics_rows"] == TOTAL
    assert result["applied_actions"] * 50 == TOTAL
    assert result["terminal_all_placed_samples"] == 2000
    assert all(obj["placed"] for obj in result["final_objects"].values())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(overlap=float("nan")),
        lambda r: r.update(overtravel=-0.1),
        lambda r: r.update(opening=float("inf")),
        lambda r: r.update(joint_position=[0.0] * 11),
        lambda r: r.update(drawer_forces=[0.0, -1.0]),
        lambda r: r.update(contacts=["not a pair"]),
        lambda r: r["objects"]["fork"].update(pos=[0.0, 0.0]),
        lambda r: r["objects"]["cup"].update(quat=[1.0, 0.0, 0.0]),
        lambda r: r["objects"]["plate"].update(vel=[0.0] * 7),
        lambda r: r["objects"]["spoon"].update(support="workbench"),
        lambda r: r["objects"]["cup"]["forces"].update(left=[float("nan"), 0.0]),
        lambda r: r["objects"].pop("cup"),
    ],
)
def test_invalid_any_object_or_idle_sensor_is_rejected(mutation):
    row = row_for("handoff/left_hold")
    mutation(row)
    result = score([row], itertools.islice(actions(), 1))
    assert not result["full_workflow_success"]
    assert "valid_rows" in result["failed_gates"]
    assert result["first_invalid_row"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"q": [0.0] * 11},
        {"q": [float("nan")] * 12},
        {"t": True},
        {"episode_id": ""},
        {"applied": "false"},
    ],
)
def test_malformed_actions_fail_explicitly(change):
    action = next(actions()) | change
    result = score([row_for("handoff/left_hold")], [action])
    assert not result["full_workflow_success"]
    assert "valid_actions" in result["failed_gates"]


@pytest.mark.parametrize(
    "failure", ["physics_tail", "action_tail", "action_extra", "changed_episode"]
)
def test_complete_action_and_physics_coverage_is_required(failure):
    physics, commands = rows(), actions()
    if failure == "physics_tail":
        physics = itertools.islice(physics, TOTAL - 1)
    elif failure == "action_tail":
        commands = itertools.islice(commands, TOTAL // 50 - 1)
    elif failure == "action_extra":
        commands = itertools.chain(
            commands,
            [
                {
                    "t": TOTAL / 1000,
                    "phase": "utensils/fork_settled",
                    "q": [0.0] * 12,
                    "episode_id": "fixture",
                }
            ],
        )
    else:
        commands = (
            action | {"episode_id": "different"} if i == 1 else action
            for i, action in enumerate(commands)
        )
    result = score(physics, commands)
    assert not result["full_workflow_success"]
    assert (
        "one_action_episode" if failure == "changed_episode" else "complete_action_coverage"
    ) in result["failed_gates"]


def test_unapplied_action_is_not_counted_as_physics_coverage():
    commands = itertools.chain([next(actions()) | {"applied": False}], actions())
    result = score(commands=commands)
    assert result["full_workflow_success"]
    assert result["unapplied_actions"] == 1 and result["applied_actions"] == TOTAL // 50


@pytest.mark.parametrize(
    "mutation,gate",
    [
        (lambda r: r["objects"]["cup"]["pos"].__setitem__(0, 0.5), "prior_placements_undisturbed"),
        (lambda r: r.update(bad=[["robot", "table"]]), "zero_forbidden_contacts"),
        (
            lambda r: r["objects"]["plate"].update(support=["workbench", "rack"]),
            "terminal_all_placed_2000",
        ),
    ],
)
def test_late_fault_cannot_hide_behind_completed_skill_summaries(mutation, gate):
    def corrupted():
        for index, row in enumerate(rows()):
            if index == TOTAL - 1:
                row = copy.deepcopy(row)
                mutation(row)
                row["full_workflow_success"] = True
            yield row

    result = score(corrupted())
    assert not result["full_workflow_success"] and gate in result["failed_gates"]


def test_contiguity_and_action_phase_are_checked():
    commands = [next(actions()) | {"phase": "cup/hold", "t": 0.05}]
    result = score([row_for("handoff/left_hold", 0.002)], commands)
    assert {"continuous_1khz", "continuous_20hz", "physics_action_alignment"} <= set(
        result["failed_gates"]
    )


def test_empty_summary_only_and_broken_iterators_fail_without_raising():
    for physics, commands, layout in (
        ([], [], LAYOUT),
        ([{"full_workflow_success": True}], [], LAYOUT),
        (None, None, None),
        ([], [], {**LAYOUT, "plate_source_m": [0, float("nan"), 0]}),
    ):
        result = score_dinner(physics, commands, layout)
        assert not result["full_workflow_success"] and result["failed_gates"]

    def broken():
        yield row_for("handoff/left_hold")
        raise ValueError("truncated JSON")

    result = score(broken(), itertools.islice(actions(), 1))
    assert not result["full_workflow_success"] and "input_error" in result["failed_gates"]
