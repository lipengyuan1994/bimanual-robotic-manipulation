"""Freeze a new corrective-data allocation for a localized bar overlap failure."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from bimanual.dinner_teacher import ASSETS
from bimanual.evidence import EvidenceStore, canonical, digest_file

CASE_SEEDS = tuple(range(52000, 52005))
TRANSPORT_TO_PLACEMENT = (770, 1070)
V2_CASE_SEEDS = tuple(range(53000, 53005))
V2_SOURCE_INTERVAL = (770, 1163)
V3_CASE_SEEDS = tuple(range(54000, 54005))
# The latest failure occurred on the first learned control after the teacher
# prefix.  Include that handoff window as well as transport, placement, release,
# and retreat so a new archive labels the whole trajectory that can influence it.
V3_SOURCE_INTERVAL = (630, 1163)
V4_CASE_SEEDS = tuple(range(55000, 55005))
# The v4 candidate retained contact but wandered during placement and did not
# become successor-ready. Train the full placement, release, and retreat tail.
V4_SOURCE_INTERVAL = (770, 1163)
V5_CASE_SEEDS = tuple(range(56000, 56005))
# A placement-progress corrective candidate reintroduced the earlier forbidden
# left-arm contact on its first learned action.  Retain the complete policy-entry
# through retreat window so this new, source-bound archive labels the trajectory
# that can create that contact.
V5_SOURCE_INTERVAL = (630, 1163)
V6_CASE_SEEDS = tuple(range(57000, 57005))
# The margin-bound candidate stayed within its safety envelope but never became
# successor-ready.  Capture the complete learned entry, placement, release, and
# retreat trajectory so corrective labels cover the unresolved completion tail.
V6_SOURCE_INTERVAL = (630, 1163)
V7_CASE_SEEDS = tuple(range(58000, 58005))
# The new evaluation held the bar for 24 learned actions before the left arm
# entered the object on action 25.  Retain the complete learned entry and
# completion tail; a shorter replay would omit the state that precedes it.
V7_SOURCE_INTERVAL = (630, 1163)
V8_CASE_SEEDS = tuple(range(59000, 59005))
# The v8 candidate held the object through 255 learned actions before it
# overlapped the workbench during placement.  The physical action count cannot
# be mapped one-to-one to a teacher frame, so retain the complete, predeclared
# bar skill view [630, 1580) instead of inventing a narrower correspondence.
V8_SOURCE_INTERVAL = (630, 1580)
ENTRY_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "f894dc670340ef881958dddeb460e32b9b2f25dff5f8b641a601bc36a3999905"
)
PLACEMENT_PROGRESS_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "e2c60f2e4ac0d5a7ed0887107bf06e0bb15e82891c6f34968ddf84112a887139"
)
PLACEMENT_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "71c8319e42fd9f6c47e82f5d1f69d5b350e9ee6c6f59742f787b601d82b193fb"
)
MARGIN_COMPLETION_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "36e2298ebe8d853b2c0d75854dcc3ea9f39d15b5618b06c1c362463b04f94d79"
)
LATE_LEFT_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "feae3370c94f3a873017e59ef257a554c6cc61bde57b4ad9bbfb65131aa9aa41"
)
LATE_WORKBENCH_OVERLAP_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "ff7e077ebc969293afcca0f0591928ac65ebbaf757e9e432c36e1be36b25ba33"
)


class BarOverlapCorrectionProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile: Literal[
        "bar_overlap_transport_placement_protocol_v1",
        "bar_overlap_transport_placement_protocol_v2",
        "bar_left_contact_entry_protocol_v3",
        "bar_placement_progress_protocol_v4",
        "bar_placement_contact_entry_protocol_v5",
        "bar_margin_completion_protocol_v6",
        "bar_late_left_contact_protocol_v7",
        "bar_late_workbench_overlap_protocol_v8",
    ]
    evidence_root: str
    diagnosis_run_id: str
    diagnosis_manifest_sha256: str
    evaluation_run_id: str
    evaluation_manifest_sha256: str
    asset_root: str
    asset_manifest_sha256: str
    plan_sha256: str
    source_interval: tuple[int, int] = TRANSPORT_TO_PLACEMENT
    case_seeds: tuple[int, int, int, int, int] = CASE_SEEDS
    overlap_limit_m: Literal[0.0025] = 0.0025
    allocation_rule: Literal["one_teacher_attempt_per_frozen_case_no_automatic_retry"]
    learned_execution: Literal[False] = False
    release_qualified: Literal[False] = False
    manifest_sha256: str

    @model_validator(mode="after")
    def exact(self):
        if any(Path(value).is_absolute() for value in (self.evidence_root, self.asset_root)):
            raise ValueError("Protocol paths must be relative")
        expected = _allocation(self.profile)
        if (self.source_interval, self.case_seeds) != expected:
            raise ValueError("Bar overlap allocation changed")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Bar overlap protocol body seal mismatch")
        return self


def _allocation(profile: str) -> tuple[tuple[int, int], tuple[int, int, int, int, int]]:
    allocations = {
        "bar_overlap_transport_placement_protocol_v1": (
            TRANSPORT_TO_PLACEMENT,
            CASE_SEEDS,
        ),
        "bar_overlap_transport_placement_protocol_v2": (V2_SOURCE_INTERVAL, V2_CASE_SEEDS),
        "bar_left_contact_entry_protocol_v3": (V3_SOURCE_INTERVAL, V3_CASE_SEEDS),
        "bar_placement_progress_protocol_v4": (V4_SOURCE_INTERVAL, V4_CASE_SEEDS),
        "bar_placement_contact_entry_protocol_v5": (V5_SOURCE_INTERVAL, V5_CASE_SEEDS),
        "bar_margin_completion_protocol_v6": (V6_SOURCE_INTERVAL, V6_CASE_SEEDS),
        "bar_late_left_contact_protocol_v7": (V7_SOURCE_INTERVAL, V7_CASE_SEEDS),
        "bar_late_workbench_overlap_protocol_v8": (V8_SOURCE_INTERVAL, V8_CASE_SEEDS),
    }
    try:
        return allocations[profile]
    except KeyError as error:
        raise ValueError("Unsupported bar overlap protocol profile") from error


def _verified_diagnosis(store: EvidenceStore, run_id: str, *, profile: str):
    diagnosis = store.verify(run_id)
    component = diagnosis.metrics.get("component", {})
    common = (
        diagnosis.kind != "single_skill_physical_failure_analysis"
        or diagnosis.outcome != "completed"
        or component.get("skill_id") != "bar_place_and_return"
        or component.get("physical_success") is not False
    )
    if profile == "bar_left_contact_entry_protocol_v3":
        forbidden = component.get("forbidden_contact_events")
        entry_contact = any(
            any(str(name).startswith("left/") for name in contact)
            for event in forbidden or []
            for contact in event.get("bad", [])
        )
        valid = (
            diagnosis.manifest_sha256 == ENTRY_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256
            and component.get("recorded_autonomous_skill_actions") == 1
            and component.get("rejected_action_log_actions") == 1
            and component.get("maximum_overlap_m", float("inf")) <= 0.0025
            and entry_contact
        )
    elif profile == "bar_placement_progress_protocol_v4":
        valid = (
            diagnosis.manifest_sha256 == PLACEMENT_PROGRESS_FAILURE_ANALYSIS_MANIFEST_SHA256
            and component.get("recorded_autonomous_skill_actions") == 1900
            and component.get("rejected_action_log_actions") == 0
            and component.get("forbidden_contact_events") == []
            and component.get("maximum_target_displacement_m", 0.0) >= 0.2
            and "readiness not reached" in str(component.get("failure_reason", ""))
        )
    elif profile == "bar_margin_completion_protocol_v6":
        valid = (
            diagnosis.manifest_sha256 == MARGIN_COMPLETION_FAILURE_ANALYSIS_MANIFEST_SHA256
            and component.get("recorded_autonomous_skill_actions") == 1900
            and component.get("confirmed_action_log_actions") == 1900
            and component.get("rejected_action_log_actions") == 0
            and component.get("forbidden_contact_events") == []
            and component.get("maximum_overtravel_m") == 0.0
            and component.get("maximum_target_displacement_m", 0.0) >= 0.2
            and "readiness not reached" in str(component.get("failure_reason", ""))
        )
    elif profile == "bar_placement_contact_entry_protocol_v5":
        forbidden = component.get("forbidden_contact_events")
        left_practice_contact = any(
            any(
                str(name).startswith("left/") and str(other) == "practice_object"
                for name, other in event.get("bad", [])
            )
            for event in forbidden or []
        )
        valid = (
            diagnosis.manifest_sha256 == PLACEMENT_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256
            and component.get("recorded_autonomous_skill_actions") == 1
            and component.get("rejected_action_log_actions") == 1
            and component.get("maximum_overlap_m", float("inf")) <= 0.0025
            and component.get("maximum_overtravel_m") == 0.0
            and left_practice_contact
        )
    elif profile == "bar_late_left_contact_protocol_v7":
        forbidden = component.get("forbidden_contact_events")
        left_practice_contact = any(
            any(
                (str(name).startswith("left/") and str(other) == "practice_object")
                or (str(other).startswith("left/") and str(name) == "practice_object")
                for name, other in event.get("bad", [])
            )
            for event in forbidden or []
        )
        valid = (
            diagnosis.manifest_sha256 == LATE_LEFT_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256
            and component.get("recorded_autonomous_skill_actions") == 24
            and component.get("confirmed_action_log_actions") == 24
            and component.get("rejected_action_log_actions") == 1
            and component.get("maximum_overtravel_m") == 0.0
            and component.get("maximum_target_displacement_m", 0.0) >= 0.05
            and left_practice_contact
        )
    elif profile == "bar_late_workbench_overlap_protocol_v8":
        valid = (
            diagnosis.manifest_sha256 == LATE_WORKBENCH_OVERLAP_FAILURE_ANALYSIS_MANIFEST_SHA256
            and component.get("recorded_autonomous_skill_actions") == 255
            and component.get("confirmed_action_log_actions") == 255
            and component.get("rejected_action_log_actions") == 1
            and component.get("maximum_overtravel_m") == 0.0
            and component.get("maximum_overlap_m", 0.0) > 0.0025
            and component.get("maximum_target_displacement_m", 0.0) >= 0.15
            and ["workbench", "practice_object"]
            in component.get("overlap_peak", {}).get("contacts", [])
        )
    else:
        valid = (
            component.get("forbidden_contact_events") == []
            and component.get("maximum_overlap_m", 0) > 0.0025
        )
    if common or not valid:
        raise ValueError("Protocol requires the localized unpromoted bar overlap diagnosis")
    evaluation = store.verify(component["evaluation_run_id"])
    if evaluation.manifest_sha256 != component.get("evaluation_manifest_sha256"):
        raise ValueError("Diagnosis evaluation binding changed")
    return diagnosis, evaluation


def create_bar_overlap_correction_protocol(
    *,
    evidence_root: Path,
    diagnosis_run_id: str,
    destination: Path,
    profile="bar_overlap_transport_placement_protocol_v1",
):
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Bar overlap protocol already exists")
    evidence_root = Path(evidence_root).resolve(strict=True)
    interval, seeds = _allocation(profile)
    diagnosis, evaluation = _verified_diagnosis(
        EvidenceStore(evidence_root), diagnosis_run_id, profile=profile
    )
    assets = ASSETS.with_name("dinner_teacher_v2").resolve(strict=True)
    body = {
        "schema_version": 1,
        "profile": profile,
        "evidence_root": os.path.relpath(evidence_root, destination.parent),
        "diagnosis_run_id": diagnosis.run_id,
        "diagnosis_manifest_sha256": diagnosis.manifest_sha256,
        "evaluation_run_id": evaluation.run_id,
        "evaluation_manifest_sha256": evaluation.manifest_sha256,
        "asset_root": os.path.relpath(assets, destination.parent),
        "asset_manifest_sha256": digest_file(assets / "manifest.json"),
        "plan_sha256": digest_file(assets / "plan.json.gz"),
        "source_interval": interval,
        "case_seeds": seeds,
        "overlap_limit_m": 0.0025,
        "allocation_rule": "one_teacher_attempt_per_frozen_case_no_automatic_retry",
        "learned_execution": False,
        "release_qualified": False,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    protocol = BarOverlapCorrectionProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical(protocol.model_dump(mode="json")) + b"\n")
    return protocol


def load_bar_overlap_correction_protocol(path: Path):
    path = Path(path).resolve(strict=True)
    protocol = BarOverlapCorrectionProtocol.model_validate_json(path.read_bytes())
    store = EvidenceStore((path.parent / protocol.evidence_root).resolve(strict=True))
    diagnosis, evaluation = _verified_diagnosis(
        store, protocol.diagnosis_run_id, profile=protocol.profile
    )
    assets = (path.parent / protocol.asset_root).resolve(strict=True)
    if (
        diagnosis.manifest_sha256 != protocol.diagnosis_manifest_sha256
        or evaluation.run_id != protocol.evaluation_run_id
        or evaluation.manifest_sha256 != protocol.evaluation_manifest_sha256
        or digest_file(assets / "manifest.json") != protocol.asset_manifest_sha256
        or digest_file(assets / "plan.json.gz") != protocol.plan_sha256
    ):
        raise ValueError("Frozen bar overlap protocol binding changed")
    return protocol
