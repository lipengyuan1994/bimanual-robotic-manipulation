"""Contact-driven drawer opening with stored utensil proxies; no retrieval claim."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict

from bimanual.dual_arm import CAMERAS, MODEL_DIR, DualArm, verify_assets
from bimanual.evidence import EvidenceStore, Manifest, provenance
from bimanual.grasp import GraspConfig, grasp_xml
from bimanual.teacher import check_joint_path, solve_downward


class DrawerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    render: bool = True
    missing_handle: bool = False
    skip_close: bool = False


def drawer_xml(config: DrawerConfig) -> str:
    root = ET.fromstring(grasp_xml(GraspConfig(missing_object=True)))
    root.set("model", "dual_so101_contact_drawer")
    world = root.find("worldbody")
    drawer = ET.SubElement(world, "body", name="drawer", pos="-.02 -.18 .39")
    ET.SubElement(
        drawer,
        "joint",
        name="drawer/slide",
        type="slide",
        axis="-1 0 0",
        range="0 .11",
        damping="1",
        frictionloss=".4",
    )
    # All five drawer panels belong to the same unactuated slide body.
    panels = [
        ("floor", "0 0 0", ".09 .09 .004"),
        ("front", "-.086 0 .017", ".004 .09 .017"),
        ("back", ".086 0 .017", ".004 .09 .017"),
        ("left", "0 -.086 .017", ".082 .004 .017"),
        ("right", "0 .086 .017", ".082 .004 .017"),
    ]
    for name, pos, size in panels:
        ET.SubElement(
            drawer,
            "geom",
            name=f"drawer/{name}",
            type="box",
            pos=pos,
            size=size,
            mass=".04",
            rgba=".4 .5 .6 1",
            friction=".5 .005 .0001",
        )
    if not config.missing_handle:
        ET.SubElement(
            drawer,
            "geom",
            name="drawer/stem",
            type="box",
            pos="-.11 0 .005",
            size=".02 .006 .006",
            mass=".005",
            rgba=".7 .7 .7 1",
        )
        ET.SubElement(
            drawer,
            "geom",
            name="drawer/handle",
            type="box",
            pos="-.137 0 .01",
            size=".01 .01 .016",
            mass=".015",
            rgba=".1 .7 .8 1",
            friction="1 .005 .0001",
        )
    for name, pos, size in [
        ("left", "-.02 -.277 .404", ".102 .004 .025"),
        ("right", "-.02 -.083 .404", ".102 .004 .025"),
        ("back", ".078 -.18 .404", ".004 .093 .025"),
        ("floor", "-.02 -.18 .38", ".102 .093 .003"),
        ("roof", "-.02 -.18 .433", ".102 .093 .004"),
    ]:
        ET.SubElement(
            world, "geom", name=f"cabinet_{name}", type="box", pos=pos, size=size, rgba=".3 .3 .3 1"
        )
    # Independent free bodies, stored across drawer width. Shapes approximate
    # utensils for clearance only; no claim of trained or validated utensil grasps.
    for name, x in (("spoon", -0.08), ("fork", -0.05)):
        body = ET.SubElement(world, "body", name=name, pos=f"{x} -.18 .397")
        ET.SubElement(body, "freejoint", name=f"{name}/free")
        ET.SubElement(
            body,
            "geom",
            name=f"{name}/shaft",
            type="capsule",
            fromto="0 -.052 0 0 .035 0",
            size=".003",
            mass=".008",
            rgba=".8 .8 .85 1",
        )
        if name == "spoon":
            ET.SubElement(
                body,
                "geom",
                name="spoon/bowl",
                type="ellipsoid",
                pos="0 .045 0",
                size=".011 .014 .003",
                mass=".003",
                rgba=".8 .8 .85 1",
            )
        else:
            ET.SubElement(
                body,
                "geom",
                name="fork/bridge",
                type="box",
                pos="0 .034 0",
                size=".01 .003 .002",
                mass=".002",
                rgba=".8 .8 .85 1",
            )
            for number, xlocal in enumerate((-0.008, -0.003, 0.003, 0.008)):
                ET.SubElement(
                    body,
                    "geom",
                    name=f"fork/tine{number}",
                    type="box",
                    pos=f"{xlocal} .046 0",
                    size=".001 .012 .002",
                    mass=".0004",
                    rgba=".8 .8 .85 1",
                )
    return ET.tostring(root, encoding="unicode")


class DrawerEnvironment(DualArm):
    def __init__(self, config: DrawerConfig):
        self.stage = "settle"
        self.contact_trace: list[dict] = []
        super().__init__(xml=drawer_xml(config))
        self.fingers = tuple(
            {
                self.model.geom(i).name
                for i in range(self.model.ngeom)
                if self.model.body(int(self.model.geom_bodyid[i])).name == f"left/{body}"
            }
            for body in ("gripper", "moving_jaw_so101_v1")
        )

    def step(self, targets, *, episode_id, sequence):
        values = np.asarray(targets, float)
        if values.shape == (12,) and not np.allclose(
            values[6:], self.data.ctrl[self.actuator_ids][6:], rtol=0, atol=1e-12
        ):
            raise ValueError("Drawer teacher does not own the right arm")
        super().step(values, episode_id=episode_id, sequence=sequence)

    def allowed(self, pair):
        names = set(pair)
        if names & {"drawer/handle", "drawer/stem"} and names & (self.fingers[0] | self.fingers[1]):
            return True
        # Real drawer-interior contacts move the free utensils. Robot/utensil,
        # utensil/cabinet and utensil/workbench contacts are not allowed here.
        return any(n.startswith(("spoon/", "fork/")) for n in pair) and all(
            n.startswith(("spoon/", "fork/", "drawer/")) for n in pair
        )

    def after_physics_step(self):
        mujoco.mj_forward(self.model, self.data)
        opening = float(self.data.joint("drawer/slide").qpos[0])
        row = dict(
            stage=self.stage,
            simulation_seconds=float(self.data.time),
            opening_m=opening,
            drawer_speed_m_s=float(self.data.joint("drawer/slide").qvel[0]),
            utensil_positions_m={
                name: self.data.body(name).xpos.tolist() for name in ("spoon", "fork")
            },
            jaw_normal_force_n=[0.0, 0.0],
            forbidden_pairs=[],
            contact_pairs=[],
            max_penetration_m=0.0,
            joint_limit_overtravel_m=max(0.0, -opening, opening - 0.11),
        )
        for i, contact in enumerate(self.data.contact):
            pair = tuple(self.model.geom(int(g)).name for g in contact.geom)
            row["contact_pairs"].append(pair)
            row["max_penetration_m"] = max(row["max_penetration_m"], -float(contact.dist))
            if not self.allowed(pair):
                row["forbidden_pairs"].append(pair)
            if set(pair) & {"drawer/handle", "drawer/stem"} and contact.efc_address >= 0:
                force = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, i, force)
                for jaw, names in enumerate(self.fingers):
                    if set(pair) & names:
                        row["jaw_normal_force_n"][jaw] += max(0.0, float(force[0]))
        self.contact_trace.append(row)
        if (
            row["forbidden_pairs"]
            or max(row["max_penetration_m"], row["joint_limit_overtravel_m"]) > 0.0025
        ):
            self.stop()
            raise RuntimeError(
                f"Forbidden contact during {self.stage}: {row['forbidden_pairs'][0]}"
                if row["forbidden_pairs"]
                else "Contact penetration or joint overtravel exceeds 2.5 mm"
            )


def score_drawer(trace: list[dict]) -> dict:
    initial_opening = trace[0]["opening_m"] if trace else 0.0
    initially_closed = (
        bool(trace) and trace[0]["stage"] == "settle" and abs(initial_opening) <= 0.001
    )
    pulled = [r for r in trace if r["stage"] == "pull"]
    held = [r for r in trace if r["stage"] == "open_hold"]
    released = [r for r in trace if r["stage"] == "released_hold"]

    def stored(row):
        # Interior XY bounds are fixed relative to the passive slide position.
        centre = np.array([-0.02 - row["opening_m"], -0.18, 0.39])
        return all(
            abs((np.array(position) - centre)[0]) < 0.08
            and abs((np.array(position) - centre)[1]) < 0.08
            and 0.392 < position[2] < 0.424
            for position in row["utensil_positions_m"].values()
        ) and set(row["utensil_positions_m"]) == {"spoon", "fork"}

    def open_row(row):
        return (
            row["opening_m"] >= 0.08
            and row["opening_m"] - initial_opening >= 0.08
            and abs(row["drawer_speed_m_s"]) < 0.01
            and stored(row)
        )

    hold_count = sum(open_row(r) and min(r["jaw_normal_force_n"]) > 0.01 for r in held)
    release_count = sum(open_row(r) and r["jaw_normal_force_n"] == [0, 0] for r in released)

    def consecutive(rows, count=400):
        return len(rows) == count and np.allclose(
            np.diff([r["simulation_seconds"] for r in rows]), 0.005, rtol=0, atol=1e-9
        )

    pull_count = sum(min(r["jaw_normal_force_n"]) > 0.01 and stored(r) for r in pulled)
    pull_ok = consecutive(pulled, 1200) and pull_count == 1200
    retained = bool(trace) and all(stored(r) for r in trace)
    hold_ok = consecutive(held) and hold_count == 400
    release_ok = consecutive(released) and release_count == 400
    contiguous = len(trace) > 1 and np.allclose(
        np.diff([r["simulation_seconds"] for r in trace]), 0.005, rtol=0, atol=1e-9
    )
    ordered = bool(
        pulled
        and held
        and released
        and pulled[-1]["simulation_seconds"] < held[0]["simulation_seconds"]
        and held[-1]["simulation_seconds"] < released[0]["simulation_seconds"]
        and trace[-1]["stage"] == "released_hold"
        and trace[-1]["simulation_seconds"] == released[-1]["simulation_seconds"]
    )
    forbidden = sum(bool(r["forbidden_pairs"]) for r in trace)
    penetration = max((r["max_penetration_m"] for r in trace), default=0)
    overtravel = max((r["joint_limit_overtravel_m"] for r in trace), default=0)
    return dict(
        drawer_success=bool(
            initially_closed
            and pull_ok
            and retained
            and hold_ok
            and release_ok
            and contiguous
            and ordered
            and not forbidden
            and max(penetration, overtravel) <= 0.0025
        ),
        initially_closed=bool(initially_closed),
        phases_ordered=bool(ordered),
        net_opening_m=trace[-1]["opening_m"] - initial_opening if trace else None,
        pull_passed=bool(pull_ok),
        pull_grasp_samples=int(pull_count),
        utensils_retained=bool(retained),
        max_jaw_normal_force_n=max((max(r["jaw_normal_force_n"]) for r in trace), default=0),
        open_hold_passed=bool(hold_ok),
        released_open_passed=bool(release_ok),
        open_grasp_samples=int(hold_count),
        released_open_samples=int(release_count),
        final_opening_m=trace[-1]["opening_m"] if trace else None,
        forbidden_contact_samples=forbidden,
        max_penetration_m=penetration,
        max_joint_limit_overtravel_m=overtravel,
        manipulation_success=None,
    )


def run_drawer(config: DrawerConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source = provenance(project_root)
    started = time.perf_counter()
    env = None
    observations, frames = [], []
    metrics = score_drawer([])
    outcome, error = "failed", None
    try:
        env = DrawerEnvironment(config)
        (directory / "scene.xml").write_text(env.xml)
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2))
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "config.json").write_text(config.model_dump_json(indent=2))
        if config.missing_handle:
            raise RuntimeError("Drawer handle is missing; no opening attempted")

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
                    f"CONTACT DRAWER TEACHER | {env.stage} | {env.data.time:.2f}s"
                    " | overhead / left wrist / right wrist",
                    fill="white",
                )
                frames.append(frame)

        def execute(stage, goal, steps):
            env.stage = stage
            start = env.data.ctrl[env.actuator_ids].copy()
            check_joint_path(env, start, goal, env.allowed)
            for i in range(steps):
                a = (i + 1) / steps
                a = a * a * (3 - 2 * a)
                action = start + a * (goal - start)
                record(action)
                env.step(action, episode_id=env.episode_id, sequence=env.sequence)

        q = env.home.copy()

        def move(stage, target, steps=60):
            nonlocal q
            q = solve_downward(env, np.array(target), q, arm="left")
            execute(stage, q, steps)

        execute("settle", q, 20)
        move("approach", [-0.157, -0.18, 0.47])
        move("descend", [-0.157, -0.18, 0.413])
        q[5] = 0.8 if config.skip_close else -0.1
        execute("close", q, 40)
        if not all(min(r["jaw_normal_force_n"]) > 0.01 for r in env.contact_trace[-100:]):
            raise RuntimeError(
                "Handle was not gripped by both jaws for the final half-second of close"
            )
        move("pull", [-0.247, -0.18, 0.413], 120)
        execute("open_hold", q, 40)
        if not score_drawer(env.contact_trace)["open_hold_passed"]:
            raise RuntimeError("Drawer did not remain at least eight centimetres open while held")
        q[5] = 0.8
        execute("release", q, 40)
        move("retreat", [-0.247, -0.18, 0.47])
        execute("released_hold", q, 40)
        record(None)
        if not score_drawer(env.contact_trace)["drawer_success"]:
            raise RuntimeError("Released drawer failed the two-second open acceptance check")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        (directory / "error.txt").write_text(error + "\n")
    finally:
        if env is not None:
            metrics = score_drawer(env.contact_trace)
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
        )
        if outcome != "completed":
            metrics["drawer_success"] = False
    return store.seal(
        directory,
        kind="contact_drawer_teacher",
        outcome=outcome,
        config=config.model_dump(),
        source=source,
        claims=["contact_drawer_open_release"] if outcome == "completed" else [],
        metrics=metrics,
    )
