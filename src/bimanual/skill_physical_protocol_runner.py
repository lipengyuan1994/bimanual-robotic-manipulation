"""Run one frozen teacher-prepared physical evaluation without outcome retries."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.evidence import EvidenceStore, digest_file
from bimanual.skill_physical_evaluation import (
    SkillPhysicalEvaluationConfig,
    run_skill_physical_evaluation,
)
from bimanual.skill_physical_protocol import load_skill_physical_protocol
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.training_cohort_runner import KIND as TRAINING_ATTEMPT_KIND
from bimanual.worker_lease import WorkerLease

KIND = "learned_skill_teacher_prepared_physical_evaluation"


def _training_child(store: EvidenceStore, wrapper, expected: ACTTrainingConfig, cohort_sha256: str):
    if (
        wrapper.kind != TRAINING_ATTEMPT_KIND
        or wrapper.outcome != "completed"
        or wrapper.config.get("skill_id") != expected.skill_id
        or wrapper.config.get("protocol_sha256") != cohort_sha256
        or wrapper.config.get("training") != expected.model_dump(mode="json")
        or wrapper.metrics.get("training_complete") is not True
    ):
        raise ValueError("Training attempt is not a completed matching cohort skill")
    child_id = wrapper.metrics.get("child_run_id")
    child_sha256 = wrapper.metrics.get("child_manifest_sha256")
    child_store = EvidenceStore(store.directory(wrapper.run_id) / "training-evidence")
    child = child_store.verify(child_id)
    if (
        child.manifest_sha256 != child_sha256
        or child.kind != "act_training"
        or child.outcome != "completed"
        or child.config != expected.model_dump(mode="json")
    ):
        raise ValueError("Training child does not match the frozen cohort configuration")
    return child_store, child_store.directory(child.run_id), child


def run_skill_physical_protocol(protocol_path: Path, skill_id: str, training_attempt_id: str):
    protocol_path = Path(protocol_path).resolve(strict=True)
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_skill_physical_protocol(protocol_path)
    if skill_id not in COHORT_SKILLS:
        raise ValueError("Unknown six-skill physical evaluation member")
    cohort_path = (protocol_path.parent / protocol.training_cohort_path).resolve(strict=True)
    cohort = load_training_cohort_protocol(cohort_path)
    raw_training = cohort.configs[COHORT_SKILLS.index(skill_id)]
    training = ACTTrainingConfig.model_validate(
        raw_training
        | {
            "dataset_path": (cohort_path.parent / raw_training["dataset_path"]).resolve(),
            "skill_views_path": (cohort_path.parent / raw_training["skill_views_path"]).resolve(),
        }
    )
    store = EvidenceStore((cohort_path.parent / cohort.evidence_root).resolve())
    store.root.mkdir(parents=True, exist_ok=True)
    wrapper = store.verify(training_attempt_id)
    child_store, training_run, child = _training_child(
        store, wrapper, training, cohort.manifest_sha256
    )
    config_raw = protocol.configs[COHORT_SKILLS.index(skill_id)]
    config = SkillPhysicalEvaluationConfig(
        training_run=training_run,
        dataset_root=training.dataset_path,
        skill_views_path=training.skill_views_path,
        skill_id=skill_id,
        device=config_raw["device"],
        max_actions=config_raw["max_actions"],
        execute_chunk_steps=config_raw["execute_chunk_steps"],
        wall_timeout_seconds=config_raw["wall_timeout_seconds"],
        evaluation_protocol_sha256=protocol.manifest_sha256,
        evaluation_protocol_file_sha256=protocol_file_sha256,
    )
    with WorkerLease.acquire(store.root / ".skill-physical-coordinator.lock"):
        matches = []
        expected = config.model_dump(mode="json")
        for manifest_path in (store.root / "runs").glob("*/manifest.json"):
            try:
                recorded = json.loads(manifest_path.read_text())
            except (OSError, ValueError):
                continue
            if (
                recorded.get("kind") == KIND
                and recorded.get("config", {}).get("evaluation_protocol_sha256")
                == protocol.manifest_sha256
                and recorded["config"].get("skill_id") == skill_id
                and recorded["config"].get("training_run") == str(training_run)
            ):
                matches.append(store.verify(manifest_path.parent.name))
        if len(matches) > 1:
            raise RuntimeError("Ambiguous repeated physical evaluations for one frozen candidate")
        if matches:
            candidate = matches[0]
            if candidate.config != expected or (
                (candidate.outcome == "completed")
                != (candidate.metrics.get("component_passed") is True)
            ):
                raise ValueError("Existing physical evaluation contradicts the frozen request")
            return candidate
        result = run_skill_physical_evaluation(
            config,
            store=store,
            project_root=Path(__file__).resolve().parents[2],
        )
        if result.config != expected:
            raise ValueError("Physical evaluation result changed its frozen configuration")
        if wrapper != store.verify(wrapper.run_id) or child != child_store.verify(child.run_id):
            raise ValueError("Training candidate changed during physical evaluation")
        return result
