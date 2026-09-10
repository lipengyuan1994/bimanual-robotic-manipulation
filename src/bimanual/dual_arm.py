"""Dual SO-101 foundation: bounded joint control and synchronized camera observations.

No teacher, grasp policy, scene object poses, or task-success evaluator is exposed.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
import xml.etree.ElementTree as ET
from importlib.resources import files
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from bimanual.evidence import EvidenceStore, Manifest, digest_file, provenance

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
JOINT_ORDER = tuple(f"{arm}/{joint}" for arm in ("left", "right") for joint in JOINTS)
CAMERAS = ("overhead", "left/wrist_cam", "right/wrist_cam")
MODEL_DIR = Path(str(files("bimanual").joinpath("models/robotstudio_so101")))
PHYSICS_HZ, CONTROL_HZ = 200, 20


def verify_assets() -> dict:
    upstream = json.loads((MODEL_DIR / "UPSTREAM.json").read_text())
    for name, expected in upstream["files"].items():
        if digest_file(MODEL_DIR / name) != expected:
            raise ValueError(f"Upstream SO-101 asset digest mismatch: {name}")
    return upstream


def scene_xml() -> str:
    """Keep upstream defaults/assets intact; namespace only instance names/references."""
    verify_assets()
    root = ET.parse(MODEL_DIR / "so101.xml").getroot()
    root.set("model", "dual_so101_foundation")
    # Relative to scene.xml in an evidence bundle; the in-memory loader uses VFS bytes.
    root.find("compiler").set("meshdir", "assets")
    visual = root.find("visual")
    ET.SubElement(visual, "global", offwidth="960", offheight="540")
    world = root.find("worldbody")
    prototype = copy.deepcopy(world.find("body"))
    world.clear()
    ET.SubElement(world, "light", pos="0 -0.2 1.8", dir="0 0 -1", directional="true")
    ET.SubElement(
        world, "geom", name="floor", type="plane", size="2 2 0.1", rgba="0.18 0.21 0.25 1"
    )
    ET.SubElement(
        world,
        "geom",
        name="workbench",
        type="box",
        pos="0 0 0.35",
        size="0.55 0.45 0.025",
        rgba="0.48 0.38 0.27 1",
    )
    ET.SubElement(world, "camera", name="overhead", pos="0 0 1.65", quat="1 0 0 0", fovy="55")
    actuators = root.find("actuator")
    templates = list(actuators)
    actuators.clear()
    for arm, x, quat in (("left", -0.28, "1 0 0 0"), ("right", 0.28, "0 0 0 1")):
        body = copy.deepcopy(prototype)
        body.set("pos", f"{x} 0 0.385")
        body.set("quat", quat)
        for number, geom in enumerate(body.iter("geom")):
            if "name" not in geom.attrib:
                geom.set("name", f"collision_or_visual_{number}")
        for element in body.iter():
            if "name" in element.attrib:
                element.set("name", f"{arm}/{element.get('name')}")
        # Keep camera intrinsics/mount position; aim its optical axis at the grasp site.
        camera = body.find(".//camera")
        forward = np.array([0.012, -0.000218, -0.098127]) - np.fromstring(
            camera.get("pos"), sep=" "
        )
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 1, 0])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        camera.attrib.pop("euler")
        camera.set("xyaxes", " ".join(str(v) for v in np.concatenate([right, up])))
        world.append(body)
        for template in templates:
            actuator = copy.deepcopy(template)
            for attr in ("name", "joint"):
                actuator.set(attr, f"{arm}/{actuator.get(attr)}")
            actuators.append(actuator)
    return ET.tostring(root, encoding="unicode")


class FoundationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    seconds: int = Field(default=4, ge=1, le=30)
    render: bool = True


class DualArm:
    """One owner per instance; synchronous observations and one-step joint targets."""

    def __init__(self, *, xml: str | None = None):
        self.xml = scene_xml() if xml is None else xml
        assets = {p.name: p.read_bytes() for p in (MODEL_DIR / "assets").glob("*.stl")}
        self.model = mujoco.MjModel.from_xml_string(self.xml, assets)
        self.data = mujoco.MjData(self.model)
        self.joint_ids = np.array([self.model.joint(n).id for n in JOINT_ORDER])
        self.actuator_ids = np.array([self.model.actuator(n).id for n in JOINT_ORDER])
        self.qadr = self.model.jnt_qposadr[self.joint_ids]
        self.vadr = self.model.jnt_dofadr[self.joint_ids]
        joint_ranges = self.model.jnt_range[self.joint_ids]
        control_ranges = self.model.actuator_ctrlrange[self.actuator_ids]
        # Upstream wrist_roll ctrlrange exceeds its joint limit: enforce BOTH.
        self.lower = np.maximum(joint_ranges[:, 0], control_ranges[:, 0])
        self.upper = np.minimum(joint_ranges[:, 1], control_ranges[:, 1])
        self.renderer = None
        self.reset()

    def reset(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        self.episode_id = uuid.uuid4().hex
        self.sequence = 0
        self.active = True
        self.home = np.tile([0.0, -1.0, 0.8, 1.2, 0.0, 0.8], 2)
        self.data.qpos[self.qadr] = self.home
        self.data.ctrl[self.actuator_ids] = self.home
        mujoco.mj_forward(self.model, self.data)
        self.max_contacts = int(self.data.ncon)

    def observe(self, *, render: bool = True) -> dict:
        rgb = {}
        if render:
            if self.renderer is None:
                self.renderer = mujoco.Renderer(self.model, height=270, width=480)
            for camera in CAMERAS:
                self.renderer.update_scene(self.data, camera=camera)
                rgb[camera] = self.renderer.render().copy()
        return dict(
            schema_version=1,
            episode_id=self.episode_id,
            sequence=self.sequence,
            simulation_seconds=float(self.data.time),
            observed_monotonic_ns=time.monotonic_ns(),
            joint_order=list(JOINT_ORDER),
            joint_position_rad=self.data.qpos[self.qadr].copy(),
            joint_velocity_rad_s=self.data.qvel[self.vadr].copy(),
            rgb=rgb,
            camera_order=list(rgb),
        )

    def step(self, targets: np.ndarray, *, episode_id: str, sequence: int) -> None:
        if not self.active:
            raise ValueError("Episode stopped; reset required")
        if episode_id != self.episode_id or sequence != self.sequence:
            raise ValueError("Stale action episode or observation sequence")
        values = np.asarray(targets, dtype=float)
        if values.shape != (12,) or not np.isfinite(values).all():
            raise ValueError("Expected 12 finite joint targets in radians")
        if np.any(values < self.lower) or np.any(values > self.upper):
            raise ValueError("Action outside joint/actuator bounds")
        self.data.ctrl[self.actuator_ids] = values
        for _ in range(PHYSICS_HZ // CONTROL_HZ):
            mujoco.mj_step(self.model, self.data)
            self.after_physics_step()
            self.max_contacts = max(self.max_contacts, int(self.data.ncon))
            if (
                not np.isfinite(self.data.qpos).all()
                or not np.isfinite(self.data.qvel).all()
                or any(w.number for w in self.data.warning)
            ):
                self.active = False
                raise RuntimeError("Non-finite state or MuJoCo warning; episode stopped")
        self.sequence += 1

    def after_physics_step(self) -> None:
        """Extension point for per-step experiment scoring and collision guards."""

    def stop(self) -> None:
        # No asynchronous action queue exists; advancing physics is now prohibited.
        self.active = False

    def close(self) -> None:
        self.stop()
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None

    def mapping(self) -> dict:
        return dict(
            schema_version=1,
            joint_order=list(JOINT_ORDER),
            camera_order=list(CAMERAS),
            joint_ids=self.joint_ids.tolist(),
            actuator_ids=self.actuator_ids.tolist(),
            qpos_addresses=self.qadr.tolist(),
            velocity_addresses=self.vadr.tolist(),
            lower_rad=self.lower.tolist(),
            upper_rad=self.upper.tolist(),
            physics_hz=PHYSICS_HZ,
            control_hz=CONTROL_HZ,
            normalization="none_radians",
        )


def run_foundation(
    config: FoundationConfig, *, store: EvidenceStore, project_root: Path
) -> Manifest:
    directory = store.new_run()
    source = provenance(project_root)
    env = None
    rows, frames, contact_pairs = [], [], set()
    started = time.perf_counter()
    try:
        env = DualArm()
        (directory / "scene.xml").write_text(env.xml)
        # Bundle exact meshes so the exported scene has no checkout-dependent paths.
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2) + "\n")
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2) + "\n")
        (directory / "config.json").write_text(config.model_dump_json(indent=2) + "\n")
        setup_seconds = time.perf_counter() - started
        loop_start = time.perf_counter()
        max_tracking_error = 0.0
        for index in range(config.seconds * CONTROL_HZ + 1):
            obs = env.observe(render=config.render)
            row = {
                k: v.tolist() if isinstance(v, np.ndarray) else v
                for k, v in obs.items()
                if k != "rgb"
            }
            if config.render:
                images = [Image.fromarray(obs["rgb"][camera]) for camera in CAMERAS]
                frame = Image.new("RGB", (480 * 3, 270))
                for col, image in enumerate(images):
                    frame.paste(image, (col * 480, 0))
                    if index == 0:
                        image.save(directory / f"camera-{col}.png")
                frames.append(frame)
            if index < config.seconds * CONTROL_HZ:
                targets = env.home.copy()
                targets[0] += 0.12 * np.sin(2 * np.pi * 0.25 * env.data.time)
                targets[6] -= 0.12 * np.sin(2 * np.pi * 0.25 * env.data.time)
                row["action_target_rad"] = targets.tolist()
                env.step(targets, episode_id=obs["episode_id"], sequence=obs["sequence"])
                max_tracking_error = max(
                    max_tracking_error, float(np.max(np.abs(env.data.qpos[env.qadr] - targets)))
                )
            else:
                row["action_target_rad"] = None
            rows.append(row)
            for contact in env.data.contact:
                names = tuple(env.model.geom(int(g)).name or f"geom-{g}" for g in contact.geom)
                contact_pairs.add(names)
        loop_seconds = time.perf_counter() - loop_start
        if env.max_contacts:
            raise RuntimeError("Unexpected contact during free-space foundation motion")
        (directory / "observations.jsonl").write_text(
            "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows)
        )
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
            kind="dual_arm_foundation",
            outcome="completed",
            config=config.model_dump(),
            source=source,
            claims=["dual_so101_step", "bounded_joint_control"]
            + (["three_camera_render"] if config.render else []),
            metrics=dict(
                simulation_seconds=float(env.data.time),
                loop_wall_seconds=loop_seconds,
                setup_seconds=setup_seconds,
                wall_seconds=time.perf_counter() - started,
                simulation_to_wall_ratio=config.seconds / loop_seconds,
                timing_scope=(
                    "loop includes observations/render; total includes setup/encoding, "
                    "excludes sealing"
                ),
                physics_hz=PHYSICS_HZ,
                control_hz=CONTROL_HZ,
                observations=len(rows),
                rendered=config.render,
                max_joint_tracking_error_rad=max_tracking_error,
                max_contacts_per_physics_step=env.max_contacts,
                contact_pairs=sorted(contact_pairs),
                contact_sampling="control boundaries, not collision safety certification",
                mujoco_version=mujoco.__version__,
                manipulation_success=None,
            ),
        )
    except (Exception, KeyboardInterrupt) as exc:
        if not (directory / "manifest.json").exists():
            (directory / "error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
            (directory / "partial-observations.jsonl").write_text(
                "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows)
            )
            store.seal(
                directory,
                kind="dual_arm_foundation",
                outcome="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                config=config.model_dump(),
                source=source,
                claims=[],
                metrics={"error": str(exc), "manipulation_success": None},
            )
        raise
    finally:
        if env:
            env.close()
