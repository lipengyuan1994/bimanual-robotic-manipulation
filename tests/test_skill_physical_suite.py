"""Suite aggregation fixtures only; no models, rendering or physical execution."""

from types import SimpleNamespace

import pytest

from bimanual import skill_physical_suite as module
from bimanual.cli import main
from bimanual.evidence import EvidenceStore, digest_file
from bimanual.skill_physical_evaluation import SkillPhysicalEvaluationConfig
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS
from bimanual.training_cohort_runner import KIND as TRAINING_KIND


def setup_suite(tmp_path, monkeypatch, *, missing=(), failed=(), dirty_process=()):
    documents = tmp_path / "docs"
    documents.mkdir()
    protocol_path = documents / "physical.json"
    cohort_path = documents / "training.json"
    protocol_path.write_text("physical")
    cohort_path.write_text("training")
    training_configs = tuple(
        ACTTrainingConfig(
            dataset_path="../dataset",
            skill_views_path="views.json",
            skill_id=skill,
            device="mps",
        ).model_dump(mode="json")
        for skill in COHORT_SKILLS
    )
    cohort = SimpleNamespace(
        manifest_sha256="a" * 64,
        configs=training_configs,
        evidence_root="../evidence",
    )
    physical_configs = tuple(
        {
            "skill_id": skill,
            "device": "mps",
            "execute_chunk_steps": 2,
            "max_actions": 1000 + index,
            "wall_timeout_seconds": 1200.0,
        }
        for index, skill in enumerate(COHORT_SKILLS)
    )
    protocol = SimpleNamespace(
        manifest_sha256="b" * 64,
        training_cohort_path="training.json",
        configs=physical_configs,
    )
    monkeypatch.setattr(module, "load_skill_physical_protocol", lambda path: protocol)
    monkeypatch.setattr(module, "load_training_cohort_protocol", lambda path: cohort)
    store = EvidenceStore(tmp_path / "evidence")

    def training_child(store, wrapper, expected, cohort_sha256):
        child_store = EvidenceStore(store.directory(wrapper.run_id) / "training-evidence")
        child = child_store.verify(wrapper.metrics["child_run_id"])
        return child_store, child_store.directory(child.run_id), child

    monkeypatch.setattr(module, "_training_child", training_child)
    evaluations = []
    for index, skill in enumerate(COHORT_SKILLS):
        raw = training_configs[index]
        resolved = ACTTrainingConfig.model_validate(
            raw
            | {
                "dataset_path": (documents / raw["dataset_path"]).resolve(),
                "skill_views_path": (documents / raw["skill_views_path"]).resolve(),
            }
        )
        wrapper_directory = store.new_run()
        child_store = EvidenceStore(wrapper_directory / "training-evidence")
        child_directory = child_store.new_run()
        (child_directory / "checkpoint.txt").write_text("CPU fixture")
        child = child_store.seal(
            child_directory,
            kind="act_training",
            outcome="completed",
            config=resolved.model_dump(mode="json"),
            metrics={"training_completed": True},
            source={},
            claims=[],
        )
        store.seal(
            wrapper_directory,
            kind=TRAINING_KIND,
            outcome="completed",
            config={
                "skill_id": skill,
                "protocol_sha256": cohort.manifest_sha256,
                "training": resolved.model_dump(mode="json"),
            },
            metrics={
                "training_complete": True,
                "child_run_id": child.run_id,
                "child_manifest_sha256": child.manifest_sha256,
            },
            source={},
            claims=[],
        )
        if skill in missing:
            continue
        frozen = physical_configs[index]
        config = SkillPhysicalEvaluationConfig(
            training_run=child_directory,
            dataset_root=resolved.dataset_path,
            skill_views_path=resolved.skill_views_path,
            skill_id=skill,
            device=frozen["device"],
            max_actions=frozen["max_actions"],
            execute_chunk_steps=frozen["execute_chunk_steps"],
            wall_timeout_seconds=frozen["wall_timeout_seconds"],
            evaluation_protocol_sha256=protocol.manifest_sha256,
            evaluation_protocol_file_sha256=digest_file(protocol_path),
        )
        passed = skill not in failed
        directory = store.new_run()
        (directory / "fixture.txt").write_text("No physical execution")
        evaluation = store.seal(
            directory,
            kind=module.EVALUATION_KIND,
            outcome="completed" if passed else "failed",
            config=config.model_dump(mode="json"),
            metrics={
                "component_passed": passed,
                "teacher_actions_used": True,
                "teacher_prefix_actions": index,
                "autonomous_skill_actions": 10 + index,
                "independent_task_success": None,
                "autonomous_workflow_success": None,
                "release_qualified": False,
            },
            source={},
            claims=[],
        )
        evaluations.append(evaluation)
        process_directory = store.new_run()
        (process_directory / "fixture.txt").write_text("Clean CPU process wrapper")
        clean = skill not in dirty_process
        store.seal(
            process_directory,
            kind=module.PROCESS_KIND,
            outcome=evaluation.outcome if clean else "timed_out",
            config=module.SkillPhysicalProcessConfig(evaluation=config).model_dump(mode="json"),
            metrics={
                "process_complete": clean,
                "child_run_id": evaluation.run_id,
                "child_manifest_verified": True,
                "child_manifest_sha256": evaluation.manifest_sha256,
                "child_outcome": evaluation.outcome,
                "child_reaped": True,
                "child_exitcode": 0,
                "guardian_terminal_verified": True,
                "guardian_reaped": True,
                "guardian_exitcode": 0,
                "forced_interruption": not clean,
                "component_passed": passed and clean,
            },
            source={},
            claims=[],
        )
    return protocol_path, store, evaluations


def test_complete_suite_seals_all_results_and_preserves_failure(tmp_path, monkeypatch):
    failed = COHORT_SKILLS[2]
    protocol_path, store, evaluations = setup_suite(tmp_path, monkeypatch, failed={failed})
    result = module.run_skill_physical_suite_report(protocol_path)
    assert result.outcome == "failed" and result.claims == []
    assert result.metrics["evaluations_complete"] is True
    assert result.metrics["components_passed"] == len(COHORT_SKILLS) - 1
    assert result.metrics["autonomous_workflow_success"] is None
    assert result.metrics["release_qualified"] is False
    assert [row["evaluation_run_id"] for row in result.metrics["results"]] == [
        evaluation.run_id for evaluation in evaluations
    ]
    assert module.run_skill_physical_suite_report(protocol_path) == result
    assert store.verify(result.run_id) == result


def test_missing_result_cannot_create_partial_suite_report(tmp_path, monkeypatch):
    protocol_path, store, _ = setup_suite(tmp_path, monkeypatch, missing={COHORT_SKILLS[-1]})
    with pytest.raises(ValueError, match="incomplete"):
        module.run_skill_physical_suite_report(protocol_path)
    assert not [row for row in store.list_runs(limit=100) if row.get("kind") == module.KIND]


def test_all_component_passes_remain_teacher_prepared_only(tmp_path, monkeypatch):
    protocol_path, _, _ = setup_suite(tmp_path, monkeypatch)
    result = module.run_skill_physical_suite_report(protocol_path)
    assert result.outcome == "completed"
    assert result.metrics["all_components_passed"] is True
    assert result.metrics["teacher_prepared_component_success"] is True
    assert result.metrics["independent_task_success"] is None
    assert result.metrics["autonomous_workflow_success"] is None
    assert result.metrics["release_qualified"] is False
    assert result.claims == ["All six frozen teacher-prepared authored-scene components passed"]


def test_duplicate_result_is_ambiguous(tmp_path, monkeypatch):
    protocol_path, store, evaluations = setup_suite(tmp_path, monkeypatch)
    source = evaluations[0]
    directory = store.new_run()
    (directory / "fixture.txt").write_text("Duplicate CPU fixture")
    store.seal(
        directory,
        kind=source.kind,
        outcome=source.outcome,
        config=source.config,
        metrics=source.metrics,
        source={},
        claims=[],
    )
    with pytest.raises(RuntimeError, match="Ambiguous repeated"):
        module.run_skill_physical_suite_report(protocol_path)


def test_interrupted_process_child_cannot_enter_suite(tmp_path, monkeypatch):
    dirty = COHORT_SKILLS[1]
    protocol_path, _, _ = setup_suite(tmp_path, monkeypatch, dirty_process={dirty})
    with pytest.raises(ValueError, match="did not finish cleanly"):
        module.run_skill_physical_suite_report(protocol_path)


def test_cli_returns_failure_for_complete_but_failed_suite(tmp_path, monkeypatch, capsys):
    result = SimpleNamespace(
        outcome="failed",
        model_dump=lambda **kwargs: {"outcome": "failed", "release_qualified": False},
    )
    monkeypatch.setattr(module, "run_skill_physical_suite_report", lambda path: result)
    assert main(["skill-physical-suite-report", str(tmp_path / "protocol.json")]) == 1
    assert '"release_qualified": false' in capsys.readouterr().out
