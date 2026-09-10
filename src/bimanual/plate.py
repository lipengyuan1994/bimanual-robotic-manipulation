"""Contact-only placement of a small plate from a source rack onto the bare table."""

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
from bimanual.grasp import GraspConfig, grasp_xml, invalid_contact_trace_row
from bimanual.teacher import ReachError, check_carried_path, check_joint_path

INITIAL = np.array([0.150, -0.090, 0.413])
DESTINATION = np.array([0.130, -0.230, 0.378])


class PlateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    render: bool = True
    missing_object: bool = False
    skip_close: bool = False


def plate_xml(config: PlateConfig) -> str:
    root = ET.fromstring(grasp_xml(GraspConfig(missing_object=True)))
    root.set("model", "dual_so101_contact_plate")
    root.find("option").set("timestep", ".001")
    world = root.find("worldbody")
    ET.SubElement(
        world,
        "geom",
        name="plate_rack",
        type="cylinder",
        pos=".15 -.09 .3925",
        size=".035 .0175",
        rgba=".3 .3 .3 1",
    )
    if not config.missing_object:
        plate = ET.SubElement(world, "body", name="plate", pos=".15 -.09 .413")
        ET.SubElement(plate, "freejoint", name="plate/free")

        def geom(name, **attributes):
            ET.SubElement(
                plate,
                "geom",
                name=f"plate/{name}",
                rgba=".86 .75 .55 1",
                friction="1.5 .01 .0001",
                priority="1",
                solref=".005 1",
                solimp=".95 .99 .001",
                **attributes,
            )

        geom("base", type="cylinder", size=".065 .003", mass=".06")
        for i in range(24):
            theta = 2 * np.pi * i / 24
            geom(
                f"rim{i}",
                type="box",
                pos=f"{0.063 * np.cos(theta)} {0.063 * np.sin(theta)} .007",
                size=".003 .0084 .007",
                euler=f"0 0 {theta}",
                mass=str(0.02 / 24),
            )
    return ET.tostring(root, encoding="unicode")


class PlateEnvironment(DualArm):
    def __init__(self, config: PlateConfig):
        self.stage = "settle"
        self.contact_trace: list[dict] = []
        self.has_object = not config.missing_object
        self.arm = "left"
        super().__init__(xml=plate_xml(config), physics_hz=1000)
        self.parked = self.home.copy()
        self.parked[6] = 1.0
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
            if self.model.body(int(self.model.geom_bodyid[i])).name == "plate"
        }

    def step(self, targets, *, episode_id, sequence):
        values = np.asarray(targets, float)
        if values.shape == (12,):
            # Only the initial, supervised parking phase owns the right pan joint.
            if self.stage == "settle":
                valid = np.allclose(values[7:], self.home[7:], rtol=0, atol=1e-12) and min(
                    self.home[6], 1
                ) <= values[6] <= max(self.home[6], 1)
            else:
                valid = np.allclose(values[6:], self.parked[6:], rtol=0, atol=1e-12)
            if not valid:
                raise ValueError("Plate teacher does not own the parked right arm")
        super().step(values, episode_id=episode_id, sequence=sequence)

    def allowed(self, pair):
        names = set(pair)
        return bool(names & self.object_geoms) and bool(
            names & ({"workbench", "plate_rack"} | self.fingers[0] | self.fingers[1])
        )

    def after_physics_step(self):
        mujoco.mj_forward(self.model, self.data)
        row = dict(
            stage=self.stage,
            simulation_seconds=float(self.data.time),
            object_position_m=self.data.body("plate").xpos.tolist() if self.has_object else None,
            object_velocity=self.data.joint("plate/free").qvel.tolist()
            if self.has_object
            else None,
            upright_cosine=float(self.data.body("plate").xmat.reshape(3, 3)[2, 2])
            if self.has_object
            else None,
            fixed_jaw_normal_force_n=0.0,
            moving_jaw_normal_force_n=0.0,
            table_contact=False,
            bare_table_contact=False,
            rack_contact=False,
            any_support_contact=False,
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
                if names & {"workbench", "plate_rack"}:
                    row["any_support_contact"] = True
                    row["rack_contact"] |= "plate_rack" in names
                    if normal > 0.01:
                        row["table_contact"] = True
                        row["bare_table_contact"] |= "workbench" in names
        self.contact_trace.append(row)
        if row["forbidden_pairs"] or row["max_penetration_m"] > 0.0025:
            self.stop()
            raise RuntimeError(
                f"Forbidden contact during {self.stage}: {row['forbidden_pairs'][0]}"
                if row["forbidden_pairs"]
                else "Contact penetration exceeds 2.5 mm"
            )


def _score_timed_plate(
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
            and not r["any_support_contact"]
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
        and np.isclose(timestamps[0], 0.001, rtol=0, atol=1e-9)
        and np.allclose(np.diff(timestamps), 0.001, rtol=0, atol=1e-9)
    )

    def continuous_phase(rows, samples):
        return (
            contiguous
            and len(rows) == samples
            and np.allclose(
                np.diff([r["simulation_seconds"] for r in rows]), 0.001, rtol=0, atol=1e-9
            )
        )

    # Duration requires distinct, consecutive physics timestamps, not just row counts.
    hold_ok = continuous_phase(hold, 2000) and all(lifted(r) for r in hold)
    release_ok = continuous_phase(settled, 2000) and all(released(r) for r in settled)
    transport_ok = destination is None or (
        continuous_phase(transport, 3000) and all(lifted(r) for r in transport)
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


def score_plate(trace: list[dict]) -> dict:
    invalid = invalid_contact_trace_row(
        trace,
        required_scalars=("upright_cosine",),
        required_bools=("any_support_contact", "bare_table_contact", "rack_contact"),
    )
    if invalid is not None:
        metrics = score_plate([])
        metrics.update(trace_valid=False, invalid_trace_row=invalid)
        return metrics
    metrics = _score_timed_plate(trace, INITIAL, DESTINATION)
    settled = [r for r in trace if r["stage"] == "settled"]
    upright = len(settled) == 2000 and all(
        r["upright_cosine"] is not None
        and r["upright_cosine"] >= np.cos(np.deg2rad(10))
        and r["bare_table_contact"]
        and not r["rack_contact"]
        for r in settled
    )
    displacement = (
        float(np.linalg.norm(np.array(trace[-1]["object_position_m"][:2]) - INITIAL[:2]))
        if trace and trace[-1]["object_position_m"] is not None
        else 0.0
    )
    metrics.update(
        trace_valid=bool(trace),
        plate_success=bool(metrics["placement_success"] and upright and displacement >= 0.06),
        released_upright=bool(upright),
        actual_displacement_xy_m=displacement,
        max_jaw_normal_force_n=max(
            (max(r["fixed_jaw_normal_force_n"], r["moving_jaw_normal_force_n"]) for r in trace),
            default=0.0,
        ),
    )
    return metrics


def solve_axis(env, target, initial, axis, column=2):
    target, initial, axis = (np.asarray(value, float) for value in (target, initial, axis))
    if target.shape != (3,) or initial.shape != (12,) or axis.shape != (3,):
        raise ReachError("Expected target/initial/axis shapes (3,), (12,), (3,)")
    if type(column) is not int or column not in (0, 1, 2):
        raise ReachError("Expected axis column 0, 1 or 2")
    if not np.isfinite(np.r_[target, initial, axis]).all() or np.linalg.norm(axis) < 1e-12:
        raise ReachError("Expected finite nonzero axis and finite targets")
    if np.any(initial < env.lower) or np.any(initial > env.upper):
        raise ReachError("Initial joint targets exceed limits")
    axis = np.asarray(axis) / np.linalg.norm(axis)
    data = mujoco.MjData(env.model)
    data.qpos[:] = env.data.qpos
    data.qpos[env.qadr] = initial
    site = env.model.site("left/pinch").id
    jp = np.zeros((3, env.model.nv))
    jr = np.zeros_like(jp)
    for _ in range(400):
        mujoco.mj_forward(env.model, data)
        direction = data.site_xmat[site].reshape(3, 3)[:, column]
        error = target - data.site_xpos[site]
        angle = np.asarray(axis) - direction
        if np.linalg.norm(error) < 0.0001 and np.linalg.norm(angle) < 0.001:
            return data.qpos[env.qadr].copy()
        mujoco.mj_jacSite(env.model, data, jp, jr, site)
        jac = np.vstack([jp, 0.1 * np.cross(jr.T, direction).T])[:, env.vadr[:5]]
        delta = jac.T @ np.linalg.solve(jac @ jac.T + 1e-5 * np.eye(6), np.r_[error, 0.1 * angle])
        data.qpos[env.qadr[:5]] = np.clip(
            data.qpos[env.qadr[:5]] + np.clip(delta, -0.1, 0.1), env.lower[:5], env.upper[:5]
        )
    raise ReachError("Plate axis-constrained IK unreachable")


def run_plate(config: PlateConfig, *, store: EvidenceStore, project_root: Path) -> Manifest:
    directory = store.new_run()
    source, started = provenance(project_root), time.perf_counter()
    env = None
    observations, frames = [], []
    outcome, error = "failed", None
    try:
        env = PlateEnvironment(config)
        (directory / "scene.xml").write_text(env.xml)
        (directory / "assets").mkdir()
        for path in (MODEL_DIR / "assets").glob("*.stl"):
            (directory / "assets" / path.name).write_bytes(path.read_bytes())
        (directory / "LICENSE-SO101").write_bytes((MODEL_DIR / "LICENSE").read_bytes())
        (directory / "upstream.json").write_text(json.dumps(verify_assets(), indent=2))
        (directory / "mapping.json").write_text(json.dumps(env.mapping(), indent=2))
        (directory / "config.json").write_text(config.model_dump_json(indent=2))
        (directory / "controller.json").write_text(
            json.dumps(
                {
                    "kind": "scripted_teacher",
                    "physics_hz": 1000,
                    "control_hz": 20,
                    "active_arm": "left",
                    "right_parking_pan_rad": 1.0,
                    "source_rack_height_m": 0.035,
                    "destination_m": DESTINATION.tolist(),
                    "release_calibration_xy_m": [0.02, 0],
                    "release_closing_axis": [0.42, -0.27, 0.866],
                    "teacher_uses_simulator_truth": True,
                    "scope": "single nominal 130mm plate; no trained policy or held-out evaluation",
                },
                indent=2,
            )
        )
        if config.missing_object:
            raise RuntimeError("Plate is missing; no manipulation attempted")

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
                    f"CONTACT PLATE TEACHER | {env.stage} | {env.data.time:.2f}s"
                    " | overhead / left wrist / right wrist",
                    fill="white",
                )
                frames.append(frame)

        closing_axis = np.array([0.0, 0.0, 1.0])

        def solve(point, initial):
            return solve_axis(env, np.asarray(point), initial, closing_axis)

        def execute(stage, goal, steps):
            env.stage = stage
            start = env.data.ctrl[env.actuator_ids].copy()
            linear = stage in {"lift", "transport", "lower", "descend", "insert", "withdraw"}
            if linear:
                scratch = mujoco.MjData(env.model)
                scratch.qpos[:] = env.data.qpos
                scratch.qpos[env.qadr] = start
                mujoco.mj_forward(env.model, scratch)
                p0 = scratch.site("left/pinch").xpos.copy()
                axis0 = scratch.site("left/pinch").xmat.reshape(3, 3)[:, 2].copy()
                scratch.qpos[env.qadr] = goal
                mujoco.mj_forward(env.model, scratch)
                p1 = scratch.site("left/pinch").xpos.copy()
            else:
                check_joint_path(env, start, goal, env.allowed)
            for i in range(steps):
                alpha = (i + 1) / steps
                alpha = alpha * alpha * (3 - 2 * alpha)
                action = (
                    solve_axis(
                        env,
                        p0 + alpha * (p1 - p0),
                        env.data.ctrl[env.actuator_ids].copy(),
                        (1 - alpha) * axis0 + alpha * closing_axis,
                    )
                    if linear
                    else start + alpha * (goal - start)
                )
                if linear:
                    if stage in {"lift", "transport", "lower"}:
                        check_carried_path(
                            env,
                            env.data.ctrl[env.actuator_ids].copy(),
                            action,
                            env.allowed,
                            body_name="plate",
                            site_name="left/pinch",
                        )
                    else:
                        check_joint_path(
                            env, env.data.ctrl[env.actuator_ids].copy(), action, env.allowed
                        )
                record(action)
                env.step(action, episode_id=env.episode_id, sequence=env.sequence)
                if stage == "lower" and env.contact_trace[-1]["any_support_contact"]:
                    break
            return env.data.ctrl[env.actuator_ids].copy()

        target = np.array([0.1, -0.08, 0.424])
        above = np.array([0.1, -0.08, 0.47])
        q = env.parked.copy()
        q[5] = 0.3
        execute("settle", q, 20)
        q = solve([0.04, -0.08, 0.46], q)
        execute("approach", q, 60)
        q = solve(target + [-0.06, 0, 0], q)
        execute("descend", q, 60)
        q = solve(target, q)
        execute("insert", q, 60)
        q[5] = 0.3 if config.skip_close else -0.14
        execute("close", q, 30)
        q = solve(above, q)
        execute("lift", q, 60)
        execute("hold", q, 40)
        if not score_plate(env.contact_trace)["hold_passed"]:
            raise RuntimeError("Plate failed the two-second airborne bilateral hold")
        delta = DESTINATION - INITIAL
        # Fixed nominal release calibration, selected before each recorded run.
        above[:2] += delta[:2] + [0.02, 0]
        q = solve(above, q)
        execute("transport", q, 60)
        release = target + delta + [0.02, 0, 0.009]
        release[2] = 0.405
        closing_axis = np.array([0.42, -0.27, 0.866])
        closing_axis /= np.linalg.norm(closing_axis)
        q = solve(release, q)
        q = execute("lower", q, 60)
        q[5] = 0.3
        execute("release", q, 30)
        q = solve(release + [-0.084, 0.054, 0], q)
        execute("withdraw", q, 100)
        above[:2] += [-0.084, 0.054]
        q = solve(above, q)
        execute("retreat", q, 40)
        execute("settled", q, 40)
        record(None)
        if not score_plate(env.contact_trace)["plate_success"]:
            raise RuntimeError("Plate failed released upright placement acceptance")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        (directory / "error.txt").write_text(error + "\n")
    finally:
        metrics = score_plate(env.contact_trace if env else [])
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
            physics_hz=1000,
            control_hz=20,
            teacher_uses_simulator_truth=True,
            planning_model="scratch rigid object-to-tool transform; live free-body contacts",
        )
        if outcome != "completed":
            metrics["plate_success"] = False
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False))
    return store.seal(
        directory,
        kind="contact_plate_teacher",
        outcome=outcome,
        config=config.model_dump(),
        source=source,
        claims=["contact_plate_upright_placement"] if outcome == "completed" else [],
        metrics=metrics,
    )
