"""Seal a conservative summary of the frozen six-skill physical component suite."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.skill_physical_evaluation import SkillPhysicalEvaluationConfig
from bimanual.skill_physical_process import PROCESS_KIND, SkillPhysicalProcessConfig
from bimanual.skill_physical_protocol import load_skill_physical_protocol
from bimanual.skill_physical_protocol_runner import KIND as EVALUATION_KIND
from bimanual.skill_physical_protocol_runner import _clean_process_child, _training_child
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.worker_lease import WorkerLease

KIND = "six_skill_teacher_prepared_physical_suite_report"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _candidate_manifests(store: EvidenceStore, protocol_sha256: str) -> dict[str, Manifest]:
    matches: dict[str, Manifest] = {}
    for path in (store.root / "runs").glob("*/manifest.json"):
        try:
            with path.open() as stream:
                header = stream.read(131072)
            if EVALUATION_KIND not in header or protocol_sha256 not in header:
                continue
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (
            raw.get("kind") != EVALUATION_KIND
            or raw.get("config", {}).get("evaluation_protocol_sha256") != protocol_sha256
        ):
            continue
        skill = raw["config"].get("skill_id")
        if skill not in COHORT_SKILLS:
            raise ValueError("Frozen physical evaluation declares an unknown skill")
        if skill in matches:
            raise RuntimeError("Ambiguous repeated physical evaluations in frozen suite")
        matches[skill] = store.verify(path.parent.name)
    return matches


def _expected_training(cohort_path: Path, cohort, skill: str) -> ACTTrainingConfig:
    raw = cohort.configs[COHORT_SKILLS.index(skill)]
    return ACTTrainingConfig.model_validate(
        raw
        | {
            "dataset_path": (cohort_path.parent / raw["dataset_path"]).resolve(),
            "skill_views_path": (cohort_path.parent / raw["skill_views_path"]).resolve(),
        }
    )


def _verified_process(store: EvidenceStore, candidate: Manifest) -> Manifest:
    expected = SkillPhysicalProcessConfig(
        evaluation=SkillPhysicalEvaluationConfig.model_validate(candidate.config)
    ).model_dump(mode="json")
    matches = []
    for path in (store.root / "runs").glob("*/manifest.json"):
        try:
            with path.open() as stream:
                header = stream.read(131072)
            if PROCESS_KIND not in header or candidate.run_id not in header:
                continue
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (
            raw.get("kind") == PROCESS_KIND
            and raw.get("config") == expected
            and raw.get("metrics", {}).get("child_run_id") == candidate.run_id
        ):
            matches.append(store.verify(path.parent.name))
    if len(matches) != 1:
        raise ValueError("Physical evaluation requires exactly one sealed process wrapper")
    process = matches[0]
    if not _clean_process_child(process, candidate):
        raise ValueError("Physical evaluation process did not finish cleanly")
    return process


def _validate_candidate(
    candidate: Manifest,
    *,
    store: EvidenceStore,
    protocol,
    protocol_file_sha256: str,
    cohort,
    cohort_path: Path,
    skill: str,
) -> dict:
    expected_training = _expected_training(cohort_path, cohort, skill)
    frozen = protocol.configs[COHORT_SKILLS.index(skill)]
    config = SkillPhysicalEvaluationConfig.model_validate(candidate.config)
    if (
        config.skill_id != skill
        or config.dataset_root != expected_training.dataset_path
        or config.skill_views_path != expected_training.skill_views_path
        or config.device != frozen["device"]
        or config.max_actions != frozen["max_actions"]
        or config.execute_chunk_steps != frozen["execute_chunk_steps"]
        or config.wall_timeout_seconds != frozen["wall_timeout_seconds"]
        or config.evaluation_protocol_sha256 != protocol.manifest_sha256
        or config.evaluation_protocol_file_sha256 != protocol_file_sha256
    ):
        raise ValueError("Physical evaluation does not match the frozen skill request")

    training_run = config.training_run.resolve()
    wrapper_directory = training_run.parents[2]
    if (
        training_run.parent.name != "runs"
        or training_run.parent.parent.name != "training-evidence"
        or wrapper_directory.parent.resolve() != (store.root / "runs").resolve()
    ):
        raise ValueError("Physical evaluation training path is outside a cohort attempt")
    wrapper = store.verify(wrapper_directory.name)
    child_store, expected_run, child = _training_child(
        store, wrapper, expected_training, cohort.manifest_sha256
    )
    if expected_run.resolve() != training_run or child_store.verify(child.run_id) != child:
        raise ValueError("Physical evaluation checkpoint no longer matches its cohort attempt")

    passed = candidate.metrics.get("component_passed") is True
    if (candidate.outcome == "completed") != passed:
        raise ValueError("Physical evaluation outcome contradicts component result")
    if (
        candidate.metrics.get("release_qualified") is not False
        or candidate.metrics.get("independent_task_success", "missing") is not None
        or candidate.metrics.get("autonomous_workflow_success", "missing") is not None
        or type(candidate.metrics.get("teacher_actions_used")) is not bool
        or type(candidate.metrics.get("teacher_prefix_actions")) is not int
        or candidate.metrics["teacher_prefix_actions"] < 0
        or type(candidate.metrics.get("autonomous_skill_actions")) is not int
        or candidate.metrics["autonomous_skill_actions"] < 0
    ):
        raise ValueError("Physical evaluation omits required scope or action disclosure")
    process = _verified_process(store, candidate)
    return {
        "skill_id": skill,
        "evaluation_run_id": candidate.run_id,
        "evaluation_manifest_sha256": candidate.manifest_sha256,
        "process_run_id": process.run_id,
        "process_manifest_sha256": process.manifest_sha256,
        "training_attempt_run_id": wrapper.run_id,
        "training_manifest_sha256": child.manifest_sha256,
        "component_passed": passed,
        "outcome": candidate.outcome,
        "teacher_prefix_actions": candidate.metrics["teacher_prefix_actions"],
        "autonomous_skill_actions": candidate.metrics["autonomous_skill_actions"],
    }


def run_skill_physical_suite_report(protocol_path: Path):
    """Require, reverify and seal exactly one result for every frozen component."""

    protocol_path = Path(protocol_path).resolve(strict=True)
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_skill_physical_protocol(protocol_path)
    cohort_path = (protocol_path.parent / protocol.training_cohort_path).resolve(strict=True)
    cohort = load_training_cohort_protocol(cohort_path)
    store = EvidenceStore((cohort_path.parent / cohort.evidence_root).resolve())
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".skill-physical-coordinator.lock"):
        candidates = _candidate_manifests(store, protocol.manifest_sha256)
        missing = [skill for skill in COHORT_SKILLS if skill not in candidates]
        if missing:
            raise ValueError("Frozen physical suite is incomplete: " + ", ".join(missing))
        rows = [
            _validate_candidate(
                candidates[skill],
                store=store,
                protocol=protocol,
                protocol_file_sha256=protocol_file_sha256,
                cohort=cohort,
                cohort_path=cohort_path,
                skill=skill,
            )
            for skill in COHORT_SKILLS
        ]
        config = {
            "protocol_path": str(protocol_path),
            "protocol_sha256": protocol.manifest_sha256,
            "protocol_file_sha256": protocol_file_sha256,
            "evaluation_runs": [
                {
                    "skill_id": row["skill_id"],
                    "run_id": row["evaluation_run_id"],
                    "manifest_sha256": row["evaluation_manifest_sha256"],
                    "process_run_id": row["process_run_id"],
                    "process_manifest_sha256": row["process_manifest_sha256"],
                }
                for row in rows
            ],
        }
        reports = []
        for path in (store.root / "runs").glob("*/manifest.json"):
            try:
                with path.open() as stream:
                    header = stream.read(131072)
                if KIND not in header or protocol.manifest_sha256 not in header:
                    continue
                candidate = store.verify(path.parent.name)
            except (OSError, ValueError):
                continue
            if candidate.kind == KIND and candidate.config == config:
                reports.append(candidate)
        if len(reports) > 1:
            raise RuntimeError("Ambiguous repeated frozen physical suite reports")
        if reports:
            return reports[0]

        passed = sum(row["component_passed"] for row in rows)
        metrics = {
            "evaluations_complete": True,
            "components_total": len(rows),
            "components_passed": passed,
            "all_components_passed": passed == len(rows),
            "teacher_prepared_component_success": passed == len(rows),
            "independent_task_success": None,
            "autonomous_workflow_success": None,
            "release_qualified": False,
            "results": rows,
        }
        directory = store.new_run()
        (directory / "suite-results.json").write_bytes(canonical(metrics))
        return store.seal(
            directory,
            kind=KIND,
            outcome="completed" if metrics["all_components_passed"] else "failed",
            config=config,
            metrics=metrics,
            source=provenance(PROJECT_ROOT),
            claims=(
                ["All six frozen teacher-prepared authored-scene components passed"]
                if metrics["all_components_passed"]
                else []
            ),
        )
