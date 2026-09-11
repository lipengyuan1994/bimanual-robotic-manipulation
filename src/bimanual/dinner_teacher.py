"""Fixed-scene teacher baseline: joint targets, never replayed object states."""

from __future__ import annotations

import gzip
import json
import shutil
import time
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict

from bimanual.dual_arm import CAMERAS, JOINT_ORDER, MODEL_DIR, DualArm, verify_assets
from bimanual.evidence import EvidenceStore, Manifest, digest_file, provenance
from bimanual.teacher import check_carried_path, check_joint_path

ASSETS = Path(str(files("bimanual") / "models/dinner_teacher_v1"))
OBJECTS = ("spoon", "fork", "plate", "cup", "practice_object")


class DinnerTeacherConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    render: bool = True


def load_plan(directory: Path = ASSETS) -> tuple[dict, dict, dict]:
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = {"scene.xml", "layout.json", "plan.json.gz"}
    if manifest.get("schema_version") != 1 or set(manifest.get("files", {})) != expected:
        raise ValueError("Invalid dinner asset manifest")
    for name, digest in manifest["files"].items():
        if digest_file(directory / name) != digest:
            raise ValueError(f"Dinner asset digest mismatch: {name}")
    plan = json.loads(gzip.decompress((directory / "plan.json.gz").read_bytes()))
    if (plan.get("schema_version"), plan.get("physics_hz"), plan.get("control_hz")) != (
        1,
        1000,
        20,
    ):
        raise ValueError("Unsupported dinner timing/schema")
    if plan.get("joint_order") != list(JOINT_ORDER) or plan.get("camera_order") != list(CAMERAS):
        raise ValueError("Dinner observation/action ordering mismatch")
    if not plan.get("steps") or len(plan["steps"]) != manifest.get("action_count"):
        raise ValueError("Incomplete dinner target plan")
    for step in plan["steps"]:
        phase_permissions(step["phase"])
        q = np.asarray(step["q"], dtype=float)
        if q.shape != (12,) or not np.isfinite(q).all():
            raise ValueError("Invalid dinner joint target")
    layout = json.loads((directory / "layout.json").read_text())
    if layout["scene_sha256"] != manifest["files"]["scene.xml"]:
        raise ValueError("Dinner layout/scene mismatch")
    return manifest, plan, layout


def phase_permissions(phase: str) -> tuple[dict[str, set[str]], str | None, str]:
    """Contact permissions and carried-path checks; the worker reserves both arms."""
    skill, stage = phase.split("/")
    if skill not in {"handoff", "cup", "plate", "utensils"} or not stage:
        raise ValueError("Unknown dinner phase")
    if stage == "transition_home":
        return {}, None, "left"
    carried = None
    arm = "right" if skill == "cup" else "left"
    if skill == "utensils":
        obj = next((n for n in ("spoon", "fork") if stage.startswith(n + "_")), None)
        active = {"left": {obj or "drawer"}}
        if obj and stage.removeprefix(obj + "_") in {
            "lift",
            "hold",
            "clearance",
            "transport",
            "lower",
        }:
            carried = obj
    elif skill in {"cup", "plate"}:
        active = {arm: {skill}}
        if stage in {"lift", "hold", "transport_clearance", "transport", "lower"}:
            carried = skill
    else:
        active = {"left": {"practice_object"}, "right": {"practice_object"}}
        if stage in {"left_lift", "left_hold"}:
            carried = "practice_object"
        if stage.startswith("bar_") or stage in {"donor_park", "receiver_return"}:
            active = {"right": {"practice_object"}}
            arm = "right"
            if stage in {"bar_align", "bar_transport", "bar_lower"}:
                carried = "practice_object"
    return active, carried, arm


class DinnerEnvironment(DualArm):
    def __init__(self, xml: str, trace, cancelled: Callable[[], bool]):
        super().__init__(xml=xml, physics_hz=1000)
        self.trace = trace
        self.cancelled = cancelled
        self.phase = "handoff/settle"
        self.active_contacts: dict[str, set[str]] = {}
        self.fingers = {
            arm: tuple(
                {
                    self.model.geom(i).name
                    for i in range(self.model.ngeom)
                    if self.model.body(int(self.model.geom_bodyid[i])).name == arm + "/" + body
                }
                for body in ("gripper", "moving_jaw_so101_v1")
            )
            for arm in ("left", "right")
        }
        self.geom_objects = {
            self.model.geom(i).name: name
            for name in OBJECTS
            for i in range(self.model.ngeom)
            if self.model.geom_bodyid[i] == self.model.body(name).id
        }

    def allowed(self, pair) -> bool:
        names = set(pair)
        objects = {self.geom_objects[n] for n in pair if n in self.geom_objects}
        if len(objects) == 1:
            obj = next(iter(objects))
            others = [n for n in pair if n not in self.geom_objects]
            if len(others) != 1:
                return False
            other = others[0]
            if other == "workbench" or (obj in {"spoon", "fork"} and other.startswith("drawer/")):
                return True
            if obj == "plate" and other == "plate_rack":
                return True
            if any(
                obj in self.active_contacts.get(a, set()) and other in (groups[0] | groups[1])
                for a, groups in self.fingers.items()
            ):
                return True
        if len(objects) == 2 and objects <= {"spoon", "fork"}:
            return True
        return bool(
            names & {"drawer/handle", "drawer/stem"}
            and "drawer" in self.active_contacts.get("left", set())
            and names & (self.fingers["left"][0] | self.fingers["left"][1])
        )

    def after_physics_step(self) -> None:
        # Retain the source teacher's forward/contact audit at each 1 ms step.
        mujoco.mj_forward(self.model, self.data)
        opening = float(self.data.joint("drawer/slide").qpos[0])
        row = dict(
            t=float(self.data.time),
            phase=self.phase,
            opening=opening,
            overtravel=max(0, -opening, opening - 0.11),
            contacts=[],
            bad=[],
            overlap=0.0,
            drawer_forces=[0.0, 0.0],
            objects={},
            joint_position=self.data.qpos[self.qadr].tolist(),
        )
        for name in OBJECTS:
            body = self.data.body(name)
            joint = int(self.model.body(name).jntadr[0])
            velocity = int(self.model.jnt_dofadr[joint])
            row["objects"][name] = dict(
                pos=body.xpos.tolist(),
                quat=body.xquat.tolist(),
                upright=float(body.xmat.reshape(3, 3)[2, 2]),
                vel=self.data.qvel[velocity : velocity + 6].tolist(),
                forces={"left": [0.0, 0.0], "right": [0.0, 0.0]},
                support=[],
            )
        for index, contact in enumerate(self.data.contact):
            pair = tuple(self.model.geom(int(g)).name for g in contact.geom)
            row["contacts"].append(pair)
            row["overlap"] = max(row["overlap"], -float(contact.dist))
            if not self.allowed(pair):
                row["bad"].append(pair)
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, index, force)
            normal = max(0.0, float(force[0]))
            if set(pair) & {"drawer/handle", "drawer/stem"}:
                for k, geoms in enumerate(self.fingers["left"]):
                    if set(pair) & geoms:
                        row["drawer_forces"][k] += normal
            for name in {self.geom_objects[g] for g in pair if g in self.geom_objects}:
                obj = row["objects"][name]
                for arm, groups in self.fingers.items():
                    for k, geoms in enumerate(groups):
                        if set(pair) & geoms:
                            obj["forces"][arm][k] += normal
                obj["support"] += [
                    g
                    for g in pair
                    if g in {"workbench", "plate_rack"}
                    or g.startswith(("drawer/", "cabinet_"))
                    or (g in self.geom_objects and self.geom_objects[g] != name)
                ]
        self.trace.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        if row["bad"] or max(row["overlap"], row["overtravel"]) > 0.0025:
            self.stop()
            raise ValueError(f"Dinner contact guard at {row['t']}: {row['bad']}")
        if self.cancelled():
            self.stop()
            raise InterruptedError("Dinner teacher cancelled")


def run_dinner_teacher(
    config: DinnerTeacherConfig,
    store: EvidenceStore,
    project_root: Path,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> Manifest:
    from bimanual.dinner_scoring import score_dinner

    directory = store.new_run()
    source = provenance(project_root)
    started = time.perf_counter()
    env = None
    frames = []
    error = None
    interrupted = False
    layout = {}

    def capture():
        obs = env.observe(render=True)
        frame = Image.new("RGB", (720, 165), "#14202b")
        for col, camera in enumerate(CAMERAS):
            frame.paste(Image.fromarray(obs["rgb"][camera]).resize((240, 135)), (240 * col, 30))
        ImageDraw.Draw(frame).text(
            (5, 5), f"TEACHER / {env.phase} / {env.data.time:.2f}s / replay 5x", fill="white"
        )
        frames.append(frame)

    try:
        if cancelled():
            raise InterruptedError("Dinner teacher cancelled before initialization")
        _, plan, layout = load_plan()
        verify_assets()
        shutil.copytree(ASSETS, directory / "teacher-assets")
        runtime = directory / "runtime-source"
        runtime.mkdir()
        for module in Path(__file__).parent.glob("*.py"):
            shutil.copyfile(module, runtime / module.name)
        shutil.copytree(MODEL_DIR / "assets", directory / "assets")
        shutil.copyfile(ASSETS / "scene.xml", directory / "scene.xml")
        for name in ("LICENSE", "UPSTREAM.json"):
            shutil.copyfile(MODEL_DIR / name, directory / name)
        with (
            gzip.open(directory / "physics.jsonl.gz", "wt") as trace,
            (directory / "actions.jsonl").open("w") as actions,
        ):
            env = DinnerEnvironment((ASSETS / "scene.xml").read_text(), trace, cancelled)
            (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2) + "\n")
            for step in plan["steps"]:
                q = np.asarray(step["q"])
                if np.any(q < env.lower) or np.any(q > env.upper):
                    raise ValueError("Dinner plan exceeds model joint/actuator limits")
            if config.render:
                capture()
            for step in plan["steps"]:
                if cancelled():
                    raise InterruptedError("Dinner teacher cancelled")
                env.phase = step["phase"]
                env.active_contacts, carried, arm = phase_permissions(env.phase)
                q = np.asarray(step["q"])
                previous = env.data.ctrl[env.actuator_ids].copy()
                if carried:
                    check_carried_path(
                        env, previous, q, env.allowed, body_name=carried, site_name=arm + "/pinch"
                    )
                else:
                    check_joint_path(env, previous, q, env.allowed)
                action = dict(
                    t=float(env.data.time),
                    phase=env.phase,
                    q=q.tolist(),
                    episode_id=env.episode_id,
                    applied=False,
                )
                try:
                    env.step(q, episode_id=env.episode_id, sequence=env.sequence)
                    action["applied"] = True
                finally:
                    actions.write(json.dumps(action, allow_nan=False) + "\n")
                if config.render and env.sequence % 10 == 0:
                    capture()
            if config.render:
                capture()
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        interrupted = isinstance(exc, (InterruptedError, KeyboardInterrupt))
    finally:
        if env is not None:
            env.stop()
            env.close()
    wall_seconds = time.perf_counter() - started
    if (directory / "physics.jsonl.gz").exists():
        with (
            gzip.open(directory / "physics.jsonl.gz", "rt") as trace,
            (directory / "actions.jsonl").open() as actions,
        ):
            score = score_dinner(
                (json.loads(line) for line in trace), (json.loads(line) for line in actions), layout
            )
    else:
        score = {"full_workflow_success": False, "failed_gates": ["initialization"]}
    if frames:
        frames[0].save(
            directory / "replay.gif", save_all=True, append_images=frames[1:], duration=100, loop=0
        )
        frames[-1].save(directory / "preview.png")
    (directory / "score.json").write_text(json.dumps(score, indent=2, allow_nan=False) + "\n")
    metrics = dict(
        score=score,
        error=error,
        wall_seconds=wall_seconds,
        teacher_assistance=True,
        learned_execution=False,
        production_ready=False,
        rendered=config.render and bool(frames),
    )
    outcome = (
        "interrupted"
        if interrupted
        else "completed"
        if error is None and score.get("full_workflow_success")
        else "failed"
    )
    return store.seal(
        directory,
        kind="dinner_teacher",
        outcome=outcome,
        config=config.model_dump(),
        metrics=metrics,
        source=source,
        claims=["fixed_scene_contact_teacher_workflow"] if outcome == "completed" else [],
    )
