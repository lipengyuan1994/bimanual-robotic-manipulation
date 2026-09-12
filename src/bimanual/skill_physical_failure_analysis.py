"""Reproduce component failure signals from sealed learned-skill evidence.

This is an evidence reader.  It neither runs a policy nor changes a checkpoint,
dataset, scene, or physical result.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from bimanual.evidence import EvidenceStore, Manifest, canonical, provenance

SUITE_KIND = "six_skill_teacher_prepared_physical_suite_report"
EVALUATION_KIND = "learned_skill_teacher_prepared_physical_evaluation"
TARGETS = {
    "bar_place_and_return": "practice_object",
    "cup_pick_place": "cup",
    "plate_pick_place": "plate",
    "drawer_open": None,
    "spoon_retrieve_place": "spoon",
    "fork_retrieve_place": "fork",
}


class SkillPhysicalFailureAnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_run_id: str


def _sealed_worker_paths(store: EvidenceStore, child: Manifest) -> tuple[Path, Path]:
    root = store.directory(child.run_id) / "worker"
    actions, physics = root / "actions.jsonl", root / "physics.jsonl"
    if not all(path in child.files for path in ("worker/actions.jsonl", "worker/physics.jsonl")):
        raise ValueError("Physical evaluation lacks sealed worker action/physics evidence")
    if not actions.is_file() or not physics.is_file():
        raise ValueError("Physical evaluation worker evidence is missing")
    return actions, physics


def _rows_for_actions(
    actions: Path, physics: Path, *, teacher_prefix_actions: int
) -> tuple[list[dict], list[dict], int, int]:
    action_rows = [json.loads(line) for line in actions.open()]
    confirmed = [row for row in action_rows if row.get("applied") is True]
    rejected = [row for row in action_rows if row.get("applied") is False]
    if not confirmed or len(confirmed) + len(rejected) != len(action_rows):
        raise ValueError("Worker action evidence is empty or malformed")
    if len(rejected) > 1 or (
        rejected
        and (rejected[0] is not action_rows[-1] or rejected[0].get("partial_physics") is not True)
    ):
        raise ValueError("Worker action evidence has an invalid rejected-action tail")
    if type(teacher_prefix_actions) is not int or teacher_prefix_actions < 0:
        raise ValueError("Physical evaluation has an invalid teacher prefix count")
    expected = len(confirmed) * 50
    # A rejected terminal action can record at most one partial 50-sample control
    # interval. Keep that bounded suffix while streaming instead of loading the
    # teacher prefix (which can be hundreds of thousands of rows) into memory.
    tail: deque[str] = deque(maxlen=expected + 50)
    total = 0
    with physics.open() as stream:
        for line in stream:
            total += 1
            tail.append(line)
    policy_rows = total - teacher_prefix_actions * 50
    if policy_rows < expected or policy_rows > expected + 50:
        raise ValueError("Physical evidence does not match prefix and action boundaries")
    while len(tail) > policy_rows:
        tail.popleft()
    return confirmed, [json.loads(line) for line in tail], total, len(rejected)


def _force_samples(rows: list[dict], target: str) -> tuple[int, float]:
    forces = [
        max(value for pair in row["objects"][target]["forces"].values() for value in pair)
        for row in rows
    ]
    return sum(value > 0.01 for value in forces), max(forces)


def _target_displacement(rows: list[dict], target: str) -> float:
    initial = rows[0]["objects"][target]["pos"]
    return max(
        sum(
            (position - initial[index]) ** 2
            for index, position in enumerate(row["objects"][target]["pos"])
        )
        ** 0.5
        for row in rows
    )


def _recommendation(skill_id: str, target_contact_samples: int, progress: float) -> str:
    if skill_id == "bar_place_and_return":
        return (
            "Inspect the policy trajectory that introduces the forbidden left-arm bar contact; "
            "do not weaken the contact guard."
        )
    if skill_id == "drawer_open":
        return (
            "Collect a separately frozen corrective dataset for sustained handle contact "
            "and the required open displacement."
        )
    if target_contact_samples == 0:
        return (
            "Collect a separately frozen corrective dataset for target approach "
            "and contact acquisition."
        )
    if progress <= 0.01:
        return (
            "Collect a separately frozen corrective dataset for grasp closure "
            "and lift after contact acquisition."
        )
    return "Inspect this component before defining a separately frozen corrective-data protocol."


def _analyse_child(store: EvidenceStore, child: Manifest, expected_skill: str) -> dict:
    if (
        child.kind != EVALUATION_KIND
        or child.config.get("skill_id") != expected_skill
        or child.metrics.get("component_passed") is not False
        or child.metrics.get("actual_policy_devices") not in (["mps"], ["mps:0"])
    ):
        raise ValueError("Suite member is not a failed, actual-MPS learned-skill evaluation")
    actions_path, physics_path = _sealed_worker_paths(store, child)
    actions, rows, total_physics_rows, rejected_actions = _rows_for_actions(
        actions_path,
        physics_path,
        teacher_prefix_actions=child.metrics.get("teacher_prefix_actions"),
    )
    target = TARGETS.get(expected_skill)
    bad = [
        {"action": index // 50 + 1, "bad": row["bad"]}
        for index, row in enumerate(rows)
        if row.get("bad")
    ]
    report = {
        "skill_id": expected_skill,
        "evaluation_run_id": child.run_id,
        "evaluation_manifest_sha256": child.manifest_sha256,
        "recorded_autonomous_skill_actions": child.metrics.get("autonomous_skill_actions"),
        "confirmed_action_log_actions": len(actions),
        "rejected_action_log_actions": rejected_actions,
        "worker_physics_rows": total_physics_rows,
        "policy_physics_rows": len(rows),
        "forbidden_contact_events": bad,
        "failure_reason": child.metrics.get("reason") or child.metrics.get("error"),
        "physical_success": False,
    }
    if target is None:
        drawer_forces = [min(row["drawer_forces"]) for row in rows]
        opening = [row["opening"] for row in rows]
        report.update(
            target="drawer",
            target_contact_samples=sum(value > 0.01 for value in drawer_forces),
            maximum_target_force=float(max(drawer_forces)),
            opening_start_m=float(opening[0]),
            opening_max_m=float(max(opening)),
            opening_progress_m=float(max(opening) - opening[0]),
        )
        progress = report["opening_progress_m"]
    else:
        contact_samples, maximum_force = _force_samples(rows, target)
        displacement = _target_displacement(rows, target)
        report.update(
            target=target,
            target_contact_samples=contact_samples,
            maximum_target_force=float(maximum_force),
            maximum_target_displacement_m=float(displacement),
        )
        progress = displacement
    report["recommended_next_step"] = _recommendation(
        expected_skill, report["target_contact_samples"], progress
    )
    return report


def analyse_skill_physical_failures(
    config: SkillPhysicalFailureAnalysisConfig, *, store: EvidenceStore, project_root: Path
) -> Manifest:
    """Seal a read-only reproduction of each failed component's physical signal."""

    config = SkillPhysicalFailureAnalysisConfig.model_validate(config.model_dump())
    suite = store.verify(config.suite_run_id)
    if suite.kind != SUITE_KIND or suite.metrics.get("evaluations_complete") is not True:
        raise ValueError("Expected a complete sealed six-skill physical suite")
    members = suite.config.get("evaluation_runs")
    if not isinstance(members, list) or len(members) != len(TARGETS):
        raise ValueError("Physical suite has an invalid component inventory")
    reports = []
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("Physical suite has a malformed component entry")
        skill_id, run_id, seal = (
            member.get("skill_id"),
            member.get("run_id"),
            member.get("manifest_sha256"),
        )
        if skill_id not in TARGETS or not isinstance(run_id, str) or not isinstance(seal, str):
            raise ValueError("Physical suite has an invalid component binding")
        child = store.verify(run_id)
        if child.manifest_sha256 != seal:
            raise ValueError("Physical suite component seal changed")
        reports.append(_analyse_child(store, child, skill_id))
    if len({report["skill_id"] for report in reports}) != len(TARGETS):
        raise ValueError("Physical suite repeats or omits a skill")
    # Reverify all large source artifacts after streaming their traces.
    if store.verify(config.suite_run_id) != suite:
        raise ValueError("Physical suite changed during analysis")
    for report in reports:
        if (
            store.verify(report["evaluation_run_id"]).manifest_sha256
            != report["evaluation_manifest_sha256"]
        ):
            raise ValueError("Physical evaluation changed during analysis")
    finding = {
        "profile": "six_skill_physical_failure_analysis_v1",
        "suite_run_id": suite.run_id,
        "suite_manifest_sha256": suite.manifest_sha256,
        "components": reports,
        "component_passes": 0,
        "independent_task_success": None,
        "autonomous_workflow_success": None,
        "release_qualified": False,
    }
    directory = store.new_run()
    (directory / "analysis.json").write_bytes(canonical(finding))
    return store.seal(
        directory,
        kind="six_skill_physical_failure_analysis",
        outcome="completed",
        config=config.model_dump(mode="json"),
        metrics=finding,
        source=provenance(project_root),
        claims=["Read-only failure diagnosis; no model, dataset, or physical result was changed"],
    )
