"""Freeze bounded corrective-data collection from a sealed component diagnosis."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bimanual.dinner_teacher import ASSETS
from bimanual.evidence import EvidenceStore, canonical, digest_file

DIAGNOSIS_KIND = "six_skill_physical_failure_analysis"
FAMILIES = (
    ("bar_contact_avoidance", ("bar_place_and_return",)),
    ("approach_contact", ("cup_pick_place", "plate_pick_place", "fork_retrieve_place")),
    ("grasp_lift", ("spoon_retrieve_place",)),
    ("drawer_pull", ("drawer_open",)),
)


class CorrectiveFamily(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    family_id: Literal["bar_contact_avoidance", "approach_contact", "grasp_lift", "drawer_pull"]
    skills: tuple[str, ...] = Field(min_length=1, max_length=3)
    case_seeds: tuple[int, ...] = Field(min_length=5, max_length=5)
    teacher_assisted: Literal[True] = True
    learned_execution: Literal[False] = False
    training_eligible: Literal[False] = False


class SkillCorrectiveCollectionProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile: Literal["six_skill_corrective_collection_protocol_v1"]
    evidence_root: str
    diagnosis_run_id: str
    diagnosis_manifest_sha256: str
    suite_run_id: str
    suite_manifest_sha256: str
    asset_root: str
    asset_manifest_sha256: str
    scene_sha256: str
    layout_sha256: str
    families: tuple[CorrectiveFamily, ...] = Field(min_length=4, max_length=4)
    allocation_rule: Literal["one_teacher_attempt_per_frozen_case_no_automatic_retry"]
    release_qualified: Literal[False] = False
    manifest_sha256: str

    @model_validator(mode="after")
    def exact_body(self):
        if any(Path(value).is_absolute() for value in (self.evidence_root, self.asset_root)):
            raise ValueError("Protocol paths must be relative")
        expected = tuple((family, skills) for family, skills in FAMILIES)
        actual = tuple((family.family_id, family.skills) for family in self.families)
        if actual != expected:
            raise ValueError("Corrective families or skills changed")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Corrective collection protocol body seal mismatch")
        return self


def _family_rows() -> list[dict]:
    return [
        CorrectiveFamily(
            family_id=family,
            skills=skills,
            case_seeds=tuple(range(51000 + index * 5, 51005 + index * 5)),
        ).model_dump(mode="json")
        for index, (family, skills) in enumerate(FAMILIES)
    ]


def create_skill_corrective_collection_protocol(
    *, evidence_root: Path, diagnosis_run_id: str, destination: Path
) -> SkillCorrectiveCollectionProtocol:
    """Create a write-once collection allocation after a verified failed suite."""

    destination = Path(destination).resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Corrective collection protocol already exists")
    evidence_root = Path(evidence_root).resolve(strict=True)
    diagnosis = EvidenceStore(evidence_root).verify(diagnosis_run_id)
    components = diagnosis.metrics.get("components")
    if (
        diagnosis.kind != DIAGNOSIS_KIND
        or diagnosis.outcome != "completed"
        or diagnosis.metrics.get("component_passes") != 0
        or diagnosis.metrics.get("release_qualified") is not False
        or not isinstance(components, list)
        or {row.get("skill_id") for row in components}
        != {skill for _, skills in FAMILIES for skill in skills}
    ):
        raise ValueError("Protocol requires the complete unpromoted six-skill failure diagnosis")
    suite = EvidenceStore(evidence_root).verify(diagnosis.metrics["suite_run_id"])
    if suite.manifest_sha256 != diagnosis.metrics.get("suite_manifest_sha256"):
        raise ValueError("Diagnosis does not bind its physical suite")
    assets = ASSETS.with_name("dinner_teacher_v2").resolve(strict=True)
    manifest = json.loads((assets / "manifest.json").read_bytes())
    if manifest.get("files", {}).get("scene.xml") != digest_file(assets / "scene.xml"):
        raise ValueError("Corrective protocol asset scene integrity mismatch")
    body = {
        "schema_version": 1,
        "profile": "six_skill_corrective_collection_protocol_v1",
        "evidence_root": os.path.relpath(evidence_root, destination.parent),
        "diagnosis_run_id": diagnosis.run_id,
        "diagnosis_manifest_sha256": diagnosis.manifest_sha256,
        "suite_run_id": suite.run_id,
        "suite_manifest_sha256": suite.manifest_sha256,
        "asset_root": os.path.relpath(assets, destination.parent),
        "asset_manifest_sha256": digest_file(assets / "manifest.json"),
        "scene_sha256": digest_file(assets / "scene.xml"),
        "layout_sha256": digest_file(assets / "layout.json"),
        "families": _family_rows(),
        "allocation_rule": "one_teacher_attempt_per_frozen_case_no_automatic_retry",
        "release_qualified": False,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = SkillCorrectiveCollectionProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_skill_corrective_collection_protocol(path: Path) -> SkillCorrectiveCollectionProtocol:
    path = Path(path).resolve(strict=True)
    protocol = SkillCorrectiveCollectionProtocol.model_validate_json(path.read_bytes())
    evidence_root = (path.parent / protocol.evidence_root).resolve(strict=True)
    diagnosis = EvidenceStore(evidence_root).verify(protocol.diagnosis_run_id)
    if (
        diagnosis.kind != DIAGNOSIS_KIND
        or diagnosis.manifest_sha256 != protocol.diagnosis_manifest_sha256
        or diagnosis.metrics.get("suite_run_id") != protocol.suite_run_id
        or diagnosis.metrics.get("suite_manifest_sha256") != protocol.suite_manifest_sha256
    ):
        raise ValueError("Corrective diagnosis binding changed")
    assets = (path.parent / protocol.asset_root).resolve(strict=True)
    if (
        digest_file(assets / "manifest.json") != protocol.asset_manifest_sha256
        or digest_file(assets / "scene.xml") != protocol.scene_sha256
        or digest_file(assets / "layout.json") != protocol.layout_sha256
    ):
        raise ValueError("Corrective collection assets changed")
    return protocol
