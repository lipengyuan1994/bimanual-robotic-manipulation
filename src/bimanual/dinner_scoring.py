"""Streaming independent dinner-physics scoring; no simulator or filesystem access."""

from __future__ import annotations

import math
from collections.abc import Iterable

OBJECTS = ("spoon", "fork", "cup", "practice_object", "plate")
REQUIRED_PHASES = {
    "handoff/left_hold": 2000,
    "handoff/both_hold": 2000,
    "handoff/receiver_hold": 2000,
    "handoff/bar_transport": 12000,
    "handoff/bar_settled": 2000,
    "utensils/pull": 6000,
    "utensils/open_hold": 2000,
    "utensils/released_hold": 2000,
    "plate/hold": 2000,
    "plate/transport": 3000,
    "plate/settled": 2000,
    "cup/hold": 2000,
    "cup/transport": 3000,
    "cup/settled": 2000,
    **{
        f"utensils/{name}_{phase}": count
        for name in ("spoon", "fork")
        for phase, count in (
            ("hold", 2000),
            ("clearance", 3000),
            ("transport", 7200),
            ("lower", 3000),
            ("settled", 2000),
        )
    },
}
ORDER_PAIRS = (
    ("handoff/left_hold", "handoff/both_hold"),
    ("handoff/both_hold", "handoff/receiver_hold"),
    ("handoff/receiver_hold", "handoff/bar_settled"),
    ("utensils/pull", "utensils/open_hold"),
    ("utensils/open_hold", "utensils/released_hold"),
    ("utensils/released_hold", "utensils/spoon_hold"),
    ("utensils/spoon_settled", "utensils/fork_hold"),
)
SETTLED_PHASES = {
    "practice_object": "handoff/bar_settled",
    "plate": "plate/settled",
    "cup": "cup/settled",
    "spoon": "utensils/spoon_settled",
    "fork": "utensils/fork_settled",
}


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value, length: int) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == length
        and all(_number(item) for item in value)
    )


def _finite_tree(value) -> bool:
    if isinstance(value, dict):
        return all(_finite_tree(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_finite_tree(item) for item in value)
    return not isinstance(value, (int, float)) or math.isfinite(value)


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _pairs(value) -> bool:
    return isinstance(value, list) and all(_strings(pair) and len(pair) == 2 for pair in value)


def _valid_row(row) -> bool:
    if not isinstance(row, dict) or not _finite_tree(row):
        return False
    if not (isinstance(row.get("phase"), str) and row["phase"]):
        return False
    if not all(_number(row.get(key)) for key in ("t", "opening", "overlap", "overtravel")):
        return False
    if not (0 <= row["overlap"] <= 0.0025 and 0 <= row["overtravel"] <= 0.0025):
        return False
    if not _vector(row.get("joint_position"), 12) or not _vector(row.get("drawer_forces"), 2):
        return False
    if (
        min(row["drawer_forces"]) < 0
        or not _pairs(row.get("contacts"))
        or not _pairs(row.get("bad"))
    ):
        return False
    objects = row.get("objects")
    if not isinstance(objects, dict) or set(objects) != set(OBJECTS):
        return False
    for obj in objects.values():
        if not isinstance(obj, dict) or not all(
            _vector(obj.get(key), size) for key, size in (("pos", 3), ("quat", 4), ("vel", 6))
        ):
            return False
        if not _number(obj.get("upright")) or not _strings(obj.get("support")):
            return False
        forces = obj.get("forces")
        if not isinstance(forces, dict) or set(forces) != {"left", "right"}:
            return False
        if any(not _vector(force, 2) or min(force) < 0 for force in forces.values()):
            return False
    return True


def _valid_action(action) -> bool:
    return (
        isinstance(action, dict)
        and _finite_tree(action)
        and _number(action.get("t"))
        and action["t"] >= 0
        and isinstance(action.get("phase"), str)
        and bool(action["phase"])
        and _vector(action.get("q"), 12)
        and isinstance(action.get("episode_id"), str)
        and bool(action["episode_id"])
        and type(action.get("applied", True)) is bool
    )


def _norm(values) -> float:
    return math.hypot(*values)


def _distance(obj, destination) -> float:
    return math.hypot(obj["pos"][0] - destination[0], obj["pos"][1] - destination[1])


def _placed(obj, name: str, coordinates: dict) -> bool:
    return (
        all(force == [0, 0] or force == (0, 0) for force in obj["forces"].values())
        and set(obj["support"]) == {"workbench"}
        and _distance(obj, coordinates[name]) < (0.02 if name in ("cup", "plate") else 0.025)
        and _norm(obj["vel"][:3]) < 0.01
        and _norm(obj["vel"][3:]) < 0.1
        and (
            name not in ("cup", "plate")
            or (obj["upright"] >= math.cos(math.radians(10)) and abs(obj["pos"][2] - 0.378) < 0.004)
        )
    )


def _airborne(obj, arm: str) -> bool:
    other = "right" if arm == "left" else "left"
    return (
        min(obj["forces"][arm]) > 0.01
        and all(v == 0 for v in obj["forces"][other])
        and not obj["support"]
    )


def _phase_pass(row, coordinates, plate_source_z, initial):
    phase, objects = row["phase"], row["objects"]
    if phase in ("utensils/pull", "utensils/open_hold", "utensils/released_hold"):
        ok = (
            min(row["drawer_forces"]) > 0.01
            if phase != "utensils/released_hold"
            else all(v == 0 for v in row["drawer_forces"])
        )
        return ok and (
            phase == "utensils/pull"
            or (row["opening"] >= 0.08 and row["opening"] - initial >= 0.08)
        )
    if phase in ("handoff/left_hold", "handoff/both_hold", "handoff/receiver_hold"):
        obj = objects["practice_object"]
        if phase == "handoff/both_hold":
            return (
                not obj["support"] and min((*obj["forces"]["left"], *obj["forces"]["right"])) > 0.01
            )
        return _airborne(obj, "left" if phase == "handoff/left_hold" else "right")
    if phase == "handoff/bar_transport":
        return _airborne(objects["practice_object"], "right")
    if phase == "handoff/bar_settled":
        return _placed(objects["practice_object"], "practice_object", coordinates)
    if phase.startswith("utensils/"):
        name = phase.split("/")[1].split("_")[0]
        part = phase.split("_")[-1]
        if name in ("spoon", "fork"):
            if part in ("hold", "clearance", "transport", "lower"):
                return _airborne(objects[name], "left")
            if part == "settled":
                return _placed(objects[name], name, coordinates)
    if phase in ("cup/hold", "cup/transport"):
        return _airborne(objects["cup"], "right") and objects["cup"]["pos"][2] - 0.378 >= 0.04
    if phase == "cup/settled":
        return _placed(objects["cup"], "cup", coordinates)
    if phase in ("plate/hold", "plate/transport_clearance", "plate/transport"):
        return (
            _airborne(objects["plate"], "left")
            and objects["plate"]["pos"][2] - plate_source_z >= 0.04
        )
    if phase == "plate/settled":
        return _placed(objects["plate"], "plate", coordinates)
    return None


def score_dinner(rows: Iterable[dict], actions: Iterable[dict], layout: dict) -> dict:
    """Score full raw traces in bounded memory; malformed/incomplete input fails closed.

    Applied actions start at time zero, own the next50 physics samples and advance
    at20Hz. Missing applied flags retain legacy true semantics. No summary flag is
    accepted as evidence. The final result is independent of actor return status.
    """
    metrics = {
        "full_workflow_success": False,
        "physics_rows": 0,
        "forbidden_samples": 0,
        "maximum_overlap_m": 0.0,
        "maximum_jaw_force_n": 0.0,
        "phases": {},
        "continuous_1khz": True,
        "valid_rows": True,
        "terminal_all_placed_samples": 0,
        "applied_actions": 0,
        "unapplied_actions": 0,
        "valid_actions": True,
        "continuous_20hz": True,
        "physics_action_alignment": True,
        "complete_action_coverage": False,
        "one_action_episode": False,
        "initially_closed": False,
        "phase_order_valid": False,
        "simulation_seconds": 0.0,
        "prior_placement_disturbance_samples": dict.fromkeys(OBJECTS, 0),
        "failed_gates": [],
        "final_objects": {},
    }
    failures = set()
    previous = 0.0
    initial = None
    last = None
    last_phase = None
    blocks = []
    locked = set()
    previous_action_time = None
    episode_id = None
    current_action = None
    required = dict(REQUIRED_PHASES)
    try:
        if (
            not isinstance(layout, dict)
            or not _finite_tree(layout)
            or any(
                not _vector(layout.get(key), 3)
                for key in ("bar_destination_m", "plate_destination_m", "plate_source_m")
            )
        ):
            failures.add("valid_layout")
            raise ValueError("Invalid layout dimensions or nonfinite values")
        coordinates = {
            "spoon": [-0.12, 0.045, 0.391],
            "fork": [-0.06, 0.062, 0.391],
            "cup": [0.066, 0.153, 0.378],
            "practice_object": layout["bar_destination_m"],
            "plate": layout["plate_destination_m"],
        }
        if "plate_transport_clearance_tool_m" in layout:
            if not _vector(layout["plate_transport_clearance_tool_m"], 3):
                failures.add("valid_layout")
                raise ValueError("Invalid plate clearance layout")
            required["plate/transport_clearance"] = 2000
        action_iterator = iter(actions)

        def next_applied():
            nonlocal previous_action_time, episode_id
            for action in action_iterator:
                if not _valid_action(action):
                    metrics["valid_actions"] = False
                    raise ValueError("Malformed action record")
                if not action.get("applied", True):
                    metrics["unapplied_actions"] += 1
                    continue
                metrics["applied_actions"] += 1
                expected = 0.0 if previous_action_time is None else previous_action_time + 0.05
                metrics["continuous_20hz"] &= abs(action["t"] - expected) < 1e-8
                previous_action_time = action["t"]
                if episode_id is None:
                    episode_id = action["episode_id"]
                    metrics["one_action_episode"] = True
                elif action["episode_id"] != episode_id:
                    metrics["one_action_episode"] = False
                return action
            return None

        for row in rows:
            offset = metrics["physics_rows"] % 50
            if offset == 0:
                current_action = next_applied()
            metrics["physics_rows"] += 1
            if not _valid_row(row):
                metrics["valid_rows"] = False
                metrics.setdefault("first_invalid_row", metrics["physics_rows"] - 1)
                continue
            metrics["continuous_1khz"] &= abs(row["t"] - previous - 0.001) < 1e-8
            previous = row["t"]
            if (
                current_action is None
                or current_action["phase"] != row["phase"]
                or abs(row["t"] - current_action["t"] - (offset + 1) * 0.001) >= 1e-8
            ):
                metrics["physics_action_alignment"] = False
            phase, objects = row["phase"], row["objects"]
            metrics["forbidden_samples"] += bool(row["bad"])
            metrics["maximum_overlap_m"] = max(metrics["maximum_overlap_m"], row["overlap"])
            metrics["maximum_jaw_force_n"] = max(
                metrics["maximum_jaw_force_n"],
                *row["drawer_forces"],
                *(v for obj in objects.values() for force in obj["forces"].values() for v in force),
            )
            sample = metrics["phases"].setdefault(
                phase, {"samples": 0, "first_t": row["t"], "last_t": row["t"]}
            )
            sample["samples"] += 1
            sample["last_t"] = row["t"]
            if phase != last_phase:
                blocks.append(phase)
                last_phase = phase
            if initial is None:
                initial = row["opening"]
            passed = _phase_pass(row, coordinates, layout["plate_source_m"][2], initial)
            if passed is not None:
                sample["passed"] = sample.get("passed", 0) + int(passed)
            placed = {name: _placed(objects[name], name, coordinates) for name in OBJECTS}
            if phase == "utensils/fork_settled":
                metrics["terminal_all_placed_samples"] += int(
                    all(placed.values())
                    and row["opening"] >= 0.08
                    and all(v == 0 for v in row["drawer_forces"])
                )
            for name, settled in SETTLED_PHASES.items():
                if phase == settled:
                    locked.add(name)
            for name in locked:
                metrics["prior_placement_disturbance_samples"][name] += int(not placed[name])
            last = row
        # Consume trailing records to detect extra applied actions, including after the final hold.
        while next_applied() is not None:
            pass
        metrics["complete_action_coverage"] = (
            metrics["physics_rows"] > 0
            and metrics["physics_rows"] == metrics["applied_actions"] * 50
            and metrics["physics_action_alignment"]
        )
        metrics["phase_order_valid"] = all(
            first in blocks and second in blocks and blocks.index(first) < blocks.index(second)
            for first, second in ORDER_PAIRS
        )
        if last is not None:
            metrics["final_objects"] = {
                name: {
                    "pos": list(obj["pos"]),
                    "upright": obj["upright"],
                    "position_error_m": _distance(obj, coordinates[name]),
                    "placed": _placed(obj, name, coordinates),
                }
                for name, obj in last["objects"].items()
            }
    except Exception as exc:
        failures.add("input_error")
        metrics["input_error"] = f"{type(exc).__name__}: {exc}"
    metrics["simulation_seconds"] = previous
    metrics["initially_closed"] = initial is not None and abs(initial) <= 0.001
    for phase, count in required.items():
        sample = metrics["phases"].get(phase, {})
        if (
            sample.get("samples") != count
            or sample.get("passed") != count
            or abs(sample.get("last_t", 0) - sample.get("first_t", 0) - (count - 1) * 0.001) >= 1e-8
            or blocks.count(phase) != 1
        ):
            failures.add(phase)
    for gate in (
        "valid_rows",
        "continuous_1khz",
        "valid_actions",
        "continuous_20hz",
        "one_action_episode",
        "physics_action_alignment",
        "complete_action_coverage",
        "initially_closed",
        "phase_order_valid",
    ):
        if not metrics[gate]:
            failures.add(gate)
    if metrics["forbidden_samples"]:
        failures.add("zero_forbidden_contacts")
    if any(metrics["prior_placement_disturbance_samples"].values()):
        failures.add("prior_placements_undisturbed")
    if metrics["terminal_all_placed_samples"] != 2000:
        failures.add("terminal_all_placed_2000")
    if not blocks or blocks[-1] != "utensils/fork_settled":
        failures.add("terminal_phase")
    metrics["failed_gates"] = sorted(failures)
    metrics["full_workflow_success"] = not failures
    return metrics
