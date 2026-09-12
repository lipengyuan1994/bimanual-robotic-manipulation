"""Verified training intervals from physically successful continuity collections."""

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
from bimanual.handoff_continuity_protocol import load_handoff_continuity_protocol
from bimanual.handoff_continuity_teacher import KIND, REQUEST, _continuity_score


class HandoffContinuitySource(Contract):
    run_id: Identifier
    source_manifest_sha256: Digest
    case_id: Identifier
    seed: Counter
    episode_id: Identifier
    episode: Artifact
    source_sha256: Digest
    start: Counter
    end: Counter
    validation_end: Counter

    @model_validator(mode="after")
    def intervals(self):
        if not self.start < self.end < self.validation_end:
            raise ValueError("Continuity correction and validation intervals must be nonempty")
        return self


class HandoffContinuityViews(Contract):
    profile: Literal["handoff_receiver_continuity_views_v1"] = (
        "handoff_receiver_continuity_views_v1"
    )
    split: Literal["train"] = "train"
    task_scope: Literal["receiver_close_shared_hold_donor_release"] = (
        "receiver_close_shared_hold_donor_release"
    )
    independent_scene_count: None = None
    sources: tuple[HandoffContinuitySource, ...] = Field(min_length=1, max_length=9)
    manifest_sha256: Digest

    @model_validator(mode="after")
    def unique_sources(self):
        if (
            len({source.run_id for source in self.sources}) != len(self.sources)
            or len({source.case_id for source in self.sources}) != len(self.sources)
            or len({source.episode_id for source in self.sources}) != len(self.sources)
        ):
            raise ValueError("Duplicate continuity source, case or episode")
        return self


class HandoffContinuityWindow(Contract):
    source_run_id: Identifier
    parent_episode_id: Identifier
    parent_observation_index: Counter
    parent_action_indices: tuple[Counter, ...]
    action_is_pad: tuple[StrictBool, ...]
    correction_end: Counter


def continuity_action_window(source: HandoffContinuitySource, local_index: int, chunk_size: int):
    source = HandoffContinuitySource.model_validate(dict(source))
    if type(local_index) is not int or not 0 <= local_index < source.end - source.start:
        raise ValueError("Local index outside continuity correction interval")
    if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
        raise ValueError("Action horizon must be between one and 100")
    parent = source.start + local_index
    return HandoffContinuityWindow(
        source_run_id=source.run_id,
        parent_episode_id=source.episode_id,
        parent_observation_index=parent,
        parent_action_indices=tuple(
            min(parent + offset, source.end - 1) for offset in range(chunk_size)
        ),
        action_is_pad=tuple(parent + offset >= source.end for offset in range(chunk_size)),
        correction_end=source.end,
    )


def validate_continuity_window(
    source: HandoffContinuitySource, local_index: int, window: HandoffContinuityWindow
):
    window = HandoffContinuityWindow.model_validate(dict(window))
    if window != continuity_action_window(source, local_index, len(window.parent_action_indices)):
        raise ValueError("Continuity window crosses correction or source boundary")


def _source(store: EvidenceStore, run_id: str) -> HandoffContinuitySource:
    manifest = store.verify(run_id)
    root = store.directory(run_id)
    metrics, config = manifest.metrics, manifest.config
    score = metrics.get("independent_score", {})
    required = {
        "physics.jsonl",
        "actions.jsonl",
        "independent-score.json",
        "protocol.json",
        "scene.xml",
        "layout.json",
        "plan.json.gz",
    }
    if not required <= set(manifest.files):
        raise ValueError("Continuity source lacks required sealed physical evidence")
    if (
        json.loads((root / "independent-score.json").read_bytes()) != score
        or _continuity_score(root / "physics.jsonl", root / "actions.jsonl") != score
    ):
        raise ValueError("Continuity source physical score does not reproduce")
    if (
        manifest.kind != KIND
        or manifest.outcome != "completed"
        or manifest.claims
        != ["Teacher-assisted contact hand-off correction source; no learned success"]
        or metrics.get("physical_handoff_success") is not True
        or score.get("profile") != "handoff_receiver_continuity_physical_score_v1"
        or score.get("physical_handoff_success") is not True
        or score.get("partial_actions") != 0
        or score.get("forbidden_contact_samples") != 0
        or score.get("acquisition_receiver_contact_samples") != 0
        or score.get("continuous_airborne_grip") is not True
        or score.get("phases_ordered") is not True
        or metrics.get("teacher_assistance") is not True
        or metrics.get("learned_execution") is not False
        or metrics.get("release_qualified") is not False
        or any(
            metrics.get(field) != 0
            for field in (
                "object_state_edits",
                "artificial_attachments",
                "external_object_force_samples",
            )
        )
        or config.get("training_only") is not True
        or config.get("correction_scope") != "receiver_close_shared_hold_donor_release"
    ):
        raise ValueError("Source is not a verified successful continuity collection")
    protocol_path = Path(config.get("protocol_path", ""))
    protocol = load_handoff_continuity_protocol(protocol_path)
    if (
        config.get("protocol_manifest_sha256") != protocol.manifest_sha256
        or config.get("protocol_file_sha256") is None
        or config.get("phase_boundaries") != protocol.phase_boundaries
    ):
        raise ValueError("Continuity source is not bound to its frozen protocol")
    selected = [case for case in protocol.cases if case.case_id == config.get("case_id")]
    if len(selected) != 1 or config.get("case") != selected[0].model_dump(mode="json"):
        raise ValueError("Continuity source case allocation changed")
    if config["protocol_file_sha256"] != manifest.files.get("protocol.json"):
        raise ValueError("Continuity source protocol copy changed")
    relative = metrics.get("demonstration_path")
    if relative != "demonstration/episode.json" or relative not in manifest.files:
        raise ValueError("Continuity source lacks a sealed demonstration")
    episode_artifact = Artifact(path=relative, sha256=manifest.files[relative])
    episode = DemonstrationEpisode.model_validate_json(episode_artifact.verify(root).read_bytes())
    validate_episode_artifacts(episode, root)
    case = selected[0]
    if (
        episode.lineage.seed != case.seed
        or episode.lineage.split != "train"
        or episode.lineage.controller_kind != "scripted_teacher"
        or episode.lineage.source_sha256 != manifest.provenance.get("source_sha256")
        or episode.lineage.code_revision != manifest.provenance.get("git_revision")
        or episode.outcome != "success"
        or episode.interventions != metrics.get("interventions")
    ):
        raise ValueError("Continuity episode lineage or outcome changed")
    for name, expected_path in (
        ("scene", "scene.xml"),
        ("config", REQUEST),
        ("controller", "controller.json"),
    ):
        artifact = getattr(episode.lineage, name)
        if artifact.path != expected_path or manifest.files.get(expected_path) != artifact.sha256:
            raise ValueError("Continuity episode lineage artifact changed")
    rows = [json.loads(line) for line in (root / "actions.jsonl").read_text().splitlines()]
    prefix = metrics.get("prefix_actions")
    acquisition = metrics.get("acquisition_actions")
    correction = metrics.get("correction_actions")
    validation = metrics.get("validation_actions")
    if any(
        type(value) is not int or value < 0
        for value in (prefix, acquisition, correction, validation)
    ):
        raise ValueError("Continuity interval counts are invalid")
    start, end = prefix + acquisition, prefix + acquisition + correction
    validation_end = end + validation
    if (
        correction <= 0
        or validation <= 0
        or len(rows) != validation_end
        or len(episode.frames) != validation_end + 1
        or score.get("action_rows") != validation_end
        or score.get("confirmed_actions") != validation_end
    ):
        raise ValueError("Continuity intervals do not cover the retained source")
    for index, (row, frame) in enumerate(zip(rows, episode.frames[:-1], strict=True)):
        if (
            row.get("sequence") != index
            or row.get("applied") is not True
            or row.get("partial_physics") is not False
            or row.get("training_eligible") is not (start <= index < end)
            or row.get("targets_rad") != list(frame.action_rad)
            or row.get("measured") != list(frame.observation.joint_position_rad)
        ):
            raise ValueError("Continuity action, observation or eligibility alignment changed")
    return HandoffContinuitySource(
        run_id=run_id,
        source_manifest_sha256=manifest.manifest_sha256,
        case_id=case.case_id,
        seed=case.seed,
        episode_id=episode.episode_id,
        episode=episode_artifact,
        source_sha256=episode.lineage.source_sha256,
        start=start,
        end=end,
        validation_end=validation_end,
    )


def create_handoff_continuity_views(
    store: EvidenceStore, run_ids, destination: Path
) -> HandoffContinuityViews:
    sources = tuple(_source(store, run_id) for run_id in run_ids)
    view = HandoffContinuityViews(sources=sources, manifest_sha256="0" * 64)
    body = view.model_dump(mode="json", exclude={"manifest_sha256"})
    view = HandoffContinuityViews.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    with Path(destination).open("x") as stream:
        stream.write(view.model_dump_json(indent=2) + "\n")
    return view


def load_handoff_continuity_views(path: Path, store: EvidenceStore) -> HandoffContinuityViews:
    view = HandoffContinuityViews.model_validate_json(Path(path).read_bytes())
    body = view.model_dump(mode="json", exclude={"manifest_sha256"})
    if hashlib.sha256(canonical(body)).hexdigest() != view.manifest_sha256:
        raise ValueError("Continuity views manifest digest mismatch")
    for source in view.sources:
        if _source(store, source.run_id) != source:
            raise ValueError("Continuity source differs from the verified recording")
    return view
