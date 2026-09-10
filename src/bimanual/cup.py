"""Contact-only placement of a small hollow cup; one declared nominal scene."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

import mujoco
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict

from bimanual.dual_arm import CAMERAS, MODEL_DIR, DualArm, verify_assets
from bimanual.evidence import EvidenceStore, Manifest, provenance
from bimanual.grasp import GraspConfig, grasp_xml, invalid_contact_trace_row, score_grasp
from bimanual.teacher import check_carried_path, check_joint_path, solve_downward

INITIAL = np.array([-0.136, -0.110, 0.378])
DESTINATION = np.array([-0.066, -0.153, 0.378])


class CupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    render: bool = True
    missing_object: bool = False
    skip_close: bool = False
    arm: Literal["left", "right"] = "left"


def cup_xml(config: CupConfig) -> str:
    root = ET.fromstring(grasp_xml(GraspConfig(missing_object=True)))
    root.set("model", "dual_so101_contact_cup")
    if config.missing_object:
        return ET.tostring(root, encoding="unicode")
    cup = ET.SubElement(
        root.find("worldbody"),
        "body",
        name="cup",
        pos=".136 .110 .378" if config.arm == "right" else "-.136 -.110 .378",
        euler=f"0 0 {np.pi if config.arm == 'right' else 0}",
    )
    ET.SubElement(cup, "freejoint", name="cup/free")

    def geom(name, **attributes):
        ET.SubElement(
            cup,
            "geom",
            name=f"cup/{name}",
            rgba=".86 .75 .55 1",
            friction="1 .005 .0001",
            solref=".01 1",
            solimp=".95 .99 .001",
            **attributes,
        )

    geom("base", type="cylinder", size=".028 .003", mass=".018")
    # A hollow cup assembled from collision walls, not a filled proxy cylinder.
    for i in range(16):
        theta = 2 * np.pi * i / 16
        geom(
            f"wall{i}",
            type="box",
            pos=f"{0.029 * np.cos(theta)} {0.029 * np.sin(theta)} .03",
            size=".0018 .0059 .03",
            euler=f"0 0 {theta}",
            mass=str(0.033 / 16),
        )
    for name, height in (("handle_top", 0.047), ("handle_bottom", 0.013)):
        geom(
            name,
            type="capsule",
            fromto=f".028 0 {height} .049 0 {height}",
            size=".004",
            mass=".003",
        )
    geom("handle_outer", type="capsule", fromto=".049 0 .013 .049 0 .047", size=".004", mass=".003")
    return ET.tostring(root, encoding="unicode")


class CupEnvironment(DualArm):
    def __init__(self, config: CupConfig):
        self.stage = "settle"
        self.contact_trace: list[dict] = []
        self.has_object = not config.missing_object
        self.arm = config.arm
        super().__init__(xml=cup_xml(config))
        self.fingers = tuple(
            {
                self.model.geom(i).name
                for i in range(self.model.ngeom)
                if self.model.body(int(self.model.geom_bodyid[i])).name == f"{self.arm}/{body}"
            }
            for body in ("gripper", "moving_jaw_so101_v1")
        )
        self.object_geoms = {
            self.model.geom(i).name
            for i in range(self.model.ngeom)
            if self.model.body(int(self.model.geom_bodyid[i])).name == "cup"
        }

    def step(self, targets, *, episode_id, sequence):
        values = np.asarray(targets, float)
        other = slice(6, 12) if self.arm == "left" else slice(0, 6)
        if values.shape == (12,) and not np.allclose(
            values[other], self.home[other], rtol=0, atol=1e-12
        ):
            raise ValueError("Cup teacher does not own the other arm")
        super().step(values, episode_id=episode_id, sequence=sequence)

    def allowed(self, pair):
        names = set(pair)
        return bool(names & self.object_geoms) and bool(
            names & ({"workbench"} | self.fingers[0] | self.fingers[1])
        )

    def after_physics_step(self):
        mujoco.mj_forward(self.model, self.data)
        row = dict(
            stage=self.stage,
            simulation_seconds=float(self.data.time),
            object_position_m=self.data.body("cup").xpos.tolist() if self.has_object else None,
            object_velocity=self.data.joint("cup/free").qvel.tolist() if self.has_object else None,
            upright_cosine=float(self.data.body("cup").xmat.reshape(3, 3)[2, 2])
            if self.has_object
            else None,
            fixed_jaw_normal_force_n=0.0,
            moving_jaw_normal_force_n=0.0,
            table_contact=False,
            contact_pairs=[],
            forbidden_pairs=[],
            max_penetration_m=0.0,
        )
        for i, contact in enumerate(self.data.contact):
            pair = tuple(self.model.geom(int(g)).name for g in contact.geom)
            names = set(pair)
            row["contact_pairs"].append(pair)
            if not self.allowed(pair):
                row["forbidden_pairs"].append(pair)
            row["max_penetration_m"] = max(row["max_penetration_m"], -float(contact.dist))
            if names & self.object_geoms and contact.efc_address >= 0:
                force = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, i, force)
                normal = max(0.0, float(force[0]))
                if names & self.fingers[0]:
                    row["fixed_jaw_normal_force_n"] += normal
                if names & self.fingers[1]:
                    row["moving_jaw_normal_force_n"] += normal
                if "workbench" in names and normal > 0.01:
                    row["table_contact"] = True
        self.contact_trace.append(row)
        if row["forbidden_pairs"] or row["max_penetration_m"] > 0.0025:
            self.stop()
            raise RuntimeError(
                f"Forbidden contact during {self.stage}: {row['forbidden_pairs'][0]}"
                if row["forbidden_pairs"]
                else "Contact penetration exceeds 2.5 mm"
            )


def score_cup(trace: list[dict], *, arm: str = "left") -> dict:
    if arm not in {"left", "right"}:
        raise ValueError("Unknown cup arm")
    invalid = invalid_contact_trace_row(trace, required_scalars=("upright_cosine",))
    if invalid is not None:
        metrics = score_cup([], arm=arm)
        metrics.update(trace_valid=False, invalid_trace_row=invalid)
        return metrics
    mirror = np.array([1.0, 1.0, 1.0]) if arm == "left" else np.array([-1.0, -1.0, 1.0])
    initial, destination = INITIAL * mirror, DESTINATION * mirror
    metrics = score_grasp(trace, initial, destination)
    settled = [r for r in trace if r["stage"] == "settled"]
    upright = len(settled) == 400 and all(
        r["upright_cosine"] is not None and r["upright_cosine"] >= np.cos(np.deg2rad(10))
        for r in settled
    )
    displacement = (
        float(np.linalg.norm(np.array(trace[-1]["object_position_m"][:2]) - initial[:2]))
        if trace and trace[-1]["object_position_m"] is not None
        else 0.0
    )
    metrics.update(
        cup_success=bool(metrics["placement_success"] and upright and displacement >= 0.06),
        released_upright=bool(upright),
        actual_displacement_xy_m=displacement,
        max_jaw_normal_force_n=max(
            (max(r["fixed_jaw_normal_force_n"], r["moving_jaw_normal_force_n"]) for r in trace),
            default=0.0,
        ),
    )
    return metrics


def run_cup(config: CupConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source, started = provenance(project_root), time.perf_counter()
    env = None
    observations, frames = [], []
    outcome, error = "failed", None
    try:
        env = CupEnvironment(config)
        (directory / "scene.xml").write_text(env.xml)
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2))
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "config.json").write_text(config.model_dump_json(indent=2))
        if config.missing_object:
            raise RuntimeError("Cup is missing; no manipulation attempted")

        def record(action):
            raw = env.observe(render=config.render and env.sequence % 4 == 0)
            row = {
                k: v.tolist() if isinstance(v, np.ndarray) else v
                for k, v in raw.items()
                if k != "rgb"
            }
            row.update(
                stage=env.stage, action_target_rad=action.tolist() if action is not None else None
            )
            observations.append(row)
            if raw["rgb"]:
                frame = Image.new("RGB", (1440, 300), "#14202b")
                for col, camera in enumerate(CAMERAS):
                    frame.paste(Image.fromarray(raw["rgb"][camera]), (480 * col, 30))
                ImageDraw.Draw(frame).text(
                    (12, 8),
                    f"CONTACT CUP TEACHER | {env.stage} | {env.data.time:.2f}s"
                    " | overhead / left wrist / right wrist",
                    fill="white",
                )
                frames.append(frame)

        def execute(stage, goal, steps):
            env.stage = stage
            start = env.data.ctrl[env.actuator_ids].copy()
            if stage in {"transport", "lower"}:
                check_carried_path(
                    env, start, goal, env.allowed, body_name="cup", site_name=f"{config.arm}/pinch"
                )
            else:
                check_joint_path(env, start, goal, env.allowed)
            for i in range(steps):
                alpha = (i + 1) / steps
                alpha = alpha * alpha * (3 - 2 * alpha)
                action = start + alpha * (goal - start)
                record(action)
                env.step(action, episode_id=env.episode_id, sequence=env.sequence)
                if stage == "lower" and env.contact_trace[-1]["table_contact"]:
                    break
            return env.data.ctrl[env.actuator_ids].copy()

        q = env.home.copy()
        grip = 5 if config.arm == "left" else 11
        mirror = np.array([1.0, 1.0, 1.0]) if config.arm == "left" else np.array([-1.0, -1.0, 1.0])
        q[grip] = 1.2
        above = np.array([-0.15, -0.08, 0.47]) * mirror
        target = np.array([-0.15, -0.08, 0.405]) * mirror
        execute("settle", q, 20)
        q = solve_downward(env, above, q, arm=config.arm)
        execute("approach", q, 40)
        q = solve_downward(env, target, q, arm=config.arm)
        execute("descend", q, 40)
        q[grip] = 1.2 if config.skip_close else 0.7
        execute("close", q, 30)
        q = solve_downward(env, above, q, arm=config.arm)
        execute("lift", q, 60)
        execute("hold", q, 40)
        if not score_cup(env.contact_trace, arm=config.arm)["hold_passed"]:
            raise RuntimeError("Cup failed the two-second airborne bilateral hold")
        above[:2] += np.array([0.07, -0.043]) * mirror[:2]
        q = solve_downward(env, above, q, arm=config.arm)
        execute("transport", q, 60)
        q = solve_downward(
            env, target + np.array([0.07, -0.043, 0.009]) * mirror, q, arm=config.arm
        )
        q = execute("lower", q, 60)
        q[grip] = 1.2
        execute("release", q, 30)
        q = solve_downward(env, above, q, arm=config.arm)
        execute("retreat", q, 40)
        execute("settled", q, 40)
        record(None)
        if not score_cup(env.contact_trace, arm=config.arm)["cup_success"]:
            raise RuntimeError("Cup failed released upright placement acceptance")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        (directory / "error.txt").write_text(error + "\n")
    finally:
        metrics = score_cup(env.contact_trace if env else [], arm=config.arm)
        if env is not None:
            metrics.update(
                simulation_seconds=float(env.data.time), mujoco_version=mujoco.__version__
            )
            env.close()
        (directory / "observations.jsonl").write_text(
            "".join(json.dumps(r, allow_nan=False) + "\n" for r in observations)
        )
        (directory / "scoring-truth.jsonl").write_text(
            "".join(
                json.dumps(r, allow_nan=False) + "\n" for r in (env.contact_trace if env else [])
            )
        )
        if frames:
            frames[0].save(directory / "preview.png")
            frames[0].save(
                directory / "replay.gif",
                save_all=True,
                append_images=frames[1:],
                duration=200,
                loop=0,
            )
        metrics.update(
            error=error,
            wall_seconds=time.perf_counter() - started,
            rendered=config.render,
            teacher_uses_simulator_truth=True,
            planning_model="scratch rigid object-to-tool transform; live free-body contacts",
        )
        if outcome != "completed":
            metrics["cup_success"] = False
    return store.seal(
        directory,
        kind="contact_cup_teacher",
        outcome=outcome,
        config=config.model_dump(),
        source=source,
        claims=["contact_cup_upright_placement"] if outcome == "completed" else [],
        metrics=metrics,
    )
