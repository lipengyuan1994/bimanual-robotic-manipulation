"""Execute one frozen local workflow release case exactly once."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bimanual.dinner_evaluation import evaluate_dinner_run
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.worker_lease import WorkerLease
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process
from bimanual.workflow_release_protocol import load_workflow_release_protocol

KIND = "local_workflow_release_case"
REQUEST = "release-case-request.json"


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


def _existing(store: EvidenceStore, request: dict) -> Manifest | None:
    matches: list[Path] = []
    identity = (request["protocol_manifest_sha256"], request["case_id"])
    for path in (store.root / "runs").glob(f"*/{REQUEST}"):
        try:
            recorded = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (
            recorded.get("protocol_manifest_sha256"),
            recorded.get("case_id"),
        ) != identity:
            continue
        if recorded != request:
            raise ValueError("Existing release case contradicts the frozen request")
        matches.append(path.parent)
    if len(matches) > 1:
        raise RuntimeError("Ambiguous repeated attempts for one frozen release case")
    if not matches:
        return None
    if not (matches[0] / "manifest.json").is_file():
        raise RuntimeError(
            "Interrupted release case requires manual adjudication; no automatic retry"
        )
    result = store.verify(matches[0].name)
    if result.kind != KIND or result.config != request:
        raise ValueError("Existing release case wrapper is invalid")
    return result


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
    process_config = WorkflowProcessConfig(execution=execution)
    request = {
        "protocol_path": str(protocol_path),
        "protocol_file_sha256": protocol_file_sha256,
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case_id": case.case_id,
        "case": case.model_dump(mode="json"),
        "process": process_config.model_dump(mode="json"),
        "selection_rule": protocol.selection_rule,
    }
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".workflow-release-coordinator.lock"):
        prior = _existing(store, request)
        if prior is not None:
            return prior
        directory = store.new_run()
        (directory / REQUEST).write_bytes(canonical(request) + b"\n")

        process_store = EvidenceStore(directory / "process-evidence")
        process = run_workflow_process(
            process_config,
            store=process_store,
            project_root=project_root,
        )
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
            and evaluation.kind == "dinner_evaluation"
            and evaluation.outcome == "completed"
            and evaluation.metrics.get("score", {}).get("independent_task_success") is True
        )
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
