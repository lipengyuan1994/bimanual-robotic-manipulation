from __future__ import annotations

import json

import pytest

from bimanual.cli import main
from bimanual.intel_benchmark_contract import IntelOpenVINOBenchmark, load_intel_openvino_benchmark


def payload() -> dict[str, object]:
    model = [0.1, 0.2, 0.3, 0.4, 0.5]
    end_to_end = [0.2, 0.4, 0.6, 0.8, 1.0]
    return {
        "schema_version": 1,
        "kind": "intel_openvino_benchmark_v1",
        "scope": "intel_core_ultra_openvino_inference_and_simulation_benchmark",
        "hardware": {
            "cpu_model": "Intel Core Ultra fixture",
            "cpu_series": "Core Ultra Series 3",
            "system_model": "fixture host",
            "ram_bytes": 32_000_000_000,
        },
        "software": {
            "os_name": "Ubuntu",
            "os_version": "24.04",
            "python_version": "3.12.0",
            "mujoco_version": "3.12.0",
            "openvino_version": "2026.3",
            "driver_versions": {"intel_gpu": "fixture"},
        },
        "inference": {
            "model_id": "fixture-model",
            "model_sha256": "a" * 64,
            "openvino_model_sha256": "b" * 64,
            "input_manifest_sha256": "c" * 64,
            "runtime_backend": "openvino",
            "requested_device": "GPU",
            "actual_device": "GPU",
            "requested_precision": "FP16",
            "actual_precision": "FP16",
            "batch_size": 2,
        },
        "timings": {
            "cold_load_compile_seconds": 3.0,
            "batch_size": 2,
            "warm_model_only_seconds": model,
            "warm_end_to_end_seconds": end_to_end,
            "warm_model_only_p50_seconds": 0.3,
            "warm_model_only_p95_seconds": 0.48,
            "warm_end_to_end_p50_seconds": 0.6,
            "warm_end_to_end_p95_seconds": 0.96,
            "throughput_items_per_second": 2 / 0.3,
            "end_to_end_items_per_second": 2 / 0.6,
        },
        "memory": {"process_peak_rss_bytes": 1_000_000, "device_peak_memory_bytes": 2_000_000},
        "simulation": {"simulation_seconds": 10.0, "wall_clock_seconds": 12.0},
        "devices": {"available_devices": ["CPU", "GPU"], "unsupported_devices": ["NPU"]},
        "fallback": {"occurred": False, "reason": None},
    }


def test_valid_record_requires_all_benchmark_evidence_fields():
    record = IntelOpenVINOBenchmark.model_validate(payload())
    assert record.hardware.cpu_series == "Core Ultra Series 3"
    assert record.timings.warm_model_only_p95_seconds == 0.48
    assert record.fallback.occurred is False


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda item: item["timings"].pop("warm_end_to_end_seconds"), "warm_end_to_end_seconds"),
        (lambda item: item["timings"].__setitem__("warm_model_only_p95_seconds", 0.47), "raw warm samples"),
        (lambda item: item["inference"].__setitem__("actual_device", "CPU"), "visible fallback"),
        (lambda item: item["inference"].__setitem__("actual_precision", "FP32"), "visible fallback"),
        (lambda item: item["fallback"].update(occurred=True, reason=None), "fallback reason"),
        (lambda item: item["hardware"].__setitem__("cpu_series", "Xeon"), "cpu_series"),
    ],
)
def test_incomplete_or_misleading_records_are_rejected(mutate, message):
    item = payload()
    mutate(item)
    with pytest.raises(Exception, match=message):
        IntelOpenVINOBenchmark.model_validate(item)


def test_explicit_fallback_is_accepted_and_visible():
    item = payload()
    item["inference"]["actual_device"] = "CPU"
    item["fallback"] = {"occurred": True, "reason": "GPU plugin unavailable"}
    record = IntelOpenVINOBenchmark.model_validate(item)
    assert record.fallback.reason == "GPU plugin unavailable"


def test_cli_validates_record_without_executing_a_benchmark(tmp_path, capsys):
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(payload()))
    assert main(["intel-benchmark-check", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["validated"] is True
    assert output["actual_device"] == "GPU"
    assert load_intel_openvino_benchmark(path).kind == "intel_openvino_benchmark_v1"
