"""A generic driven pendulum for learning and environment validation.

This is not an SO-101 scene, manipulation controller, or learned policy.
"""

from __future__ import annotations

import csv
import math
import time
from importlib.resources import files
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from bimanual.evidence import EvidenceStore, Manifest, provenance


class LabConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    seed: int = Field(default=7, ge=0, le=2**32 - 1)
    seconds: int = Field(default=4, ge=1, le=30)
    damping: float = Field(default=0.1, ge=0, le=5)
    torque: float = Field(default=0.2, ge=-0.5, le=0.5)
    render: bool = True


def simulate(config: LabConfig) -> tuple[list[dict[str, float]], list[Image.Image], float]:
    xml = files("bimanual").joinpath("models/pendulum.xml").read_text()
    model = mujoco.MjModel.from_xml_string(xml)
    model.dof_damping[:] = config.damping
    data = mujoco.MjData(model)
    data.qpos[0] = np.random.default_rng(config.seed).uniform(-0.7, 0.7)
    mujoco.mj_forward(model, data)
    rows, frames = [], []
    renderer = mujoco.Renderer(model, height=320, width=480) if config.render else None
    start = time.perf_counter()
    try:
        for step in range(config.seconds * 20 + 1):
            # Each logged observation is at the start of its action interval.
            # The final observation has no subsequent applied action.
            action = config.torque * math.sin(2 * math.pi * 0.5 * data.time)
            rows.append(
                dict(
                    step=step,
                    simulation_seconds=float(data.time),
                    angle_rad=float(data.qpos[0]),
                    velocity_rad_s=float(data.qvel[0]),
                    action_nm=action if step < config.seconds * 20 else 0.0,
                )
            )
            if renderer:
                renderer.update_scene(data, camera="overview")
                frames.append(Image.fromarray(renderer.render().copy()))
            if step < config.seconds * 20:
                data.ctrl[0] = action
                mujoco.mj_step(model, data, nstep=10)
            if not np.isfinite(np.concatenate([data.qpos, data.qvel])).all():
                raise RuntimeError("Non-finite simulation state")
    finally:
        if renderer:
            renderer.close()
    return rows, frames, time.perf_counter() - start


def run_lab(config: LabConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source = provenance(project_root)
    xml = files("bimanual").joinpath("models/pendulum.xml").read_text()
    (directory / "scene.xml").write_text(xml)
    (directory / "config.json").write_text(config.model_dump_json(indent=2) + "\n")
    try:
        rows, frames, elapsed = simulate(config)
        with (directory / "trajectory.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        if frames:
            frames[0].save(directory / "preview.png")
            frames[0].save(
                directory / "replay.gif",
                save_all=True,
                append_images=frames[1:],
                duration=50,
                loop=0,
            )
        return store.seal(
            directory,
            kind="preparation_pendulum",
            outcome="completed",
            config=config.model_dump(),
            metrics={
                "simulation_seconds": rows[-1]["simulation_seconds"],
                "wall_seconds": elapsed,
                "simulation_to_wall_ratio": config.seconds / elapsed,
                "timing_scope": "physics/render loop; excludes setup and artifact encoding",
                "physics_hz": 200,
                "control_hz": 20,
                "observations": len(rows),
                "mujoco_version": mujoco.__version__,
                "rendered": bool(frames),
                "manipulation_success": None,
            },
            source=source,
            claims=["generic_physics_step"] + (["offscreen_render"] if frames else []),
        )
    except (Exception, KeyboardInterrupt) as exc:
        if (directory / "manifest.json").exists():
            raise  # Never alter an already published record after a later error.
        (directory / "error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
        store.seal(
            directory,
            kind="preparation_pendulum",
            outcome="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            config=config.model_dump(),
            metrics={"error": str(exc), "manipulation_success": None},
            source=source,
            claims=[],
        )
        raise
