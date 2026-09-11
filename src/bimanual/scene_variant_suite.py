"""Resumable preparation and verification of all frozen perturbation scenes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.scene_variant_protocol import (
    DinnerPerturbationProtocol,
    create_scene_variant_bundle,
    load_dinner_perturbation_protocol,
    load_scene_variant_bundle,
)


class SceneVariantSuiteEntry(Contract):
    case_id: str = Field(pattern=r"^[a-z]+-[0-9]+$")
    family: Literal["placement", "mass", "friction", "shape", "lighting", "background", "combined"]
    seed: int = Field(strict=True, ge=0, lt=2**32)
    run_id: str = Field(min_length=1)
    manifest_sha256: Digest
    scene_sha256: Digest
    layout_sha256: Digest


class SceneVariantSuiteIndex(Contract):
    profile: Literal["frozen_dinner_scene_variant_suite_v1"] = (
        "frozen_dinner_scene_variant_suite_v1"
    )
    protocol_manifest_sha256: Digest
    entries: Annotated[tuple[SceneVariantSuiteEntry, ...], Field(min_length=16, max_length=16)]
    evaluation_attempted: Literal[False] = False
    task_success: None = None

    @model_validator(mode="after")
    def unique_cases(self):
        if len({entry.case_id for entry in self.entries}) != len(self.entries):
            raise ValueError("Prepared scene suite contains duplicate case ids")
        if len({entry.run_id for entry in self.entries}) != len(self.entries):
            raise ValueError("Prepared scene suite reuses a child run")
        return self


def _cases(protocol: DinnerPerturbationProtocol) -> tuple[tuple[str, int], ...]:
    return tuple((family, protocol.diagnostic_seed) for family in protocol.families) + tuple(
        ("combined", seed) for seed in protocol.combined_test_seeds
    )


def _case_id(family: str, seed: int) -> str:
    return f"{family}-{seed}"


def _candidate_manifests(store: EvidenceStore, kind: str):
    for path in sorted((store.root / "runs").glob("*/manifest.json")):
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("kind") == kind:
            yield store.verify(path.parent.name)


def _children(
    store: EvidenceStore, protocol: DinnerPerturbationProtocol
) -> dict[tuple[str, int], list[Manifest]]:
    found = {case: [] for case in _cases(protocol)}
    for manifest in _candidate_manifests(store, "dinner_scene_variant"):
        key = (manifest.config.get("family"), manifest.config.get("seed"))
        if (
            key in found
            and manifest.metrics.get("protocol_manifest_sha256") == protocol.manifest_sha256
        ):
            verified = load_scene_variant_bundle(store.directory(manifest.run_id))
            if (verified.family, verified.seed) != key:
                raise ValueError("Prepared scene child identity changed during suite discovery")
            found[key].append(manifest)
    return found


def _entry(store: EvidenceStore, manifest: Manifest) -> SceneVariantSuiteEntry:
    verified = load_scene_variant_bundle(store.directory(manifest.run_id))
    return SceneVariantSuiteEntry(
        case_id=_case_id(verified.family, verified.seed),
        family=verified.family,
        seed=verified.seed,
        run_id=manifest.run_id,
        manifest_sha256=manifest.manifest_sha256,
        scene_sha256=verified.scene_sha256,
        layout_sha256=verified.layout_sha256,
    )


def load_scene_variant_suite(
    run_root: Path, *, protocol_path: Path
) -> tuple[Manifest, SceneVariantSuiteIndex]:
    run_root = run_root.resolve(strict=True)
    store = EvidenceStore(run_root.parent.parent)
    manifest = store.verify(run_root.name)
    if (
        manifest.kind != "dinner_scene_variant_suite"
        or manifest.outcome != "prepared"
        or manifest.claims
    ):
        raise ValueError("Expected a prepared non-claiming dinner scene suite")
    protocol = load_dinner_perturbation_protocol(protocol_path.resolve(strict=True))
    index = SceneVariantSuiteIndex.model_validate_json((run_root / "suite.json").read_bytes())
    if index.protocol_manifest_sha256 != protocol.manifest_sha256:
        raise ValueError("Prepared scene suite belongs to a different protocol")
    expected = tuple(_case_id(*case) for case in _cases(protocol))
    if tuple(entry.case_id for entry in index.entries) != expected:
        raise ValueError("Prepared scene suite does not contain the frozen ordered cases")
    for entry in index.entries:
        child = store.verify(entry.run_id)
        if child.manifest_sha256 != entry.manifest_sha256 or _entry(store, child) != entry:
            raise ValueError(f"Prepared scene suite child changed: {entry.case_id}")
    if (
        manifest.metrics.get("prepared_case_count") != len(expected)
        or manifest.metrics.get("protocol_manifest_sha256") != protocol.manifest_sha256
        or manifest.metrics.get("evaluation_attempted") is not False
        or manifest.metrics.get("task_success") is not None
    ):
        raise ValueError("Prepared scene suite metrics disagree with its frozen index")
    return manifest, index


def prepare_scene_variant_suite(
    *, protocol_path: Path, store: EvidenceStore, project_root: Path
) -> Manifest:
    """Resume missing scene inputs and seal exactly one complete ordered index."""
    protocol_path = protocol_path.resolve(strict=True)
    protocol = load_dinner_perturbation_protocol(protocol_path)
    existing_reports = [
        manifest
        for manifest in _candidate_manifests(store, "dinner_scene_variant_suite")
        if manifest.metrics.get("protocol_manifest_sha256") == protocol.manifest_sha256
    ]
    if len(existing_reports) > 1:
        raise ValueError("Multiple prepared scene suite reports match the frozen protocol")
    if existing_reports:
        manifest = existing_reports[0]
        load_scene_variant_suite(store.directory(manifest.run_id), protocol_path=protocol_path)
        return manifest
    found = _children(store, protocol)
    entries = []
    for family, seed in _cases(protocol):
        matches = found[(family, seed)]
        if len(matches) > 1:
            raise ValueError(f"Multiple prepared scenes match {_case_id(family, seed)}")
        if matches:
            child = matches[0]
        else:
            child = create_scene_variant_bundle(
                protocol_path=protocol_path,
                family=family,
                seed=seed,
                store=store,
                project_root=project_root,
            )
        entries.append(_entry(store, child))
    index = SceneVariantSuiteIndex(
        protocol_manifest_sha256=protocol.manifest_sha256,
        entries=tuple(entries),
    )
    directory = store.new_run()
    (directory / "protocol.json").write_bytes(protocol_path.read_bytes())
    (directory / "suite.json").write_bytes(canonical(index.model_dump(mode="json")) + b"\n")
    metrics = {
        "prepared_case_count": len(entries),
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "protocol_file_sha256": digest_file(protocol_path),
        "evaluation_attempted": False,
        "task_success": None,
    }
    result = store.seal(
        directory,
        kind="dinner_scene_variant_suite",
        outcome="prepared",
        config={"protocol": str(protocol_path), "selection": protocol.selection_rule},
        metrics=metrics,
        source=provenance(project_root.resolve()),
        claims=[],
    )
    load_scene_variant_suite(directory, protocol_path=protocol_path)
    return result
