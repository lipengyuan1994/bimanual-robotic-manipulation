"""Run one frozen teacher-prepared physical evaluation without outcome retries."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.evidence import EvidenceStore, digest_file
from bimanual.skill_physical_evaluation import (
    SkillPhysicalEvaluationConfig,
)
from bimanual.skill_physical_process import (
    PROCESS_KIND,
    SkillPhysicalProcessConfig,
    run_skill_physical_process,
)
from bimanual.skill_physical_protocol import load_skill_physical_protocol
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.training_cohort_runner import KIND as TRAINING_ATTEMPT_KIND
from bimanual.worker_lease import WorkerLease

KIND = "learned_skill_teacher_prepared_physical_evaluation"


def _clean_process_child(process, child) -> bool:
    """Return true only when the process wrapper certifies a clean child result."""

    return (
        process.kind == PROCESS_KIND
        and process.metrics.get("process_complete") is True
        and process.metrics.get("child_manifest_verified") is True
        and process.metrics.get("child_run_id") == child.run_id
        and process.metrics.get("child_manifest_sha256") == child.manifest_sha256
        and process.metrics.get("child_outcome") == child.outcome
        and process.metrics.get("child_reaped") is True
        and process.metrics.get("child_exitcode") == 0
        and process.metrics.get("guardian_terminal_verified") is True
        and process.metrics.get("guardian_reaped") is True
        and process.metrics.get("guardian_exitcode") == 0
        and process.metrics.get("forced_interruption") is False
        and process.metrics.get("component_passed")
        == (child.metrics.get("component_passed") is True)
        and process.outcome == child.outcome
    )


def _reverify_protocol(path: Path, file_sha256: str, manifest_sha256: str) -> None:
    if digest_file(path) != file_sha256:
        raise ValueError("Physical evaluation protocol file changed during execution")
    if load_skill_physical_protocol(path).manifest_sha256 != manifest_sha256:
        raise ValueError("Physical evaluation protocol sources changed during execution")


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
        process_matches = []
        expected = config.model_dump(mode="json")
        process_expected = SkillPhysicalProcessConfig(evaluation=config).model_dump(mode="json")
        interrupted = []
        for config_path in (store.root / "runs").glob("*/config.json"):
            if (config_path.parent / "manifest.json").exists():
                continue
            try:
                with config_path.open() as stream:
                    header = stream.read(131072)
                if not all(
                    token in header
                    for token in (protocol.manifest_sha256, skill_id, str(training_run))
                ):
                    continue
                recorded = json.loads(config_path.read_text())
            except (OSError, ValueError):
                raise ValueError(
                    "Matching interrupted physical process config is unreadable"
                ) from None
            if recorded != process_expected:
                raise ValueError("Interrupted physical process contradicts the frozen request")
            interrupted.append(config_path.parent.name)
        if interrupted:
            raise RuntimeError(
                "Interrupted physical process requires manual adjudication; no automatic retry"
            )
        for manifest_path in (store.root / "runs").glob("*/manifest.json"):
            try:
                with manifest_path.open() as stream:
                    header = stream.read(131072)
                if (
                    not all(
                        token in header
                        for token in (protocol.manifest_sha256, skill_id, str(training_run))
                    )
                    or KIND not in header
                    and PROCESS_KIND not in header
                ):
                    continue
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
            if (
                recorded.get("kind") == PROCESS_KIND
                and recorded.get("config", {})
                .get("evaluation", {})
                .get("evaluation_protocol_sha256")
                == protocol.manifest_sha256
                and recorded["config"]["evaluation"].get("skill_id") == skill_id
                and recorded["config"]["evaluation"].get("training_run") == str(training_run)
            ):
                process_matches.append(store.verify(manifest_path.parent.name))
        if len(matches) > 1:
            raise RuntimeError("Ambiguous repeated physical evaluations for one frozen candidate")
        if len(process_matches) > 1:
            raise RuntimeError("Ambiguous repeated physical evaluation processes")
        if process_matches:
            process = process_matches[0]
            if process.config != process_expected:
                raise ValueError("Existing physical process contradicts the frozen request")
            child_id = process.metrics.get("child_run_id")
            if child_id is None:
                if matches:
                    raise ValueError("Physical process omitted the discovered child evaluation")
                _reverify_protocol(
                    protocol_path, protocol_file_sha256, protocol.manifest_sha256
                )
                return process
            child_result = store.verify(child_id)
            if (
                process.metrics.get("child_manifest_verified") is not True
                or process.metrics.get("child_manifest_sha256") != child_result.manifest_sha256
                or len(matches) != 1
                or matches[0] != child_result
            ):
                raise ValueError("Physical process child binding is incomplete or contradictory")
            _reverify_protocol(
                protocol_path, protocol_file_sha256, protocol.manifest_sha256
            )
            return child_result if _clean_process_child(process, child_result) else process
        if matches:
            raise RuntimeError(
                "Physical evaluation child has no sealed process wrapper; "
                "manual adjudication required"
            )
        process = run_skill_physical_process(
            SkillPhysicalProcessConfig(evaluation=config),
            store=store,
            project_root=Path(__file__).resolve().parents[2],
        )
        _reverify_protocol(protocol_path, protocol_file_sha256, protocol.manifest_sha256)
        child_id = process.metrics.get("child_run_id")
        if isinstance(child_id, str):
            child_result = store.verify(child_id)
            if process.metrics.get("child_manifest_sha256") != child_result.manifest_sha256:
                raise ValueError("Physical process child binding changed after execution")
            result = child_result if _clean_process_child(process, child_result) else process
        else:
            result = process
        if result.config != expected:
            if result.kind != PROCESS_KIND or result.config.get("evaluation") != expected:
                raise ValueError("Physical evaluation result changed its frozen configuration")
        if wrapper != store.verify(wrapper.run_id) or child != child_store.verify(child.run_id):
            raise ValueError("Training candidate changed during physical evaluation")
        return result
