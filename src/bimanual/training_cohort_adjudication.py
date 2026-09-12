"""Explicitly preserve and classify a zero-update cohort infrastructure failure."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from pathlib import Path

from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.worker_lease import WorkerLease

KIND = "training_cohort_preflight_adjudication"
ATTEMPT_KIND = "training_cohort_skill_attempt"
ERROR = "RuntimeError: Requested MPS unavailable; no fallback"


def _config(protocol_path: Path, protocol, skill_id: str) -> ACTTrainingConfig:
    raw = protocol.configs[COHORT_SKILLS.index(skill_id)]
    return ACTTrainingConfig.model_validate(
        raw
        | {
            "dataset_path": (protocol_path.parent / raw["dataset_path"]).resolve(),
            "skill_views_path": (protocol_path.parent / raw["skill_views_path"]).resolve(),
        }
    )


def _validate_failure(
    store: EvidenceStore,
    wrapper: Manifest,
    *,
    protocol_sha256: str,
    config: ACTTrainingConfig,
) -> Manifest:
    if (
        wrapper.kind != ATTEMPT_KIND
        or wrapper.outcome != "failed"
        or wrapper.metrics.get("training_complete") is not False
        or wrapper.config.get("protocol_sha256") != protocol_sha256
        or wrapper.config.get("skill_id") != config.skill_id
        or wrapper.config.get("training") != config.model_dump(mode="json")
    ):
        raise ValueError("Attempt is not the exact failed cohort request")
    attempt = store.directory(wrapper.run_id)
    if json.loads((attempt / "runner-error.json").read_text()) != {"error": ERROR}:
        raise ValueError("Wrapper does not record the supported MPS preflight failure")
    child_store = EvidenceStore(attempt / "training-evidence")
    children = list((child_store.root / "runs").glob("*/manifest.json"))
    if len(children) != 1:
        raise ValueError("Preflight failure requires exactly one sealed training child")
    child = child_store.verify(children[0].parent.name)
    error_text = (children[0].parent / "error.txt").read_text()
    if (
        child.kind != "act_training"
        or child.outcome != "failed"
        or child.config != config.model_dump(mode="json")
        or child.metrics.get("requested_device") != "mps"
        or child.metrics.get("actual_device") is not None
        or child.metrics.get("training_completed") is not False
        or child.metrics.get("steps") != []
        or ERROR not in error_text
        or any(path.name == "checkpoint" for path in children[0].parent.iterdir())
    ):
        raise ValueError("Training child advanced beyond the supported zero-update failure")
    return child


def _matching_adjudications(
    store: EvidenceStore,
    *,
    protocol_sha256: str,
    skill_id: str,
) -> dict[str, Manifest]:
    results = {}
    for path in (store.root / "runs").glob("*/manifest.json"):
        try:
            with path.open() as stream:
                header = stream.read(131072)
        except (OSError, ValueError):
            continue
        if KIND not in header or protocol_sha256 not in header or skill_id not in header:
            continue
        manifest = store.verify(path.parent.name)
        if (
            manifest.kind == KIND
            and manifest.config.get("protocol_sha256") == protocol_sha256
            and manifest.config.get("skill_id") == skill_id
            and manifest.metrics.get("replacement_attempts_authorized") == 1
        ):
            attempt_id = manifest.config.get("failed_attempt_run_id")
            if not isinstance(attempt_id, str) or attempt_id in results:
                raise ValueError("Ambiguous cohort preflight adjudication")
            results[attempt_id] = manifest
    return results


def adjudicated_attempt_ids(
    store: EvidenceStore,
    protocol_path: Path,
    protocol,
    skill_id: str,
) -> set[str]:
    config = _config(protocol_path, protocol, skill_id)
    results = _matching_adjudications(
        store, protocol_sha256=protocol.manifest_sha256, skill_id=skill_id
    )
    for attempt_id, adjudication in results.items():
        wrapper = store.verify(attempt_id)
        child = _validate_failure(
            store, wrapper, protocol_sha256=protocol.manifest_sha256, config=config
        )
        if (
            adjudication.config.get("failed_attempt_manifest_sha256") != wrapper.manifest_sha256
            or adjudication.metrics.get("failed_child_run_id") != child.run_id
            or adjudication.metrics.get("failed_child_manifest_sha256") != child.manifest_sha256
        ):
            raise ValueError("Adjudication no longer binds the failed attempt")
    return set(results)


def adjudicate_training_cohort_preflight(protocol_path: Path, attempt_id: str) -> Manifest:
    """Authorize one replacement only after a live native MPS probe succeeds."""

    protocol_path = Path(protocol_path).resolve(strict=True)
    protocol = load_training_cohort_protocol(protocol_path)
    store = EvidenceStore((protocol_path.parent / protocol.evidence_root).resolve())
    wrapper = store.verify(attempt_id)
    skill_id = wrapper.config.get("skill_id")
    if skill_id not in COHORT_SKILLS:
        raise ValueError("Failed attempt does not name a cohort skill")
    config = _config(protocol_path, protocol, skill_id)
    child = _validate_failure(
        store, wrapper, protocol_sha256=protocol.manifest_sha256, config=config
    )
    with WorkerLease.acquire(store.root / ".training-cohort-coordinator.lock"):
        existing = _matching_adjudications(
            store, protocol_sha256=protocol.manifest_sha256, skill_id=skill_id
        )
        if attempt_id in existing:
            return existing[attempt_id]
        if existing:
            raise ValueError("Another failed attempt is already adjudicated for this skill")
        if platform.machine() != "arm64":
            raise RuntimeError("Adjudication requires the native Apple Silicon runtime")
        import torch

        if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
            raise RuntimeError("Live native MPS probe must pass before replacement authorization")
        probe = {
            "python": sys.executable,
            "machine": platform.machine(),
            "torch": importlib.metadata.version("torch"),
            "mps_built": True,
            "mps_available": True,
            "mps_device_count": torch.mps.device_count(),
        }
        directory = store.new_run()
        (directory / "mps-probe.json").write_bytes(canonical(probe))
        metrics = {
            "failure_class": "restricted_process_mps_preflight_unavailable",
            "failed_child_run_id": child.run_id,
            "failed_child_manifest_sha256": child.manifest_sha256,
            "failed_updates": 0,
            "checkpoint_created": False,
            "live_native_mps_probe": probe,
            "replacement_attempts_authorized": 1,
            "training_success": None,
            "physical_success": None,
        }
        return store.seal(
            directory,
            kind=KIND,
            outcome="completed",
            config={
                "protocol_path": str(protocol_path),
                "protocol_file_sha256": digest_file(protocol_path),
                "protocol_sha256": protocol.manifest_sha256,
                "skill_id": skill_id,
                "failed_attempt_run_id": wrapper.run_id,
                "failed_attempt_manifest_sha256": wrapper.manifest_sha256,
                "reason": "Explicit replacement of zero-update environment preflight only",
            },
            metrics=metrics,
            source=provenance(Path(__file__).resolve().parents[2]),
            claims=["One replacement authorized; no training or physical quality claim"],
        )
