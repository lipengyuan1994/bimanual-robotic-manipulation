"""Truth-assisted drawer-to-table teacher for an explicit ergonomic utensil scene."""

from __future__ import annotations

import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

import mujoco
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict

from bimanual.drawer import DrawerConfig, DrawerEnvironment, drawer_xml
from bimanual.dual_arm import CAMERAS, MODEL_DIR, DualArm, verify_assets
from bimanual.evidence import EvidenceStore, Manifest, provenance
from bimanual.teacher import ReachError, check_carried_path, check_joint_path, solve_downward

OBJECTS = ("spoon", "fork")
PHYSICS_HZ = 1000
VARIANT = "ergonomic_flush_roof_v1"
DESTINATIONS = {"spoon": (-0.12, 0.045), "fork": (-0.06, 0.062)}


class UtensilConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    render: bool = True
    missing_object: Literal["spoon", "fork"] | None = None
    skip_close: Literal["spoon", "fork"] | None = None
    scene_variant: Literal["ergonomic_flush_roof_v1"] = VARIANT


def utensils_xml(config: UtensilConfig) -> str:
    """Named scene variant; does not alter the canonical thin-shaft drawer scene."""
    root = ET.fromstring(drawer_xml(DrawerConfig(render=False)))
    root.set("model", "dual_so101_ergonomic_utensils")
    root.find("option").set("timestep", ".001")
    roof = root.find(".//geom[@name='cabinet_roof']")
    roof.set("pos", "-.014 -.18 .433")
    roof.set("size", ".096 .093 .004")
    world = root.find("worldbody")
    for name in OBJECTS:
        body = root.find(f".//body[@name='{name}']")
        if config.missing_object == name:
            world.remove(body)
            continue
        xyz = np.fromstring(body.get("pos"), sep=" ")
        xyz[0] += 0.015
        xyz[2] = 0.400
        body.set("pos", " ".join(str(v) for v in xyz))
        shaft = body.find(f"geom[@name='{name}/shaft']")
        shaft.attrib.pop("fromto")
        shaft.attrib.update(
            type="box",
            size=".006 .02 .006",
            pos="0 -.032 0",
            mass=".012",
            priority="1",
            condim="6",
            friction="1 .01 .002",
            solref=".01 1",
        )
        ET.SubElement(
            body,
            "geom",
            name=name + "/neck",
            type="capsule",
            fromto="0 -.012 0 0 .035 0",
            size=".0025",
            mass=".002",
            rgba=".8 .8 .85 1",
        )
    gripper = root.find(".//body[@name='left/gripper']")
    ET.SubElement(
        gripper,
        "site",
        name="left/utensil_pinch",
        pos="-.001 -.000218 -.0982",
        quat="1 0 1 0",
        size=".002",
        group="3",
    )
    return ET.tostring(root, encoding="unicode")


class UtensilEnvironment(DrawerEnvironment):
    def __init__(self, config: UtensilConfig):
        self.stage = "settle"
        self.contact_trace: list[dict] = []
        self.active_utensil: str | None = None
        self.placed: set[str] = set()
        self.objects = tuple(n for n in OBJECTS if n != config.missing_object)
        DualArm.__init__(self, xml=utensils_xml(config), physics_hz=PHYSICS_HZ)
        self.fingers = tuple(
            {
                self.model.geom(i).name
                for i in range(self.model.ngeom)
                if self.model.body(int(self.model.geom_bodyid[i])).name == f"left/{body}"
            }
            for body in ("gripper", "moving_jaw_so101_v1")
        )

    def allowed(self, pair):
        if (
            any(n.startswith(tuple(obj + "/" for obj in self.placed)) for n in pair)
            and "workbench" in pair
        ):
            return True
        if self.active_utensil and any(n.startswith(self.active_utensil + "/") for n in pair):
            if set(pair) & (self.fingers[0] | self.fingers[1]) or "workbench" in pair:
                return True
        return super().allowed(pair)

    def after_physics_step(self):
        mujoco.mj_forward(self.model, self.data)
        opening = float(self.data.joint("drawer/slide").qpos[0])
        row = dict(
            stage=self.stage,
            simulation_seconds=float(self.data.time),
            opening_m=opening,
            drawer_speed_m_s=float(self.data.joint("drawer/slide").qvel[0]),
            jaw_normal_force_n=[0.0, 0.0],
            forbidden_pairs=[],
            contact_pairs=[],
            max_penetration_m=0.0,
            joint_limit_overtravel_m=max(0.0, -opening, opening - 0.11),
            objects={
                n: dict(
                    position_m=self.data.body(n).xpos.tolist(),
                    quaternion_wxyz=self.data.body(n).xquat.tolist(),
                    velocity=self.data.joint(n + "/free").qvel.tolist(),
                    jaw_normal_force_n=[0.0, 0.0],
                    support=[],
                )
                for n in self.objects
            },
        )
        for i, contact in enumerate(self.data.contact):
            pair = tuple(self.model.geom(int(g)).name for g in contact.geom)
            row["contact_pairs"].append(pair)
            row["max_penetration_m"] = max(row["max_penetration_m"], -float(contact.dist))
            if not self.allowed(pair):
                row["forbidden_pairs"].append(pair)
            force = np.zeros(6)
            if contact.efc_address >= 0:
                mujoco.mj_contactForce(self.model, self.data, i, force)
            normal = max(0.0, float(force[0]))
            for jaw, names in enumerate(self.fingers):
                if set(pair) & names:
                    if set(pair) & {"drawer/handle", "drawer/stem"}:
                        row["jaw_normal_force_n"][jaw] += normal
                    for obj in self.objects:
                        if any(n.startswith(obj + "/") for n in pair):
                            row["objects"][obj]["jaw_normal_force_n"][jaw] += normal
            for obj in self.objects:
                if any(n.startswith(obj + "/") for n in pair):
                    row["objects"][obj]["support"].extend(
                        n
                        for n in pair
                        if n.startswith(("drawer/", "cabinet_"))
                        or n == "workbench"
                        or any(n.startswith(other + "/") for other in self.objects if other != obj)
                    )
        self.contact_trace.append(row)
        if (
            row["forbidden_pairs"]
            or max(row["max_penetration_m"], row["joint_limit_overtravel_m"]) > 0.0025
        ):
            self.stop()
            raise RuntimeError(
                f"Forbidden contact: {row['forbidden_pairs']}"
                if row["forbidden_pairs"]
                else "Contact penetration or joint overtravel exceeds 2.5 mm"
            )
        if self.active_utensil and self.stage in {
            self.active_utensil + "_clearance",
            self.active_utensil + "_transport",
        }:
            if not _airborne(row["objects"][self.active_utensil]):
                self.stop()
                raise RuntimeError("Lost continuous airborne bilateral carry")


def _airborne(obj: dict) -> bool:
    return min(obj["jaw_normal_force_n"]) > 0.01 and not obj["support"]


def _placed(obj: dict, name: str) -> bool:
    return bool(
        obj["jaw_normal_force_n"] == [0, 0]
        and set(obj["support"]) == {"workbench"}
        and np.linalg.norm(np.array(obj["position_m"][:2]) - DESTINATIONS[name]) < 0.025
        and 0.375 < obj["position_m"][2] < 0.395
        and np.linalg.norm(obj["velocity"][:3]) < 0.01
        and np.linalg.norm(obj["velocity"][3:]) < 0.1
    )


def _valid_truth_row(row: dict) -> bool:
    """Reject incomplete or nonfinite evidence before any min/max or success checks."""

    def vector(values, size, *, nonnegative=False):
        return (
            isinstance(values, (list, tuple))
            and len(values) == size
            and all(
                type(value) in (int, float)
                and math.isfinite(value)
                and (not nonnegative or value >= 0)
                for value in values
            )
        )

    try:
        if not isinstance(row, dict) or not isinstance(row["stage"], str):
            return False
        if not vector([row[k] for k in ("simulation_seconds", "opening_m", "drawer_speed_m_s")], 3):
            return False
        if not vector(
            [row[k] for k in ("max_penetration_m", "joint_limit_overtravel_m")], 2, nonnegative=True
        ):
            return False
        if not vector(row["jaw_normal_force_n"], 2, nonnegative=True):
            return False
        for field in ("contact_pairs", "forbidden_pairs"):
            if not isinstance(row[field], list) or not all(
                isinstance(pair, (list, tuple))
                and len(pair) == 2
                and all(isinstance(name, str) for name in pair)
                for pair in row[field]
            ):
                return False
        if set(row["objects"]) != set(OBJECTS):
            return False
        for obj in row["objects"].values():
            if not all(
                vector(obj[key], size)
                for key, size in (("position_m", 3), ("quaternion_wxyz", 4), ("velocity", 6))
            ):
                return False
            if not vector(obj["jaw_normal_force_n"], 2, nonnegative=True):
                return False
            if not isinstance(obj["support"], list) or not all(
                isinstance(name, str) for name in obj["support"]
            ):
                return False
        return True
    except (KeyError, TypeError, AttributeError):
        return False


def score_utensils(trace: list[dict]) -> dict:
    """Independent fixed-sequence 1 kHz scorer; truth is never a policy observation."""
    for index, row in enumerate(trace):
        if not _valid_truth_row(row):
            # Reuse the normal empty-run result so consumers retain stable metric keys.
            metrics = score_utensils([])
            metrics.update(trace_valid=False, invalid_trace_row=index)
            return metrics
    stages = [
        ("settle", 1000),
        ("approach", 3000),
        ("descend", 3000),
        ("close", 2000),
        ("pull", 6000),
        ("open_hold", 2000),
        ("release", 2000),
        ("retreat", 3000),
        ("released_hold", 2000),
    ]
    for obj in OBJECTS:
        stages.extend(
            (obj + "_" + stage, count)
            for stage, count in [
                ("approach", 3000),
                ("preshape", 2000),
                ("descend", 3000),
                ("close", 2000),
                ("lift", 3000),
                ("hold", 2000),
                ("clearance", 3000),
                ("transport", 7200),
                ("lower", 3000),
                ("release", 2000),
                ("retreat", 3000),
                ("settled", 2000),
            ]
        )
    by_stage = {stage: [] for stage, _ in stages}
    blocks = []
    for row in trace:
        by_stage.setdefault(row["stage"], []).append(row)
        if not blocks or blocks[-1][0] != row["stage"]:
            blocks.append([row["stage"], 1])
        else:
            blocks[-1][1] += 1
    ordered = blocks == [[stage, count] for stage, count in stages]
    contiguous = (
        bool(trace)
        and abs(trace[0]["simulation_seconds"] - 0.001) < 1e-9
        and np.allclose(np.diff([r["simulation_seconds"] for r in trace]), 0.001, rtol=0, atol=1e-9)
    )
    closed = bool(trace) and trace[0]["stage"] == "settle" and abs(trace[0]["opening_m"]) <= 0.001
    initial = trace[0]["opening_m"] if trace else 0.0

    def stored(row):
        centre = np.array([-0.02 - row["opening_m"], -0.18, 0.39])
        return set(row["objects"]) == set(OBJECTS) and all(
            abs((np.array(o["position_m"]) - centre)[0]) < 0.08
            and abs((np.array(o["position_m"]) - centre)[1]) < 0.08
            and 0.392 < o["position_m"][2] < 0.424
            for o in row["objects"].values()
        )

    def opened(row):
        return (
            row["opening_m"] >= 0.08
            and row["opening_m"] - initial >= 0.08
            and abs(row["drawer_speed_m_s"]) < 0.01
        )

    prefix = [r for r in trace if r["stage"] in {s for s, _ in stages[:9]}]
    drawer = bool(
        closed
        and len(prefix) == 24000
        and all(stored(r) for r in prefix)
        and len(by_stage["pull"]) == 6000
        and all(min(r["jaw_normal_force_n"]) > 0.01 for r in by_stage["pull"])
        and len(by_stage["open_hold"]) == 2000
        and all(opened(r) and min(r["jaw_normal_force_n"]) > 0.01 for r in by_stage["open_hold"])
        and len(by_stage["released_hold"]) == 2000
        and all(opened(r) and r["jaw_normal_force_n"] == [0, 0] for r in by_stage["released_hold"])
    )
    metrics = dict(
        trace_valid=bool(trace),
        drawer_opened=drawer,
        initially_closed=bool(closed),
        phases_ordered=bool(ordered),
        contiguous_physics=bool(contiguous),
        physics_hz=PHYSICS_HZ,
        control_hz=20,
        forbidden_contact_samples=sum(bool(r["forbidden_pairs"]) for r in trace),
        max_penetration_m=max((r["max_penetration_m"] for r in trace), default=0.0),
        max_joint_limit_overtravel_m=max(
            (r["joint_limit_overtravel_m"] for r in trace), default=0.0
        ),
        final_opening_m=trace[-1]["opening_m"] if trace else None,
        manipulation_success=None,
    )
    both = True
    for obj in OBJECTS:
        ok = True
        for stage, expected in [
            ("hold", 2000),
            ("clearance", 3000),
            ("transport", 7200),
            ("lower", 3000),
            ("settled", 2000),
        ]:
            rows = by_stage[obj + "_" + stage]
            passed = sum(
                obj in r["objects"]
                and (
                    _placed(r["objects"][obj], obj)
                    if stage == "settled"
                    else _airborne(r["objects"][obj])
                )
                for r in rows
            )
            metrics[obj + "_" + stage + "_samples"] = int(passed)
            ok = ok and len(rows) == expected and passed == expected
        final = by_stage["fork_settled"]
        ok = (
            ok
            and len(final) == 2000
            and all(
                obj in r["objects"] and _placed(r["objects"][obj], obj) and opened(r) for r in final
            )
        )
        metrics[obj + "_placed"] = bool(ok)
        metrics[obj + "_final_position_m"] = (
            trace[-1]["objects"].get(obj, {}).get("position_m") if trace else None
        )
        metrics[obj + "_max_jaw_normal_force_n"] = max(
            (max(r["objects"][obj]["jaw_normal_force_n"]) for r in trace if obj in r["objects"]),
            default=0.0,
        )
        both = both and ok
    metrics["utensils_success"] = bool(
        drawer
        and both
        and ordered
        and contiguous
        and not metrics["forbidden_contact_samples"]
        and max(metrics["max_penetration_m"], metrics["max_joint_limit_overtravel_m"]) <= 0.0025
    )
    return metrics


def solve_utensil_tip(env: DualArm, target, initial, *, arm: str) -> np.ndarray:
    """Downward position IK retaining wrist roll; live simulation is untouched."""
    if arm not in {"left", "right"}:
        raise ReachError("Unknown arm")
    target, initial = np.asarray(target, float), np.asarray(initial, float)
    if target.shape != (3,) or not np.isfinite(target).all():
        raise ReachError("Expected a finite XYZ target")
    if initial.shape != (12,) or not np.isfinite(initial).all():
        raise ReachError("Expected twelve finite initial joint positions")
    if np.any(initial < env.lower) or np.any(initial > env.upper):
        raise ReachError("Initial joint positions exceed limits")
    channels = slice(0, 4) if arm == "left" else slice(6, 10)
    data = mujoco.MjData(env.model)
    data.qpos[:] = env.data.qpos
    data.qpos[env.qadr] = initial
    site = env.model.site(f"{arm}/utensil_pinch").id
    jp = np.zeros((3, env.model.nv))
    jr = np.zeros_like(jp)
    for _ in range(250):
        mujoco.mj_forward(env.model, data)
        axis = data.site_xmat[site].reshape(3, 3)[:, 0]
        position_error = target - data.site_xpos[site]
        axis_error = np.array([0, 0, -1]) - axis
        if np.linalg.norm(position_error) < 0.0001 and np.linalg.norm(axis_error) < 0.001:
            return data.qpos[env.qadr].copy()
        mujoco.mj_jacSite(env.model, data, jp, jr, site)
        jac = np.vstack([jp, 0.1 * np.cross(jr.T, axis).T])[:, env.vadr[channels]]
        delta = jac.T @ np.linalg.solve(
            jac @ jac.T + 1e-5 * np.eye(6), np.r_[position_error, 0.1 * axis_error]
        )
        data.qpos[env.qadr[channels]] = np.clip(
            data.qpos[env.qadr[channels]] + np.clip(delta, -0.1, 0.1),
            env.lower[channels],
            env.upper[channels],
        )
    raise ReachError("Fixed-roll target unreachable within IK tolerances and joint limits")


def run_utensils(config: UtensilConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source = provenance(project_root)
    started = time.perf_counter()
    env = None
    observations, frames = [], []
    metrics = score_utensils([])
    outcome, error = "failed", None
    try:
        env = UtensilEnvironment(config)
        (directory / "scene.xml").write_text(env.xml)
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2))
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "config.json").write_text(config.model_dump_json(indent=2))
        if config.missing_object:
            raise RuntimeError(f"Required {config.missing_object} is missing; no motion attempted")

        def record(action):
            obs = env.observe(render=config.render and env.sequence % 4 == 0)
            row = {
                k: v.tolist() if isinstance(v, np.ndarray) else v
                for k, v in obs.items()
                if k != "rgb"
            }
            row.update(
                stage=env.stage, action_target_rad=action.tolist() if action is not None else None
            )
            observations.append(row)
            if obs["rgb"]:
                frame = Image.new("RGB", (1440, 300), "#14202b")
                for col, camera in enumerate(CAMERAS):
                    frame.paste(Image.fromarray(obs["rgb"][camera]), (480 * col, 30))
                ImageDraw.Draw(frame).text(
                    (12, 8),
                    f"ERGONOMIC UTENSIL TEACHER | {env.stage} | {env.data.time:.2f}s"
                    " | 1 kHz physics",
                    fill="white",
                )
                frames.append(frame)

        def execute(stage, goal, steps):
            env.stage = stage
            start = env.data.ctrl[env.actuator_ids].copy()
            if env.active_utensil and stage in {
                env.active_utensil + suffix for suffix in ("_clearance", "_transport", "_lower")
            }:
                check_carried_path(
                    env,
                    start,
                    goal,
                    env.allowed,
                    body_name=env.active_utensil,
                    site_name="left/utensil_pinch",
                )
            else:
                check_joint_path(env, start, goal, env.allowed)
            for i in range(steps):
                a = (i + 1) / steps
                a = a * a * (3 - 2 * a)
                action = start + a * (goal - start)
                record(action)
                env.step(action, episode_id=env.episode_id, sequence=env.sequence)

        q = env.home.copy()
        tool_yaw = None

        def move(stage, target, steps=60):
            nonlocal q
            target = np.asarray(target, float)
            q = (solve_utensil_tip if env.active_utensil else solve_downward)(
                env, target, q, arm="left"
            )
            if env.active_utensil and tool_yaw is not None:
                for _ in range(5):
                    scratch = mujoco.MjData(env.model)
                    scratch.qpos[:] = env.data.qpos
                    scratch.qpos[env.qadr] = q
                    mujoco.mj_forward(env.model, scratch)
                    axis = scratch.body("left/gripper").xmat.reshape(3, 3)[:, 0]
                    yaw = np.arctan2(axis[1], axis[0])
                    delta = (tool_yaw - yaw + np.pi) % (2 * np.pi) - np.pi
                    if abs(delta) < 0.001:
                        break
                    q[4] = np.clip(q[4] + delta, env.lower[4], env.upper[4])
                    q = solve_utensil_tip(env, target, q, arm="left")
                else:
                    raise ReachError("World-yaw IK tolerance not reached")
            execute(stage, q, steps)

        execute("settle", q, 20)
        move("approach", [-0.157, -0.18, 0.47])
        move("descend", [-0.157, -0.18, 0.413])
        q[5] = -0.1
        execute("close", q, 40)
        if not all(min(r["jaw_normal_force_n"]) > 0.01 for r in env.contact_trace[-500:]):
            raise RuntimeError("Drawer handle grasp not established")
        move("pull", [-0.269, -0.18, 0.413], 120)
        execute("open_hold", q, 40)
        q[5] = 0.8
        execute("release", q, 40)
        move("retreat", [-0.269, -0.18, 0.47])
        execute("released_hold", q, 40)
        if not score_utensils(env.contact_trace)["drawer_opened"]:
            raise RuntimeError("Drawer did not open and remain released for two seconds")
        for obj, roll, clearance, destination in [
            ("spoon", 1.1, 0.458, [-0.12, 0.02]),
            ("fork", 1.0, 0.453, [-0.06, 0.03]),
        ]:
            env.active_utensil = obj
            tool_yaw = None
            q[4] = roll
            body = env.data.body(obj)
            target = (
                body.xpos.copy()
                + body.xmat.reshape(3, 3) @ np.array([0, -0.025, 0])
                + [0, 0, 0.0045]
            )
            move(obj + "_approach", [*target[:2], 0.45])
            q[5] = 0
            execute(obj + "_preshape", q, 40)
            move(obj + "_descend", target)
            q[5] = 0 if config.skip_close == obj else -0.07
            execute(obj + "_close", q, 40)
            if not all(
                _airborne(r["objects"][obj]) or min(r["objects"][obj]["jaw_normal_force_n"]) > 0.01
                for r in env.contact_trace[-500:]
            ):
                raise RuntimeError(f"{obj} grasp not established by both jaws")
            move(obj + "_lift", [*target[:2], 0.45])
            execute(obj + "_hold", q, 40)
            if not all(_airborne(r["objects"][obj]) for r in env.contact_trace[-2000:]):
                raise RuntimeError(f"{obj} did not pass the two-second airborne hold")
            axis = env.data.body("left/gripper").xmat.reshape(3, 3)[:, 0]
            tool_yaw = np.arctan2(axis[1], axis[0])
            move(obj + "_clearance", [*target[:2], clearance])
            previous = target[:2].copy()
            waypoints = [[-0.15, -0.10], [-0.10, -0.04], destination]
            for segment, endxy in enumerate(waypoints):
                for i in range(1, 4):
                    alpha = i / 3
                    if obj == "spoon":
                        q[4] = 1.1 - 0.4 * (segment + alpha) / len(waypoints)
                    xy = (1 - alpha) * previous + alpha * np.array(endxy)
                    move(obj + "_transport", [*xy, clearance], 16)
                previous = np.array(endxy)
            move(obj + "_lower", [*destination, 0.391])
            q[5] = 0.8
            execute(obj + "_release", q, 40)
            move(obj + "_retreat", [*destination, 0.45])
            execute(obj + "_settled", q, 40)
            if not all(_placed(r["objects"][obj], obj) for r in env.contact_trace[-2000:]):
                raise RuntimeError(f"{obj} failed released tabletop placement")
            env.placed.add(obj)
        record(None)
        if not score_utensils(env.contact_trace)["utensils_success"]:
            raise RuntimeError("Combined drawer and both-utensil acceptance check failed")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        (directory / "error.txt").write_text(error + "\n")
    finally:
        if env is not None:
            metrics = score_utensils(env.contact_trace)
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
            scene_variant=VARIANT,
        )
        if outcome != "completed":
            metrics["utensils_success"] = False
    return store.seal(
        directory,
        kind="contact_utensils_teacher",
        outcome=outcome,
        config=config.model_dump(),
        source=source,
        claims=["contact_drawer_spoon_fork_placement"] if outcome == "completed" else [],
        metrics=metrics,
    )
