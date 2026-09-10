"""Verified local LeRobot v3 dataset export using the pinned optional 0.6.1 API."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from bimanual.contracts import (
    DemonstrationEpisode,
    validate_episode_artifacts,
    validate_split_seeds,
)
from bimanual.demonstrations import require_successful_training_episode
from bimanual.dual_arm import CAMERAS, CONTROL_HZ, JOINT_ORDER
from bimanual.evidence import EvidenceStore, canonical, digest_file

LEROBOT_VERSION = "0.6.1"
CAMERA_FEATURES = dict(
    zip(
        CAMERAS,
        (
            "observation.images.overhead",
            "observation.images.left_wrist",
            "observation.images.right_wrist",
        ),
        strict=True,
    )
)


@dataclass(frozen=True)
class ExportSource:
    root: Path
    episode: DemonstrationEpisode
    episode_sha256: str
    evidence_manifest_sha256: str


def _read_source(root: Path) -> ExportSource:
    root = root.resolve(strict=True)
    # Authoritative existing evidence validation includes transitive scene assets.
    manifest = EvidenceStore(root.parent.parent).verify(root.name)
    if root.parent != (root.parent.parent / "runs"):
        raise ValueError("Expected a sealed evidence run under a runs directory")
    record_path = root / "demonstration" / "episode.json"
    record = DemonstrationEpisode.model_validate_json(record_path.read_bytes())
    validate_episode_artifacts(record, root)
    compatible_outcomes = {
        "success": {"completed", "success"},
        "failure": {"failed", "failure"},
        "cancelled": {"interrupted", "cancelled"},
    }
    if manifest.outcome not in compatible_outcomes[record.outcome]:
        raise ValueError("Episode and sealed run outcomes disagree")
    if record.lineage.code_revision != manifest.provenance.get("git_revision") or (
        record.lineage.source_sha256 != manifest.provenance.get("source_sha256")
    ):
        raise ValueError("Episode and sealed source lineage disagree")
    return ExportSource(root, record, digest_file(record_path), digest_file(root / "manifest.json"))


def preflight_sources(
    run_roots: tuple[Path, ...],
    *,
    comparison_run_roots: tuple[Path, ...] = (),
    max_frames: int = 100_000,
) -> tuple[ExportSource, ...]:
    """Validate all candidates before any optional import or output mutation.

    Comparison roots are held-out records used for leakage checks, never exported.
    The caller must supply the complete known split collection for a global check.
    """
    if not run_roots or max_frames < 1:
        raise ValueError("Provide at least one source run and a positive frame limit")
    sources = tuple(_read_source(Path(root)) for root in run_roots)
    comparisons = tuple(_read_source(Path(root)) for root in comparison_run_roots)
    validate_split_seeds(tuple(source.episode for source in (*sources, *comparisons)))
    for source in sources:
        require_successful_training_episode(source.episode)
    if sum(len(source.episode.frames) - 1 for source in sources) > max_frames:
        raise ValueError("Export exceeds the explicit frame limit")
    return sources


def lerobot_features() -> dict:
    numeric = {"dtype": "float32", "shape": (12,), "names": list(JOINT_ORDER)}
    return {
        "observation.state": dict(numeric),
        "observation.velocity": dict(numeric),
        "action": dict(numeric),
        **{
            feature: {
                "dtype": "image",
                "shape": (270, 480, 3),
                "names": ["height", "width", "channels"],
            }
            for feature in CAMERA_FEATURES.values()
        },
    }


def iter_export_frames(source: ExportSource):
    """One action-aligned row per confirmed transition; terminal stays in raw source."""
    for frame in source.episode.frames[:-1]:
        observation = frame.observation
        result = {
            "observation.state": np.asarray(observation.joint_position_rad, dtype=np.float32),
            "observation.velocity": np.asarray(observation.joint_velocity_rad_s, dtype=np.float32),
            "action": np.asarray(frame.action_rad, dtype=np.float32),
            "task": source.episode.instruction,
        }
        for camera in observation.frames:
            image_path = camera.artifact.verify(source.root)
            with Image.open(image_path) as image:
                result[CAMERA_FEATURES[camera.camera]] = np.array(image, dtype=np.uint8)
        yield result


def _load_lerobot():
    try:
        version = importlib.metadata.version("lerobot")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "LeRobot 0.6.1 requires the verified native training environment"
        ) from exc
    if version != LEROBOT_VERSION:
        raise RuntimeError(f"Expected LeRobot {LEROBOT_VERSION}; found {version}")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    return LeRobotDataset


def export_lerobot_dataset(
    run_roots: tuple[Path, ...],
    destination: Path,
    *,
    repo_id: str,
    comparison_run_roots: tuple[Path, ...] = (),
    max_frames: int = 100_000,
) -> Path:
    """Export local image-backed LeRobot v3. No Hub upload, overwrite or resume."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", repo_id):
        raise ValueError("repo_id must be a simple owner/dataset identifier")
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Dataset destination already exists")
    sources = preflight_sources(
        run_roots, comparison_run_roots=comparison_run_roots, max_frames=max_frames
    )
    if any(destination.resolve().is_relative_to(source.root) for source in sources):
        raise ValueError("Cannot export inside a sealed source run")
    dataset_type = _load_lerobot()
    dataset = None
    try:
        dataset = dataset_type.create(
            repo_id=repo_id,
            root=destination,
            fps=CONTROL_HZ,
            robot_type="dual_so101_sim",
            features=lerobot_features(),
            use_videos=False,
            image_writer_processes=0,
            image_writer_threads=0,
        )
        lineage = []
        for index, source in enumerate(sources):
            # Copy sealed raw evidence, including terminal images and transitive scene assets.
            # Reverification detects changes during export instead of sealing mixed input.
            raw_destination = destination / "raw_sources" / f"{index:06d}"
            raw_destination.parent.mkdir(exist_ok=True)
            shutil.copytree(source.root, raw_destination, symlinks=False)
            copied_manifest = json.loads((raw_destination / "manifest.json").read_text())
            if digest_file(raw_destination / "manifest.json") != source.evidence_manifest_sha256:
                raise ValueError("Copied evidence manifest changed")
            for name, expected in copied_manifest["files"].items():
                if digest_file(raw_destination / name) != expected:
                    raise ValueError("Copied source artifact changed")
            for frame in iter_export_frames(source):
                dataset.add_frame(frame)
            dataset.save_episode()
            current = _read_source(source.root)
            if current != source:
                raise ValueError("Source changed during export")
            lineage.append(
                {
                    "episode_index": index,
                    "episode_id": source.episode.episode_id,
                    "raw_root": raw_destination.relative_to(destination).as_posix(),
                    "episode_sha256": source.episode_sha256,
                    "evidence_manifest_sha256": source.evidence_manifest_sha256,
                    "seed": source.episode.lineage.seed,
                    "split": "train",
                    "source_simulation_start_seconds": (
                        source.episode.frames[0].observation.simulation_seconds
                    ),
                    "exported_transitions": len(source.episode.frames) - 1,
                    "lineage": source.episode.lineage.model_dump(),
                }
            )
        dataset.finalize()
        expected_frames = sum(len(source.episode.frames) - 1 for source in sources)
        if dataset.num_frames != expected_frames or dataset.num_episodes != len(sources):
            raise ValueError("LeRobot reported unexpected episode/frame counts")
        # Read real library output after footer flush; all rows retain absolute targets.
        offset = 0
        for source in sources:
            for row_index, expected in enumerate(iter_export_frames(source)):
                actual = dataset[offset]
                for feature in ("observation.state", "observation.velocity", "action"):
                    np.testing.assert_array_equal(actual[feature].numpy(), expected[feature])
                if abs(float(actual["timestamp"].item()) - row_index / CONTROL_HZ) > 1e-6:
                    raise ValueError("LeRobot timestamp differs from source transition cadence")
                for feature in CAMERA_FEATURES.values():
                    decoded = actual[feature].permute(1, 2, 0).numpy()
                    pixels = np.rint(decoded * 255).astype(np.uint8)
                    np.testing.assert_array_equal(pixels, expected[feature])
                offset += 1
        files = {
            path.relative_to(destination).as_posix(): digest_file(path)
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        }
        payload = {
            "schema_version": 1,
            "format": "lerobot_v3",
            "lerobot_version": LEROBOT_VERSION,
            "repo_id": repo_id,
            "fps": CONTROL_HZ,
            "storage": "images",
            "split": "train",
            "frames": expected_frames,
            "episodes": lineage,
            "comparison_episode_sha256": [
                digest_file(Path(root) / "demonstration" / "episode.json")
                for root in comparison_run_roots
            ],
            "camera_features": CAMERA_FEATURES,
            "joint_order": JOINT_ORDER,
            "normalization": "none; float32 radians and original uint8 RGB",
            "files": files,
        }
        payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
        with (destination / "export_manifest.json").open("x") as stream:
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return destination
    except Exception as exc:
        if dataset is not None:
            try:
                dataset.finalize()
            except Exception:
                pass
        if dataset is not None and destination.is_dir():
            with (destination / "EXPORT_FAILED.json").open("x") as stream:
                json.dump({"error": str(exc), "type": type(exc).__name__}, stream)
        raise
