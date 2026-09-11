"""Training-only measured-state approach collection; never a deployed policy."""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from bimanual.contracts import Artifact, EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dinner_teacher import ASSETS, DinnerEnvironment, load_plan
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.teacher import check_joint_path

GOAL_INDICES = (59, 119, 179)


class FeedbackApproachConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)
    max_delta_rad: float = Field(default=0.03, gt=0, le=0.03)
    position_tolerance_rad: float = Field(default=0.015, gt=0, le=0.015)
    velocity_tolerance_rad_s: float = Field(default=0.05, gt=0, le=0.05)
    max_actions_per_goal: int = Field(default=300, ge=1, le=3000)
    record_demonstration: bool = False
    variation_seed: int = Field(default=0, ge=0, le=1_000_000)
    acquisition_offset_rad: float = Field(default=0.0, ge=0, le=0.08)


def feedback_target(measured: np.ndarray, goal: np.ndarray, max_delta_rad: float) -> np.ndarray:
    """Bound the largest joint correction, retaining the direction to the subgoal."""
    if (
        measured.shape != (12,)
        or goal.shape != (12,)
        or not np.isfinite(measured).all()
        or not np.isfinite(goal).all()
        or not np.isfinite(max_delta_rad)
        or not 0 < max_delta_rad <= 0.03
    ):
        raise ValueError("Invalid feedback state, goal or correction bound")
    delta = goal - measured
    return measured + delta * min(1.0, max_delta_rad / max(float(np.max(np.abs(delta))), 1e-12))


def run_feedback_approach(
    config: FeedbackApproachConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
) -> Manifest:
    """Normal reset, three joint subgoals, contact guards, and sealed partial failures.

    Success means approach subgoals only. No grasp or hand-off is attempted/scored.
    Recording captures all three cameras immediately before each applied action.
    """
    config = FeedbackApproachConfig.model_validate(config.model_dump())
    directory = store.new_run()
    source = provenance(project_root)
    started = time.perf_counter()
    outcome = "failed"
    metrics = dict(
        goals_reached=0,
        actions=0,
        acquisition_actions=0,
        correction_start_action=0,
        physical_handoff_success=None,
        teacher_assistance=True,
        learned_execution=False,
        normal_reset=True,
    )
    env = recorder = trace = actions = pending = None
    partial = recording_failed = False
    run_config = config.model_dump() | {"training_only": True, "goal_indices": list(GOAL_INDICES)}

    def artifact(name):
        return Artifact(path=name, sha256=digest_file(directory / name))

    try:
        if cancelled():
            raise InterruptedError("Feedback collection cancelled before initialization")
        assets = ASSETS.with_name("dinner_teacher_v2")
        manifest, plan, _ = load_plan(assets)
        goals = [
            dict(phase=plan["steps"][i]["phase"], q=plan["steps"][i]["q"]) for i in GOAL_INDICES
        ]
        acquisition = []
        if config.acquisition_offset_rad:
            perturbed = np.asarray(goals[0]["q"], dtype=float).copy()
            perturbed[:4] += np.random.default_rng(config.variation_seed).uniform(
                -config.acquisition_offset_rad, config.acquisition_offset_rad, 4
            )
            acquisition = [dict(phase="feedback/acquisition", q=perturbed.tolist())]
        run_config.update(goals=goals, acquisition=acquisition, asset_manifest=manifest)
        (directory / "config.json").write_bytes(canonical(run_config))
        (directory / "scene.xml").write_bytes((assets / "scene.xml").read_bytes())
        (directory / "controller.json").write_bytes(
            canonical(
                {
                    "kind": "scripted_teacher",
                    "mode": "measured_feedback_approach_v1",
                    "training_only": True,
                    "goal_source": "verified v2 authored joint subgoals",
                    "source_sha256": source["source_sha256"],
                }
            )
        )
        trace = (directory / "physics.jsonl").open("x")
        actions = (directory / "actions.jsonl").open("xb")
        env = DinnerEnvironment((directory / "scene.xml").read_text(), trace, cancelled)
        limits = JointLimits(lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist())
        for goal in acquisition + goals:
            limits.validate_targets(goal["q"])
        if config.record_demonstration:
            recorder = DemonstrationRecorder(
                directory,
                instruction=(
                    "Approach the practice bar with the left gripper open; stop before grasping."
                ),
                instruction_revision=0,
                lineage=EpisodeLineage(
                    code_revision=source["git_revision"],
                    source_sha256=source["source_sha256"],
                    scene=artifact("scene.xml"),
                    config=artifact("config.json"),
                    controller=artifact("controller.json"),
                    controller_kind="scripted_teacher",
                    seed=config.variation_seed,
                    split="train",
                ),
                joint_limits=limits,
            )
        for goal in acquisition + goals:
            eligible = goal["phase"] != "feedback/acquisition"
            env.phase, env.active_contacts = goal["phase"], {}
            target = np.asarray(goal["q"], dtype=float)
            # Include a final check after the last permitted action.
            for count in range(config.max_actions_per_goal + 1):
                if cancelled():
                    raise InterruptedError("Feedback collection cancelled")
                measured, velocity = env.data.qpos[env.qadr].copy(), env.data.qvel[env.vadr].copy()
                if not np.isfinite(velocity).all():
                    raise ValueError("Non-finite measured velocity")
                action = feedback_target(measured, target, config.max_delta_rad)
                error = float(np.max(np.abs(target - measured)))
                if (
                    error <= config.position_tolerance_rad
                    and np.max(np.abs(velocity)) <= config.velocity_tolerance_rad_s
                ):
                    if eligible:
                        metrics["goals_reached"] += 1
                    break
                if count == config.max_actions_per_goal:
                    raise TimeoutError(f"Feedback goal timeout: {env.phase}; error={error}")
                limits.validate_targets(action.tolist())
                check_joint_path(env, measured, action, env.allowed)
                sequence = env.sequence
                pending = env.observe(render=True) if recorder else None
                row = dict(
                    sequence=sequence,
                    phase=env.phase,
                    measured=measured.tolist(),
                    target=action.tolist(),
                    goal_error_rad=error,
                    applied=False,
                    training_eligible=eligible,
                )
                try:
                    partial = True
                    env.step(action, episode_id=env.episode_id, sequence=sequence)
                    partial = False
                    row["applied"] = True
                    metrics["actions"] += 1
                    if not eligible:
                        metrics["acquisition_actions"] += 1
                        metrics["correction_start_action"] = metrics["actions"]
                    if recorder:
                        try:
                            recorder.record(pending, action)
                        except (Exception, KeyboardInterrupt):
                            recording_failed = True
                            raise
                    pending = None
                finally:
                    row["partial_physics"] = partial
                    actions.write(canonical(row) + b"\n")
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as error:
        outcome = (
            "interrupted" if isinstance(error, (InterruptedError, KeyboardInterrupt)) else "failed"
        )
        metrics["error"] = f"{type(error).__name__}: {error}"
        (directory / "error.txt").write_text(traceback.format_exc())
    finally:
        if recorder is not None and not recording_failed:
            try:
                recorder.record(pending if partial else env.observe(render=True), None)
                path = recorder.finalize(
                    interventions=int(metrics["acquisition_actions"] > 0),
                    outcome={"completed": "success", "interrupted": "cancelled"}.get(
                        outcome, "failure"
                    ),
                    outcome_reason=metrics.get(
                        "error", "Reached approach subgoals only; no grasp or hand-off"
                    ),
                )
                metrics.update(
                    demonstration_path=path.relative_to(directory).as_posix(),
                    recorded_observations=len(recorder.frames),
                )
            except (Exception, KeyboardInterrupt) as error:
                outcome = "failed"
                metrics["recording_error"] = f"{type(error).__name__}: {error}"
        # Each cleanup is independent so a renderer error cannot prevent trace closure/sealing.
        cleanup_errors = []
        for operation in ([env.stop, env.close] if env is not None else []) + [
            stream.close for stream in (actions, trace) if stream is not None
        ]:
            try:
                operation()
            except (Exception, KeyboardInterrupt) as error:
                cleanup_errors.append(f"{type(error).__name__}: {error}")
        if cleanup_errors:
            metrics["cleanup_errors"] = cleanup_errors
            outcome = "failed"
    metrics["wall_seconds"] = time.perf_counter() - started
    return store.seal(
        directory,
        kind="feedback_approach_teacher_recording",
        outcome=outcome,
        config=run_config,
        metrics=metrics,
        source=source,
        claims=["Training-only approach collection; no grasp, learned-policy or dinner success"],
    )
