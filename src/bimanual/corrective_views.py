"""Sealed, training-only corrective intervals; never full hand-off supervision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from bimanual.contracts import (
    Artifact,
    Contract,
    Counter,
    DemonstrationEpisode,
    Digest,
    Identifier,
    validate_episode_artifacts,
)
from bimanual.evidence import EvidenceStore, canonical


class CorrectiveSource(Contract):
    run_id: Identifier
    source_manifest_sha256: Digest
    episode_id: Identifier
    episode: Artifact
    source_sha256: Digest
    seed: Counter
    start: Counter
    end: Counter
    terminal_parent_frame: Counter

    @model_validator(mode="after")
    def interval(self):
        if self.start >= self.end or self.terminal_parent_frame != self.end:
            raise ValueError("Corrective interval must be nonempty and end at its terminal frame")
        return self


class CorrectiveViews(Contract):
    profile: Literal["feedback_approach_corrective_views_v1"] = (
        "feedback_approach_corrective_views_v1"
    )
    split: Literal["train"] = "train"
    task_scope: Literal["approach_only"] = "approach_only"
    independent_scene_count: None = None
    sources: tuple[CorrectiveSource, ...] = Field(min_length=1)
    manifest_sha256: Digest

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.run_id for s in self.sources}) != len(self.sources) or len(
            {s.episode_id for s in self.sources}
        ) != len(self.sources):
            raise ValueError("Duplicate corrective source or episode")
        return self


class CorrectiveWindow(Contract):
    source_run_id: Identifier
    parent_episode_id: Identifier
    parent_observation_index: Counter
    parent_action_indices: tuple[Counter, ...]
    action_is_pad: tuple[StrictBool, ...]
    terminal_parent_frame: Counter


def corrective_action_window(source: CorrectiveSource, local_index: int, chunk_size: int):
    source = CorrectiveSource.model_validate(dict(source))
    if type(local_index) is not int or not 0 <= local_index < source.end - source.start:
        raise ValueError("Local index outside corrective source")
    if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
        raise ValueError("Action horizon must be between one and 100")
    parent = source.start + local_index
    return CorrectiveWindow(
        source_run_id=source.run_id,
        parent_episode_id=source.episode_id,
        parent_observation_index=parent,
        parent_action_indices=tuple(min(parent + i, source.end - 1) for i in range(chunk_size)),
        action_is_pad=tuple(parent + i >= source.end for i in range(chunk_size)),
        terminal_parent_frame=source.end,
    )


def validate_corrective_window(source, local_index, window: CorrectiveWindow):
    window = CorrectiveWindow.model_validate(dict(window))
    if window != corrective_action_window(source, local_index, len(window.parent_action_indices)):
        raise ValueError("Corrective window crosses source or interval boundary")


def _source(store: EvidenceStore, run_id: str) -> CorrectiveSource:
    manifest = store.verify(run_id)
    root = store.directory(run_id)
    metrics, config = manifest.metrics, manifest.config
    if (
        manifest.kind != "feedback_approach_teacher_recording"
        or manifest.outcome != "completed"
        or metrics.get("goals_reached") != 3
        or metrics.get("physical_handoff_success") is not None
        or metrics.get("teacher_assistance") is not True
        or metrics.get("learned_execution") is not False
        or metrics.get("normal_reset") is not True
        or config.get("training_only") is not True
        or config.get("record_demonstration") is not True
    ):
        raise ValueError("Source must be completed training-only feedback approach collection")
    start = metrics.get("correction_start_action")
    if (
        type(start) is not int
        or start < 0
        or type(metrics.get("acquisition_actions")) is not int
        or start != metrics["acquisition_actions"]
    ):
        raise ValueError("Invalid acquisition/correction boundary")
    relative = metrics.get("demonstration_path")
    if relative != "demonstration/episode.json" or relative not in manifest.files:
        raise ValueError("Source lacks a sealed demonstration episode")
    episode_artifact = Artifact(path=relative, sha256=manifest.files[relative])
    episode = DemonstrationEpisode.model_validate_json(episode_artifact.verify(root).read_text())
    validate_episode_artifacts(episode, root)
    seed = config.get("variation_seed")
    if (
        type(seed) is not int
        or not 0 <= seed <= 1_000_000
        or episode.lineage.seed != seed
        or episode.lineage.split != "train"
        or episode.lineage.controller_kind != "scripted_teacher"
        or episode.outcome != "success"
        or episode.interventions != int(start > 0)
        or episode.lineage.source_sha256 != manifest.provenance.get("source_sha256")
        or episode.lineage.code_revision != manifest.provenance.get("git_revision")
    ):
        raise ValueError("Corrective source lineage, outcome or seed mismatch")
    for name in ("scene", "config", "controller"):
        artifact = getattr(episode.lineage, name)
        if (
            artifact.path != name + (".xml" if name == "scene" else ".json")
            or manifest.files.get(artifact.path) != artifact.sha256
        ):
            raise ValueError("Episode lineage artifact not bound to source")
    if json.loads((root / "config.json").read_text()) != config:
        raise ValueError("Recorded configuration differs from source configuration")
    rows = [json.loads(line) for line in (root / "actions.jsonl").read_text().splitlines()]
    end = len(episode.frames) - 1
    if (
        len(rows) != end
        or type(metrics.get("actions")) is not int
        or metrics["actions"] != end
        or not 0 <= start < end
    ):
        raise ValueError("Incomplete corrective action interval")
    for index, (row, frame) in enumerate(zip(rows, episode.frames[:-1], strict=True)):
        if (
            type(row.get("sequence")) is not int
            or row["sequence"] != index
            or row.get("applied") is not True
            or row.get("partial_physics") is not False
            or row.get("training_eligible") is not (index >= start)
            or (index < start and row.get("phase") != "feedback/acquisition")
            or (index >= start and row.get("phase") == "feedback/acquisition")
            or row.get("target") != list(frame.action_rad)
            or row.get("measured") != list(frame.observation.joint_position_rad)
        ):
            raise ValueError("Action/observation alignment or eligibility mismatch")
    return CorrectiveSource(
        run_id=run_id,
        source_manifest_sha256=manifest.manifest_sha256,
        episode_id=episode.episode_id,
        episode=episode_artifact,
        source_sha256=episode.lineage.source_sha256,
        seed=seed,
        start=start,
        end=end,
        terminal_parent_frame=end,
    )


def create_corrective_views(store: EvidenceStore, run_ids, destination: Path) -> CorrectiveViews:
    sources = tuple(_source(store, run_id) for run_id in run_ids)
    view = CorrectiveViews(sources=sources, manifest_sha256="0" * 64)
    payload = view.model_dump(exclude={"manifest_sha256"})
    view = CorrectiveViews.model_validate(
        payload | {"manifest_sha256": hashlib.sha256(canonical(payload)).hexdigest()}
    )
    with Path(destination).open("x") as stream:
        stream.write(view.model_dump_json(indent=2) + "\n")
    return view


def load_corrective_views(path: Path, store: EvidenceStore) -> CorrectiveViews:
    view = CorrectiveViews.model_validate_json(Path(path).read_text())
    expected = hashlib.sha256(canonical(view.model_dump(exclude={"manifest_sha256"}))).hexdigest()
    if view.manifest_sha256 != expected:
        raise ValueError("Corrective view manifest digest mismatch")
    for source in view.sources:
        if _source(store, source.run_id) != source:
            raise ValueError("Corrective source or interval differs from verified recording")
    return view
