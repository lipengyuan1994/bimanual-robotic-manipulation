"""Phase-free physical outcomes for the frozen dinner scene; evaluator truth only."""

from __future__ import annotations

from collections.abc import Iterable

from bimanual.dinner_scoring import (
    OBJECTS,
    _airborne,
    _distance,
    _finite_tree,
    _number,
    _placed,
    _valid_row,
    _vector,
)

PROFILE = "dinner_contact_outcomes_v1"
# Preserve original hold + transport durations, including plate clearance and utensil lowering.
CARRY_SAMPLES = {
    "practice_object": 14000,
    "cup": 5000,
    "plate": 7000,
    "spoon": 15200,
    "fork": 15200,
}
ARMS = {
    "practice_object": "right",
    "cup": "right",
    "plate": "left",
    "spoon": "left",
    "fork": "left",
}


def score_dinner_outcomes(
    rows: Iterable[dict], layout: dict, *, metadata: dict, actions: Iterable[dict]
) -> dict:
    """Score contiguous 1kHz physical samples without consulting phase/skill labels.

    Metadata counters must come from worker instrumentation. This scorer cannot
    establish absence of unlogged state edits from contact summaries alone. It
    consumes evaluator-only poses/forces; none are an operating policy input.
    """
    result = dict(
        applied_actions=0,
        complete_action_coverage=False,
        valid_actions=True,
        profile=PROFILE,
        independent_task_success=False,
        physics_rows=0,
        valid_rows=True,
        continuous_1khz=True,
        forbidden_samples=0,
        maximum_overlap_m=0.0,
        terminal_all_placed_samples=0,
        handoff_stage=0,
        handoff_samples=[0, 0, 0],
        drawer_contact_samples=0,
        drawer_open_contact_samples=0,
        drawer_released_open_samples=0,
        drawer_opened_by_contact=False,
        drawer_released_open=False,
        final_objects={},
        failed_gates=[],
    )
    failures = set()
    state = {
        name: dict(
            airborne_samples=0,
            maximum_airborne_samples=0,
            maximum_contact_transport_m=0.0,
            carry_completed=False,
            released_samples=0,
            accepted=False,
            disturbance_samples=0,
        )
        for name in OBJECTS
    }
    result["objects"] = state
    anchors = dict.fromkeys(OBJECTS)
    previous, initial_opening, contact_start = 0.0, None, None
    donor_run = shared_run = receiver_run = 0
    final = None
    try:
        if (
            not isinstance(metadata, dict)
            or not _finite_tree(metadata)
            or type(metadata.get("physics_hz")) is not int
            or metadata["physics_hz"] != 1000
            or any(
                type(metadata.get(key)) is not int or metadata[key] != 0
                for key in (
                    "object_state_edits",
                    "artificial_attachments",
                    "external_object_force_samples",
                )
            )
        ):
            raise ValueError("Missing 1kHz/zero-intervention worker instrumentation")
        if (
            not isinstance(layout, dict)
            or not _finite_tree(layout)
            or any(
                not _vector(layout.get(key), 3)
                for key in ("bar_destination_m", "plate_destination_m", "plate_source_m")
            )
        ):
            raise ValueError("Malformed frozen dinner layout")
        coordinates = {
            "spoon": [-0.12, 0.045, 0.391],
            "fork": [-0.06, 0.062, 0.391],
            "cup": [0.066, 0.153, 0.378],
            "plate": layout["plate_destination_m"],
            "practice_object": layout["bar_destination_m"],
        }
        action_iterator = iter(actions)
        episode_id = None
        current_action = None

        def next_action():
            nonlocal episode_id
            action = next(action_iterator, None)
            if action is None:
                return None
            index = result["applied_actions"]
            if (
                not isinstance(action, dict)
                or not _finite_tree(action)
                or not isinstance(action.get("episode_id"), str)
                or not action["episode_id"]
                or type(action.get("observation_sequence")) is not int
                or action["observation_sequence"] != index
                or not _vector(action.get("targets_rad"), 12)
                or action.get("applied") is not True
                or action.get("partial_physics") is not False
                or not _number(action.get("simulation_seconds_before"))
                or not _number(action.get("simulation_seconds_after"))
                or abs(action["simulation_seconds_before"] - index / 20) >= 1e-8
                or abs(action["simulation_seconds_after"] - (index + 1) / 20) >= 1e-8
                or (episode_id is not None and action["episode_id"] != episode_id)
            ):
                result["valid_actions"] = False
                raise ValueError("Malformed, discontinuous or unconfirmed action evidence")
            episode_id = action["episode_id"]
            result["applied_actions"] += 1
            return action

        for row in rows:
            offset = result["physics_rows"] % 50
            if offset == 0:
                current_action = next_action()
            if current_action is None:
                raise ValueError("Physics has no confirmed owning action")
            result["physics_rows"] += 1
            # Supply the shared validator's legacy label without reading the caller's label.
            if not isinstance(row, dict) or not _valid_row(row | {"phase": "ignored"}):
                result["valid_rows"] = False
                raise ValueError(f"Malformed physical sample {result['physics_rows'] - 1}")
            if abs(row["t"] - previous - 0.001) >= 1e-8:
                result["continuous_1khz"] = False
                raise ValueError("Noncontiguous physical samples")
            previous = row["t"]
            if initial_opening is None:
                initial_opening = row["opening"]
            result["forbidden_samples"] += bool(row["bad"])
            result["maximum_overlap_m"] = max(result["maximum_overlap_m"], row["overlap"])
            objects = row["objects"]
            bar = objects["practice_object"]
            donor = _airborne(bar, "left")
            shared = (
                not bar["support"] and min((*bar["forces"]["left"], *bar["forces"]["right"])) > 0.01
            )
            receiver = _airborne(bar, "right")
            stage = result["handoff_stage"]
            donor_run = donor_run + 1 if donor else 0
            shared_run = shared_run + 1 if shared and stage >= 1 else 0
            receiver_run = receiver_run + 1 if receiver and stage >= 2 else 0
            for i, count in enumerate((donor_run, shared_run, receiver_run)):
                result["handoff_samples"][i] = max(result["handoff_samples"][i], count)
            if stage == 0 and donor_run >= 2000:
                result["handoff_stage"] = 1
            elif stage == 1 and shared_run >= 2000:
                result["handoff_stage"] = 2
            elif stage == 2 and receiver_run >= 2000:
                result["handoff_stage"] = 3
            # No supported rest or dropped bar may connect otherwise independent handoff holds.
            if 0 < result["handoff_stage"] < 3 and (
                bar["support"] or not any(v > 0.01 for f in bar["forces"].values() for v in f)
            ):
                result["handoff_stage"] = 0
                donor_run = shared_run = receiver_run = 0
            contact = min(row["drawer_forces"]) > 0.01
            opened = row["opening"] >= 0.08 and row["opening"] - initial_opening >= 0.08
            if contact:
                if contact_start is None:
                    contact_start = row["opening"]
                result["drawer_contact_samples"] += 1
                result["drawer_open_contact_samples"] = (
                    result["drawer_open_contact_samples"] + 1 if opened else 0
                )
                if (
                    abs(contact_start) <= 0.001
                    and row["opening"] - contact_start >= 0.08
                    and result["drawer_contact_samples"] >= 8000
                    and result["drawer_open_contact_samples"] >= 2000
                ):
                    result["drawer_opened_by_contact"] = True
            else:
                contact_start = None
                if not result["drawer_opened_by_contact"]:
                    result["drawer_contact_samples"] = result["drawer_open_contact_samples"] = 0
            released_open = opened and all(v == 0 for v in row["drawer_forces"])
            result["drawer_released_open_samples"] = (
                result["drawer_released_open_samples"] + 1
                if released_open and result["drawer_opened_by_contact"]
                else 0
            )
            if result["drawer_released_open_samples"] >= 2000:
                result["drawer_released_open"] = True
            for name, obj in objects.items():
                item = state[name]
                airborne = _airborne(obj, ARMS[name])
                if name == "practice_object":
                    airborne &= result["handoff_stage"] >= 2
                if name in ("spoon", "fork"):
                    airborne &= result["drawer_released_open"]
                if name in ("cup", "plate"):
                    baseline = 0.378 if name == "cup" else layout["plate_source_m"][2]
                    airborne &= obj["pos"][2] - baseline >= 0.04
                if airborne:
                    if anchors[name] is None:
                        anchors[name] = tuple(obj["pos"])
                    item["airborne_samples"] += 1
                    distance = _distance(obj, anchors[name])
                    item["maximum_contact_transport_m"] = max(
                        item["maximum_contact_transport_m"], distance
                    )
                    item["maximum_airborne_samples"] = max(
                        item["maximum_airborne_samples"], item["airborne_samples"]
                    )
                    if item["airborne_samples"] >= CARRY_SAMPLES[name] and distance >= 0.06:
                        item["carry_completed"] = True
                else:
                    item["airborne_samples"] = 0
                    anchors[name] = None
                placed = _placed(obj, name, coordinates)
                if item["accepted"] and not placed:
                    item["disturbance_samples"] += 1
                item["released_samples"] = (
                    item["released_samples"] + 1 if placed and item["carry_completed"] else 0
                )
                if item["released_samples"] >= 2000:
                    item["accepted"] = True
            all_placed = (
                all(s["carry_completed"] and s["released_samples"] > 0 for s in state.values())
                and released_open
                and result["handoff_stage"] == 3
            )
            result["terminal_all_placed_samples"] = (
                result["terminal_all_placed_samples"] + 1 if all_placed else 0
            )
            final = row
        extra = next_action()
        result["complete_action_coverage"] = (
            extra is None
            and result["physics_rows"] > 0
            and result["physics_rows"] == result["applied_actions"] * 50
        )
        if final:
            result["final_objects"] = {
                name: dict(
                    pos=obj["pos"],
                    placed=_placed(obj, name, coordinates),
                    position_error_m=_distance(obj, coordinates[name]),
                )
                for name, obj in final["objects"].items()
            }
    except Exception as exc:
        failures.add("input_error")
        result["input_error"] = f"{type(exc).__name__}: {exc}"
    if initial_opening is None or abs(initial_opening) > 0.001:
        failures.add("initially_closed")
    for gate in (
        "valid_actions",
        "complete_action_coverage",
        "valid_rows",
        "continuous_1khz",
        "drawer_opened_by_contact",
        "drawer_released_open",
    ):
        if not result[gate]:
            failures.add(gate)
    if result["forbidden_samples"]:
        failures.add("zero_forbidden_contacts")
    if result["handoff_stage"] != 3:
        failures.add("ordered_contact_handoff")
    for name, item in state.items():
        if not item["carry_completed"]:
            failures.add(name + ":contact_transport")
        if not item["accepted"]:
            failures.add(name + ":released_placement")
        if item["disturbance_samples"]:
            failures.add(name + ":placement_disturbed")
    if result["terminal_all_placed_samples"] < 2000:
        failures.add("terminal_all_placed_2000")
    result["simulation_seconds"] = previous
    result["failed_gates"] = sorted(failures)
    result["independent_task_success"] = not failures
    return result
