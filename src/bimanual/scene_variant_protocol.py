"""Write-once six-family dinner perturbation allocation and scene bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
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
    variant, report = dinner_scene_variant(
        (directory / "base-scene.xml").read_text(), seed=seed, family=family
    )
    (directory / "scene.xml").write_text(variant)
    (directory / "variant.json").write_bytes(canonical(report) + b"\n")
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
    }
    return store.seal(
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
