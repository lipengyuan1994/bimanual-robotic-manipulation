"""Execute one frozen local workflow release case exactly once."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

from bimanual.dinner_evaluation import _trace_layout, evaluate_dinner_run
from bimanual.dinner_outcomes import PROFILE as DINNER_SCORE_PROFILE
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process
from bimanual.workflow_release_protocol import load_workflow_release_protocol
from bimanual.workflow_step_report import WorkflowStepReport

KIND = "local_workflow_release_case"
REQUEST = "release-case-request.json"
RESERVATION_PREFIX = "release-case-"


def _reservation_name(protocol_manifest_sha256: str, case_id: str) -> str:
    identity = hashlib.sha256(canonical([protocol_manifest_sha256, case_id])).hexdigest()[:24]
    return RESERVATION_PREFIX + identity


def build_release_case_request(protocol_path: Path, protocol, case) -> dict:
    """Reconstruct the one canonical process request from frozen protocol inputs."""
    protocol_path = Path(protocol_path).resolve(strict=True)
    suite_root = (protocol_path.parent / protocol.scene_suite_run).resolve(strict=True)
    scene_root = suite_root.parent.parent / "runs" / case.run_id
    execution = WorkflowExecutionConfig(
        workflow_manifest=(protocol_path.parent / protocol.workflow_manifest).resolve(strict=True),
        planner_model_directory=(protocol_path.parent / protocol.planner_model_root).resolve(
            strict=True
        ),
        scene_variant_run=scene_root.resolve(strict=True),
        instruction=protocol.instruction,
        policy_device=protocol.policy_device,
        planner_device=protocol.planner_device,
        camera_profile=protocol.camera_profile,
        wall_timeout_seconds=protocol.wall_timeout_seconds,
        step_timeout_seconds=protocol.step_timeout_seconds,
        max_tokens=protocol.max_tokens,
    )
    process = WorkflowProcessConfig(execution=execution)
    return {
        "protocol_path": str(protocol_path),
        "protocol_file_sha256": digest_file(protocol_path),
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case_id": case.case_id,
        "case": case.model_dump(mode="json"),
        "process": process.model_dump(mode="json"),
        "selection_rule": protocol.selection_rule,
    }


def _clean_process(process: Manifest, child: Manifest, expected: dict) -> bool:
    return (
        process.kind == "dinner_workflow_process"
        and process.config == expected
        and process.metrics.get("child_manifest_verified") is True
        and process.metrics.get("child_run_id") == child.run_id
        and process.metrics.get("child_manifest_sha256") == child.manifest_sha256
        and process.metrics.get("child_outcome") == child.outcome
        and process.metrics.get("child_reaped") is True
        and process.metrics.get("child_exitcode") == 0
        and process.metrics.get("guardian_terminal_verified") is True
        and process.metrics.get("guardian_reaped") is True
        and process.metrics.get("guardian_exitcode") == 0
        and process.metrics.get("forced_interruption") is False
    )


def expected_evaluation_config(child: Manifest) -> dict:
    return {
        "source_run": child.run_id,
        "source_manifest_sha256": child.manifest_sha256,
        "profile": DINNER_SCORE_PROFILE,
        "selected_trace_layout": _trace_layout(child.kind),
        "instrumentation": child.metrics.get("instrumentation", {}),
        "instrumentation_scope": child.metrics.get(
            "instrumentation_evidence", "Source declaration provenance unspecified"
        ),
        "instrumentation_run": None,
        "instrumentation_manifest_sha256": None,
    }


def evaluation_is_independent_success(evaluation: Manifest, child: Manifest) -> bool:
    diagnostics = evaluation.metrics.get("full_trace_diagnostics", {})
    audit = evaluation.metrics.get("learned_execution_audit", {})
    return bool(
        evaluation.config == expected_evaluation_config(child)
        and evaluation.kind == "dinner_evaluation"
        and evaluation.outcome == "completed"
        and evaluation.metrics.get("source_outcome") == child.outcome
        and evaluation.metrics.get("source_kind") == child.kind
        and evaluation.metrics.get("selected_trace_layout") == _trace_layout(child.kind)
        and evaluation.metrics.get("scene_binding_verified") is True
        and evaluation.metrics.get("learned_execution_verified") is True
        and audit.get("profile") == "learned_dinner_execution_audit_v1"
        and audit.get("verified") is True
        and audit.get("applicable") is True
        and diagnostics.get("errors") == []
        and diagnostics.get("forbidden_samples") == 0
        and evaluation.metrics.get("score", {}).get("independent_task_success") is True
        and evaluation.claims
        == [
            "Physical scoring of retained evidence; no new execution, generalization "
            "or learned-policy certification"
        ]
    )


def _existing(store: EvidenceStore, request: dict) -> Manifest | None:
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    if not directory.exists():
        return None
    request_path = directory / REQUEST
    try:
        recorded = json.loads(request_path.read_bytes())
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "Interrupted release case requires manual adjudication; reservation is incomplete"
        ) from error
    if recorded != request:
        raise ValueError("Existing release case contradicts the frozen request")
    if not (directory / "manifest.json").is_file():
        raise RuntimeError(
            "Interrupted release case requires manual adjudication; no automatic retry"
        )
    result = store.verify(directory.name)
    if result.kind != KIND or result.config != request:
        raise ValueError("Existing release case wrapper is invalid")
    return result


def _reserve(store: EvidenceStore, request: dict) -> Path:
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    request_path = directory / REQUEST
    with request_path.open("xb") as stream:
        stream.write(canonical(request) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return directory


def _execution_evidence(child: Manifest | None, evaluation: Manifest | None, root: Path) -> dict:
    report = None
    report_error = None
    if child is not None:
        if "step-report.json" not in child.files:
            report_error = "sealed workflow child has no step-report.json"
        else:
            try:
                report = WorkflowStepReport.model_validate_json(
                    (root / child.run_id / "step-report.json").read_bytes()
                )
            except (OSError, ValueError) as error:
                report_error = f"{type(error).__name__}: {error}"
    attempts = tuple(report.attempts) if report is not None else ()
    failure_codes = Counter(row.failure_code for row in attempts if row.failure_code)
    terminal_reasons = [
        {"step_id": row.step_id, "outcome": row.outcome, "reason": row.reason}
        for row in attempts
        if row.outcome != "succeeded"
    ]
    score = evaluation.metrics.get("score", {}) if evaluation is not None else {}
    diagnostics = (
        evaluation.metrics.get("full_trace_diagnostics", {}) if evaluation is not None else {}
    )
    learned_verified = (
        evaluation.metrics.get("learned_execution_verified") is True
        if evaluation is not None
        else False
    )
    return {
        "step_report_available": report is not None,
        "step_report_error": report_error,
        "workflow_state": report.workflow_state if report is not None else None,
        "attempt_count": report.attempt_count if report is not None else 0,
        "retry_count": (
            sum(max(0, step.attempt_count - 1) for step in report.steps)
            if report is not None
            else 0
        ),
        "successful_attempts": report.successful_attempts if report is not None else 0,
        "failed_attempts": report.failed_attempts if report is not None else 0,
        "failure_codes": dict(sorted(failure_codes.items())),
        "terminal_reasons": terminal_reasons,
        "applied_actions": sum(row.applied_actions for row in attempts),
        "rejected_actions": sum(row.rejected_actions for row in attempts),
        "partial_actions": sum(row.partial_physics_actions for row in attempts),
        "planning_wall_seconds": sum(row.planning_wall_seconds for row in attempts),
        "planner_inference_seconds": sum(row.model_inference_seconds for row in attempts),
        "policy_inference_seconds": sum(row.policy_inference_total_seconds for row in attempts),
        "execution_wall_seconds": sum(row.execution_wall_seconds for row in attempts),
        "simulated_duration_seconds": sum(row.simulated_duration_seconds for row in attempts),
        "failed_gates": score.get("failed_gates", []),
        "forbidden_contact_samples": diagnostics.get("forbidden_samples", 0),
        "diagnostic_partial_actions": diagnostics.get("partial_actions", 0),
        "diagnostic_errors": diagnostics.get("errors", []),
        "scene_binding_verified": (
            evaluation.metrics.get("scene_binding_verified") is True
            if evaluation is not None
            else False
        ),
        "learned_execution_verified": learned_verified,
        "zero_intervention_verified": learned_verified,
        "operator_interventions": 0 if learned_verified else None,
    }


def _copy_child_for_scoring(
    process_store: EvidenceStore,
    process: Manifest,
    evaluation_store: EvidenceStore,
) -> tuple[Manifest, Path]:
    child_id = process.metrics.get("child_run_id")
    if not isinstance(child_id, str):
        raise ValueError("Workflow process did not preserve a child execution")
    child_store = EvidenceStore(process_store.directory(process.run_id) / "child-evidence")
    child = child_store.verify(child_id)
    destination = evaluation_store.directory(child_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(child_store.directory(child_id), destination)
    copied = evaluation_store.verify(child_id)
    if copied != child:
        raise ValueError("Copied workflow execution differs from the process child")
    return child, destination


def run_workflow_release_case(
    protocol_path: Path,
    case_id: str,
    *,
    store: EvidenceStore,
    project_root: Path,
) -> Manifest:
    """Run and score one declared scene once, preserving failures and interruptions."""
    protocol_path = Path(protocol_path).resolve(strict=True)
    project_root = Path(project_root).resolve()
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_workflow_release_protocol(protocol_path)
    selected = [case for case in protocol.cases if case.case_id == case_id]
    if len(selected) != 1:
        raise ValueError("Case id is not a member of the frozen release protocol")
    case = selected[0]
    request = build_release_case_request(protocol_path, protocol, case)
    process_config = WorkflowProcessConfig.model_validate(request["process"])
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".workflow-release-coordinator.lock"):
        prior = _existing(store, request)
        if prior is not None:
            return prior
        shared_lease = WorkerLease.acquire(store.root / MODEL_JOB_LEASE)
        try:
            directory = _reserve(store, request)
        except BaseException:
            shared_lease.close()
            raise

        process_store = EvidenceStore(directory / "process-evidence")
        try:
            process = run_workflow_process(
                process_config,
                store=process_store,
                project_root=project_root,
                model_job_lease_path=store.root / MODEL_JOB_LEASE,
                model_job_lease=shared_lease,
            )
        except BaseException:
            shared_lease.close()
            raise
        process = process_store.verify(process.run_id)
        evaluation_store = EvidenceStore(directory / "evaluation-evidence")
        evaluation = None
        child = None
        process_clean = False
        if isinstance(process.metrics.get("child_run_id"), str):
            child, _ = _copy_child_for_scoring(process_store, process, evaluation_store)
            process_clean = _clean_process(process, child, process_config.model_dump(mode="json"))
            if process_clean:
                evaluation = evaluate_dinner_run(
                    child.run_id,
                    store=evaluation_store,
                    project_root=project_root,
                )
                evaluation = evaluation_store.verify(evaluation.run_id)

        if (
            digest_file(protocol_path) != protocol_file_sha256
            or load_workflow_release_protocol(protocol_path).manifest_sha256
            != protocol.manifest_sha256
        ):
            raise ValueError("Frozen workflow release protocol changed during execution")
        independent_success = bool(
            process_clean
            and evaluation is not None
            and child is not None
            and evaluation_is_independent_success(evaluation, child)
        )
        execution_evidence = _execution_evidence(child, evaluation, evaluation_store.root / "runs")
        metrics = {
            "case_id": case.case_id,
            "family": case.family,
            "seed": case.seed,
            "process_run_id": process.run_id,
            "process_manifest_sha256": process.manifest_sha256,
            "process_outcome": process.outcome,
            "process_transport_clean": process_clean,
            "execution_complete": process.metrics.get("execution_complete") is True,
            "child_run_id": child.run_id if child is not None else None,
            "child_manifest_sha256": child.manifest_sha256 if child is not None else None,
            "evaluation_run_id": evaluation.run_id if evaluation is not None else None,
            "evaluation_manifest_sha256": (
                evaluation.manifest_sha256 if evaluation is not None else None
            ),
            "evaluation_outcome": evaluation.outcome if evaluation is not None else None,
            "independent_task_success": independent_success,
            "execution_evidence": execution_evidence,
            "release_success": None,
            "intel_validated": False,
        }
        (directory / "result.json").write_bytes(canonical(metrics) + b"\n")
        return store.seal(
            directory,
            kind=KIND,
            outcome="completed" if independent_success else "failed",
            config=request,
            metrics=metrics,
            source=provenance(project_root),
            claims=(
                ["One frozen local scene passed independent dinner scoring; Intel not evaluated"]
                if independent_success
                else []
            ),
        )
