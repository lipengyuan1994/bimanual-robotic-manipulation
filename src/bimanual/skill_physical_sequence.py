"""Resume all frozen component evaluations after the full training cohort seals."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.evidence import EvidenceStore, Manifest, digest_file
from bimanual.skill_physical_process import PROCESS_KIND
from bimanual.skill_physical_protocol import load_skill_physical_protocol
from bimanual.skill_physical_protocol_runner import (
    KIND as EVALUATION_KIND,
)
from bimanual.skill_physical_protocol_runner import (
    _training_child,
    run_skill_physical_protocol,
)
from bimanual.skill_physical_suite import run_skill_physical_suite_report
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.training_cohort_adjudication import adjudicated_attempt_ids
from bimanual.training_cohort_runner import KIND as TRAINING_ATTEMPT_KIND
from bimanual.worker_lease import WorkerLease

REQUEST = "cohort-attempt.json"


def _expected_training(cohort_path: Path, cohort, skill: str) -> ACTTrainingConfig:
    raw = cohort.configs[COHORT_SKILLS.index(skill)]
    return ACTTrainingConfig.model_validate(
        raw
        | {
            "dataset_path": (cohort_path.parent / raw["dataset_path"]).resolve(),
            "skill_views_path": (cohort_path.parent / raw["skill_views_path"]).resolve(),
        }
    )


def _completed_training_attempts(
    store: EvidenceStore, cohort_path: Path, cohort
) -> dict[str, Manifest]:
    """Require one exact, sealed training attempt for every frozen skill."""
    candidates: dict[str, list[Path]] = {skill: [] for skill in COHORT_SKILLS}
    for request_path in (store.root / "runs").glob(f"*/{REQUEST}"):
        try:
            payload = request_path.read_bytes()
            if len(payload) > 131072:
                raise ValueError("Oversized cohort attempt request")
            request = json.loads(payload)
        except (OSError, ValueError) as error:
            raise ValueError("Cohort attempt request is unreadable") from error
        if not isinstance(request, dict):
            raise ValueError("Cohort attempt request must be an object")
        if request.get("protocol_sha256") != cohort.manifest_sha256:
            continue
        skill = request.get("skill_id")
        if skill not in candidates:
            raise ValueError("Cohort attempt declares an unknown skill")
        candidates[skill].append(request_path.parent)
    matches: dict[str, list[Manifest]] = {skill: [] for skill in COHORT_SKILLS}
    for skill, directories in candidates.items():
        excluded = adjudicated_attempt_ids(store, cohort_path, cohort, skill)
        for directory in directories:
            if directory.name in excluded:
                continue
            if not (directory / "manifest.json").is_file():
                raise RuntimeError("Training cohort has an interrupted attempt")
            wrapper = store.verify(directory.name)
            expected = _expected_training(cohort_path, cohort, skill)
            runner_sha256 = wrapper.provenance.get("source_files", {}).get(
                "src/bimanual/training_cohort_runner.py"
            )
            if (
                wrapper.config != json.loads((directory / REQUEST).read_bytes())
                or wrapper.config.get("protocol_file_sha256") != digest_file(cohort_path)
                or wrapper.config.get("runner_source_sha256") != runner_sha256
                or not isinstance(runner_sha256, str)
            ):
                raise ValueError("Training attempt declaration or source binding changed")
            _training_child(store, wrapper, expected, cohort.manifest_sha256)
            if wrapper.kind != TRAINING_ATTEMPT_KIND:
                raise ValueError("Training attempt kind changed after verification")
            matches[skill].append(wrapper)
    duplicate = [skill for skill, rows in matches.items() if len(rows) > 1]
    if duplicate:
        raise RuntimeError(
            "Training cohort has ambiguous completed attempts: " + ", ".join(duplicate)
        )
    missing = [skill for skill, rows in matches.items() if not rows]
    if missing:
        raise RuntimeError("Training cohort is incomplete: " + ", ".join(missing))
    return {skill: rows[0] for skill, rows in matches.items()}


def run_skill_physical_sequence(protocol_path: Path) -> dict:
    """Run/reuse all six one-attempt cases, then seal the complete suite report.

    All training candidates are verified before the first model evaluation. A clean
    physical failure remains a result and does not hide later cases. A process-level
    interruption stops the sequence because the frozen case requires adjudication.
    """
    protocol_path = Path(protocol_path).resolve(strict=True)
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_skill_physical_protocol(protocol_path)
    cohort_path = (protocol_path.parent / protocol.training_cohort_path).resolve(strict=True)
    cohort = load_training_cohort_protocol(cohort_path)
    store = EvidenceStore((cohort_path.parent / cohort.evidence_root).resolve())
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".skill-physical-sequence.lock"):
        attempts = _completed_training_attempts(store, cohort_path, cohort)
        results = []
        for skill in COHORT_SKILLS:
            result = run_skill_physical_protocol(protocol_path, skill, attempts[skill].run_id)
            row = {
                "skill_id": skill,
                "run_id": result.run_id,
                "manifest_sha256": result.manifest_sha256,
                "kind": result.kind,
                "outcome": result.outcome,
                "component_passed": result.metrics.get("component_passed") is True,
            }
            results.append(row)
            if result.kind == PROCESS_KIND:
                return {
                    "profile": "six_skill_physical_sequence_v1",
                    "protocol_sha256": protocol.manifest_sha256,
                    "protocol_file_sha256": protocol_file_sha256,
                    "evaluations": results,
                    "evaluations_complete": False,
                    "suite": None,
                    "independent_task_success": None,
                    "autonomous_workflow_success": None,
                    "release_qualified": False,
                    "reason": "Physical process requires adjudication before continuing",
                }
            if result.kind != EVALUATION_KIND:
                raise ValueError("Frozen component runner returned an unsupported result kind")
        suite = run_skill_physical_suite_report(protocol_path)
        return {
            "profile": "six_skill_physical_sequence_v1",
            "protocol_sha256": protocol.manifest_sha256,
            "protocol_file_sha256": protocol_file_sha256,
            "evaluations": results,
            "evaluations_complete": True,
            "suite": {
                "run_id": suite.run_id,
                "manifest_sha256": suite.manifest_sha256,
                "outcome": suite.outcome,
                "all_components_passed": suite.metrics.get("all_components_passed") is True,
            },
            "independent_task_success": None,
            "autonomous_workflow_success": None,
            "release_qualified": False,
            "reason": "Teacher-prepared component results only; full workflow remains untested",
        }
