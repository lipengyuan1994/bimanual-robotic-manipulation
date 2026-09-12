"""Scripted contact-only practice-bar transfer; not learned dinner-task control."""

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
from bimanual.teacher import ReachError, check_joint_path


class HandoffConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    render: bool = True
    missing_object: bool = False
    skip_receiver_close: bool = False


def handoff_xml(config: HandoffConfig) -> str:
    root = ET.fromstring(grasp_xml(GraspConfig(missing_object=config.missing_object)))
    root.set("model", "dual_so101_contact_handoff")
    body = root.find(".//body[@name='practice_object']")
    if body is not None:
        body.set("pos", "0 0 .391")
        # Long practice bar with explicit contact-material assumptions. Stock
        # finger priority is 1; matching it lets both surfaces determine friction.
        geom = body.find("geom")
        geom.attrib.update(
            size=".09 .01 .016",
            mass=".025",
            friction="1 .01 .002",
            condim="6",
            priority="1",
            solref=".01 1",
        )
    return ET.tostring(root, encoding="unicode")


def solve_fixed_roll(env: DualArm, target, initial, *, arm: str) -> np.ndarray:
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
    site = env.model.site(f"{arm}/pinch").id
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


class HandoffEnvironment(DualArm):
    def __init__(self, config: HandoffConfig):
        self.stage = "settle"
        self.contact_trace: list[dict] = []
        super().__init__(xml=handoff_xml(config))
        self.fingers = {
            arm: tuple(
                {
                    self.model.geom(i).name
                    for i in range(self.model.ngeom)
                    if self.model.body(int(self.model.geom_bodyid[i])).name == f"{arm}/{body}"
                }
                for body in ("gripper", "moving_jaw_so101_v1")
            )
            for arm in ("left", "right")
        }

    def step(self, targets, *, episode_id, sequence):
        if self.stage not in {
            "settle",
            "orient",
            "left_approach",
            "left_descend",
            "left_close",
            "left_lift",
            "left_hold",
            "right_approach",
            "right_descend",
            "right_close",
            "both_hold",
            "left_release",
            "left_retreat",
            "receiver_hold",
        }:
            raise ValueError("Unknown handoff stage")
        values = np.asarray(targets, dtype=float)
        if values.shape == (12,):
            parked = (
                slice(6, 12)
                if self.stage.startswith("left_")
                else slice(0, 6)
                if self.stage.startswith("right_")
                else slice(0, 12)
                if self.stage in {"settle", "both_hold", "receiver_hold"}
                else None
            )
            if parked is not None and not np.allclose(
                values[parked], self.data.ctrl[self.actuator_ids][parked], rtol=0, atol=1e-12
            ):
                raise ValueError("Stage does not own the requested arm movement")
        super().step(values, episode_id=episode_id, sequence=sequence)

    def allowed(self, pair):
        names = set(pair)
        if names == {"practice_object", "workbench"}:
            return self.stage in {
                "settle",
                "orient",
                "left_approach",
                "left_descend",
                "left_close",
                "left_lift",
            }
        return "practice_object" in names and any(
            names & (fixed | moving) for fixed, moving in self.fingers.values()
        )

    def after_physics_step(self):
        mujoco.mj_forward(self.model, self.data)
        exists = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "practice_object") >= 0
        row = dict(
            stage=self.stage,
            simulation_seconds=float(self.data.time),
            object_position_m=self.data.body("practice_object").xpos.tolist() if exists else None,
            object_orientation_wxyz=self.data.body("practice_object").xquat.tolist()
            if exists
            else None,
            jaw_normal_force_n={arm: [0.0, 0.0] for arm in self.fingers},
            forbidden_pairs=[],
            contact_pairs=[],
            table_contact=False,
            max_penetration_m=0.0,
        )
        for i, contact in enumerate(self.data.contact):
            pair = tuple(self.model.geom(int(g)).name for g in contact.geom)
            row["contact_pairs"].append(pair)
            if not self.allowed(pair):
                row["forbidden_pairs"].append(pair)
            row["max_penetration_m"] = max(row["max_penetration_m"], -float(contact.dist))
            if "practice_object" in pair and contact.efc_address >= 0:
                row["table_contact"] |= "workbench" in pair
                force = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, i, force)
                for arm, surfaces in self.fingers.items():
                    for jaw, names in enumerate(surfaces):
                        if set(pair) & names:
                            row["jaw_normal_force_n"][arm][jaw] += max(0.0, float(force[0]))
        self.contact_trace.append(row)
        if row["forbidden_pairs"] or row["max_penetration_m"] > 0.0025:
            self.stop()
            raise RuntimeError(
                f"Forbidden contact during {self.stage}: {row['forbidden_pairs'][0]}"
                if row["forbidden_pairs"]
                else "Contact penetration exceeds the 2.5 mm limit"
            )


def score_handoff(trace: list[dict]) -> dict:
    """Require sustained donor, shared and receiver ownership in that order."""
    phases = {
        name: [r for r in trace if r["stage"] == name]
        for name in ("left_hold", "both_hold", "receiver_hold")
    }

    def owned(row, owners):
        forces = row["jaw_normal_force_n"]
        return (
            row["object_position_m"] is not None
            and row["object_position_m"][2] > 0.42
            and not row["table_contact"]
            and all(
                min(forces[arm]) > 0.01 if arm in owners else forces[arm] == [0, 0]
                for arm in ("left", "right")
            )
        )

    owners = ({"left"}, {"left", "right"}, {"right"})
    counts = {
        name: sum(owned(r, owner) for r in phases[name])
        for name, owner in zip(phases, owners, strict=True)
    }
    passed = {
        name: len(phases[name]) == 400
        and counts[name] == 400
        and np.allclose(
            np.diff([r["simulation_seconds"] for r in phases[name]]), 0.005, rtol=0, atol=1e-9
        )
        for name in phases
    }
    timestamps = [r["simulation_seconds"] for r in trace]
    contiguous = len(trace) > 1 and np.allclose(np.diff(timestamps), 0.005, rtol=0, atol=1e-9)
    ordered = all(phases[name] for name in phases) and (
        phases["left_hold"][-1]["simulation_seconds"] < phases["both_hold"][0]["simulation_seconds"]
        and phases["both_hold"][-1]["simulation_seconds"]
        < phases["receiver_hold"][0]["simulation_seconds"]
    )
    transfer_rows = [
        r
        for r in trace
        if phases["left_hold"]
        and r["simulation_seconds"] >= phases["left_hold"][0]["simulation_seconds"]
    ]
    airborne = bool(transfer_rows) and all(
        not r["table_contact"]
        and r["object_position_m"] is not None
        and r["object_position_m"][2] > 0.42
        for r in transfer_rows
    )
    forbidden = sum(bool(r["forbidden_pairs"]) for r in trace)
    penetration = max((r["max_penetration_m"] for r in trace), default=0)
    receiver = phases["receiver_hold"]
    return dict(
        handoff_success=bool(
            all(passed.values())
            and contiguous
            and ordered
            and airborne
            and not forbidden
            and penetration <= 0.0025
        ),
        donor_hold_passed=bool(passed["left_hold"]),
        shared_hold_passed=bool(passed["both_hold"]),
        receiver_hold_passed=bool(passed["receiver_hold"]),
        donor_only_samples=int(counts["left_hold"]),
        shared_grasp_samples=int(counts["both_hold"]),
        receiver_only_samples=int(counts["receiver_hold"]),
        trace_contiguous=bool(contiguous),
        airborne_transfer=bool(airborne),
        phases_ordered=bool(ordered),
        forbidden_contact_samples=forbidden,
        max_penetration_m=penetration,
        receiver_hold_sag_m=(
            receiver[0]["object_position_m"][2] - receiver[-1]["object_position_m"][2]
        )
        if receiver
        else None,
        manipulation_success=None,
    )


def run_handoff(config: HandoffConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source = provenance(project_root)
    started = time.perf_counter()
    env = None
    observations, frames = [], []
    outcome, error = "failed", None
    metrics = score_handoff([])
    try:
        env = HandoffEnvironment(config)
        (directory / "scene.xml").write_text(env.xml)
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2))
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "config.json").write_text(config.model_dump_json(indent=2))
        if config.missing_object:
            raise RuntimeError("Practice bar is missing; no handoff attempted")

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
                    frame.paste(Image.fromarray(obs["rgb"][camera]), (col * 480, 30))
                ImageDraw.Draw(frame).text(
                    (12, 8),
                    f"CONTACT HANDOFF TEACHER | {env.stage} | {env.data.time:.2f}s"
                    " | overhead / left wrist / right wrist",
                    fill="white",
                )
                frames.append(frame)

        def execute(stage, goal, steps):
            env.stage = stage
            start = env.data.ctrl[env.actuator_ids].copy()
            check_joint_path(env, start, goal, env.allowed)
            for i in range(steps):
                alpha = (i + 1) / steps
                alpha = alpha * alpha * (3 - 2 * alpha)
                action = start + alpha * (goal - start)
                record(action)
                env.step(action, episode_id=env.episode_id, sequence=env.sequence)

        q = env.home.copy()

        def move(stage, target, arm, steps=60):
            nonlocal q
            q = solve_fixed_roll(env, target, q, arm=arm)
            execute(stage, q, steps)

        execute("settle", q, 20)
        q[[4, 10]] = 1.57
        execute("orient", q, 40)
        move("left_approach", [-0.075, 0, 0.46], "left")
        move("left_descend", [-0.075, 0, 0.404], "left")
        q[5] = -0.1
        execute("left_close", q, 30)
        move("left_lift", [-0.075, 0, 0.46], "left")
        execute("left_hold", q, 40)
        if not score_handoff(env.contact_trace)["donor_hold_passed"]:
            raise RuntimeError(
                "Donor did not establish two seconds of exclusive airborne ownership"
            )
        # Privileged teacher target stays separate from operating observations.
        body = env.data.body("practice_object")
        receiver = body.xpos + body.xmat.reshape(3, 3) @ np.array([0.075, 0, 0])
        receiver[2] += 0.013
        move("right_approach", receiver + [0, 0, 0.022], "right")
        move("right_descend", receiver, "right", 40)
        q[11] = 0.8 if config.skip_receiver_close else -0.1
        execute("right_close", q, 40)
        execute("both_hold", q, 40)
        if not score_handoff(env.contact_trace)["shared_hold_passed"]:
            raise RuntimeError("Receiver did not establish a shared grasp; donor remains closed")
        q[5] = 0.8
        execute("left_release", q, 40)
        move("left_retreat", [-0.09, -0.04, 0.47], "left")
        execute("receiver_hold", q, 40)
        record(None)
        if not score_handoff(env.contact_trace)["handoff_success"]:
            raise RuntimeError("Receiver-only airborne handoff acceptance failed")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        (directory / "error.txt").write_text(error + "\n")
    finally:
        if env is not None:
            metrics = score_handoff(env.contact_trace)
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
        # A late recording or process failure cannot receive a success claim.
        if outcome != "completed":
            metrics["handoff_success"] = False
    return store.seal(
        directory,
        kind="contact_handoff_teacher",
        outcome=outcome,
        config=config.model_dump(),
        source=source,
        claims=["contact_bar_handoff"] if outcome == "completed" else [],
        metrics=metrics,
    )
