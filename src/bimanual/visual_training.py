"""Frozen visual seed allocation; no recording, ingestion or quality claims."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import canonical, digest_file
from bimanual.skill_views import PLAN_SHA256_V2

Seed = Annotated[int, Field(strict=True, ge=0, lt=2**32)]
BASE_SCENE_SHA256 = "3aa969c78966a920508553c4800bc46aa8a0cac190a2aa487fc7948c2266ed92"


class VisualTrainingProtocol(Contract):
    profile: Literal["dinner_visual_training_protocol_v1"] = "dinner_visual_training_protocol_v1"
    recipe: Literal["v2"] = "v2"
    generator_profile: Literal["dinner_visual_variants_v1"] = "dinner_visual_variants_v1"
    physical_layout_count: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    scope: Literal["visual_conditions_only"] = "visual_conditions_only"
    validated_recordings: Literal[False] = False
    previously_used_development_seeds: tuple[Seed, ...] = (0, 7)
    training_seeds: tuple[Seed, ...] = Field(min_length=1)
    validation_seeds: tuple[Seed, ...] = Field(min_length=1)
    test_seeds: tuple[Seed, ...] = Field(min_length=1)
    base_scene_sha256: Digest
    plan_sha256: Digest
    teacher_assets_manifest_sha256: Digest
    generator_sha256: Digest
    manifest_sha256: Digest

    @model_validator(mode="after")
    def allocation_and_seal(self):
        allocations = (self.training_seeds, self.validation_seeds, self.test_seeds)
        if any(len(set(seeds)) != len(seeds) for seeds in allocations):
            raise ValueError("Duplicate seeds within a split")
        combined = tuple(seed for seeds in allocations for seed in seeds)
        if len(set(combined)) != len(combined):
            raise ValueError("Visual seed allocations must be disjoint")
        exposed = self.previously_used_development_seeds
        if len(set(exposed)) != len(exposed) or not {0, 7}.issubset(exposed):
            raise ValueError(
                "Development exclusions must uniquely include known seeds zero and seven"
            )
        if set(exposed).intersection((*self.validation_seeds, *self.test_seeds)):
            raise ValueError("Held-out allocation includes seeds with development exposure")
        if self.base_scene_sha256 != BASE_SCENE_SHA256 or self.plan_sha256 != PLAN_SHA256_V2:
            raise ValueError("Unsupported base dinner scene or v2 plan")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Visual protocol seal mismatch")
        return self

    def require_training_seed(self, seed: int) -> None:
        """Allocation check only; never authorizes an unverified source recording."""
        if type(seed) is not int or seed not in self.training_seeds:
            raise ValueError("Source seed is outside the frozen training allocation")


def _bindings(assets_path: Path | None, generator_path: Path | None) -> dict:
    assets = assets_path or Path(str(files("bimanual") / "models/dinner_teacher_v2"))
    generator = generator_path or Path(__file__).with_name("visual_variants.py")
    manifest = json.loads((assets / "manifest.json").read_text())
    for name in ("scene.xml", "layout.json", "plan.json.gz"):
        if digest_file(assets / name) != manifest.get("files", {}).get(name):
            raise ValueError("Teacher asset identity mismatch")
    scene = digest_file(assets / "scene.xml")
    plan = digest_file(assets / "plan.json.gz")
    if scene != BASE_SCENE_SHA256 or plan != PLAN_SHA256_V2 or manifest.get("action_count") != 5049:
        raise ValueError("Unsupported base dinner assets")
    return dict(
        base_scene_sha256=scene,
        plan_sha256=plan,
        teacher_assets_manifest_sha256=digest_file(assets / "manifest.json"),
        generator_sha256=digest_file(generator),
    )


def create_visual_training_protocol(
    path: Path,
    *,
    training_seeds: tuple[int, ...],
    validation_seeds: tuple[int, ...],
    test_seeds: tuple[int, ...],
    assets_path: Path | None = None,
    generator_path: Path | None = None,
    previously_used_development_seeds: tuple[int, ...] = (0, 7),
) -> VisualTrainingProtocol:
    """Write once before collecting variants. Attempts belong in separate evidence."""
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Visual training protocol already exists")
    body = dict(
        schema_version=1,
        profile="dinner_visual_training_protocol_v1",
        recipe="v2",
        generator_profile="dinner_visual_variants_v1",
        physical_layout_count=1,
        scope="visual_conditions_only",
        validated_recordings=False,
        previously_used_development_seeds=previously_used_development_seeds,
        training_seeds=training_seeds,
        validation_seeds=validation_seeds,
        test_seeds=test_seeds,
        **_bindings(assets_path, generator_path),
    )
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = VisualTrainingProtocol.model_validate(body)
    with path.open("x") as stream:
        stream.write(result.model_dump_json(indent=2) + "\n")
    return result


def load_visual_training_protocol(
    path: Path,
    *,
    assets_path: Path | None = None,
    generator_path: Path | None = None,
) -> VisualTrainingProtocol:
    """Check canonical seal and current asset/generator identity, without ingesting data."""
    result = VisualTrainingProtocol.model_validate_json(Path(path).read_bytes())
    for key, value in _bindings(assets_path, generator_path).items():
        if getattr(result, key) != value:
            raise ValueError(f"Visual protocol source identity changed: {key}")
    return result
