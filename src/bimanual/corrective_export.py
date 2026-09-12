"""Separate LeRobot adjunct export; acquisition is retained as evidence, never a label."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from bimanual.contracts import Artifact, DemonstrationEpisode
from bimanual.corrective_views import load_corrective_views
from bimanual.dataset_export import (
    CAMERA_FEATURES,
    LEROBOT_VERSION,
    _load_lerobot,
    lerobot_features,
    validate_export_timestamp,
)
from bimanual.dual_arm import JOINT_ORDER
from bimanual.evidence import EvidenceStore, canonical, digest_file

PROFILE = "feedback_approach_corrective_lerobot_v1"


def _native():
    if platform.system() == "Darwin" and platform.machine() != "arm64":
        raise RuntimeError("Local corrective export requires native Apple Silicon Python")


def _frames(root, source):
    episode = DemonstrationEpisode.model_validate_json(source.episode.verify(root).read_text())
    for frame in episode.frames[source.start : source.end]:
        obs = frame.observation
        row = {
            "observation.state": np.asarray(obs.joint_position_rad, dtype=np.float32),
            "observation.velocity": np.asarray(obs.joint_velocity_rad_s, dtype=np.float32),
            "action": np.asarray(frame.action_rad, dtype=np.float32),
            "task": episode.instruction,
        }
        for camera in obs.frames:
            with Image.open(camera.artifact.verify(root)) as image:
                row[CAMERA_FEATURES[camera.camera]] = np.array(image, dtype=np.uint8)
        yield row


def _episodes(views):
    offset, rows = 0, []
    for index, source in enumerate(views.sources):
        size = source.end - source.start
        rows.append(
            dict(
                episode_index=index,
                episode_id=source.episode_id,
                run_id=source.run_id,
                raw_root=f"raw_sources/runs/{source.run_id}",
                seed=source.seed,
                split="train",
                parent_start=source.start,
                parent_end=source.end,
                dataset_start=offset,
                dataset_end=offset + size,
                exported_transitions=size,
                source_manifest_sha256=source.source_manifest_sha256,
                episode_sha256=source.episode.sha256,
            )
        )
        offset += size
    return rows


def _parity(dataset, views, store):
    expected_count = sum(s.end - s.start for s in views.sources)
    if dataset.num_frames != expected_count or dataset.num_episodes != len(views.sources):
        raise ValueError("Corrective export frame/episode count mismatch")
    offset = 0
    for episode_index, source in enumerate(views.sources):
        for local, expected in enumerate(_frames(store.directory(source.run_id), source)):
            actual = dataset[offset]
            for key in ("observation.state", "observation.velocity", "action"):
                np.testing.assert_array_equal(actual[key].numpy(), expected[key])
            validate_export_timestamp(float(actual["timestamp"].item()), local)
            for key, expected_index in (
                ("episode_index", episode_index),
                ("frame_index", local),
                ("index", offset),
            ):
                value = actual[key].item()
                if (
                    isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, float, np.integer, np.floating))
                    or not np.isfinite(value)
                    or value != expected_index
                ):
                    raise ValueError("Corrective export index mapping mismatch")
            if actual["task"] != expected["task"]:
                raise ValueError("Corrective export instruction mismatch")
            for feature in CAMERA_FEATURES.values():
                rgb = actual[feature].permute(1, 2, 0).numpy()
                np.testing.assert_array_equal(
                    np.rint(rgb * 255).astype(np.uint8), expected[feature]
                )
            offset += 1


def export_corrective_dataset(view_path, store: EvidenceStore, destination, repo_id) -> Path:
    """Write a new local image-backed dataset; never upload, overwrite or alter intake gates."""
    _native()
    if not isinstance(repo_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", repo_id):
        raise ValueError("Invalid corrective dataset repo_id")
    destination, view_path = Path(destination).absolute(), Path(view_path)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Corrective dataset destination already exists")
    views = load_corrective_views(view_path, store)
    original_view = view_path.read_bytes()
    if any(destination.resolve().is_relative_to(store.directory(s.run_id)) for s in views.sources):
        raise ValueError("Cannot export inside sealed source")
    dataset = None
    try:
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
        (destination / "corrective_views.json").write_bytes(original_view)
        copied = EvidenceStore(destination / "raw_sources")
        for source in views.sources:
            raw = copied.directory(source.run_id)
            raw.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(store.directory(source.run_id), raw, symlinks=False)
        if load_corrective_views(destination / "corrective_views.json", copied) != views:
            raise ValueError("Copied corrective source changed")
        for source in views.sources:
            for row in _frames(copied.directory(source.run_id), source):
                dataset.add_frame(row)
            dataset.save_episode()
        dataset.finalize()
        _parity(dataset, views, copied)
        if (
            load_corrective_views(view_path, store) != views
            or view_path.read_bytes() != original_view
        ):
            raise ValueError("Corrective input changed during export")
        payload = dict(
            schema_version=1,
            profile=PROFILE,
            format="lerobot_v3",
            lerobot_version=LEROBOT_VERSION,
            repo_id=repo_id,
            fps=20,
            storage="images",
            split="train",
            task_scope="approach_only",
            independent_scene_count=None,
            frames=sum(s.end - s.start for s in views.sources),
            episodes=_episodes(views),
            camera_features=CAMERA_FEATURES,
            joint_order=list(JOINT_ORDER),
            corrective_views_sha256=digest_file(destination / "corrective_views.json"),
            files={
                p.relative_to(destination).as_posix(): digest_file(p)
                for p in sorted(destination.rglob("*"))
                if p.is_file()
            },
        )
        payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
        with (destination / "export_manifest.json").open("x") as stream:
            json.dump(payload, stream, indent=2, allow_nan=False)
        return destination
    except (Exception, KeyboardInterrupt) as error:
        if dataset is not None:
            try:
                dataset.finalize()
            except (Exception, KeyboardInterrupt):
                pass
        if destination.is_dir():
            with (destination / "EXPORT_FAILED.json").open("x") as stream:
                json.dump(dict(error=str(error), type=type(error).__name__), stream)
        raise


def _require_offline_hub():
    # LeRobot may try Hub recovery even with an explicit root. Require offline
    # mode latched before imports; do not mutate process-global library settings.
    from huggingface_hub import constants

    if os.environ.get("HF_HUB_OFFLINE") != "1" or not constants.HF_HUB_OFFLINE:
        raise RuntimeError("Start corrective verification with HF_HUB_OFFLINE=1 before imports")


def verify_corrective_dataset(root: Path) -> dict:
    """Verify hashes, original corrected intervals and actual decoded LeRobot row parity."""
    _native()
    root = Path(root).resolve(strict=True)
    payload = json.loads((root / "export_manifest.json").read_text())
    body = {k: v for k, v in payload.items() if k != "manifest_sha256"}
    if hashlib.sha256(canonical(body)).hexdigest() != payload.get("manifest_sha256"):
        raise ValueError("Corrective export manifest digest mismatch")
    expected = dict(
        schema_version=1,
        profile=PROFILE,
        format="lerobot_v3",
        lerobot_version=LEROBOT_VERSION,
        fps=20,
        storage="images",
        split="train",
        task_scope="approach_only",
        independent_scene_count=None,
        camera_features=CAMERA_FEATURES,
        joint_order=list(JOINT_ORDER),
    )
    if any(key not in payload or payload[key] != value for key, value in expected.items()):
        raise ValueError("Unsupported corrective export profile")
    if not isinstance(payload.get("repo_id"), str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", payload["repo_id"]
    ):
        raise ValueError("Invalid corrective dataset repo_id")
    files = payload.get("files", {})
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p != root / "export_manifest.json"
    }
    if not files or actual != set(files) or "EXPORT_FAILED.json" in actual:
        raise ValueError("Incomplete or unsealed corrective dataset")
    for name, sha in files.items():
        Artifact(path=name, sha256=sha).verify(root)
    store = EvidenceStore(root / "raw_sources")
    views = load_corrective_views(root / "corrective_views.json", store)
    if payload.get("corrective_views_sha256") != digest_file(root / "corrective_views.json"):
        raise ValueError("Corrective view binding mismatch")
    if payload.get("episodes") != _episodes(views) or payload.get("frames") != sum(
        s.end - s.start for s in views.sources
    ):
        raise ValueError("Corrective export source/index mapping mismatch")
    if "meta/info.json" not in files or not any(
        name.startswith("data/") and name.endswith(".parquet") for name in files
    ):
        raise ValueError("Corrective dataset requires sealed local metadata and data")
    dataset_type = _load_lerobot()
    _require_offline_hub()
    dataset = dataset_type(
        repo_id=payload["repo_id"],
        root=root,
        delta_timestamps=None,
        download_videos=False,
        token=False,
    )
    _parity(dataset, views, store)
    return payload
