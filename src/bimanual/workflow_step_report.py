"""Fail-closed per-attempt timing and outcome evidence for dinner workflows."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, TypeAdapter

from bimanual.contracts import Contract, Counter, Digest, Identifier
from bimanual.evidence import canonical
from bimanual.supervisor import Snapshot


class WorkflowStepAttempt(Contract):
    attempt_id: Identifier
    task_id: Identifier
    step_id: Identifier
    attempt_number: int = Field(strict=True, ge=1, le=3)
    capability_id: Identifier
    checkpoint_sha256: Digest
    planner_job_id: Identifier
    planning_boundary: Literal["ready", "recovery"]
    failed_attempt_id: Identifier | None = None
    planning_started_ns: Counter
    model_response_received_ns: Counter
    revalidated_ns: Counter
    dispatched_ns: Counter
    planning_wall_seconds: float = Field(ge=0)
    model_inference_seconds: float = Field(ge=0)
    revalidation_wall_seconds: float = Field(ge=0)
    capture_wall_seconds: float = Field(ge=0)
    execution_started_ns: Counter
    execution_ended_ns: Counter
    execution_wall_seconds: float = Field(ge=0)
    total_step_wall_seconds: float = Field(ge=0)
    simulation_seconds_before: float = Field(ge=0)
    simulation_seconds_after: float = Field(ge=0)
    simulated_duration_seconds: float = Field(ge=0)
    action_rows: int = Field(strict=True, ge=0)
    applied_actions: int = Field(strict=True, ge=0)
    rejected_actions: int = Field(strict=True, ge=0)
    partial_physics_actions: int = Field(strict=True, ge=0)
    policy_inference_seconds: tuple[float, ...]
    policy_inference_total_seconds: float = Field(ge=0)
    outcome: Literal[
        "succeeded", "failed", "unreachable", "timed_out", "cancelled", "queue_clear_failed"
    ]
    reason: str
    failure_code: str | None = None
    physical_success: bool | None = None
    successor_ready: bool | None = None
    final_parking_ready: bool | None = None


class WorkflowStepStatus(Contract):
    ordinal: int = Field(strict=True, ge=0)
    step_id: Identifier
    capability_id: Identifier
    status: Literal[
        "succeeded",
        "failed",
        "unreachable",
        "timed_out",
        "cancelled",
        "queue_clear_failed",
        "not_attempted",
    ]
    attempt_count: int = Field(strict=True, ge=0, le=3)
    terminal_attempt_id: Identifier | None = None


class WorkflowStepReport(Contract):
    schema_version: int = 1
    profile: str = "dinner_workflow_step_report_v1"
    task_id: Identifier | None = None
    workflow_state: str
    execution_complete: bool
    attempt_count: int = Field(strict=True, ge=0)
    successful_attempts: int = Field(strict=True, ge=0)
    failed_attempts: int = Field(strict=True, ge=0)
    total_applied_actions: int = Field(strict=True, ge=0)
    steps: tuple[WorkflowStepStatus, ...]
    attempts: tuple[WorkflowStepAttempt, ...]
    independent_task_success: None = None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    canonical(value)
    return value


def _read_jsonl(path: Path, *, optional: bool = False) -> list[dict[str, Any]]:
    if optional and not path.exists():
        return []
    rows = []
    for index, line in enumerate(path.read_bytes().splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path.name}:{index}")
        canonical(value)
        rows.append(value)
    return rows


def _seconds(later: int, earlier: int, label: str) -> float:
    if type(later) is not int or type(earlier) is not int or later < earlier:
        raise ValueError(f"Invalid or regressing {label} timestamps")
    return (later - earlier) / 1_000_000_000


def _finite_seconds(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Missing numeric {label}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"Invalid {label}")
    return result


def _capture_digest(capture: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(capture)).hexdigest()


def build_workflow_step_report(directory: Path) -> WorkflowStepReport:
    """Join sealed raw artifacts one-to-one; ambiguity or missing evidence is fatal."""
    directory = Path(directory)
    snapshot = Snapshot.model_validate(_read_json(directory / "final-supervisor.json"))
    profile = _read_json(directory / "execution-profile.json")
    entries = profile.get("entries")
    if not isinstance(entries, list) or any(not isinstance(row, dict) for row in entries):
        raise ValueError("Execution profile entries are missing or malformed")
    checkpoints: dict[str, str] = {}
    capabilities: dict[str, str] = {}
    for row in entries:
        skill = row.get("skill_id")
        if not isinstance(skill, str) or skill in checkpoints:
            raise ValueError("Execution profile skill identities must be unique")
        checkpoints[skill] = TypeAdapter(Digest).validate_python(row.get("checkpoint_sha256"))
        capabilities[skill] = TypeAdapter(Identifier).validate_python(row.get("capability_id"))

    action_rows = _read_jsonl(directory / "worker" / "actions.jsonl", optional=True)
    skill_rows = _read_jsonl(directory / "worker" / "skill-execution.jsonl", optional=True)
    capture_rows = _read_jsonl(directory / "worker" / "planner-captures.jsonl", optional=True)
    capture_seconds: dict[str, float] = {}
    for row in capture_rows:
        capture = row.get("capture")
        if not isinstance(capture, dict):
            raise ValueError("Planner capture row lacks its capture declaration")
        start = capture.get("policy_observation", {}).get("observed_monotonic_ns")
        duration = _seconds(row.get("capture_finished_monotonic_ns"), start, "capture")
        digest = _capture_digest(capture)
        if digest in capture_seconds:
            raise ValueError("Duplicate planner capture declaration")
        capture_seconds[digest] = duration

    planning: dict[str, tuple[dict, dict, dict, dict]] = {}
    planning_root = directory / "worker" / "planning"
    if planning_root.exists():
        for job_dir in sorted(path for path in planning_root.iterdir() if path.is_dir()):
            dispatch_path = job_dir / "dispatch.json"
            if not dispatch_path.exists():
                continue
            job = _read_json(job_dir / "job.json")
            response = _read_json(job_dir / "model-response.json")
            revalidation = _read_json(job_dir / "revalidation.json")
            dispatch = _read_json(dispatch_path)
            attempt = dispatch.get("attempt")
            if attempt is None:
                continue
            if not isinstance(attempt, dict) or attempt.get("attempt_id") in planning:
                raise ValueError("Planner dispatch attempt identity is missing or duplicated")
            planning[attempt["attempt_id"]] = (job, response, revalidation, dispatch)

    terminal_skill_events = {
        "termination_requested",
        "error",
        "revoked",
    }
    result_rows = []
    prior_by_step: dict[str, dict[str, Any]] = {}
    for result in snapshot.attempts:
        attempt = result.attempt
        if attempt.attempt_id not in planning:
            raise ValueError("Every supervisor attempt requires exactly one planner dispatch")
        job, response, revalidation, dispatch = planning.pop(attempt.attempt_id)
        if dispatch.get("attempt") != attempt.model_dump(mode="json"):
            raise ValueError("Planner dispatch disagrees with the canonical supervisor attempt")
        skill = attempt.step_id
        if skill not in checkpoints:
            raise ValueError("Attempt step is absent from the execution profile")
        task_step = next(
            (step for step in snapshot.task.steps if step.step_id == attempt.step_id), None
        )
        if task_step is None or task_step.capability_id != capabilities.get(skill):
            raise ValueError("Attempt capability disagrees with the execution profile")
        previous = prior_by_step.get(skill)
        if attempt.number == 1:
            if job.get("boundary_kind") != "ready" or job.get("failed_attempt_id") is not None:
                raise ValueError("First attempt must originate at a ready planning boundary")
        else:
            if (
                previous is None
                or previous["attempt_id"] != job.get("failed_attempt_id")
                or previous["attempt_number"] != attempt.number - 1
                or previous["outcome"] not in {"failed", "timed_out"}
                or job.get("boundary_kind") != "recovery"
            ):
                raise ValueError("Retry does not bind its immediately preceding failed attempt")
        if job.get("context", {}).get("retry_number") != attempt.number - 1:
            raise ValueError("Planner retry number disagrees with supervisor attempt number")

        metrics = response.get("model_metrics")
        if not isinstance(metrics, dict):
            raise ValueError("Actionable planner response lacks model metrics")
        inference_seconds = _finite_seconds(
            metrics.get("inference_seconds"), "model inference time"
        )
        created_ns = job.get("created_ns")
        received_ns = response.get("received_ns")
        revalidated_ns = revalidation.get("revalidated_ns")
        dispatched_ns = dispatch.get("at_ns")
        if not created_ns <= received_ns <= revalidated_ns <= dispatched_ns:
            raise ValueError("Planning lifecycle timestamps are out of order")
        captures = (
            job.get("warmup_capture"),
            job.get("original_capture"),
            revalidation.get("fresh_planner_capture"),
        )
        if any(not isinstance(capture, dict) for capture in captures):
            raise ValueError("Planning lifecycle is missing a declared capture")
        try:
            capture_wall = sum(capture_seconds[_capture_digest(capture)] for capture in captures)
        except KeyError as error:
            raise ValueError(
                "Planning capture lacks matching append-only timing evidence"
            ) from error

        actions = [row for row in action_rows if row.get("attempt_id") == attempt.attempt_id]
        applied = sum(row.get("applied") is True for row in actions)
        rejected = sum(row.get("applied") is not True for row in actions)
        partial = sum(row.get("partial_physics") is True for row in actions)
        terminal = [
            row
            for row in skill_rows
            if row.get("attempt_id") == attempt.attempt_id
            and row.get("event") in terminal_skill_events
        ]
        if len(terminal) > 1:
            raise ValueError("Attempt has ambiguous terminal skill evidence")
        detail = terminal[0] if terminal else {}
        if detail and detail.get("applied_actions") != applied:
            raise ValueError("Skill result and physical action count disagree")
        inference_samples = tuple(
            _finite_seconds(row.get("inference_seconds"), "policy inference time")
            for row in skill_rows
            if row.get("attempt_id") == attempt.attempt_id and row.get("event") == "forecast"
        )
        before = attempt.observation.simulation_seconds
        after = result.observation.simulation_seconds if result.observation is not None else before
        if after < before:
            raise ValueError("Attempt simulation time regressed")
        row = WorkflowStepAttempt(
            attempt_id=attempt.attempt_id,
            task_id=attempt.task_id,
            step_id=skill,
            attempt_number=attempt.number,
            capability_id=task_step.capability_id,
            checkpoint_sha256=checkpoints[skill],
            planner_job_id=job["job_id"],
            planning_boundary=job["boundary_kind"],
            failed_attempt_id=job.get("failed_attempt_id"),
            planning_started_ns=created_ns,
            model_response_received_ns=received_ns,
            revalidated_ns=revalidated_ns,
            dispatched_ns=dispatched_ns,
            planning_wall_seconds=_seconds(dispatched_ns, created_ns, "planning"),
            model_inference_seconds=inference_seconds,
            revalidation_wall_seconds=_seconds(dispatched_ns, received_ns, "revalidation"),
            capture_wall_seconds=capture_wall,
            execution_started_ns=attempt.started_ns,
            execution_ended_ns=result.ended_ns,
            execution_wall_seconds=_seconds(result.ended_ns, attempt.started_ns, "execution"),
            total_step_wall_seconds=_seconds(result.ended_ns, created_ns, "total step"),
            simulation_seconds_before=before,
            simulation_seconds_after=after,
            simulated_duration_seconds=after - before,
            action_rows=len(actions),
            applied_actions=applied,
            rejected_actions=rejected,
            partial_physics_actions=partial,
            policy_inference_seconds=inference_samples,
            policy_inference_total_seconds=sum(inference_samples),
            outcome=result.outcome,
            reason=result.reason,
            failure_code=detail.get("failure_code"),
            physical_success=detail.get("physical_success"),
            successor_ready=detail.get("successor_ready"),
            final_parking_ready=detail.get("final_parking_ready"),
        )
        serialized = row.model_dump(mode="json")
        prior_by_step[skill] = serialized
        result_rows.append(row)
    if planning:
        raise ValueError("Planner dispatch exists without a canonical supervisor attempt")
    known_attempts = {row.attempt_id for row in result_rows}
    if any(row.get("attempt_id") not in known_attempts for row in action_rows + skill_rows):
        raise ValueError("Worker evidence exists without a canonical supervisor attempt")
    execution_complete = snapshot.state == "execution_complete"
    if execution_complete and (
        snapshot.active is not None
        or len(snapshot.completed_steps) != len(snapshot.task.steps)
        or any(row.outcome != "succeeded" for row in result_rows)
    ):
        raise ValueError("Execution-complete state contradicts attempt evidence")
    step_rows = []
    task_steps = snapshot.task.steps if snapshot.task else ()
    for ordinal, step in enumerate(task_steps):
        attempts = [row for row in result_rows if row.step_id == step.step_id]
        if step.step_id in snapshot.completed_steps:
            if not attempts or attempts[-1].outcome != "succeeded":
                raise ValueError("Completed step lacks a terminal successful attempt")
            status = "succeeded"
        elif attempts:
            status = attempts[-1].outcome
        else:
            status = "not_attempted"
        step_rows.append(
            WorkflowStepStatus(
                ordinal=ordinal,
                step_id=step.step_id,
                capability_id=step.capability_id,
                status=status,
                attempt_count=len(attempts),
                terminal_attempt_id=attempts[-1].attempt_id if attempts else None,
            )
        )
    return WorkflowStepReport(
        task_id=snapshot.task.task_id if snapshot.task else None,
        workflow_state=snapshot.state,
        execution_complete=execution_complete,
        attempt_count=len(result_rows),
        successful_attempts=sum(row.outcome == "succeeded" for row in result_rows),
        failed_attempts=sum(row.outcome != "succeeded" for row in result_rows),
        total_applied_actions=sum(row.applied_actions for row in result_rows),
        steps=tuple(step_rows),
        attempts=tuple(result_rows),
    )
