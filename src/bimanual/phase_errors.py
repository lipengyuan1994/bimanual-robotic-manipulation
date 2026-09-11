"""Offline error summaries; phase labels never become operating policy inputs."""

from __future__ import annotations

import numpy as np


def summarize_phase_errors(forecasts, phases, *, start: int, end: int) -> list[dict]:
    """Require exact frame coverage and recompute errors from recorded targets."""
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(phases):
        raise ValueError("Invalid analysis interval")
    if len(forecasts) != end - start:
        raise ValueError("Incomplete forecast coverage")
    groups = {}
    for index, row in enumerate(forecasts, start):
        if type(row.get("parent_frame")) is not int or row["parent_frame"] != index:
            raise ValueError("Forecast frames must be unique and ordered")
        if "error" in row:
            raise ValueError("Failed forecasts require separate failure analysis")
        prediction = np.asarray(row["prediction_rad"], dtype=float)
        expected = np.asarray(row["expected_rad"], dtype=float)
        if (
            prediction.ndim != 2
            or prediction.shape[1] != 12
            or not len(prediction)
            or prediction.shape != expected.shape
            or not np.isfinite(prediction).all()
            or not np.isfinite(expected).all()
        ):
            raise ValueError("Invalid prediction or target shape/values")
        phase = phases[index]
        if not isinstance(phase, str) or not phase:
            raise ValueError("Missing phase label")
        groups.setdefault(phase, []).append(np.abs(prediction[0] - expected[0]))
    return [
        {
            "phase": phase,
            "frames": len(values),
            "mean_abs_rad": float(np.mean(values)),
            "max_abs_rad": float(np.max(values)),
            "per_joint_mean_abs_rad": np.mean(values, axis=0).tolist(),
        }
        for phase, values in groups.items()
    ]
