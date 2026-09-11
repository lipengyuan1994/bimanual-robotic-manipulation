"""Resume the frozen training cohort in order, one model job at a time."""

from __future__ import annotations

import time
from pathlib import Path

from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.training_cohort_runner import run_training_cohort_skill


def run_training_cohort_sequence(
    protocol_path: Path,
    *,
    wait_for_active_seconds: float = 0,
    poll_interval_seconds: float = 5,
) -> dict:
    """Run/reconcile each skill in order and stop at the first sealed failure.

    Every child attempt remains independently sealed by the one-skill runner. The
    sequence adds no success or quality claim and is safe to restart: completed
    attempts are reverified and reused, while failed attempts are never retried.
    """

    if (
        not isinstance(wait_for_active_seconds, (int, float))
        or not 0 <= wait_for_active_seconds <= 86400
        or not isinstance(poll_interval_seconds, (int, float))
        or not 0.05 <= poll_interval_seconds <= 60
    ):
        raise ValueError("Invalid active-job wait limits")
    protocol_path = Path(protocol_path).resolve()
    protocol = load_training_cohort_protocol(protocol_path)
    results = []
    deadline = time.monotonic() + wait_for_active_seconds
    for skill in COHORT_SKILLS:
        while True:
            try:
                result = run_training_cohort_skill(protocol_path, skill)
                break
            except RuntimeError as error:
                if "holds this lease" not in str(error) or time.monotonic() >= deadline:
                    raise
                time.sleep(min(poll_interval_seconds, max(0, deadline - time.monotonic())))
        results.append(
            {
                "skill_id": skill,
                "run_id": result.run_id,
                "manifest_sha256": result.manifest_sha256,
                "outcome": result.outcome,
                "training_complete": result.metrics.get("training_complete") is True,
                "physical_success": None,
            }
        )
        if result.outcome != "completed" or result.metrics.get("training_complete") is not True:
            break
    return {
        "profile": "six_skill_training_sequence_v1",
        "protocol_sha256": protocol.manifest_sha256,
        "skills": results,
        "all_training_complete": len(results) == len(COHORT_SKILLS)
        and all(row["training_complete"] for row in results),
        "physical_success": None,
        "quality_claim": False,
        "wait_for_active_seconds": float(wait_for_active_seconds),
    }
