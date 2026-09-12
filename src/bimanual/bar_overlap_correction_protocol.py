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


class BarOverlapCorrectionProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile: Literal[
        "bar_overlap_transport_placement_protocol_v1", "bar_overlap_transport_placement_protocol_v2"
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
        expected = (
            (TRANSPORT_TO_PLACEMENT, CASE_SEEDS)
            if self.profile.endswith("v1")
            else (V2_SOURCE_INTERVAL, V2_CASE_SEEDS)
        )
        if (self.source_interval, self.case_seeds) != expected:
            raise ValueError("Bar overlap allocation changed")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Bar overlap protocol body seal mismatch")
        return self


def _verified_diagnosis(store: EvidenceStore, run_id: str):
    diagnosis = store.verify(run_id)
    component = diagnosis.metrics.get("component", {})
    if (
        diagnosis.kind != "single_skill_physical_failure_analysis"
        or diagnosis.outcome != "completed"
        or component.get("skill_id") != "bar_place_and_return"
        or component.get("forbidden_contact_events") != []
        or component.get("maximum_overlap_m", 0) <= 0.0025
        or component.get("physical_success") is not False
    ):
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
    diagnosis, evaluation = _verified_diagnosis(EvidenceStore(evidence_root), diagnosis_run_id)
    assets = ASSETS.with_name("dinner_teacher_v2").resolve(strict=True)
    interval, seeds = (
        (TRANSPORT_TO_PLACEMENT, CASE_SEEDS)
        if profile.endswith("v1")
        else (V2_SOURCE_INTERVAL, V2_CASE_SEEDS)
    )
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
    diagnosis, evaluation = _verified_diagnosis(store, protocol.diagnosis_run_id)
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
