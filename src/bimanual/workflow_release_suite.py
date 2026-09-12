"""Aggregate every frozen local workflow release case without selecting outcomes."""

from __future__ import annotations

import json
import math
from pathlib import Path

from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.worker_lease import WorkerLease
from bimanual.workflow_release_protocol import load_workflow_release_protocol
from bimanual.workflow_release_runner import KIND as CASE_KIND
from bimanual.workflow_release_runner import REQUEST, _clean_process

KIND = "local_workflow_release_suite"


def _wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _validate_wrapper(store: EvidenceStore, wrapper: Manifest, protocol, case) -> dict:
    request = wrapper.config
    if (
        wrapper.kind != CASE_KIND
        or request.get("protocol_manifest_sha256") != protocol.manifest_sha256
        or request.get("case_id") != case.case_id
        or request.get("case") != case.model_dump(mode="json")
        or wrapper.metrics.get("case_id") != case.case_id
        or wrapper.metrics.get("family") != case.family
        or wrapper.metrics.get("seed") != case.seed
        or wrapper.metrics.get("intel_validated") is not False
        or wrapper.metrics.get("release_success") is not None
    ):
        raise ValueError(f"Release case wrapper changed: {case.case_id}")
    directory = store.directory(wrapper.run_id)
    process_store = EvidenceStore(directory / "process-evidence")
    process = process_store.verify(wrapper.metrics.get("process_run_id"))
    if process.manifest_sha256 != wrapper.metrics.get(
        "process_manifest_sha256"
    ) or process.outcome != wrapper.metrics.get("process_outcome"):
        raise ValueError(f"Release process binding changed: {case.case_id}")
    child = None
    child_id = wrapper.metrics.get("child_run_id")
    if child_id is not None:
        child_store = EvidenceStore(process_store.directory(process.run_id) / "child-evidence")
        child = child_store.verify(child_id)
        if child.manifest_sha256 != wrapper.metrics.get("child_manifest_sha256"):
            raise ValueError(f"Release child binding changed: {case.case_id}")
    clean = bool(child is not None and _clean_process(process, child, request["process"]))
    if clean != wrapper.metrics.get("process_transport_clean"):
        raise ValueError(f"Release process integrity changed: {case.case_id}")
    evaluation = None
    evaluation_id = wrapper.metrics.get("evaluation_run_id")
    evaluation_store = EvidenceStore(directory / "evaluation-evidence")
    if child is not None:
        copied = evaluation_store.verify(child.run_id)
        if copied != child:
            raise ValueError(f"Scoring copy changed: {case.case_id}")
    if evaluation_id is not None:
        evaluation = evaluation_store.verify(evaluation_id)
        if (
            evaluation.manifest_sha256 != wrapper.metrics.get("evaluation_manifest_sha256")
            or evaluation.outcome != wrapper.metrics.get("evaluation_outcome")
            or evaluation.kind != "dinner_evaluation"
            or evaluation.config.get("source_run") != child_id
        ):
            raise ValueError(f"Independent evaluation binding changed: {case.case_id}")
    if (evaluation is not None) != clean:
        raise ValueError(f"Independent evaluation availability changed: {case.case_id}")
    success = bool(
        clean
        and evaluation is not None
        and evaluation.outcome == "completed"
        and evaluation.metrics.get("score", {}).get("independent_task_success") is True
    )
    if (
        success != wrapper.metrics.get("independent_task_success")
        or (wrapper.outcome == "completed") != success
        or wrapper.claims
        != (
            ["One frozen local scene passed independent dinner scoring; Intel not evaluated"]
            if success
            else []
        )
    ):
        raise ValueError(f"Release case outcome changed: {case.case_id}")
    return {
        "case_id": case.case_id,
        "family": case.family,
        "seed": case.seed,
        "wrapper_run_id": wrapper.run_id,
        "wrapper_manifest_sha256": wrapper.manifest_sha256,
        "process_outcome": process.outcome,
        "execution_complete": wrapper.metrics.get("execution_complete") is True,
        "process_transport_clean": clean,
        "evaluation_outcome": evaluation.outcome if evaluation is not None else None,
        "independent_task_success": success,
    }


def _discover(store: EvidenceStore, protocol) -> dict[str, Manifest]:
    found: dict[str, list[Manifest]] = {case.case_id: [] for case in protocol.cases}
    for request_path in (store.root / "runs").glob(f"*/{REQUEST}"):
        try:
            request = json.loads(request_path.read_text())
        except (OSError, ValueError):
            continue
        if request.get("protocol_manifest_sha256") != protocol.manifest_sha256:
            continue
        case_id = request.get("case_id")
        if case_id not in found:
            raise ValueError("Release case references an unknown frozen case")
        if not (request_path.parent / "manifest.json").is_file():
            raise RuntimeError(f"Interrupted frozen release case requires adjudication: {case_id}")
        found[case_id].append(store.verify(request_path.parent.name))
    missing = [case_id for case_id, matches in found.items() if not matches]
    repeated = [case_id for case_id, matches in found.items() if len(matches) > 1]
    if missing:
        raise RuntimeError("Frozen release cases are missing: " + ", ".join(missing))
    if repeated:
        raise RuntimeError("Frozen release cases are duplicated: " + ", ".join(repeated))
    return {case_id: matches[0] for case_id, matches in found.items()}


def _rows(store: EvidenceStore, protocol) -> list[dict]:
    wrappers = _discover(store, protocol)
    return [
        _validate_wrapper(store, wrappers[case.case_id], protocol, case) for case in protocol.cases
    ]


def _metrics(rows: list[dict]) -> dict:
    successes = sum(row["independent_task_success"] for row in rows)
    diagnostics = [row for row in rows if row["family"] != "combined"]
    combined = [row for row in rows if row["family"] == "combined"]

    def group(group_rows: list[dict]) -> dict:
        passed = sum(row["independent_task_success"] for row in group_rows)
        return {
            "case_count": len(group_rows),
            "successful_cases": passed,
            "failed_cases": len(group_rows) - passed,
            "success_rate": passed / len(group_rows),
            "success_rate_wilson95": _wilson(passed, len(group_rows)),
            "all_passed": passed == len(group_rows),
        }

    if len(diagnostics) != 6 or len(combined) != 10:
        raise ValueError("Release result table must contain six diagnostics and ten test seeds")
    return {
        "case_count": len(rows),
        "successful_cases": successes,
        "failed_cases": len(rows) - successes,
        "success_rate": successes / len(rows),
        "success_rate_wilson95": _wilson(successes, len(rows)),
        "one_factor_diagnostics": group(diagnostics),
        "combined_test_seeds": group(combined),
        "hackathon_10_seed_target_met": all(row["independent_task_success"] for row in combined),
        "local_prequalification_passed": successes == len(rows),
        "intel_validated": False,
        "release_success": None,
        "cases": rows,
    }


def _reverify_protocol(path: Path, file_sha256: str, manifest_sha256: str) -> None:
    if (
        digest_file(path) != file_sha256
        or load_workflow_release_protocol(path).manifest_sha256 != manifest_sha256
    ):
        raise ValueError("Frozen workflow release protocol changed during aggregation")


def create_workflow_release_suite(
    protocol_path: Path,
    *,
    store: EvidenceStore,
    project_root: Path,
) -> Manifest:
    """Seal the ordered sixteen-case local result table once all attempts exist."""
    protocol_path = Path(protocol_path).resolve(strict=True)
    project_root = Path(project_root).resolve()
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_workflow_release_protocol(protocol_path)
    config = {
        "protocol_path": str(protocol_path),
        "protocol_file_sha256": protocol_file_sha256,
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "selection_rule": protocol.selection_rule,
    }
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".workflow-release-coordinator.lock"):
        existing = []
        for path in (store.root / "runs").glob("*/manifest.json"):
            try:
                with path.open() as stream:
                    header = stream.read(131072)
            except OSError:
                continue
            if KIND not in header or protocol.manifest_sha256 not in header:
                continue
            candidate = store.verify(path.parent.name)
            if (
                candidate.kind == KIND
                and candidate.config.get("protocol_manifest_sha256") == protocol.manifest_sha256
            ):
                existing.append(candidate)
        if len(existing) > 1:
            raise RuntimeError("Multiple aggregate reports exist for one frozen release protocol")
        if existing:
            if existing[0].config != config:
                raise ValueError("Existing release suite contradicts the frozen protocol")
            rows = _rows(store, protocol)
            expected_metrics = _metrics(rows)
            local_passed = expected_metrics["local_prequalification_passed"]
            expected_claims = (
                ["All frozen local scenes passed independent dinner scoring; Intel not evaluated"]
                if local_passed
                else []
            )
            if (
                existing[0].metrics != expected_metrics
                or existing[0].outcome != ("completed" if local_passed else "failed")
                or existing[0].claims != expected_claims
            ):
                raise ValueError("Existing release suite no longer matches its source cases")
            _reverify_protocol(protocol_path, protocol_file_sha256, protocol.manifest_sha256)
            return existing[0]
        rows = _rows(store, protocol)
        _reverify_protocol(protocol_path, protocol_file_sha256, protocol.manifest_sha256)
        metrics = _metrics(rows)
        local_passed = metrics["local_prequalification_passed"]
        directory = store.new_run()
        (directory / "protocol.json").write_bytes(protocol_path.read_bytes())
        (directory / "result.json").write_bytes(canonical(metrics) + b"\n")
        return store.seal(
            directory,
            kind=KIND,
            outcome="completed" if local_passed else "failed",
            config=config,
            metrics=metrics,
            source=provenance(project_root),
            claims=(
                ["All frozen local scenes passed independent dinner scoring; Intel not evaluated"]
                if local_passed
                else []
            ),
        )
