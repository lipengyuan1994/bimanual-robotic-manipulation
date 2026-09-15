"""Fail-closed evidence contract for future Intel/OpenVINO benchmark runs.

This module validates a record supplied by a benchmark runner.  It deliberately
does not discover hardware, import OpenVINO, convert a model, or make an Intel
claim.  Those actions belong on an eligible target host.  A valid record proves
only that the runner recorded the required fields consistently; its contents
still need sealed run artifacts and an actual Core Ultra host before R6/R7 can
be considered satisfied.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from bimanual.contracts import Contract, Digest, Finite

PositiveFinite = Annotated[Finite, Field(gt=0)]
NonnegativeFinite = Annotated[Finite, Field(ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]

KIND = "intel_openvino_benchmark_v1"
SCOPE = "intel_core_ultra_openvino_inference_and_simulation_benchmark"
SUPPORTED_SERIES = ("Core Ultra Series 2", "Core Ultra Series 3")


def _percentile(values: tuple[float, ...], fraction: float) -> float:
    """Match the linear percentile convention used by NumPy for auditability."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


class BenchmarkHardware(Contract):
    cpu_model: Annotated[str, Field(min_length=1)]
    cpu_series: Literal["Core Ultra Series 2", "Core Ultra Series 3"]
    system_model: Annotated[str, Field(min_length=1)]
    ram_bytes: PositiveInt

    @field_validator("cpu_model")
    @classmethod
    def cpu_model_is_core_ultra(cls, value: str) -> str:
        if "intel core ultra" not in value.casefold():
            raise ValueError("cpu_model must identify an Intel Core Ultra processor")
        return value


class BenchmarkSoftware(Contract):
    os_name: Annotated[str, Field(min_length=1)]
    os_version: Annotated[str, Field(min_length=1)]
    python_version: Annotated[str, Field(min_length=1)]
    mujoco_version: Annotated[str, Field(min_length=1)]
    openvino_version: Annotated[str, Field(min_length=1)]
    driver_versions: dict[Annotated[str, Field(min_length=1)], Annotated[str, Field(min_length=1)]]

    @field_validator("driver_versions")
    @classmethod
    def drivers_are_present(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("driver_versions must record the target device drivers")
        return value


class BenchmarkInference(Contract):
    model_id: Annotated[str, Field(min_length=1)]
    model_sha256: Digest
    openvino_model_sha256: Digest
    input_manifest_sha256: Digest
    runtime_backend: Literal["openvino"]
    requested_device: Annotated[str, Field(min_length=1)]
    actual_device: Annotated[str, Field(min_length=1)]
    requested_precision: Literal["FP32", "FP16", "INT8"]
    actual_precision: Literal["FP32", "FP16", "INT8"]
    batch_size: PositiveInt


class BenchmarkTimings(Contract):
    """Raw wall-clock timings, kept separate by measurement scope."""

    cold_load_compile_seconds: NonnegativeFinite
    batch_size: PositiveInt
    warm_model_only_seconds: Annotated[tuple[PositiveFinite, ...], Field(min_length=5)]
    warm_end_to_end_seconds: Annotated[tuple[PositiveFinite, ...], Field(min_length=5)]
    warm_model_only_p50_seconds: PositiveFinite
    warm_model_only_p95_seconds: PositiveFinite
    warm_end_to_end_p50_seconds: PositiveFinite
    warm_end_to_end_p95_seconds: PositiveFinite
    throughput_items_per_second: PositiveFinite
    end_to_end_items_per_second: PositiveFinite

    @model_validator(mode="after")
    def aggregates_match_raw_samples(self) -> Self:
        checks = (
            (
                "warm_model_only_p50_seconds",
                self.warm_model_only_p50_seconds,
                _percentile(self.warm_model_only_seconds, 0.5),
            ),
            (
                "warm_model_only_p95_seconds",
                self.warm_model_only_p95_seconds,
                _percentile(self.warm_model_only_seconds, 0.95),
            ),
            (
                "warm_end_to_end_p50_seconds",
                self.warm_end_to_end_p50_seconds,
                _percentile(self.warm_end_to_end_seconds, 0.5),
            ),
            (
                "warm_end_to_end_p95_seconds",
                self.warm_end_to_end_p95_seconds,
                _percentile(self.warm_end_to_end_seconds, 0.95),
            ),
        )
        for name, reported, calculated in checks:
            if not math.isclose(reported, calculated, rel_tol=1e-9, abs_tol=1e-12):
                raise ValueError(f"{name} does not match raw warm samples")
        expected_model = (
            self.batch_size / sum(self.warm_model_only_seconds) * len(self.warm_model_only_seconds)
        )
        expected_e2e = (
            self.batch_size / sum(self.warm_end_to_end_seconds) * len(self.warm_end_to_end_seconds)
        )
        if not math.isclose(self.throughput_items_per_second, expected_model, rel_tol=1e-9):
            raise ValueError("throughput_items_per_second does not match model-only samples")
        if not math.isclose(self.end_to_end_items_per_second, expected_e2e, rel_tol=1e-9):
            raise ValueError("end_to_end_items_per_second does not match end-to-end samples")
        return self


class BenchmarkMemory(Contract):
    process_peak_rss_bytes: PositiveInt
    device_peak_memory_bytes: Annotated[int | None, Field(strict=True, ge=0)]


class BenchmarkSimulation(Contract):
    simulation_seconds: NonnegativeFinite
    wall_clock_seconds: PositiveFinite


class BenchmarkDevices(Contract):
    available_devices: Annotated[tuple[str, ...], Field(min_length=1)]
    unsupported_devices: tuple[str, ...]

    @field_validator("available_devices", "unsupported_devices")
    @classmethod
    def device_names_are_nonempty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("device names must be nonempty")
        if len(set(value)) != len(value):
            raise ValueError("device names must not be repeated")
        return value


class BenchmarkFallback(Contract):
    occurred: bool
    reason: str | None = None

    @model_validator(mode="after")
    def fallback_reason_is_visible(self) -> Self:
        if self.occurred and not self.reason:
            raise ValueError("fallback reason is required when a fallback occurred")
        if not self.occurred and self.reason is not None:
            raise ValueError("fallback reason must be null when no fallback occurred")
        return self


class IntelOpenVINOBenchmark(Contract):
    """The record a target-host runner must produce before release review."""

    kind: Literal[KIND] = KIND
    scope: Literal[SCOPE] = SCOPE
    hardware: BenchmarkHardware
    software: BenchmarkSoftware
    inference: BenchmarkInference
    timings: BenchmarkTimings
    memory: BenchmarkMemory
    simulation: BenchmarkSimulation
    devices: BenchmarkDevices
    fallback: BenchmarkFallback

    @model_validator(mode="after")
    def device_and_fallback_are_consistent(self) -> Self:
        requested = self.inference.requested_device
        actual = self.inference.actual_device
        if actual not in self.devices.available_devices:
            raise ValueError("actual_device is absent from available_devices")
        changed_device = requested != actual
        changed_precision = self.inference.requested_precision != self.inference.actual_precision
        if (changed_device or changed_precision) and not self.fallback.occurred:
            raise ValueError(
                "requested/actual device or precision mismatch requires visible fallback"
            )
        if not changed_device and not changed_precision and self.fallback.occurred:
            raise ValueError("fallback cannot be reported when device and precision both match")
        if requested in self.devices.unsupported_devices and requested == actual:
            raise ValueError("actual_device cannot also be reported unsupported")
        if self.timings.batch_size != self.inference.batch_size:
            raise ValueError("timing batch_size must match inference batch_size")
        return self


def load_intel_openvino_benchmark(path: Path) -> IntelOpenVINOBenchmark:
    """Load a local record; malformed JSON and missing contract fields fail closed."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load benchmark record {path}: {exc}") from exc
    try:
        return IntelOpenVINOBenchmark.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid Intel/OpenVINO benchmark record: {exc}") from exc
