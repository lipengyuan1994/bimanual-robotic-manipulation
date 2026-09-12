"""Read-only eligibility verification for bar-overlap teacher sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bimanual.bar_overlap_correction_protocol import load_bar_overlap_correction_protocol
from bimanual.evidence import EvidenceStore, canonical

KIND = "bar_overlap_corrective_teacher_recording"


def verify_bar_overlap_source(store: EvidenceStore, run_id: str) -> dict:
    manifest = store.verify(run_id)
    root, metrics, config = store.directory(run_id), manifest.metrics, manifest.config
    required = {
        "actions.jsonl",
        "physics.jsonl",
        "protocol.json",
        "collection-segments.json",
        "demonstration/episode.json",
    }
    if (
        manifest.kind != KIND
        or manifest.outcome != "completed"
        or not required <= set(manifest.files)
        or metrics.get("physical_skill_success") is not True
        or metrics.get("recording_complete") is not True
        or any(
            metrics.get(key) != 0
            for key in (
                "object_state_edits",
                "artificial_attachments",
                "external_object_force_samples",
            )
        )
    ):
        raise ValueError("Source is not a completed contact-only bar-overlap recording")
    protocol_path = Path(config.get("protocol_path", ""))
    if not protocol_path.is_file():
        raise ValueError("Source no longer names a readable frozen protocol")
    protocol = load_bar_overlap_correction_protocol(protocol_path)
    if config.get("protocol_manifest_sha256") != protocol.manifest_sha256:
        raise ValueError("Source protocol binding changed")
    rows = [json.loads(line) for line in (root / "actions.jsonl").read_text().splitlines()]
    prefix = metrics.get("prefix_actions", -1) + metrics.get("acquisition_actions", -1)
    replay = rows[prefix:]
    if (
        len(rows) != prefix + metrics.get("replay_actions", -1)
        or not replay
        or any(
            row.get("segment") != "replay"
            or row.get("candidate_replay_action") is not True
            or row.get("training_eligible") is not False
            for row in replay
        )
        or any(
            not protocol.source_interval[0]
            <= row.get("source_plan_index", -1)
            < protocol.source_interval[1]
            for row in replay
        )
    ):
        raise ValueError("Source replay interval or label boundary changed")
    episode = json.loads((root / "demonstration/episode.json").read_bytes())
    return {
        "run_id": run_id,
        "manifest_sha256": manifest.manifest_sha256,
        "replay_actions": len(replay),
        "source_interval": protocol.source_interval,
        "episode_id": episode["episode_id"],
        "episode_sha256": manifest.files["demonstration/episode.json"],
        "start": prefix,
        "end": prefix + len(replay),
        "seed": config["case"]["seed"],
    }


def create_bar_overlap_views(store: EvidenceStore, run_ids, destination: Path) -> dict:
    sources = [verify_bar_overlap_source(store, run_id) for run_id in run_ids]
    body = {"schema_version": 1, "profile": "bar_overlap_corrective_views_v1", "sources": sources}
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    Path(destination).write_bytes(canonical(body) + b"\n")
    return body
