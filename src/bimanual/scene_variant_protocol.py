"""Write-once six-family dinner perturbation allocation and scene bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.dual_arm import DualArm
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.scene_variants import FAMILIES, dinner_scene_variant

DEFAULT_DIAGNOSTIC_SEED = 29001
DEFAULT_COMBINED_TEST_SEEDS = tuple(range(30001, 30011))


def _assets() -> Path:
    return Path(str(files("bimanual") / "models/dinner_teacher_v2"))


def _bindings() -> dict:
    assets = _assets()
    manifest = json.loads((assets / "manifest.json").read_text())
    expected = {"scene.xml", "layout.json", "plan.json.gz"}
    if manifest.get("schema_version") != 1 or set(manifest.get("files", {})) != expected:
        raise ValueError("Invalid nominal dinner assets for perturbation protocol")
    for name, digest in manifest["files"].items():
        if digest_file(assets / name) != digest:
            raise ValueError(f"Nominal dinner asset changed: {name}")
    generator = Path(__file__).with_name("scene_variants.py")
    return {
        "base_scene_sha256": manifest["files"]["scene.xml"],
        "base_layout_sha256": manifest["files"]["layout.json"],
        "base_plan_sha256": manifest["files"]["plan.json.gz"],
        "base_manifest_sha256": digest_file(assets / "manifest.json"),
        "generator_sha256": digest_file(generator),
    }


class DinnerPerturbationProtocol(Contract):
    profile: Literal["dinner_six_family_perturbation_protocol_v1"] = (
        "dinner_six_family_perturbation_protocol_v1"
    )
    families: tuple[
        Literal["placement", "mass", "friction", "shape", "lighting", "background"], ...
    ]
    diagnostic_seed: Annotated[int, Field(strict=True, ge=0, lt=2**32)]
    combined_test_seeds: Annotated[tuple[int, ...], Field(min_length=10, max_length=10)]
    base_scene_sha256: Digest
    base_layout_sha256: Digest
    base_plan_sha256: Digest
    base_manifest_sha256: Digest
    generator_sha256: Digest
    selection_rule: Literal[
        "one_factor_diagnostics_then_all_six_combined_on_every_frozen_test_seed"
    ] = "one_factor_diagnostics_then_all_six_combined_on_every_frozen_test_seed"
    retain_every_attempt: Literal[True] = True
    generated_scenes_validated: Literal[False] = False
    task_success: None = None
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_allocation(self):
        if self.families != FAMILIES:
            raise ValueError("Perturbation protocol must include all six ordered families")
        if len(set(self.combined_test_seeds)) != 10:
            raise ValueError("Combined perturbation test seeds must be ten unique values")
        if self.diagnostic_seed in self.combined_test_seeds:
            raise ValueError("One-factor diagnostic seed must not be a combined test seed")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Dinner perturbation protocol body seal mismatch")
        return self


def create_dinner_perturbation_protocol(
    destination: Path,
    *,
    diagnostic_seed: int = DEFAULT_DIAGNOSTIC_SEED,
    combined_test_seeds: tuple[int, ...] = DEFAULT_COMBINED_TEST_SEEDS,
) -> DinnerPerturbationProtocol:
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Dinner perturbation protocol already exists")
    body = {
        "schema_version": 1,
        "profile": "dinner_six_family_perturbation_protocol_v1",
        "families": FAMILIES,
        "diagnostic_seed": diagnostic_seed,
        "combined_test_seeds": combined_test_seeds,
        **_bindings(),
        "selection_rule": (
            "one_factor_diagnostics_then_all_six_combined_on_every_frozen_test_seed"
        ),
        "retain_every_attempt": True,
        "generated_scenes_validated": False,
        "task_success": None,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    protocol = DinnerPerturbationProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(canonical(protocol.model_dump(mode="json")) + b"\n")
    return protocol


def load_dinner_perturbation_protocol(path: Path) -> DinnerPerturbationProtocol:
    protocol = DinnerPerturbationProtocol.model_validate_json(Path(path).read_bytes())
    for key, value in _bindings().items():
        if getattr(protocol, key) != value:
            raise ValueError(f"Dinner perturbation source identity changed: {key}")
    return protocol


@dataclass(frozen=True)
class VerifiedSceneVariant:
    root: Path
    manifest: Manifest
    protocol: DinnerPerturbationProtocol
    family: str
    seed: int
    scene_sha256: str
    layout_sha256: str


def load_scene_variant_bundle(run_root: Path) -> VerifiedSceneVariant:
    """Verify prepared scene, base sources, allocation and scoring layout."""
    run_root = run_root.resolve(strict=True)
    manifest = EvidenceStore(run_root.parent.parent).verify(run_root.name)
    if manifest.kind != "dinner_scene_variant" or manifest.outcome != "prepared" or manifest.claims:
        raise ValueError("Expected a prepared non-claiming dinner scene variant")
    protocol = load_dinner_perturbation_protocol(run_root / "protocol.json")
    family, seed = manifest.config.get("family"), manifest.config.get("seed")
    if family == "combined":
        allocated = seed in protocol.combined_test_seeds
    else:
        allocated = family in protocol.families and seed == protocol.diagnostic_seed
    if not allocated:
        raise ValueError("Prepared scene is outside its frozen allocation")
    if digest_file(run_root / "base-scene.xml") != protocol.base_scene_sha256:
        raise ValueError("Prepared scene base XML differs from its protocol")
    if digest_file(run_root / "base-layout.json") != protocol.base_layout_sha256:
        raise ValueError("Prepared scene base layout differs from its protocol")
    report = json.loads((run_root / "variant.json").read_text())
    scene_sha = digest_file(run_root / "scene.xml")
    if (
        report.get("profile") != "dinner_scene_variants_v1"
        or report.get("requested_family") != family
        or report.get("seed") != seed
        or report.get("base_xml_sha256") != protocol.base_scene_sha256
        or report.get("variant_xml_sha256") != scene_sha
        or report.get("evaluation_success") is not None
    ):
        raise ValueError("Prepared scene report or generated XML identity mismatch")
    base_layout = json.loads((run_root / "base-layout.json").read_text())
    expected_layout = dict(base_layout, scene_sha256=scene_sha)
    layout = json.loads((run_root / "layout.json").read_text())
    if layout != expected_layout:
        raise ValueError("Prepared scene scoring layout changed beyond its scene binding")
    layout_sha = digest_file(run_root / "layout.json")
    if (
        manifest.metrics.get("protocol_manifest_sha256") != protocol.manifest_sha256
        or manifest.metrics.get("scene_sha256") != scene_sha
        or manifest.metrics.get("layout_sha256") != layout_sha
        or manifest.metrics.get("evaluation_attempted") is not False
        or manifest.metrics.get("task_success") is not None
    ):
        raise ValueError("Prepared scene evidence metrics disagree with its files")
    return VerifiedSceneVariant(
        root=run_root,
        manifest=manifest,
        protocol=protocol,
        family=family,
        seed=seed,
        scene_sha256=scene_sha,
        layout_sha256=layout_sha,
    )


def create_scene_variant_bundle(
    *,
    protocol_path: Path,
    family: str,
    seed: int,
    store: EvidenceStore,
    project_root: Path,
) -> Manifest:
    """Materialize a frozen scene only; do not execute a teacher or learned policy."""
    protocol_path = protocol_path.resolve(strict=True)
    protocol = load_dinner_perturbation_protocol(protocol_path)
    if family == "combined":
        if seed not in protocol.combined_test_seeds:
            raise ValueError("Combined scene seed is outside the frozen test allocation")
    elif family in protocol.families:
        if seed != protocol.diagnostic_seed:
            raise ValueError("One-factor scene must use the frozen diagnostic seed")
    else:
        raise ValueError("Scene family is outside the frozen perturbation protocol")
    directory = store.new_run()
    assets = _assets()
    shutil.copyfile(protocol_path, directory / "protocol.json")
    shutil.copyfile(assets / "scene.xml", directory / "base-scene.xml")
    shutil.copyfile(assets / "layout.json", directory / "base-layout.json")
    variant, report = dinner_scene_variant(
        (directory / "base-scene.xml").read_text(), seed=seed, family=family
    )
    (directory / "scene.xml").write_text(variant)
    (directory / "variant.json").write_bytes(canonical(report) + b"\n")
    layout = json.loads((directory / "base-layout.json").read_text())
    layout["scene_sha256"] = digest_file(directory / "scene.xml")
    (directory / "layout.json").write_bytes(canonical(layout) + b"\n")
    model = DualArm(xml=variant, physics_hz=1000).model
    metrics = {
        "scene_compiles": True,
        "nq": model.nq,
        "nv": model.nv,
        "family_count": len(report["families"]),
        "physical_layout_varied": report["physical_layout_varied"],
        "visual_conditions_varied": report["visual_conditions_varied"],
        "evaluation_attempted": False,
        "task_success": None,
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "scene_sha256": digest_file(directory / "scene.xml"),
        "layout_sha256": digest_file(directory / "layout.json"),
    }
    result = store.seal(
        directory,
        kind="dinner_scene_variant",
        outcome="prepared",
        config={
            "protocol": str(protocol_path),
            "family": family,
            "seed": seed,
            "mode": "pre_episode_scene_generation_only",
        },
        metrics=metrics,
        source=provenance(project_root.resolve()),
        claims=[],
    )
    load_scene_variant_bundle(directory)
    return result
