"""Measured per-attempt outcomes; no teacher schedule or planner authority."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from bimanual.dinner_outcomes import ARMS, CARRY_SAMPLES
from bimanual.dinner_scoring import (
    _airborne,
    _distance,
    _finite_tree,
    _number,
    _placed,
    _valid_row,
    _vector,
)
from bimanual.skill_registry import dinner_capability
from bimanual.skill_views import INTERVALS

_TARGETS = dict(
    handoff_transfer="practice_object",
    bar_place_and_return="practice_object",
    cup_pick_place="cup",
    plate_pick_place="plate",
    drawer_open="drawer",
    spoon_retrieve_place="spoon",
    fork_retrieve_place="fork",
)
_PROTECTED = dict(
    handoff_transfer=(),
    bar_place_and_return=(),
    cup_pick_place=("practice_object",),
    plate_pick_place=("practice_object", "cup"),
    drawer_open=("practice_object", "cup", "plate"),
    spoon_retrieve_place=("practice_object", "cup", "plate"),
    fork_retrieve_place=("practice_object", "cup", "plate", "spoon"),
)


@dataclass(frozen=True)
class SkillOutcome:
    state: Literal["pending", "succeeded", "failed"]
    reason: str
    counters: Mapping[str, int | float | bool]

    def report(self) -> dict:
        return dict(
            profile="dinner_skill_outcomes_v1",
            state=self.state,
            reason=self.reason,
            counters=dict(self.counters),
            independent_task_success=None,
            successor_start_ready=None,
        )


class SkillOutcomeMonitor:
    """One attempt and serialized worker; every call consumes one confirmed control step.

    Prerequisites are current measured conditions, not reconstructed history. A
    retry receives a NEW monitor and must establish all of its own contact/hold
    evidence. Already-open drawers/already-placed targets are not shortcut successes.
    Per-skill success does not certify parking, next-model readiness, full task,
    unlogged intervention absence or model quality. The worker/full evaluator owns
    intervention counters and subsequent actions after this attempt terminates.
    """

    def __init__(
        self,
        skill_id: str,
        *,
        episode_id: str,
        initial_sequence: int,
        initial_simulation_seconds: float,
        layout: dict,
        max_actions: int | None = None,
    ):
        capability = dinner_capability(skill_id)
        if (
            not isinstance(episode_id, str)
            or not episode_id
            or type(initial_sequence) is not int
            or initial_sequence < 0
            or not _number(initial_simulation_seconds)
            or initial_simulation_seconds < 0
            or abs(initial_simulation_seconds - initial_sequence / 20) >= 1e-8
        ):
            raise ValueError("Invalid attempt episode/sequence/time identity")
        if (
            not isinstance(layout, dict)
            or not _finite_tree(layout)
            or any(
                not _vector(layout.get(key), 3)
                for key in ("bar_destination_m", "plate_destination_m", "plate_source_m")
            )
        ):
            raise ValueError("Malformed dinner layout")
        _, start, end = next(interval for interval in INTERVALS if interval[0] == skill_id)
        # Explicit bounded development envelope: twice the nominal demonstration duration.
        if max_actions is None:
            max_actions = 2 * (end - start)
        if type(max_actions) is not int or max_actions <= 0:
            raise ValueError("Action budget must be a positive integer")
        self.skill_id, self.episode_id = skill_id, episode_id
        self.initial_sequence, self.initial_time = initial_sequence, initial_simulation_seconds
        self.max_actions, self._arms = max_actions, capability.execution_arms
        self._target, self._protected = _TARGETS[skill_id], _PROTECTED[skill_id]
        self._coordinates = dict(
            spoon=(-0.12, 0.045, 0.391),
            fork=(-0.06, 0.062, 0.391),
            cup=(0.066, 0.153, 0.378),
            plate=tuple(layout["plate_destination_m"]),
            practice_object=tuple(layout["bar_destination_m"]),
        )
        self._plate_z = layout["plate_source_m"][2]
        self._counters = dict(
            actions=0,
            physics_rows=0,
            handoff_stage=0,
            donor_samples=0,
            shared_samples=0,
            receiver_samples=0,
            airborne_samples=0,
            maximum_airborne_samples=0,
            maximum_contact_transport_m=0.0,
            carry_completed=False,
            released_samples=0,
            drawer_contact_samples=0,
            drawer_open_contact_samples=0,
            drawer_driven_open=False,
            maximum_overlap_m=0.0,
        )
        self._anchor = self._initial_opening = self._drawer_contact_start = self._hold = None
        self._state, self._reason = "pending", "Awaiting confirmed physical progress"

    def snapshot(self) -> SkillOutcome:
        return SkillOutcome(self._state, self._reason, MappingProxyType(dict(self._counters)))

    def _initial(self, row):
        target = self._target
        self._initial_opening = row["opening"]
        if target == "drawer" and abs(row["opening"]) > 0.001:
            raise ValueError("Drawer attempt requires a measured closed initial drawer")
        if target in ("spoon", "fork") and (row["opening"] < 0.08 or any(row["drawer_forces"])):
            raise ValueError("Utensil attempt requires a measured open released drawer")
        if self.skill_id == "bar_place_and_return":
            if not _airborne(row["objects"][target], "right"):
                raise ValueError("Bar placement requires an initial receiver-only airborne grip")
        elif target != "drawer" and self.skill_id != "handoff_transfer":
            if _placed(row["objects"][target], target, self._coordinates):
                raise ValueError("Already-placed target is not a new manipulation attempt")

    def _row(self, row):
        c, objects = self._counters, row["objects"]
        if row["bad"]:
            raise ValueError("Forbidden physical contact")
        c["maximum_overlap_m"] = max(c["maximum_overlap_m"], row["overlap"])
        for name in self._protected:
            if not _placed(objects[name], name, self._coordinates):
                raise ValueError(f"Required previous placement missing or disturbed: {name}")
        for name, obj in objects.items():
            if name != self._target and any(
                force for pair in obj["forces"].values() for force in pair
            ):
                raise ValueError("Jaw contact with an object outside the registered skill")
        if self._target in ("spoon", "fork") and (
            row["opening"] < 0.08 or any(row["drawer_forces"])
        ):
            raise ValueError("Open released drawer prerequisite was disturbed")
        if self.skill_id == "handoff_transfer":
            obj, stage = objects["practice_object"], c["handoff_stage"]
            predicates = (
                _airborne(obj, "left"),
                not obj["support"]
                and min((*obj["forces"]["left"], *obj["forces"]["right"])) > 0.01,
                _airborne(obj, "right"),
            )
            keys = ("donor_samples", "shared_samples", "receiver_samples")
            if stage < 3:
                key = keys[stage]
                c[key] = c[key] + 1 if predicates[stage] else 0
                if c[key] >= 2000:
                    c["handoff_stage"] += 1
            if 0 < c["handoff_stage"] < 3 and (
                obj["support"] or not any(v > 0.01 for pair in obj["forces"].values() for v in pair)
            ):
                raise ValueError("Handoff support/grip continuity lost after donor hold")
            if c["handoff_stage"] == 3 and not predicates[2]:
                raise ValueError("Receiver grip lost after its handoff hold")
            # Success still requires receiver ownership in the final sample of the action.
            return c["handoff_stage"] == 3 and predicates[2]
        if self._target == "drawer":
            contact = min(row["drawer_forces"]) > 0.01
            opened = row["opening"] >= 0.08 and row["opening"] - self._initial_opening >= 0.08
            if contact:
                if self._drawer_contact_start is None:
                    self._drawer_contact_start = row["opening"]
                c["drawer_contact_samples"] += 1
                c["drawer_open_contact_samples"] = (
                    c["drawer_open_contact_samples"] + 1 if opened else 0
                )
                if (
                    abs(self._drawer_contact_start) <= 0.001
                    and row["opening"] - self._drawer_contact_start >= 0.08
                    and c["drawer_contact_samples"] >= 8000
                    and c["drawer_open_contact_samples"] >= 2000
                ):
                    c["drawer_driven_open"] = True
            else:
                self._drawer_contact_start = None
                if not c["drawer_driven_open"]:
                    c["drawer_contact_samples"] = c["drawer_open_contact_samples"] = 0
            c["released_samples"] = (
                c["released_samples"] + 1
                if (c["drawer_driven_open"] and opened and not any(row["drawer_forces"]))
                else 0
            )
            return c["released_samples"] >= 2000
        obj, arm = objects[self._target], ARMS[self._target]
        if any(obj["forces"]["left" if arm == "right" else "right"]):
            raise ValueError("Target grasp widened registered object ownership")
        airborne = _airborne(obj, arm)
        if self._target in ("cup", "plate"):
            airborne &= obj["pos"][2] - (0.378 if self._target == "cup" else self._plate_z) >= 0.04
        if airborne:
            if self._anchor is None:
                self._anchor = tuple(obj["pos"])
            c["airborne_samples"] += 1
            distance = _distance(obj, self._anchor)
            c["maximum_airborne_samples"] = max(
                c["maximum_airborne_samples"], c["airborne_samples"]
            )
            c["maximum_contact_transport_m"] = max(c["maximum_contact_transport_m"], distance)
            # The receiver's 2s handoff hold belongs to the preceding attempt.
            required = 12000 if self._target == "practice_object" else CARRY_SAMPLES[self._target]
            if c["airborne_samples"] >= required and distance >= 0.06:
                c["carry_completed"] = True
        else:
            c["airborne_samples"], self._anchor = 0, None
        c["released_samples"] = (
            c["released_samples"] + 1
            if (c["carry_completed"] and _placed(obj, self._target, self._coordinates))
            else 0
        )
        return c["released_samples"] >= 2000

    def consume(self, action: dict, rows: Iterable[dict]) -> SkillOutcome:
        if self._state != "pending":
            raise RuntimeError("A terminal skill monitor cannot consume another action")
        try:
            c = self._counters
            sequence = self.initial_sequence + c["actions"]
            before = self.initial_time + c["actions"] / 20
            if (
                not isinstance(action, dict)
                or not _finite_tree(action)
                or action.get("episode_id") != self.episode_id
                or type(action.get("observation_sequence")) is not int
                or action["observation_sequence"] != sequence
                or not _number(action.get("simulation_seconds_before"))
                or not _number(action.get("simulation_seconds_after"))
                or abs(action["simulation_seconds_before"] - before) >= 1e-8
                or abs(action["simulation_seconds_after"] - before - 0.05) >= 1e-8
                or not _vector(action.get("targets_rad"), 12)
                or action.get("applied") is not True
                or action.get("partial_physics") is not False
            ):
                raise ValueError("Unconfirmed, partial or mismatched action identity")
            targets = tuple(action["targets_rad"])
            if self._hold is None:
                self._hold = targets
            for arm, offset in (("left", 0), ("right", 6)):
                if (
                    arm not in self._arms
                    and targets[offset : offset + 6] != self._hold[offset : offset + 6]
                ):
                    raise ValueError(
                        "Action moved an unowned arm away from its bound holding target"
                    )
            iterator = iter(rows)
            succeeded = False
            for offset in range(50):
                row = next(iterator, None)
                if (
                    not isinstance(row, dict)
                    or not _valid_row(row | {"phase": "ignored"})
                    or abs(row["t"] - before - (offset + 1) / 1000) >= 1e-8
                ):
                    raise ValueError("Malformed, missing or discontinuous 1kHz physical sample")
                if c["physics_rows"] == 0:
                    self._initial(row)
                succeeded = self._row(row)
                c["physics_rows"] += 1
            if next(iterator, None) is not None:
                raise ValueError("More than fifty physical samples for one control action")
            c["actions"] += 1
            if succeeded:
                self._state, self._reason = (
                    "succeeded",
                    "Measured contact and hold predicates passed",
                )
            elif c["actions"] >= self.max_actions:
                self._state, self._reason = "failed", "Physical outcome action budget exhausted"
        except Exception as exc:
            self._state, self._reason = "failed", f"{type(exc).__name__}: {exc}"
        return self.snapshot()
