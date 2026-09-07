"""Explicit native-runtime and arithmetic probes, independent of trained models."""

from __future__ import annotations

import importlib.metadata
import platform
import site
import subprocess
import sys
import time
from typing import Any


def audit_extensions() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"status": "not_applicable", "reason": "Mach-O audit is specific to macOS"}
    from pathlib import Path

    paths = sorted(
        {
            p.resolve()
            for root in site.getsitepackages()
            for p in Path(root).rglob("*")
            if p.suffix in {".so", ".dylib"} and p.is_file()
        }
    )
    bad = []
    universal = 0
    for path in paths:
        result = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        architectures = result.stdout.split()
        if result.returncode != 0 or "arm64" not in architectures:
            bad.append({"file": str(path), "architectures": architectures, "error": result.stderr})
        elif len(architectures) > 1:
            universal += 1
    return {
        "status": "passed" if paths and not bad else "failed",
        "checked": len(paths),
        "universal_with_arm64": universal,
        "bad": bad,
    }


def diagnose(require_device: str = "cpu") -> dict[str, Any]:
    native = platform.system() != "Darwin" or platform.machine() == "arm64"
    report: dict[str, Any] = {
        "schema_version": 1,
        "scope": "general_runtime_only",
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "requested_device": require_device,
        "native_runtime": "passed" if native else "failed",
        "intel_demonstration": "not_validated",
        "manipulation_success": None,
    }
    if not native:
        report["outcome"] = "failed"
        report["reason"] = "Intel/Rosetta Python is forbidden on this Mac"
        return report

    import mujoco
    import numpy as np

    report["versions"] = {"mujoco": mujoco.__version__, "numpy": np.__version__}
    for package in ("torch", "torchvision", "lerobot", "transformers", "fastapi"):
        try:
            report["versions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["versions"][package] = None
    report["extensions"] = audit_extensions()
    matrix = np.arange(16, dtype=np.float32).reshape(4, 4) / 16
    np.testing.assert_allclose(matrix @ np.eye(4), matrix)
    model = mujoco.MjModel.from_xml_string(
        '<mujoco><worldbody><body><joint type="hinge"/>'
        '<geom type="sphere" size="0.1"/></body></worldbody></mujoco>'
    )
    data = mujoco.MjData(model)
    mujoco.mj_step(model, data, nstep=10)
    report["mujoco_step"] = "passed" if data.time > 0 else "failed"
    report["cpu"] = {"status": "passed", "workload": "numpy_arithmetic"}
    report["mps"] = {"status": "not_installed", "reason": "Install the ml extra to probe PyTorch"}
    if report["versions"]["torch"]:
        import torch

        x = torch.arange(1024, dtype=torch.float32).reshape(32, 32) / 1024
        cpu = x @ x.T
        report["cpu"] = {"status": "passed", "workload": "torch_float32_matmul", "device": "cpu"}
        report["mps"] = {
            "status": "unavailable",
            "built": torch.backends.mps.is_built(),
            "available": torch.backends.mps.is_available(),
        }
        if torch.backends.mps.is_available():
            try:
                start = time.perf_counter()
                gpu_x = x.to("mps")
                actual = gpu_x @ gpu_x.T
                torch.mps.synchronize()
                elapsed = time.perf_counter() - start
                torch.testing.assert_close(actual.cpu(), cpu, rtol=2e-4, atol=2e-4)
                report["mps"].update(
                    status="passed",
                    device=str(actual.device),
                    cpu_max_abs_error=float((actual.cpu() - cpu).abs().max()),
                    probe_seconds=elapsed,
                    workload="torch_float32_matmul_only",
                )
            except Exception as exc:
                report["mps"].update(status="failed", reason=str(exc))
    report["outcome"] = (
        "passed"
        if report[require_device]["status"] == "passed"
        and report["mujoco_step"] == "passed"
        and report["extensions"]["status"] in {"passed", "not_applicable"}
        else "failed"
    )
    return report
