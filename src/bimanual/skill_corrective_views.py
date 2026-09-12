"""Independent, read-only training views over six-skill corrective teacher sources."""

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
from bimanual.skill_corrective_teacher import KIND, REQUEST
from bimanual.skill_outcomes import SkillOutcomeMonitor


class SkillCorrectiveSource(Contract):
    run_id: Identifier
    source_manifest_sha256: Digest
    case_id: Identifier
    family_id: Identifier
    skill_id: Identifier
    seed: Counter
    episode_id: Identifier
    episode: Artifact
    source_sha256: Digest
    start: Counter
    end: Counter
    terminal_parent_frame: Counter

    @model_validator(mode="after")
    def interval(self):
        if not self.start < self.end or self.terminal_parent_frame != self.end:
            raise ValueError("Corrective replay interval is invalid")
        return self


class SkillCorrectiveViews(Contract):
    profile: Literal["six_skill_corrective_views_v1"] = "six_skill_corrective_views_v1"
    split: Literal["train"] = "train"
    task_scope: Literal["bounded_component_replay_only"] = "bounded_component_replay_only"
    independent_scene_count: None = None
    sources: tuple[SkillCorrectiveSource, ...] = Field(min_length=1)
    manifest_sha256: Digest

    @model_validator(mode="after")
    def unique_sources(self):
        if len({source.run_id for source in self.sources}) != len(self.sources) or len(
            {source.case_id for source in self.sources}
        ) != len(self.sources):
            raise ValueError("Duplicate corrective source or case")
        return self


class SkillCorrectiveWindow(Contract):
    source_run_id: Identifier
    parent_episode_id: Identifier
    parent_observation_index: Counter
    parent_action_indices: tuple[Counter, ...]
    action_is_pad: tuple[StrictBool, ...]
    terminal_parent_frame: Counter


def corrective_action_window(source: SkillCorrectiveSource, local_index: int, chunk_size: int):
    source = SkillCorrectiveSource.model_validate(dict(source))
    if type(local_index) is not int or not 0 <= local_index < source.end - source.start:
        raise ValueError("Local index outside corrective replay")
    if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
        raise ValueError("Action horizon must be between one and 100")
    parent = source.start + local_index
    return SkillCorrectiveWindow(
        source_run_id=source.run_id,
        parent_episode_id=source.episode_id,
        parent_observation_index=parent,
        parent_action_indices=tuple(
            min(parent + offset, source.end - 1) for offset in range(chunk_size)
        ),
        action_is_pad=tuple(parent + offset >= source.end for offset in range(chunk_size)),
        terminal_parent_frame=source.end,
    )


def validate_corrective_window(
    source: SkillCorrectiveSource, local_index: int, window: SkillCorrectiveWindow
):
    window = SkillCorrectiveWindow.model_validate(dict(window))
    if window != corrective_action_window(source, local_index, len(window.parent_action_indices)):
        raise ValueError("Corrective window crosses replay or source boundary")


def _score(root: Path, *, skill_id: str, rows: list[dict], start: int, layout: dict) -> dict:
    first = rows[start]
    monitor = SkillOutcomeMonitor(
        skill_id,
        episode_id=first["episode_id"],
        initial_sequence=first["observation_sequence"],
        initial_simulation_seconds=first["simulation_seconds_before"],
        layout=layout,
        max_actions=len(rows) - start,
    )
    trace = [json.loads(line) for line in (root / "physics.jsonl").read_text().splitlines()]
    if len(trace) != len(rows) * 50:
        raise ValueError("Corrective physics/action row ratio is invalid")
    for index in range(start, len(rows)):
        monitor.consume(rows[index], trace[index * 50 : (index + 1) * 50])
    return monitor.snapshot().report()


def _source(store: EvidenceStore, run_id: str) -> SkillCorrectiveSource:
    manifest = store.verify(run_id)
    root, metrics, config = store.directory(run_id), manifest.metrics, manifest.config
    required = {
        "physics.jsonl",
        "actions.jsonl",
        "independent-score.json",
        "collection-segments.json",
        "scene.xml",
        "layout.json",
        "plan.json.gz",
        "protocol.json",
        REQUEST,
        "controller.json",
    }
    if not required <= set(manifest.files):
        raise ValueError("Corrective source lacks required sealed evidence")
    case = config.get("case")
    if (
        manifest.kind != KIND
        or manifest.outcome != "completed"
        or metrics.get("teacher_assistance") is not True
        or metrics.get("learned_execution") is not False
        or metrics.get("training_eligible") is not False
        or metrics.get("physical_skill_success") is not True
        or metrics.get("recording_complete") is not True
        or metrics.get("release_qualified") is not False
        or config.get("training_only") is not True
        or not isinstance(case, dict)
        or config.get("case_id") != case.get("case_id")
        or any(
            metrics.get(field) != 0
            for field in (
                "object_state_edits",
                "artificial_attachments",
                "external_object_force_samples",
            )
        )
    ):
        raise ValueError("Source is not a completed corrective teacher recording")
    relative = metrics.get("demonstration_path")
    if relative != "demonstration/episode.json" or relative not in manifest.files:
        raise ValueError("Corrective source lacks a sealed demonstration")
    episode_artifact = Artifact(path=relative, sha256=manifest.files[relative])
    episode = DemonstrationEpisode.model_validate_json(episode_artifact.verify(root).read_bytes())
    validate_episode_artifacts(episode, root)
    rows = [json.loads(line) for line in (root / "actions.jsonl").read_text().splitlines()]
    prefix, acquisition, replay = (
        metrics.get("prefix_actions"),
        metrics.get("acquisition_actions"),
        metrics.get("replay_actions"),
    )
    start = prefix + acquisition if type(prefix) is int and type(acquisition) is int else -1
    if (
        not all(type(value) is int and value >= 0 for value in (prefix, acquisition, replay))
        or replay <= 0
        or len(rows) != start + replay
        or len(episode.frames) != len(rows) + 1
        or episode.outcome != "success"
        or episode.interventions != metrics.get("interventions")
        or episode.lineage.seed != case.get("seed")
        or episode.lineage.split != "train"
        or episode.lineage.controller_kind != "scripted_teacher"
        or episode.lineage.source_sha256 != manifest.provenance.get("source_sha256")
        or episode.lineage.code_revision != manifest.provenance.get("git_revision")
    ):
        raise ValueError("Corrective source count, lineage or outcome changed")
    for name, expected_path in (
        ("scene", "scene.xml"),
        ("config", REQUEST),
        ("controller", "controller.json"),
    ):
        artifact = getattr(episode.lineage, name)
        if artifact.path != expected_path or artifact.sha256 != manifest.files.get(expected_path):
            raise ValueError("Corrective episode lineage artifact changed")
    for index, (row, frame) in enumerate(zip(rows, episode.frames[:-1], strict=True)):
        segment = "prefix" if index < prefix else "acquisition" if index < start else "replay"
        if (
            row.get("observation_sequence") != frame.observation.sequence
            or row.get("episode_id") != episode.episode_id
            or row.get("targets_rad") != list(frame.action_rad)
            or row.get("applied") is not True
            or row.get("partial_physics") is not False
            or row.get("segment") != segment
            or row.get("training_eligible") is not False
            or row.get("candidate_replay_action") is not (segment == "replay")
        ):
            raise ValueError("Corrective action/observation alignment changed")
    layout = json.loads((root / "layout.json").read_bytes())
    score = _score(root, skill_id=case.get("skill_id"), rows=rows, start=start, layout=layout)
    if (
        score != metrics.get("independent_score")
        or score != json.loads((root / "independent-score.json").read_bytes())
        or score.get("state") != "succeeded"
    ):
        raise ValueError("Corrective physical score does not reproduce")
    return SkillCorrectiveSource(
        run_id=run_id,
        source_manifest_sha256=manifest.manifest_sha256,
        case_id=case["case_id"],
        family_id=case["family_id"],
        skill_id=case["skill_id"],
        seed=case["seed"],
        episode_id=episode.episode_id,
        episode=episode_artifact,
        source_sha256=episode.lineage.source_sha256,
        start=start,
        end=len(rows),
        terminal_parent_frame=len(rows),
    )


def create_skill_corrective_views(
    store: EvidenceStore, run_ids, destination: Path
) -> SkillCorrectiveViews:
    sources = tuple(_source(store, run_id) for run_id in run_ids)
    view = SkillCorrectiveViews(sources=sources, manifest_sha256="0" * 64)
    body = view.model_dump(mode="json", exclude={"manifest_sha256"})
    view = SkillCorrectiveViews.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    with Path(destination).open("x") as stream:
        stream.write(view.model_dump_json(indent=2) + "\n")
    return view


def load_skill_corrective_views(path: Path, store: EvidenceStore) -> SkillCorrectiveViews:
    view = SkillCorrectiveViews.model_validate_json(Path(path).read_bytes())
    body = view.model_dump(mode="json", exclude={"manifest_sha256"})
    if hashlib.sha256(canonical(body)).hexdigest() != view.manifest_sha256:
        raise ValueError("Corrective views manifest digest mismatch")
    for source in view.sources:
        if _source(store, source.run_id) != source:
            raise ValueError("Corrective source differs from the verified recording")
    return view
