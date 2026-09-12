"""Frozen measured-state hand-off continuity correction allocation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest, Identifier
from bimanual.dinner_teacher import ASSETS
from bimanual.dual_arm import JOINT_ORDER
from bimanual.evidence import EvidenceStore, canonical, digest_file

OFFSET_RAD = 0.015
CASE_SEEDS = tuple(range(41000, 41009))
RECEIVER_JOINT_INDICES = (6, 7, 8, 9)
PHASE_BOUNDARIES = {
    "teacher_prefix_start": 0,
    "teacher_prefix_end": 310,
    "correction_teacher_goal": 369,
    "correction_replay_start": 370,
    "correction_replay_end": 530,
    "validation_tail_start": 530,
    "validation_tail_end": 630,
}


class HandoffContinuityCase(Contract):
    case_id: Identifier
    seed: int = Field(strict=True, ge=0)
    receiver_joint_index: int | None = Field(default=None, strict=True, ge=6, le=9)
    offset_rad: float = Field(default=0.0, ge=-OFFSET_RAD, le=OFFSET_RAD)

    @model_validator(mode="after")
    def zero_or_axis_offset(self):
        if (self.receiver_joint_index is None) != (self.offset_rad == 0):
            raise ValueError("Only the baseline case may have no receiver joint offset")
        if self.receiver_joint_index is not None and abs(self.offset_rad) != OFFSET_RAD:
            raise ValueError("Axis cases must use the frozen signed offset")
        return self


def expected_cases() -> tuple[HandoffContinuityCase, ...]:
    rows = [HandoffContinuityCase(case_id="receiver-baseline", seed=CASE_SEEDS[0])]
    seed = iter(CASE_SEEDS[1:])
    for joint_index in RECEIVER_JOINT_INDICES:
        joint_name = JOINT_ORDER[joint_index].replace("/", "-")
        for sign, label in ((-1, "minus"), (1, "plus")):
            rows.append(
                HandoffContinuityCase(
                    case_id=f"receiver-{joint_name}-{label}",
                    seed=next(seed),
                    receiver_joint_index=joint_index,
                    offset_rad=sign * OFFSET_RAD,
                )
            )
    return tuple(rows)


def _runtime_sources() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    names = (
        "handoff_continuity_protocol.py",
        "handoff_continuity_teacher.py",
        "dinner_teacher.py",
        "teacher.py",
    )
    return {name: digest_file(root / name) for name in names if (root / name).is_file()}


class HandoffContinuityProtocol(Contract):
    profile: Literal["handoff_receiver_continuity_collection_protocol_v1"] = (
        "handoff_receiver_continuity_collection_protocol_v1"
    )
    evidence_root: str
    diagnosis_run_id: Identifier
    diagnosis_manifest_sha256: Digest
    diagnosis_finding: Literal[
        "receiver close/shared hold through donor release, with the receiver gripper "
        "held closed and varied measured approach states"
    ]
    asset_root: str
    asset_manifest_file_sha256: Digest
    asset_source_manifest_sha256: Digest
    scene_sha256: Digest
    layout_sha256: Digest
    plan_sha256: Digest
    phase_boundaries: dict[str, int]
    receiver_joint_indices: tuple[int, int, int, int] = RECEIVER_JOINT_INDICES
    receiver_joint_names: tuple[str, str, str, str]
    acquisition_offset_rad: Literal[0.015] = OFFSET_RAD
    cases: Annotated[tuple[HandoffContinuityCase, ...], Field(min_length=9, max_length=9)]
    runtime_sources: dict[str, Digest]
    allocation_rule: Literal["one_attempt_per_case_no_automatic_retry"] = (
        "one_attempt_per_case_no_automatic_retry"
    )
    correction_scope: Literal["receiver_close_shared_hold_donor_release"] = (
        "receiver_close_shared_hold_donor_release"
    )
    teacher_assistance: Literal[True] = True
    learned_execution: Literal[False] = False
    release_qualified: Literal[False] = False
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_protocol(self):
        for value in (self.evidence_root, self.asset_root):
            if not value or Path(value).is_absolute():
                raise ValueError("Protocol source roots must be relative to the protocol file")
        if self.phase_boundaries != PHASE_BOUNDARIES:
            raise ValueError("Hand-off correction phase boundaries changed")
        if self.receiver_joint_names != tuple(
            JOINT_ORDER[index] for index in RECEIVER_JOINT_INDICES
        ):
            raise ValueError("Receiver joint ordering changed")
        if self.cases != expected_cases():
            raise ValueError("Hand-off continuity case allocation changed")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Hand-off continuity protocol body seal mismatch")
        return self


def create_handoff_continuity_protocol(
    *, evidence_root: Path, diagnosis_run_id: str, destination: Path
) -> HandoffContinuityProtocol:
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Hand-off continuity protocol already exists")
    evidence_root = Path(evidence_root).resolve(strict=True)
    diagnosis = EvidenceStore(evidence_root).verify(diagnosis_run_id)
    finding = diagnosis.metrics.get("recommended_data_region")
    if (
        diagnosis.kind != "handoff_continuity_failure_analysis"
        or diagnosis.outcome != "completed"
        or diagnosis.metrics.get("physical_success") is not False
        or diagnosis.metrics.get("checkpoint_promoted") is not False
        or finding
        != "receiver close/shared hold through donor release, with the receiver gripper "
        "held closed and varied measured approach states"
    ):
        raise ValueError("Protocol requires the verified unpromoted continuity diagnosis")
    assets = ASSETS.with_name("dinner_teacher_v2").resolve(strict=True)
    asset_manifest_path = assets / "manifest.json"
    asset_manifest = json.loads(asset_manifest_path.read_bytes())
    files = asset_manifest.get("files", {})
    expected = {
        "scene.xml": digest_file(assets / "scene.xml"),
        "layout.json": digest_file(assets / "layout.json"),
        "plan.json.gz": digest_file(assets / "plan.json.gz"),
    }
    if files != expected:
        raise ValueError("Dinner teacher asset manifest does not bind exact correction inputs")
    body = {
        "schema_version": 1,
        "profile": "handoff_receiver_continuity_collection_protocol_v1",
        "evidence_root": os.path.relpath(evidence_root, destination.parent),
        "diagnosis_run_id": diagnosis.run_id,
        "diagnosis_manifest_sha256": diagnosis.manifest_sha256,
        "diagnosis_finding": finding,
        "asset_root": os.path.relpath(assets, destination.parent),
        "asset_manifest_file_sha256": digest_file(asset_manifest_path),
        "asset_source_manifest_sha256": asset_manifest["source_manifest_sha256"],
        "scene_sha256": expected["scene.xml"],
        "layout_sha256": expected["layout.json"],
        "plan_sha256": expected["plan.json.gz"],
        "phase_boundaries": PHASE_BOUNDARIES,
        "receiver_joint_indices": RECEIVER_JOINT_INDICES,
        "receiver_joint_names": [JOINT_ORDER[index] for index in RECEIVER_JOINT_INDICES],
        "acquisition_offset_rad": OFFSET_RAD,
        "cases": [case.model_dump(mode="json") for case in expected_cases()],
        "runtime_sources": _runtime_sources(),
        "allocation_rule": "one_attempt_per_case_no_automatic_retry",
        "correction_scope": "receiver_close_shared_hold_donor_release",
        "teacher_assistance": True,
        "learned_execution": False,
        "release_qualified": False,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = HandoffContinuityProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_handoff_continuity_protocol(path: Path) -> HandoffContinuityProtocol:
    path = Path(path).resolve(strict=True)
    protocol = HandoffContinuityProtocol.model_validate_json(path.read_bytes())
    evidence_root = (path.parent / protocol.evidence_root).resolve(strict=True)
    diagnosis = EvidenceStore(evidence_root).verify(protocol.diagnosis_run_id)
    if (
        diagnosis.manifest_sha256 != protocol.diagnosis_manifest_sha256
        or diagnosis.kind != "handoff_continuity_failure_analysis"
        or diagnosis.metrics.get("recommended_data_region") != protocol.diagnosis_finding
        or diagnosis.metrics.get("checkpoint_promoted") is not False
    ):
        raise ValueError("Frozen continuity diagnosis changed")
    assets = (path.parent / protocol.asset_root).resolve(strict=True)
    if (
        digest_file(assets / "manifest.json") != protocol.asset_manifest_file_sha256
        or digest_file(assets / "scene.xml") != protocol.scene_sha256
        or digest_file(assets / "layout.json") != protocol.layout_sha256
        or digest_file(assets / "plan.json.gz") != protocol.plan_sha256
        or _runtime_sources() != protocol.runtime_sources
    ):
        raise ValueError("Frozen continuity source changed")
    return protocol
