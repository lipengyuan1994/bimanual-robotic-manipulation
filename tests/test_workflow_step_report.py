import json
import shutil

import pytest

from bimanual.contracts import Observation
from bimanual.dinner_control import DINNER_WORKER_INSTRUMENTATION
from bimanual.dual_arm import CAMERAS
from bimanual.evidence import EvidenceStore, canonical
from bimanual.skill_registry import dinner_capability
from bimanual.supervisor import Attempt, AttemptResult, Snapshot, StepSpec, TaskSpec
from bimanual.workflow_step_report import build_workflow_step_report

SKILL = "cup_pick_place"
CHECKPOINT = "c" * 64


def observation(sequence, at_ns, simulation_seconds):
    capture = dict(
        sequence=sequence,
        observed_monotonic_ns=at_ns,
        simulation_seconds=simulation_seconds,
    )
    return Observation(
        episode_id="episode",
        instruction_revision=0,
        **capture,
        joint_position_rad=[0.0] * 12,
        joint_velocity_rad_s=[0.0] * 12,
        frames=[
            dict(
                camera=camera,
                **capture,
                artifact=dict(path=f"{sequence}-{index}.png", sha256="a" * 64),
            )
            for index, camera in enumerate(CAMERAS)
        ],
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(canonical(row) + b"\n" for row in rows))


@pytest.fixture
def evidence(tmp_path):
    capability = dinner_capability(SKILL)
    task = TaskSpec(
        task_id="task",
        episode_id="episode",
        instruction_revision=0,
        instruction="Place the cup",
        steps=(
            StepSpec(
                step_id=SKILL,
                capability_id=capability.capability_id,
                timeout_ns=10_000,
            ),
        ),
    )
    initial = observation(0, 80, 0.0)
    terminal = observation(1, 800, 0.05)
    attempt = Attempt(
        attempt_id="attempt-1",
        task_id=task.task_id,
        step_id=SKILL,
        number=1,
        request=capability.request("episode", 0, 0),
        observation=initial,
        started_ns=400,
        deadline_ns=10_400,
        arms=capability.execution_arms,
        shared_workspace=capability.shared_workspace,
    )
    result = AttemptResult(
        attempt=attempt,
        ended_ns=900,
        observation=terminal,
        outcome="succeeded",
        reason="Physical placement and final readiness passed",
    )
    snapshot = Snapshot(
        task=task,
        tasks=(task,),
        state="execution_complete",
        completed_steps=(SKILL,),
        active=None,
        attempts=(result,),
        events=(),
    )
    write_json(tmp_path / "final-supervisor.json", snapshot.model_dump(mode="json"))
    write_json(
        tmp_path / "execution-profile.json",
        {
            "execution_profile_sha256": "e" * 64,
            "entries": [
                {
                    "skill_id": SKILL,
                    "capability_id": capability.capability_id,
                    "checkpoint_sha256": CHECKPOINT,
                }
            ],
        },
    )
    captures = [
        ({"policy_observation": {"observed_monotonic_ns": 110}, "name": "warmup"}, 120),
        ({"policy_observation": {"observed_monotonic_ns": 130}, "name": "original"}, 140),
        ({"policy_observation": {"observed_monotonic_ns": 220}, "name": "fresh"}, 240),
    ]
    write_jsonl(
        tmp_path / "worker" / "planner-captures.jsonl",
        [
            {"capture": capture, "capture_finished_monotonic_ns": finished}
            for capture, finished in captures
        ],
    )
    job = tmp_path / "worker" / "planning" / "job-1"
    write_json(
        job / "job.json",
        {
            "job_id": "job-1",
            "boundary_kind": "ready",
            "failed_attempt_id": None,
            "created_ns": 100,
            "context": {"retry_number": 0},
            "warmup_capture": captures[0][0],
            "original_capture": captures[1][0],
        },
    )
    write_json(
        job / "model-response.json",
        {"received_ns": 200, "model_metrics": {"inference_seconds": 0.25}},
    )
    write_json(
        job / "revalidation.json",
        {"revalidated_ns": 300, "fresh_planner_capture": captures[2][0]},
    )
    write_json(
        job / "dispatch.json",
        {"attempt": attempt.model_dump(mode="json"), "at_ns": 400},
    )
    write_jsonl(
        tmp_path / "worker" / "actions.jsonl",
        [
            {
                "attempt_id": "attempt-1",
                "applied": True,
                "partial_physics": False,
                "simulation_seconds_before": 0.0,
                "simulation_seconds_after": 0.05,
            }
        ],
    )
    write_jsonl(
        tmp_path / "worker" / "skill-execution.jsonl",
        [
            {
                "attempt_id": "attempt-1",
                "event": "forecast",
                "applied_actions": 0,
                "inference_seconds": 0.01,
            },
            {
                "attempt_id": "attempt-1",
                "event": "termination_requested",
                "applied_actions": 1,
                "physical_success": True,
                "successor_ready": None,
                "final_parking_ready": True,
                "failure_code": None,
            }
        ],
    )
    return tmp_path


def test_builds_joined_per_step_outcome_and_latency(evidence):
    report = build_workflow_step_report(evidence)
    assert report.execution_complete and report.attempt_count == 1
    assert report.steps[0].status == "succeeded"
    row = report.attempts[0]
    assert row.checkpoint_sha256 == CHECKPOINT
    assert row.model_inference_seconds == 0.25
    assert row.planning_wall_seconds == pytest.approx(3e-7)
    assert row.capture_wall_seconds == pytest.approx(4e-8)
    assert row.execution_wall_seconds == pytest.approx(5e-7)
    assert row.simulated_duration_seconds == pytest.approx(0.05)
    assert row.applied_actions == row.action_rows == 1
    assert row.policy_inference_seconds == (0.01,)
    assert row.policy_inference_total_seconds == 0.01
    assert row.physical_success is True and row.final_parking_ready is True
    assert report.independent_task_success is None


def test_missing_planner_dispatch_is_rejected(evidence):
    (evidence / "worker" / "planning" / "job-1" / "dispatch.json").unlink()
    with pytest.raises(ValueError, match="requires exactly one planner dispatch"):
        build_workflow_step_report(evidence)


def test_action_count_disagreement_is_rejected(evidence):
    path = evidence / "worker" / "skill-execution.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]["applied_actions"] = 2
    write_jsonl(path, rows)
    with pytest.raises(ValueError, match="action count disagree"):
        build_workflow_step_report(evidence)


def test_regressing_planning_timestamps_are_rejected(evidence):
    path = evidence / "worker" / "planning" / "job-1" / "revalidation.json"
    row = json.loads(path.read_text())
    row["revalidated_ns"] = 150
    write_json(path, row)
    with pytest.raises(ValueError, match="out of order"):
        build_workflow_step_report(evidence)


def test_retry_without_immediate_failed_predecessor_is_rejected(evidence):
    supervisor_path = evidence / "final-supervisor.json"
    supervisor = json.loads(supervisor_path.read_text())
    supervisor["attempts"][0]["attempt"]["number"] = 2
    write_json(supervisor_path, supervisor)
    planning = evidence / "worker" / "planning" / "job-1"
    dispatch = json.loads((planning / "dispatch.json").read_text())
    dispatch["attempt"]["number"] = 2
    write_json(planning / "dispatch.json", dispatch)
    job = json.loads((planning / "job.json").read_text())
    job["context"]["retry_number"] = 1
    write_json(planning / "job.json", job)
    with pytest.raises(ValueError, match="Retry does not bind"):
        build_workflow_step_report(evidence)


def test_source_bound_learned_execution_audit(evidence, tmp_path, monkeypatch):
    import bimanual.dinner_evaluation as evaluation

    report = build_workflow_step_report(evidence)
    write_json(evidence / "step-report.json", report.model_dump(mode="json"))
    write_json(
        evidence / "worker" / "worker.json",
        {
            "teacher_schedule_used": False,
            "instrumentation": DINNER_WORKER_INSTRUMENTATION,
        },
    )
    store = EvidenceStore(tmp_path.parent / f"{tmp_path.name}-store")
    directory = store.new_run()
    shutil.copytree(evidence, directory, dirs_exist_ok=True)
    source = store.seal(
        directory,
        kind="dinner_workflow_execution",
        outcome="completed",
        config={},
        metrics={
            "execution_complete": True,
            "instrumentation": DINNER_WORKER_INSTRUMENTATION,
        },
        source={},
        claims=[],
    )
    monkeypatch.setattr(evaluation, "SKILLS", (SKILL,))
    audit = evaluation._learned_execution_audit(directory, source)
    assert audit == {
        "profile": "learned_dinner_execution_audit_v1",
        "verified": True,
        "applicable": True,
        "reasons": [],
    }
