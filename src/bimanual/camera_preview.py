"""Bounded previews of existing worker captures; never robot-control inputs."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import stat
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict

from bimanual.contracts import Observation


class PreviewCapture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    camera_source: Literal["live_mujoco", "injected_unverified"]
    observation: Observation


def bounded_file(root: Path, path: Path, limit: int) -> bytes:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Preview path escapes worker")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Preview is not a regular file")
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("Preview exceeds size limit")
    return value


def read_camera_preview(worker: Path) -> dict | None:
    try:
        capture = PreviewCapture.model_validate_json(
            bounded_file(worker, worker / "camera-preview.json", 32768)
        )
        observation = capture.observation
        images = []
        for frame in observation.frames:
            content = bounded_file(worker, worker / frame.artifact.path, 1024 * 1024)
            if hashlib.sha256(content).hexdigest() != frame.artifact.sha256:
                return None
            with Image.open(io.BytesIO(content)) as image:
                if image.format != "PNG" or image.size != (480, 270) or image.mode != "RGB":
                    return None
                image.verify()
            images.append(
                {
                    "camera": frame.camera,
                    "data_url": "data:image/png;base64," + base64.b64encode(content).decode(),
                }
            )
        return dict(
            episode_id=observation.episode_id,
            sequence=observation.sequence,
            simulation_seconds=observation.simulation_seconds,
            observed_monotonic_ns=observation.observed_monotonic_ns,
            camera_source=capture.camera_source,
            images=images,
            task_success_verified=False,
        )
    except (OSError, ValueError, RuntimeError, SyntaxError, Image.DecompressionBombError):
        return None
