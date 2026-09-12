#!/usr/bin/env python3
"""Replay sandbox-blocked physical cases once on a verified local MPS process.

This is deliberately separate from the frozen suite's evidence root.  It never
rewrites or hides the original sealed failures: it accepts only clean,
zero-autonomous-action MPS-preflight failures and records a distinct replacement
suite bound to them.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

from bimanual.evidence import EvidenceStore, canonical, digest_file, provenance
from bimanual.skill_physical_evaluation import SkillPhysicalEvaluationConfig
from bimanual.skill_physical_process import (
    PROCESS_KIND,
    SkillPhysicalProcessConfig,
    run_skill_physical_process,
)
from bimanual.skill_physical_protocol import load_skill_physical_protocol
from bimanual.skill_physical_protocol_runner import KIND as EVALUATION_KIND

MPS_PREFLIGHT_ERROR = "RuntimeError: MPS unavailable or CPU fallback enabled"
REPLAY_KIND = "mps_physical_preflight_replay"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("--failed-suite", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    return parser.parse_args()


def _probe_mps() -> dict[str, object]:
    if platform.machine() != "arm64":
        raise RuntimeError("Replay requires the native Apple Silicon runtime")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0":
        raise RuntimeError("Replay requires PYTORCH_ENABLE_MPS_FALLBACK=0")
    import torch

    if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
        raise RuntimeError("Replay requires live native MPS availability")
    return {
        "python": sys.executable,
        "machine": platform.machine(),
        "torch": importlib.metadata.version("torch"),
        "mps_built": True,
        "mps_available": True,
        "mps_device_count": torch.mps.device_count(),
    }


def _load_originals(protocol_path: Path, suite_id: str) -> tuple[object, object, EvidenceStore]:
    protocol_path = protocol_path.resolve(strict=True)
    protocol = load_skill_physical_protocol(protocol_path)
    cohort_path = (protocol_path.parent / protocol.training_cohort_path).resolve(strict=True)
    from bimanual.training_cohort import load_training_cohort_protocol

    cohort = load_training_cohort_protocol(cohort_path)
    store = EvidenceStore((cohort_path.parent / cohort.evidence_root).resolve())
    suite = store.verify(suite_id)
    if (
        suite.kind != "six_skill_teacher_prepared_physical_suite_report"
        or suite.config.get("protocol_sha256") != protocol.manifest_sha256
        or suite.outcome != "failed"
        or suite.metrics.get("components_total") != len(protocol.configs)
        or suite.metrics.get("components_passed") != 0
        or suite.metrics.get("evaluations_complete") is not True
    ):
        raise ValueError("Replay requires the exact all-preflight-failed frozen suite")
    return protocol, suite, store


def _validated_request(protocol, suite, store: EvidenceStore, index: int) -> tuple[dict, dict]:
    frozen = protocol.configs[index]
    original = suite.metrics["results"][index]
    if original.get("skill_id") != frozen["skill_id"]:
        raise ValueError("Suite order does not match the frozen protocol")
    evaluation = store.verify(original["evaluation_run_id"])
    process = store.verify(original["process_run_id"])
    if (
        evaluation.kind != EVALUATION_KIND
        or evaluation.manifest_sha256 != original["evaluation_manifest_sha256"]
        or evaluation.outcome != "failed"
        or evaluation.config.get("skill_id") != frozen["skill_id"]
        or evaluation.config.get("device") != "mps"
        or evaluation.metrics.get("error") != MPS_PREFLIGHT_ERROR
        or evaluation.metrics.get("actual_policy_devices") is not None
        or evaluation.metrics.get("autonomous_skill_actions") != 0
        or evaluation.metrics.get("physical_success") is not False
    ):
        raise ValueError("Original result is not an untouched MPS preflight failure")
    if (
        process.kind != PROCESS_KIND
        or process.manifest_sha256 != original["process_manifest_sha256"]
        or process.metrics.get("process_complete") is not True
        or process.metrics.get("child_manifest_verified") is not True
        or process.metrics.get("child_run_id") != evaluation.run_id
        or process.metrics.get("child_manifest_sha256") != evaluation.manifest_sha256
    ):
        raise ValueError("Original MPS preflight process was not cleanly preserved")
    return frozen, {
        "skill_id": frozen["skill_id"],
        "evaluation_run_id": evaluation.run_id,
        "evaluation_manifest_sha256": evaluation.manifest_sha256,
        "process_run_id": process.run_id,
        "process_manifest_sha256": process.manifest_sha256,
        "training_attempt_run_id": original["training_attempt_run_id"],
        "training_manifest_sha256": original["training_manifest_sha256"],
    }


def main() -> int:
    args = parse_args()
    protocol, original_suite, original_store = _load_originals(args.protocol, args.failed_suite)
    probe = _probe_mps()
    replay_store = EvidenceStore(args.evidence_root.resolve())
    replay_store.root.mkdir(parents=True, exist_ok=True)

    existing = [
        row
        for row in replay_store.list_runs(limit=100)
        if row.get("kind") == REPLAY_KIND
        and row.get("config", {}).get("failed_suite_run_id") == original_suite.run_id
    ]
    if len(existing) > 1:
        raise RuntimeError("Ambiguous MPS preflight replay records")
    if existing:
        print(json.dumps(replay_store.verify(existing[0]["run_id"]).model_dump(mode="json")))
        return 0

    originals = [_validated_request(protocol, original_suite, original_store, i) for i in range(6)]
    results: list[dict[str, object]] = []
    for frozen, original in originals:
        # The original suite records the child run id separately. Resolve it from
        # the wrapper rather than interpreting a manifest digest as a directory.
        wrapper = original_store.verify(str(original["training_attempt_run_id"]))
        child_id = wrapper.metrics["child_run_id"]
        training_directory = (
            original_store.directory(wrapper.run_id) / "training-evidence/runs" / child_id
        )
        config = SkillPhysicalEvaluationConfig(
            training_run=training_directory,
            dataset_root=Path(
                original_store.verify(str(original["evaluation_run_id"])).config["dataset_root"]
            ),
            skill_views_path=Path(
                original_store.verify(str(original["evaluation_run_id"])).config["skill_views_path"]
            ),
            skill_id=frozen["skill_id"],
            device="mps",
            max_actions=frozen["max_actions"],
            execute_chunk_steps=frozen["execute_chunk_steps"],
            wall_timeout_seconds=frozen["wall_timeout_seconds"],
            evaluation_protocol_sha256=protocol.manifest_sha256,
            evaluation_protocol_file_sha256=digest_file(args.protocol),
        )
        result = run_skill_physical_process(
            SkillPhysicalProcessConfig(evaluation=config),
            store=replay_store,
            project_root=Path(__file__).resolve().parents[1],
        )
        results.append(
            {
                "skill_id": frozen["skill_id"],
                "original": original,
                "replacement_process_run_id": result.run_id,
                "replacement_process_manifest_sha256": result.manifest_sha256,
                "replacement_outcome": result.outcome,
                "component_passed": result.metrics.get("component_passed") is True,
            }
        )
        if result.kind != PROCESS_KIND or result.metrics.get("process_complete") is not True:
            raise RuntimeError("Replacement process did not finish cleanly; no automatic retry")

    directory = replay_store.new_run()
    (directory / "mps-probe.json").write_bytes(canonical(probe))
    (directory / "replay-results.json").write_bytes(canonical(results))
    manifest = replay_store.seal(
        directory,
        kind=REPLAY_KIND,
        outcome="completed" if all(row["component_passed"] for row in results) else "failed",
        config={
            "protocol_path": str(args.protocol.resolve()),
            "protocol_sha256": protocol.manifest_sha256,
            "protocol_file_sha256": digest_file(args.protocol),
            "failed_suite_run_id": original_suite.run_id,
            "failed_suite_manifest_sha256": original_suite.manifest_sha256,
            "replacement_policy": "one_local_mps_replay_for_each_clean_zero_action_preflight_failure",
        },
        metrics={
            "live_native_mps_probe": probe,
            "original_failures_preserved": len(results),
            "replacement_cases_complete": len(results),
            "replacement_components_passed": sum(
                row["component_passed"] for row in results
            ),
            "independent_task_success": None,
            "autonomous_workflow_success": None,
            "release_qualified": False,
        },
        source=provenance(Path(__file__).resolve().parents[1]),
        claims=[],
    )
    print(json.dumps(manifest.model_dump(mode="json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
