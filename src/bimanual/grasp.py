"""Contact-only pick/hold/release experiment with independently scored truth logs.

This teacher uses simulator truth. It is not ACT, VLA reasoning, or dinner-task success.
"""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

import mujoco
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bimanual.contracts import Artifact, EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dual_arm import CAMERAS, MODEL_DIR, DualArm, scene_xml, verify_assets
from bimanual.evidence import EvidenceStore, Manifest, digest_file, provenance
from bimanual.teacher import check_joint_path, solve_downward


class GraspConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    render: bool = True
    record_demo: bool = False
    seed: int = Field(default=0, ge=0, strict=True)
    split: Literal["train", "validation", "test"] = "train"
    arm: Literal["left", "right"] = "left"
    object_x: float | None = Field(default=None, ge=-0.5, le=0.5)
    object_y: float | None = Field(default=None, ge=-0.4, le=0.4)
    destination_xy: tuple[float, float] | None = None
    mass_kg: float = Field(default=0.025, ge=0.01, le=0.05)
    missing_object: bool = False
    skip_close: bool = False

    @model_validator(mode="after")
    def locations(self):
        if self.record_demo and not self.render:
            raise ValueError("Demonstration recording requires all three rendered cameras")
        sign = 1 if self.arm == "left" else -1
        if self.object_x is None:
            self.object_x = sign * -0.15
        if self.object_y is None:
            self.object_y = sign * -0.08
        if self.destination_xy is not None:
            delta = np.asarray(self.destination_xy) - [self.object_x, self.object_y]
            if np.linalg.norm(delta) < 0.06:
                raise ValueError("Placement destination must be at least 6 cm from pickup")
            if abs(self.destination_xy[0]) > 0.5 or abs(self.destination_xy[1]) > 0.4:
                raise ValueError("Placement destination is outside the workbench")
        return self


def grasp_xml(config: GraspConfig) -> str:
    root = ET.fromstring(scene_xml())
    root.set("model", "dual_so101_contact_grasp")
    # An explicit task tool point, separate from the untouched upstream site.
    for arm in ("left", "right"):
        gripper = root.find(f".//body[@name='{arm}/gripper']")
        ET.SubElement(
            gripper,
            "site",
            name=f"{arm}/pinch",
            pos=".008 -.000218 -.09",
            quat="1 0 1 0",
            size=".002",
            rgba="0 1 0 1",
            group="3",
        )
    if not config.missing_object:
        body = ET.SubElement(
            root.find("worldbody"),
            "body",
            name="practice_object",
            pos=f"{config.object_x} {config.object_y} .391",
        )
        ET.SubElement(body, "freejoint", name="practice_object/free")
        ET.SubElement(
            body,
            "geom",
            name="practice_object",
            type="box",
            size=".01 .01 .016",
            mass=str(config.mass_kg),
            rgba=".1 .7 .8 1",
            friction="1 .005 .0001",
        )
    return ET.tostring(root, encoding="unicode")


class GraspEnvironment(DualArm):
    def __init__(self, config: GraspConfig):
        self.arm = config.arm
        self.stage = "settle"
        self.contact_trace: list[dict] = []
        super().__init__(xml=grasp_xml(config))
        # Finger geoms are identified by their owning bodies, including mesh geoms.
        self.fixed = {
            self.model.geom(i).name
            for i in range(self.model.ngeom)
            if self.model.body(int(self.model.geom_bodyid[i])).name == f"{self.arm}/gripper"
        }
        self.moving = {
            self.model.geom(i).name
            for i in range(self.model.ngeom)
            if self.model.body(int(self.model.geom_bodyid[i])).name
            == f"{self.arm}/moving_jaw_so101_v1"
        }

    def step(self, targets, *, episode_id: str, sequence: int) -> None:
        values = np.asarray(targets, dtype=float)
        inactive = slice(6, 12) if self.arm == "left" else slice(0, 6)
        if values.shape == (12,) and not np.array_equal(values[inactive], self.home[inactive]):
            raise ValueError("This single-arm skill does not own the other arm")
        super().step(values, episode_id=episode_id, sequence=sequence)

    def allowed(self, pair: tuple[str, str]) -> bool:
        names = set(pair)
        if names == {"practice_object", "workbench"}:
            return True
        return (
            "practice_object" in names
            and bool(names & (self.fixed | self.moving))
            and self.stage
            in {"descend", "close", "lift", "hold", "transport", "lower", "release", "retreat"}
        )

    def after_physics_step(self) -> None:
        # mj_step integrates qpos after computing contacts; refresh derived state
        # so contact forces, object pose and velocity share the recorded timestamp.
        mujoco.mj_forward(self.model, self.data)
        pairs, forbidden = [], []
        fixed_force = moving_force = 0.0
        table_contact = False
        max_penetration = 0.0
        for i, contact in enumerate(self.data.contact):
            pair = tuple(self.model.geom(int(g)).name for g in contact.geom)
            pairs.append(pair)
            max_penetration = max(max_penetration, -float(contact.dist))
            if not self.allowed(pair):
                forbidden.append(pair)
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, i, force)
            if "practice_object" in pair and contact.efc_address >= 0:
                if set(pair) & self.fixed:
                    fixed_force += max(0, float(force[0]))
                if set(pair) & self.moving:
                    moving_force += max(0, float(force[0]))
                table_contact |= "workbench" in pair
        exists = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "practice_object") >= 0
        position = self.data.body("practice_object").xpos.copy() if exists else None
        velocity = self.data.qvel[-6:].copy() if exists else None
        self.contact_trace.append(
            dict(
                stage=self.stage,
                simulation_seconds=float(self.data.time),
                object_position_m=position.tolist() if exists else None,
                object_velocity=velocity.tolist() if exists else None,
                fixed_jaw_normal_force_n=fixed_force,
                moving_jaw_normal_force_n=moving_force,
                table_contact=bool(table_contact),
                contact_pairs=pairs,
                forbidden_pairs=forbidden,
                max_penetration_m=max_penetration,
            )
        )
        if forbidden:
            self.stop()
            raise RuntimeError(f"Forbidden contact during {self.stage}: {forbidden[0]}")
        if max_penetration > 0.0025:
            self.stop()
            raise RuntimeError("Contact penetration exceeds the 2.5 mm experiment limit")


def score_grasp(
    trace: list[dict], initial: np.ndarray, destination: np.ndarray | None = None
) -> dict:
    """Require a complete 2s airborne hold and 2s released settling, not a height spike."""
    final_position = initial if destination is None else destination
    transport = [r for r in trace if r["stage"] == "transport"]
    hold = [r for r in trace if r["stage"] == "hold"]
    settled = [r for r in trace if r["stage"] == "settled"]

    def lifted(r):
        return (
            r["object_position_m"] is not None
            and r["object_position_m"][2] - initial[2] >= 0.04
            and not r["table_contact"]
            and r["fixed_jaw_normal_force_n"] > 0.01
            and r["moving_jaw_normal_force_n"] > 0.01
        )

    def released(r):
        return (
            r["object_position_m"] is not None
            and np.linalg.norm(np.array(r["object_position_m"][:2]) - final_position[:2])
            < (0.03 if destination is None else 0.02)
            and abs(r["object_position_m"][2] - final_position[2]) < 0.004
            and r["table_contact"]
            and r["fixed_jaw_normal_force_n"] == 0
            and r["moving_jaw_normal_force_n"] == 0
            and np.linalg.norm(r["object_velocity"][:3]) < 0.01
            and np.linalg.norm(r["object_velocity"][3:]) < 0.1
        )

    timestamps = np.array([r["simulation_seconds"] for r in trace])
    contiguous = bool(
        len(trace) > 1
        and np.isfinite(timestamps).all()
        and np.isclose(timestamps[0], 0.005, rtol=0, atol=1e-9)
        and np.allclose(np.diff(timestamps), 0.005, rtol=0, atol=1e-9)
    )

    def continuous_phase(rows, samples):
        return (
            contiguous
            and len(rows) == samples
            and np.allclose(
                np.diff([r["simulation_seconds"] for r in rows]), 0.005, rtol=0, atol=1e-9
            )
        )

    # Duration requires distinct, consecutive physics timestamps, not just row counts.
    hold_ok = continuous_phase(hold, 400) and all(lifted(r) for r in hold)
    release_ok = continuous_phase(settled, 400) and all(released(r) for r in settled)
    transport_ok = destination is None or (
        continuous_phase(transport, 600) and all(lifted(r) for r in transport)
    )
    phases = [hold, settled] if destination is None else [hold, transport, settled]
    ordered = bool(
        all(phases)
        and all(
            before[-1]["simulation_seconds"] < after[0]["simulation_seconds"]
            for before, after in zip(phases[:-1], phases[1:], strict=True)
        )
        and settled[-1] is trace[-1]
    )
    collisions = sum(bool(r["forbidden_pairs"]) for r in trace)
    penetration = max((r["max_penetration_m"] for r in trace), default=0)
    return dict(
        grasp_success=bool(
            hold_ok
            and release_ok
            and transport_ok
            and ordered
            and not collisions
            and penetration <= 0.0025
        ),
        placement_success=bool(
            hold_ok
            and release_ok
            and transport_ok
            and ordered
            and not collisions
            and penetration <= 0.0025
        )
        if destination is not None
        else None,
        transport_passed=bool(transport_ok) if destination is not None else None,
        trace_contiguous=contiguous,
        phases_ordered=ordered,
        airborne_transport_samples=int(sum(lifted(r) for r in transport)),
        final_position_error_m=(
            float(np.linalg.norm(np.array(trace[-1]["object_position_m"]) - final_position))
            if trace and trace[-1]["object_position_m"] is not None
            else None
        ),
        destination_position_m=final_position.tolist(),
        hold_passed=bool(hold_ok),
        release_passed=bool(release_ok),
        airborne_bilateral_hold_samples=int(sum(lifted(r) for r in hold)),
        settled_release_samples=int(sum(released(r) for r in settled)),
        forbidden_contact_samples=collisions,
        max_lift_m=max(
            (
                r["object_position_m"][2] - initial[2]
                for r in trace
                if r["object_position_m"] is not None
            ),
            default=0,
        ),
        max_penetration_m=penetration,
        manipulation_success=None,
    )


def run_grasp(config: GraspConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source = provenance(project_root)
    started = time.perf_counter()
    env = None
    recorder = None
    pending_observation = None
    partial_step = False
    observations, frames = [], []
    metrics = {"grasp_success": False, "manipulation_success": None}
    outcome, error = "failed", None
    destination = (
        None if config.destination_xy is None else np.array([*config.destination_xy, 0.391])
    )
    grip = 5 if config.arm == "left" else 11
    try:
        env = GraspEnvironment(config)
        (directory / "scene.xml").write_text(env.xml)
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2))
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "config.json").write_text(config.model_dump_json(indent=2))
        if config.record_demo:
            # The controller bundle is provenance, never a policy observation.
            (directory / "controller.json").write_text(
                json.dumps(
                    {
                        "kind": "scripted_teacher",
                        "source": source,
                        "teacher_uses_simulator_truth": True,
                        "seed_semantics": "metadata only; this scene has no randomization yet",
                        "sources": {
                            name: (project_root / "src" / "bimanual" / name).read_text()
                            for name in ("grasp.py", "teacher.py", "dual_arm.py")
                        },
                    },
                    indent=2,
                )
            )

            def artifact(name):
                return Artifact(path=name, sha256=digest_file(directory / name))

            recorder = DemonstrationRecorder(
                directory,
                instruction=(
                    f"Use the {config.arm} arm to pick up the practice block"
                    + (
                        f" and place it at world XY {config.destination_xy} metres."
                        if destination is not None
                        else " and return it to its start."
                    )
                ),
                instruction_revision=0,
                lineage=EpisodeLineage(
                    code_revision=source["git_revision"],
                    source_sha256=source["source_sha256"],
                    scene=artifact("scene.xml"),
                    config=artifact("config.json"),
                    controller=artifact("controller.json"),
                    controller_kind="scripted_teacher",
                    seed=config.seed,
                    split=config.split,
                ),
                joint_limits=JointLimits(
                    lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist()
                ),
            )
        if config.missing_object:
            raise RuntimeError("Practice object is missing; no grasp attempted")
        initial = env.data.body("practice_object").xpos.copy()
        target = initial.copy()
        target[2] = 0.404
        above = target.copy()
        above[2] = 0.46
        q = env.home.copy()

        def record(action):
            obs = env.observe(
                render=config.record_demo or (config.render and env.sequence % 2 == 0)
            )
            row = {
                k: v.tolist() if isinstance(v, np.ndarray) else v
                for k, v in obs.items()
                if k != "rgb"
            }
            row.update(
                stage=env.stage, action_target_rad=action.tolist() if action is not None else None
            )
            observations.append(row)
            if obs["rgb"] and env.sequence % 2 == 0:
                frame = Image.new("RGB", (1440, 300), "#14202b")
                for col, camera in enumerate(CAMERAS):
                    frame.paste(Image.fromarray(obs["rgb"][camera]), (col * 480, 30))
                ImageDraw.Draw(frame).text(
                    (12, 8),
                    f"CONTACT GRASP TEACHER | {env.stage} | {env.data.time:.2f}s"
                    " | overhead / left wrist / right wrist",
                    fill="white",
                )
                frames.append(frame)
            return obs

        def execute(stage, goal, steps):
            nonlocal pending_observation, partial_step
            env.stage = stage
            start = env.data.ctrl[env.actuator_ids].copy()
            check_joint_path(env, start, goal, env.allowed)
            for i in range(steps):
                alpha = (i + 1) / steps
                alpha = alpha * alpha * (3 - 2 * alpha)
                action = start + alpha * (goal - start)
                pending_observation = record(action)
                try:
                    env.step(action, episode_id=env.episode_id, sequence=env.sequence)
                except (Exception, KeyboardInterrupt):
                    partial_step = True
                    raise
                if recorder:
                    recorder.record(pending_observation, action)

        execute("settle", q, 20)
        q = solve_downward(env, above, q, arm=config.arm)
        execute("approach", q, 40)
        q = solve_downward(env, target, q, arm=config.arm)
        execute("descend", q, 40)
        q[grip] = 0.8 if config.skip_close else -0.1
        execute("close", q, 30)
        q = solve_downward(env, above, q, arm=config.arm)
        execute("lift", q, 60)
        execute("hold", q, 40)
        # Stop before continuing to placement if the hold did not establish a grasp.
        metrics = score_grasp(env.contact_trace, initial, destination)
        if not metrics["hold_passed"]:
            raise RuntimeError("Object was not held airborne by both jaws for two seconds")
        if destination is not None:
            above[:2] = destination[:2]
            q = solve_downward(env, above, q, arm=config.arm)
            execute("transport", q, 60)
            metrics = score_grasp(env.contact_trace, initial, destination)
            if not metrics["transport_passed"]:
                raise RuntimeError("Object lost bilateral airborne support during transport")
        # Open just above the support surface rather than force the held object
        # into the table after it has shifted slightly inside the fingers.
        release_target = target + np.array([0, 0, 0.009])
        if destination is not None:
            release_target[:2] = destination[:2]
        q = solve_downward(env, release_target, q, arm=config.arm)
        execute("lower", q, 60)
        q[grip] = 0.8
        execute("release", q, 30)
        q = solve_downward(env, above, q, arm=config.arm)
        execute("retreat", q, 40)
        execute("settled", q, 40)
        record(None)
        metrics = score_grasp(env.contact_trace, initial, destination)
        if not metrics["grasp_success"]:
            raise RuntimeError("Release did not settle within the documented acceptance bounds")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        (directory / "error.txt").write_text(error + "\n")
    finally:
        if env:
            if recorder:
                try:
                    # A rejected/partially executed command is never an applied
                    # training action. End at its captured pre-command boundary.
                    terminal = pending_observation if partial_step else env.observe(render=True)
                    recorder.record(terminal, None)
                    episode_path = recorder.finalize(
                        outcome={"completed": "success", "interrupted": "cancelled"}.get(
                            outcome, "failure"
                        ),
                        outcome_reason=error
                        or "Independent physical placement/grasp checks passed",
                    )
                    metrics["demonstration_path"] = str(episode_path.relative_to(directory))
                    metrics["demonstration_transitions"] = len(recorder.frames) - 1
                except (Exception, KeyboardInterrupt) as exc:
                    # Preserve partial images and the failure in the sealed run.
                    metrics["demonstration_error"] = f"{type(exc).__name__}: {exc}"
                    outcome = "failed"
                    error = error or metrics["demonstration_error"]
            # Always preserve the full contact history, even if a later stage failed.
            if not config.missing_object:
                metrics.update(
                    score_grasp(
                        env.contact_trace,
                        np.array([config.object_x, config.object_y, 0.391]),
                        destination,
                    )
                )
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
                duration=100,
                loop=0,
            )
        metrics.update(
            error=error,
            wall_seconds=time.perf_counter() - started,
            rendered=config.render,
            teacher_uses_simulator_truth=True,
        )
    return store.seal(
        directory,
        kind="contact_placement_teacher" if destination is not None else "contact_grasp_teacher",
        outcome=outcome,
        config=config.model_dump(),
        source=source,
        claims=(
            ["contact_grasp_hold_release"]
            + (["contact_transport_placement"] if destination is not None else [])
        )
        if outcome == "completed"
        else [],
        metrics=metrics,
    )
