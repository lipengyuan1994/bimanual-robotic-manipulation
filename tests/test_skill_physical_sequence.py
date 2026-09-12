"""CPU-only sequence orchestration fixtures; no model or MuJoCo execution."""

import json
from types import SimpleNamespace

import pytest

from bimanual import skill_physical_sequence as module
from bimanual.cli import main
from bimanual.evidence import EvidenceStore, digest_file
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS
from bimanual.training_cohort_runner import KIND as TRAINING_KIND


def setup(tmp_path, monkeypatch, *, missing=()):
    docs = tmp_path / "docs"
    docs.mkdir()
    protocol_path = docs / "physical.json"
    cohort_path = docs / "training.json"
    protocol_path.write_text("physical")
    cohort_path.write_text("training")
    configs = tuple(
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
        evidence_root="../evidence",
        configs=configs,
    )
    protocol = SimpleNamespace(
        manifest_sha256="b" * 64,
        training_cohort_path="training.json",
    )
    monkeypatch.setattr(module, "load_skill_physical_protocol", lambda path: protocol)
    monkeypatch.setattr(module, "load_training_cohort_protocol", lambda path: cohort)
    store = EvidenceStore(tmp_path / "evidence")
    for index, skill in enumerate(COHORT_SKILLS):
        if skill in missing:
            continue
        expected = module._expected_training(cohort_path, cohort, skill)
        directory = store.new_run()
        runner_sha256 = "c" * 64
        request = {
            "protocol_sha256": cohort.manifest_sha256,
            "protocol_file_sha256": digest_file(cohort_path),
            "skill_id": skill,
            "training": expected.model_dump(mode="json"),
            "runner_source_sha256": runner_sha256,
        }
        (directory / module.REQUEST).write_text(json.dumps(request))
        child_store = EvidenceStore(directory / "training-evidence")
        child_directory = child_store.new_run()
        child = child_store.seal(
            child_directory,
            kind="act_training",
            outcome="completed",
            config=expected.model_dump(mode="json"),
            metrics={"training_completed": True},
            source={},
            claims=[],
        )
        store.seal(
            directory,
            kind=TRAINING_KIND,
            outcome="completed",
            config=request,
            metrics={
                "training_complete": True,
                "child_run_id": child.run_id,
                "child_manifest_sha256": child.manifest_sha256,
            },
            source={
                "fixture": index,
                "source_files": {"src/bimanual/training_cohort_runner.py": runner_sha256},
            },
            claims=[],
        )
    return protocol_path, store


def result(store, skill, *, kind=module.EVALUATION_KIND, outcome="failed"):
    directory = store.new_run()
    return store.seal(
        directory,
        kind=kind,
        outcome=outcome,
        config={"skill_id": skill},
        metrics={"component_passed": outcome == "completed"},
        source={},
        claims=[],
    )


def test_runs_every_clean_case_in_order_and_preserves_component_failures(tmp_path, monkeypatch):
    protocol, store = setup(tmp_path, monkeypatch)
    calls = []

    def run(path, skill, attempt):
        calls.append((skill, attempt))
        return result(store, skill, outcome="completed" if skill == COHORT_SKILLS[-1] else "failed")

    suite = result(store, "suite", kind="six_skill_teacher_prepared_physical_suite_report")
    monkeypatch.setattr(module, "run_skill_physical_protocol", run)
    monkeypatch.setattr(module, "run_skill_physical_suite_report", lambda path: suite)
    report = module.run_skill_physical_sequence(protocol)
    assert [row[0] for row in calls] == list(COHORT_SKILLS)
    assert report["evaluations_complete"] is True
    assert len(report["evaluations"]) == len(COHORT_SKILLS)
    assert sum(row["component_passed"] for row in report["evaluations"]) == 1
    assert report["independent_task_success"] is None
    assert report["release_qualified"] is False
    assert report["suite"]["run_id"] == suite.run_id


def test_all_training_must_complete_before_first_evaluation(tmp_path, monkeypatch):
    protocol, _ = setup(tmp_path, monkeypatch, missing={COHORT_SKILLS[-1]})
    monkeypatch.setattr(
        module,
        "run_skill_physical_protocol",
        lambda *args: pytest.fail("Evaluation started before all training completed"),
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        module.run_skill_physical_sequence(protocol)


def test_process_failure_stops_without_suite_or_later_case(tmp_path, monkeypatch):
    protocol, store = setup(tmp_path, monkeypatch)
    calls = []

    def run(path, skill, attempt):
        calls.append(skill)
        return result(store, skill, kind=module.PROCESS_KIND, outcome="timed_out")

    monkeypatch.setattr(module, "run_skill_physical_protocol", run)
    monkeypatch.setattr(
        module,
        "run_skill_physical_suite_report",
        lambda path: pytest.fail("Partial sequence cannot aggregate"),
    )
    report = module.run_skill_physical_sequence(protocol)
    assert calls == [COHORT_SKILLS[0]]
    assert report["evaluations_complete"] is False and report["suite"] is None
    assert "adjudication" in report["reason"]


def test_duplicate_or_interrupted_training_attempt_fails_closed(tmp_path, monkeypatch):
    protocol, store = setup(tmp_path, monkeypatch)
    first = next((store.root / "runs").glob(f"*/{module.REQUEST}"))
    duplicate = store.new_run()
    duplicate.joinpath(module.REQUEST).write_bytes(first.read_bytes())
    duplicate.joinpath("manifest.json").write_bytes(first.with_name("manifest.json").read_bytes())
    with pytest.raises((RuntimeError, ValueError)):
        module.run_skill_physical_sequence(protocol)

    duplicate.joinpath("manifest.json").unlink()
    with pytest.raises(RuntimeError, match="interrupted"):
        module.run_skill_physical_sequence(protocol)


def test_explicitly_adjudicated_attempt_is_excluded_before_completion_check(tmp_path, monkeypatch):
    protocol, store = setup(tmp_path, monkeypatch)
    failed = store.new_run()
    failed.joinpath(module.REQUEST).write_text(
        json.dumps({"protocol_sha256": "a" * 64, "skill_id": "cup_pick_place"})
    )
    monkeypatch.setattr(
        module,
        "adjudicated_attempt_ids",
        lambda store, path, cohort, skill: {failed.name} if skill == "cup_pick_place" else set(),
    )
    monkeypatch.setattr(
        module,
        "run_skill_physical_protocol",
        lambda path, skill, attempt: result(store, skill),
    )
    suite = result(store, "suite", kind="six_skill_teacher_prepared_physical_suite_report")
    monkeypatch.setattr(module, "run_skill_physical_suite_report", lambda path: suite)
    report = module.run_skill_physical_sequence(protocol)
    assert report["evaluations_complete"] is True


def test_sequence_cli_preserves_incomplete_exit(tmp_path, monkeypatch, capsys):
    protocol = tmp_path / "physical.json"
    monkeypatch.setattr(
        module,
        "run_skill_physical_sequence",
        lambda path: {
            "profile": "six_skill_physical_sequence_v1",
            "evaluations_complete": False,
            "release_qualified": False,
        },
    )

    assert main(["skill-physical-protocol-run-all", str(protocol)]) == 1
    assert '"release_qualified": false' in capsys.readouterr().out
