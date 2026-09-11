"""Resume the frozen training cohort in order, one model job at a time."""

from __future__ import annotations

from pathlib import Path

from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.training_cohort_runner import run_training_cohort_skill


def run_training_cohort_sequence(protocol_path: Path) -> dict:
    """Run/reconcile each skill in order and stop at the first sealed failure.

    Every child attempt remains independently sealed by the one-skill runner. The
    sequence adds no success or quality claim and is safe to restart: completed
    attempts are reverified and reused, while failed attempts are never retried.
    """

    protocol_path = Path(protocol_path).resolve()
    protocol = load_training_cohort_protocol(protocol_path)
    results = []
    for skill in COHORT_SKILLS:
        result = run_training_cohort_skill(protocol_path, skill)
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
    }
