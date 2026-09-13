"""One-time physical evaluation declaration for the bar corrective checkpoint."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_physical_protocol import _source_paths
from bimanual.training import ACTTrainingConfig

PROFILE = "bar_transport_physical_evaluation_protocol_v1"
SKILL = "bar_place_and_return"


class BarTransportPhysicalProtocol(Contract):
    profile: Literal[PROFILE] = PROFILE
    training_run: str
    training_manifest_sha256: Digest
    dataset_root: str
    dataset_manifest_sha256: Digest
    skill_views_path: str
    skill_views_sha256: Digest
    sampling_declaration_sha256: Digest
    evaluation_sources: dict[str, Digest]
    device: Literal["mps"] = "mps"
    execute_chunk_steps: Literal[2] = 2
    max_actions: Literal[1900] = 1900
    wall_timeout_seconds: Literal[1200.0] = 1200.0
    execution_authorized_by_this_artifact: Literal[False] = False
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact(self):
        if any(
            not value or Path(value).is_absolute()
            for value in (self.training_run, self.dataset_root, self.skill_views_path)
        ) or set(self.evaluation_sources) != set(_source_paths(Path(__file__).resolve().parent)):
            raise ValueError("Bar physical evaluation declaration has invalid source bindings")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Bar physical evaluation declaration digest mismatch")
        return self


def create_bar_transport_physical_protocol(
    training_run: Path, destination: Path
) -> BarTransportPhysicalProtocol:
    """Freeze one evaluation only after a matching corrective run completed."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Bar physical evaluation declaration already exists")
    training_run = Path(training_run).resolve(strict=True)
    store = EvidenceStore(training_run.parents[1])
    manifest = store.verify(training_run.name)
    config = ACTTrainingConfig.model_validate(manifest.config)
    if (
        manifest.kind != "act_training"
        or manifest.outcome != "completed"
        or manifest.metrics.get("training_completed") is not True
        or manifest.metrics.get("actual_device") != "mps"
        or config.skill_id != SKILL
        or config.sampling_profile != "bar_transport_placement_v1"
        or config.corrective_dataset_path is None
        or config.sampling_protocol_run is None
    ):
        raise ValueError("Training run is not a completed MPS bar transport corrective candidate")
    from bimanual.skill_registry import load_skill_checkpoint

    binding = load_skill_checkpoint(training_run, skill_id=SKILL, dataset_root=config.dataset_path)
    binding.reverify()
    root = Path(__file__).resolve().parent
    body = dict(
        schema_version=1,
        profile=PROFILE,
        training_run=os.path.relpath(training_run, destination.parent),
        training_manifest_sha256=manifest.manifest_sha256,
        dataset_root=os.path.relpath(config.dataset_path, destination.parent),
        dataset_manifest_sha256=digest_file(config.dataset_path / "export_manifest.json"),
        skill_views_path=os.path.relpath(config.skill_views_path, destination.parent),
        skill_views_sha256=digest_file(config.skill_views_path),
        sampling_declaration_sha256=digest_file(config.sampling_protocol_run),
        evaluation_sources={name: digest_file(root / name) for name in _source_paths(root)},
        device="mps",
        execute_chunk_steps=2,
        max_actions=1900,
        wall_timeout_seconds=1200.0,
        execution_authorized_by_this_artifact=False,
    )
    result = BarTransportPhysicalProtocol.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_bar_transport_physical_protocol(path: Path) -> BarTransportPhysicalProtocol:
    path = Path(path).resolve(strict=True)
    result = BarTransportPhysicalProtocol.model_validate_json(path.read_bytes())
    root = Path(__file__).resolve().parent
    for name, digest in result.evaluation_sources.items():
        if digest_file(root / name) != digest:
            raise ValueError("Bar physical evaluator source changed after protocol freeze")
    return result


def run_bar_transport_physical_protocol(path: Path):
    """Execute the one declared component evaluation, never retrying it automatically."""
    path = Path(path).resolve(strict=True)
    file_sha256 = digest_file(path)
    protocol = load_bar_transport_physical_protocol(path)
    training_run = (path.parent / protocol.training_run).resolve(strict=True)
    store = EvidenceStore(training_run.parents[1])
    matches = []
    for manifest_path in (store.root / "runs").glob("*/manifest.json"):
        manifest = store.verify(manifest_path.parent.name)
        if (
            manifest.kind == "learned_skill_teacher_prepared_physical_evaluation"
            and manifest.config.get("evaluation_protocol_sha256") == protocol.manifest_sha256
            and manifest.config.get("evaluation_protocol_file_sha256") == file_sha256
        ):
            matches.append(manifest)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("Bar physical evaluation has ambiguous prior results")
    from bimanual.skill_physical_evaluation import (
        SkillPhysicalEvaluationConfig,
        run_skill_physical_evaluation,
    )

    config = SkillPhysicalEvaluationConfig(
        training_run=training_run,
        dataset_root=(path.parent / protocol.dataset_root).resolve(strict=True),
        skill_views_path=(path.parent / protocol.skill_views_path).resolve(strict=True),
        skill_id=SKILL,
        device=protocol.device,
        max_actions=protocol.max_actions,
        execute_chunk_steps=protocol.execute_chunk_steps,
        wall_timeout_seconds=protocol.wall_timeout_seconds,
        evaluation_protocol_sha256=protocol.manifest_sha256,
        evaluation_protocol_file_sha256=file_sha256,
    )
    return run_skill_physical_evaluation(config, store=store, project_root=Path.cwd())
