"""Read-only local-Qwen runtime readiness record; it never loads model weights."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import sys
import traceback
from pathlib import Path

from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.planner import MODEL_ID, verify_model

KIND = "local_qwen_planner_preflight"
SCOPE = "local_qwen_runtime_readiness_no_model_execution"
PACKAGES = ("torch", "transformers", "openvino", "optimum")


def _package_report(name: str) -> dict[str, object]:
    installed = importlib.util.find_spec(name) is not None
    try:
        version: str | None = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"installed": installed, "version": version}


def _native_runtime() -> dict[str, object]:
    machine = platform.machine()
    system = platform.system()
    native = system != "Darwin" or machine == "arm64"
    return {
        "system": system,
        "machine": machine,
        "native_arm64_required": system == "Darwin",
        "native_runtime": native,
        "python": sys.version.split()[0],
        "executable": sys.executable,
    }


def _mps_report(torch_package: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "torch_imported": False,
        "built": None,
        "available": None,
        "device_count": None,
    }
    if not torch_package["installed"]:
        return report
    import torch

    report.update(
        torch_imported=True,
        built=bool(torch.backends.mps.is_built()),
        available=bool(torch.backends.mps.is_available()),
    )
    if report["available"]:
        report["device_count"] = int(torch.mps.device_count())
    return report


def run_planner_preflight(
    *, model_root: Path, store: EvidenceStore, project_root: Path
) -> Manifest:
    """Seal byte-level model and runtime readiness without constructing Qwen.

    This intentionally does not import any Transformers model class, construct an
    ``AutoProcessor``, deserialize model weights, make a network request, acquire
    a model lease, or run inference. File hashing necessarily reads each declared
    snapshot file. An unavailable accelerator is useful state for a preflight
    record, not a failure to collect the record.
    """
    project_root = Path(project_root).resolve()
    model_root = Path(model_root)
    if not model_root.is_absolute():
        model_root = project_root / model_root
    model_root = model_root.resolve()
    directory = store.new_run()
    source = provenance(project_root)
    config = {
        "model_root": str(model_root),
        "model_identity": MODEL_ID,
        "scope": SCOPE,
    }
    metrics: dict[str, object] = {
        "model_load_attempted": False,
        "inference_attempted": False,
        "live_dispatch_authorized": False,
        "manipulation_success": None,
        "intel_validated": False,
        "model": None,
        "runtime": _native_runtime(),
        "packages": {},
        "mps": None,
        "pytorch_enable_mps_fallback": {
            "environment_value": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK"),
            "effective_value": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0"),
        },
    }
    outcome = "failed"
    try:
        model = verify_model(model_root)
        metrics["model"] = {
            "repo_id": model["repo_id"],
            "revision": model["revision"],
            "file_count": len(model["files"]),
            "model_manifest_sha256": digest_file(model_root / "model-manifest.json"),
        }
        packages = {name: _package_report(name) for name in PACKAGES}
        metrics["packages"] = packages
        metrics["mps"] = _mps_report(packages["torch"])
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        (directory / "error.txt").write_text(traceback.format_exc())
    (directory / "preflight.json").write_bytes(canonical(metrics) + b"\n")
    return store.seal(
        directory,
        kind=KIND,
        outcome=outcome,
        config=config,
        metrics=metrics,
        source=source,
        claims=[],
    )
