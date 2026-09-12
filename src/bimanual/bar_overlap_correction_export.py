"""Immutable local LeRobot export for verified bar-overlap corrective views."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from bimanual.bar_overlap_correction_views import verify_bar_overlap_source
from bimanual.contracts import Artifact
from bimanual.dataset_export import _load_lerobot, lerobot_features
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_corrective_export import (
    _episodes,
    _frames,
    _native,
    _parity,
    _require_offline_hub,
)

PROFILE = "bar_overlap_corrective_lerobot_v1"


def _load_sources(view_path: Path, store: EvidenceStore) -> tuple[dict, list[SimpleNamespace]]:
    view = json.loads(view_path.read_bytes())
    if view.get("schema_version") != 1 or view.get("profile") != "bar_overlap_corrective_views_v1":
        raise ValueError("Unsupported bar-overlap corrective view")
    body = {key: value for key, value in view.items() if key != "manifest_sha256"}
    if hashlib.sha256(canonical(body)).hexdigest() != view.get("manifest_sha256"):
        raise ValueError("Bar-overlap corrective view digest mismatch")
    sources = []
    for declared in view.get("sources", []):
        source = verify_bar_overlap_source(store, declared["run_id"])
        if source != {**declared, "source_interval": tuple(declared["source_interval"])}:
            raise ValueError("View source binding changed")
        sources.append(
            SimpleNamespace(
                **source,
                source_manifest_sha256=source["manifest_sha256"],
                episode=Artifact(
                    path="demonstration/episode.json", sha256=source["episode_sha256"]
                ),
            )
        )
    if not sources:
        raise ValueError("Bar-overlap corrective view has no sources")
    return view, sources


def export_bar_overlap_dataset(view_path, store: EvidenceStore, destination, repo_id) -> Path:
    """Export a sealed, replay-only local dataset from frozen bar-overlap views."""
    _native()
    view_path = Path(view_path)
    destination = Path(destination).absolute()
    if (
        destination.exists()
        or destination.is_symlink()
        or not isinstance(repo_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", repo_id)
    ):
        raise ValueError("Invalid export destination or repo id")
    original_view, sources = _load_sources(view_path, store)
    views = SimpleNamespace(sources=sources)
    dataset = _load_lerobot().create(
        repo_id=repo_id,
        root=destination,
        fps=20,
        robot_type="dual_so101_sim",
        features=lerobot_features(),
        use_videos=False,
        image_writer_processes=0,
        image_writer_threads=0,
    )
    (destination / "bar_overlap_views.json").write_bytes(view_path.read_bytes())
    copied = EvidenceStore(destination / "raw_sources")
    for source in sources:
        copied.directory(source.run_id).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            store.directory(source.run_id), copied.directory(source.run_id), symlinks=False
        )
        copied_source = verify_bar_overlap_source(copied, source.run_id)
        if copied_source != {
            key: value
            for key, value in source.__dict__.items()
            if key not in {"source_manifest_sha256", "episode"}
        }:
            raise ValueError("Copied bar-overlap source changed")
    for source in sources:
        for row in _frames(copied.directory(source.run_id), source):
            dataset.add_frame(row)
        dataset.save_episode()
    dataset.finalize()
    _parity(dataset, views, copied)
    payload = {
        "schema_version": 1,
        "profile": PROFILE,
        "format": "lerobot_v3",
        "repo_id": repo_id,
        "frames": sum(s.end - s.start for s in sources),
        "episodes": _episodes(views),
        "views_sha256": digest_file(destination / "bar_overlap_views.json"),
        "files": {
            p.relative_to(destination).as_posix(): digest_file(p)
            for p in destination.rglob("*")
            if p.is_file()
        },
    }
    payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    (destination / "export_manifest.json").write_bytes(canonical(payload) + b"\n")
    return destination


def _verify_manifest(root: Path) -> dict:
    payload = json.loads((root / "export_manifest.json").read_text())
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if hashlib.sha256(canonical(body)).hexdigest() != payload.get("manifest_sha256"):
        raise ValueError("Bar-overlap export manifest digest mismatch")
    expected = {
        "schema_version": 1,
        "profile": PROFILE,
        "format": "lerobot_v3",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("Unsupported bar-overlap export profile")
    if "fps" in payload and payload["fps"] != 20:
        raise ValueError("Unsupported bar-overlap export frame rate")
    if not isinstance(payload.get("repo_id"), str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", payload["repo_id"]
    ):
        raise ValueError("Invalid bar-overlap export repo id")
    files = payload.get("files")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != root / "export_manifest.json"
    }
    if (
        not isinstance(files, dict)
        or not files
        or actual != set(files)
        or "EXPORT_FAILED.json" in actual
    ):
        raise ValueError("Incomplete or unsealed bar-overlap export")
    if "meta/info.json" not in files or not any(
        name.startswith("data/") and name.endswith(".parquet") for name in files
    ):
        raise ValueError("Bar-overlap export lacks local LeRobot data")
    return payload


def verify_bar_overlap_dataset(root: Path) -> dict:
    """Audit every retained source artifact and decoded LeRobot row."""
    _native()
    root = Path(root).resolve(strict=True)
    payload = _verify_manifest(root)
    for name, sha256 in payload["files"].items():
        Artifact(path=name, sha256=sha256).verify(root)
    views_path = root / "bar_overlap_views.json"
    if payload.get("views_sha256") != digest_file(views_path):
        raise ValueError("Bar-overlap export view binding mismatch")
    _, sources = _load_sources(views_path, EvidenceStore(root / "raw_sources"))
    views = SimpleNamespace(sources=sources)
    if payload.get("episodes") != _episodes(views) or payload.get("frames") != sum(
        source.end - source.start for source in sources
    ):
        raise ValueError("Bar-overlap export source/index mapping mismatch")
    _require_offline_hub()
    dataset = _load_lerobot()(
        repo_id=payload["repo_id"],
        root=root,
        delta_timestamps=None,
        download_videos=False,
        token=False,
    )
    _parity(dataset, views, EvidenceStore(root / "raw_sources"))
    return payload


def verify_bar_overlap_dataset_binding(root: Path) -> dict:
    """Bind a training job to the sealed export without repeating the full audit."""
    _native()
    root = Path(root).resolve(strict=True)
    payload = _verify_manifest(root)
    views_path = root / "bar_overlap_views.json"
    if payload.get("views_sha256") != digest_file(views_path):
        raise ValueError("Bar-overlap export view binding mismatch")
    _, sources = _load_sources(views_path, EvidenceStore(root / "raw_sources"))
    views = SimpleNamespace(sources=sources)
    if payload.get("episodes") != _episodes(views) or payload.get("frames") != sum(
        source.end - source.start for source in sources
    ):
        raise ValueError("Bar-overlap export source/index mapping mismatch")
    return payload
