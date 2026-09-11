"""Reproducible diagnosis of sealed learned hand-off physical failures."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from bimanual.dinner_scoring import _airborne
from bimanual.dinner_teacher import ASSETS, load_plan
from bimanual.dual_arm import JOINT_ORDER
from bimanual.evidence import EvidenceStore, Manifest, canonical, provenance

GRIP_THRESHOLD = 0.01
HOLD_SAMPLES = 2000


class HandoffFailureAnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    wrapper_run_ids: tuple[str, ...] = Field(min_length=1, max_length=10)


def _worker_paths(child_store: EvidenceStore, child: Manifest) -> tuple[Path, Path]:
    root = child_store.directory(child.run_id)
    actions, physics = root / "worker/actions.jsonl", root / "worker/physics.jsonl"
    if (
        child.files.get("worker/actions.jsonl") is None
        or child.files.get("worker/physics.jsonl") is None
    ):
        raise ValueError("Physical child is missing sealed worker action/physics evidence")
    if len(child.files) != len(set(child.files)):
        raise ValueError("Physical child has duplicate evidence paths")
    return actions, physics


def _nearest_teacher(q: np.ndarray, teacher: np.ndarray, phases: list[str]) -> dict:
    distances = np.sqrt(np.mean(np.square(teacher - q), axis=1))
    index = int(np.argmin(distances))
    return {
        "index": index,
        "phase": phases[index],
        "joint_rms_rad": float(distances[index]),
        "left_gripper_target_rad": float(teacher[index, 5]),
        "right_gripper_target_rad": float(teacher[index, 11]),
    }


def _analyse_child(child_store: EvidenceStore, child: Manifest, teacher, phases) -> dict:
    if (
        child.kind != "learned_handoff_physical_diagnostic"
        or child.outcome != "failed"
        or child.metrics.get("physical_success") is not False
        or child.config.get("device") != "mps"
    ):
        raise ValueError("Expected a failed MPS hand-off physical diagnostic")
    actions_path, physics_path = _worker_paths(child_store, child)
    actions = [json.loads(line) for line in actions_path.open()]
    expected_actions = child.metrics.get("applied_actions")
    if type(expected_actions) is not int or len(actions) != expected_actions:
        raise ValueError("Physical action count does not match sealed child metrics")

    stage = donor = shared = receiver = 0
    transitions = []
    terminal = None
    physics_rows = 0
    lost = None
    with physics_path.open() as stream:
        for action_index, action in enumerate(actions, start=1):
            rows = []
            for sample_in_action in range(50):
                line = stream.readline()
                if not line:
                    break
                row = json.loads(line)
                rows.append(row)
                physics_rows += 1
                obj = row["objects"]["practice_object"]
                predicates = (
                    _airborne(obj, "left"),
                    not obj["support"]
                    and min((*obj["forces"]["left"], *obj["forces"]["right"])) > GRIP_THRESHOLD,
                    _airborne(obj, "right"),
                )
                counts = [donor, shared, receiver]
                if stage < 3:
                    counts[stage] = counts[stage] + 1 if predicates[stage] else 0
                    donor, shared, receiver = counts
                    if counts[stage] >= HOLD_SAMPLES:
                        stage += 1
                        transitions.append(
                            {
                                "stage": stage,
                                "action": action_index,
                                "sample_in_action": sample_in_action + 1,
                                "physics_sample": physics_rows,
                            }
                        )
                continuity = not obj["support"] and any(
                    value > GRIP_THRESHOLD for pair in obj["forces"].values() for value in pair
                )
                if 0 < stage < 3 and not continuity and lost is None:
                    lost = {
                        "action": action_index,
                        "sample_in_action": sample_in_action + 1,
                        "physics_sample": physics_rows,
                        "support": list(obj["support"]),
                        "left_forces": list(obj["forces"]["left"]),
                        "right_forces": list(obj["forces"]["right"]),
                        "object_position_m": list(obj["pos"]),
                    }
                terminal = row
            if len(rows) not in (50,) and action_index != len(actions):
                raise ValueError("Nonterminal physical action has incomplete 1 kHz evidence")
            if action.get("applied") is not True and action_index != len(actions):
                raise ValueError("Nonterminal action was not confirmed applied")
        if stream.readline():
            raise ValueError("Physics evidence extends beyond the action log")
    if terminal is None or lost is None:
        raise ValueError("Sealed failure does not reproduce a post-donor continuity loss")
    expected_reason = "ValueError: Handoff support/grip continuity lost after donor hold"
    if child.metrics.get("reason") != expected_reason:
        raise ValueError("Sealed failure reason differs from reproduced continuity loss")
    targets = np.asarray(actions[-1].get("targets_rad"), dtype=float)
    joints = np.asarray(terminal.get("joint_position"), dtype=float)
    if targets.shape != (12,) or joints.shape != (12,) or not np.isfinite(targets).all():
        raise ValueError("Terminal hand-off action/joint evidence is malformed")
    nearest = _nearest_teacher(joints, teacher, phases)
    return {
        "wrapper_child_run_id": child.run_id,
        "child_manifest_sha256": child.manifest_sha256,
        "execute_chunk_steps": child.config["execute_chunk_steps"],
        "applied_actions": len(actions),
        "physics_rows": physics_rows,
        "stage_reached": stage,
        "stage_transitions": transitions,
        "continuity_loss": lost,
        "terminal_target": {
            "left_gripper_rad": float(targets[5]),
            "right_gripper_rad": float(targets[11]),
        },
        "nearest_nominal_teacher": nearest,
        "terminal_right_gripper_error_rad": float(
            targets[11] - nearest["right_gripper_target_rad"]
        ),
        "physical_success": False,
    }


def analyse_handoff_failures(
    config: HandoffFailureAnalysisConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
) -> Manifest:
    """Verify wrapper/child/source seals, reproduce failure stages, and seal findings."""

    config = HandoffFailureAnalysisConfig.model_validate(config.model_dump())
    if len(set(config.wrapper_run_ids)) != len(config.wrapper_run_ids):
        raise ValueError("Each physical wrapper may be analysed only once")
    directory = store.new_run()
    _, plan, _ = load_plan(ASSETS.with_name("dinner_teacher_v2"))
    teacher = np.asarray([step["q"] for step in plan["steps"]], dtype=float)
    phases = [step["phase"] for step in plan["steps"]]
    reports = []
    training = None
    wrappers = []
    children = []
    for run_id in config.wrapper_run_ids:
        wrapper = store.verify(run_id)
        if wrapper.kind != "learned_handoff_physical_diagnostic_process":
            raise ValueError("Expected a sealed hand-off physical process wrapper")
        child_id = wrapper.metrics.get("child_run_id")
        child_sha256 = wrapper.metrics.get("child_sha256")
        if not isinstance(child_id, str) or not isinstance(child_sha256, str):
            raise ValueError("Wrapper lacks a pinned child result")
        child_store = EvidenceStore(store.directory(run_id) / "child-evidence")
        child = child_store.verify(child_id)
        if child.manifest_sha256 != child_sha256:
            raise ValueError("Wrapper and child manifest seals disagree")
        current_training = child.config.get("training_run")
        if training is None:
            training = current_training
        elif current_training != training:
            raise ValueError("Compared physical failures must use one checkpoint")
        report = _analyse_child(child_store, child, teacher, phases)
        report.update(
            wrapper_run_id=run_id,
            wrapper_manifest_sha256=wrapper.manifest_sha256,
        )
        reports.append(report)
        wrappers.append(wrapper)
        children.append((child_store, child))
    training_manifest = store.verify(training)
    if (
        training_manifest.kind != "act_training"
        or training_manifest.outcome != "completed"
        or training_manifest.config.get("skill_id") != "handoff_transfer"
    ):
        raise ValueError("Compared checkpoint is not a completed hand-off ACT training run")
    # Reverify every large source after streaming so analysis cannot race a mutation.
    for wrapper in wrappers:
        if store.verify(wrapper.run_id) != wrapper:
            raise ValueError("Physical wrapper changed during analysis")
    for child_store, child in children:
        if child_store.verify(child.run_id) != child:
            raise ValueError("Physical child changed during analysis")
    if store.verify(training) != training_manifest:
        raise ValueError("Training checkpoint changed during analysis")
    finding = {
        "profile": "handoff_continuity_failure_analysis_v1",
        "joint_order": list(JOINT_ORDER),
        "training_run_id": training,
        "training_manifest_sha256": training_manifest.manifest_sha256,
        "comparisons": reports,
        "finding": (
            "Both attempts lose all practice-bar grip after the donor-hold milestone; "
            "the terminal forecast opens the receiver gripper relative to the nearest "
            "nominal left-release target."
        ),
        "recommended_data_region": (
            "receiver close/shared hold through donor release, with the receiver gripper "
            "held closed and varied measured approach states"
        ),
        "physical_success": False,
        "checkpoint_promoted": False,
        "generalization_validated": False,
    }
    (directory / "analysis.json").write_bytes(canonical(finding))
    return store.seal(
        directory,
        kind="handoff_continuity_failure_analysis",
        outcome="completed",
        config=config.model_dump(mode="json"),
        metrics=finding,
        source=provenance(project_root),
        claims=["Reproduced failure diagnosis only; checkpoint remains unpromoted"],
    )
