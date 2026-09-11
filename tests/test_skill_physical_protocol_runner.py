"""Protocol-runner lifecycle fixtures; no model, rendering, or physical execution."""

from types import SimpleNamespace

import pytest

from bimanual import skill_physical_protocol_runner as module
from bimanual.cli import main
from bimanual.evidence import EvidenceStore
from bimanual.training import ACTTrainingConfig
from bimanual.training_cohort import COHORT_SKILLS
from bimanual.training_cohort_runner import KIND as TRAINING_KIND


def setup(
    tmp_path,
    monkeypatch,
    *,
    evaluation_outcome="failed",
    process_without_child=False,
    interrupted_after_child=False,
):
    skill = COHORT_SKILLS[0]
    documents = tmp_path / "docs"
    documents.mkdir()
    protocol_path = documents / "physical.json"
    cohort_path = documents / "training.json"
    protocol_path.write_text("physical")
    cohort_path.write_text("training")
    raw = ACTTrainingConfig(
        dataset_path="../dataset",
        skill_views_path="views.json",
        skill_id=skill,
        device="mps",
    ).model_dump(mode="json")
    cohort = SimpleNamespace(
        manifest_sha256="a" * 64,
        configs=tuple(raw for _ in COHORT_SKILLS),
        evidence_root="../evidence",
    )
    physical_config = {
        "skill_id": skill,
        "device": "mps",
        "execute_chunk_steps": 2,
        "max_actions": 1900,
        "wall_timeout_seconds": 1200.0,
    }
    protocol = SimpleNamespace(
        manifest_sha256="b" * 64,
        training_cohort_path="training.json",
        configs=tuple(physical_config for _ in COHORT_SKILLS),
    )
    monkeypatch.setattr(module, "load_skill_physical_protocol", lambda path: protocol)
    monkeypatch.setattr(module, "load_training_cohort_protocol", lambda path: cohort)

    store = EvidenceStore(tmp_path / "evidence")
    wrapper_directory = store.new_run()
    child_store = EvidenceStore(wrapper_directory / "training-evidence")
    child_directory = child_store.new_run()
    (child_directory / "checkpoint.txt").write_text("CPU fixture")
    resolved = ACTTrainingConfig.model_validate(
        raw
        | {
            "dataset_path": (documents / raw["dataset_path"]).resolve(),
            "skill_views_path": (documents / raw["skill_views_path"]).resolve(),
        }
    )
    child = child_store.seal(
        child_directory,
        kind="act_training",
        outcome="completed",
        config=resolved.model_dump(mode="json"),
        metrics={"training_completed": True},
        source={},
        claims=[],
    )
    wrapper = store.seal(
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
    calls = []

    def evaluate(process_config, *, store, **kwargs):
        config = process_config.evaluation
        calls.append(config)
        if process_without_child:
            process_directory = store.new_run()
            (process_directory / "fixture.txt").write_text("Timed out before child result")
            return store.seal(
                process_directory,
                kind=module.PROCESS_KIND,
                outcome="timed_out",
                config=process_config.model_dump(mode="json"),
                metrics={
                    "child_run_id": None,
                    "child_manifest_verified": False,
                    "child_manifest_sha256": None,
                },
                source={},
                claims=[],
            )
        child_directory = store.new_run()
        (child_directory / "fixture.txt").write_text("No physical evaluation")
        child = store.seal(
            child_directory,
            kind=module.KIND,
            outcome=evaluation_outcome,
            config=config.model_dump(mode="json"),
            metrics={"component_passed": evaluation_outcome == "completed"},
            source={},
            claims=[],
        )
        process_directory = store.new_run()
        (process_directory / "fixture.txt").write_text("No spawned process")
        return store.seal(
            process_directory,
            kind=module.PROCESS_KIND,
            outcome=evaluation_outcome,
            config=process_config.model_dump(mode="json"),
            metrics={
                "child_run_id": child.run_id,
                "child_manifest_verified": True,
                "child_manifest_sha256": child.manifest_sha256,
                "child_outcome": child.outcome,
                "process_complete": not interrupted_after_child,
                "child_reaped": True,
                "child_exitcode": 0,
                "guardian_terminal_verified": True,
                "guardian_reaped": True,
                "guardian_exitcode": 0,
                "forced_interruption": interrupted_after_child,
                "component_passed": evaluation_outcome == "completed"
                and not interrupted_after_child,
            },
            source={},
            claims=[],
        )

    monkeypatch.setattr(module, "run_skill_physical_process", evaluate)
    return protocol_path, skill, wrapper, calls


def test_runs_once_with_exact_protocol_and_training_binding(tmp_path, monkeypatch):
    protocol_path, skill, wrapper, calls = setup(tmp_path, monkeypatch)
    first = module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    second = module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    assert first == second and first.outcome == "failed"
    assert len(calls) == 1
    assert calls[0].evaluation_protocol_sha256 == "b" * 64
    assert calls[0].skill_id == skill and calls[0].max_actions == 1900


def test_rejects_wrong_training_skill_before_evaluation(tmp_path, monkeypatch):
    protocol_path, skill, wrapper, calls = setup(tmp_path, monkeypatch)
    store = EvidenceStore(tmp_path / "evidence")
    directory = store.directory(wrapper.run_id)
    # The wrapper seal makes this mutation detectable before any evaluator call.
    import json

    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["config"]["skill_id"] = COHORT_SKILLS[1]
    (directory / "manifest.json").write_text(json.dumps(manifest))
    try:
        module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    except ValueError:
        pass
    else:
        raise AssertionError("Tampered training wrapper was accepted")
    assert calls == []


def test_timed_out_process_is_preserved_without_automatic_retry(tmp_path, monkeypatch):
    protocol_path, skill, wrapper, calls = setup(tmp_path, monkeypatch, process_without_child=True)
    first = module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    second = module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    assert first == second and first.kind == module.PROCESS_KIND
    assert first.outcome == "timed_out" and len(calls) == 1


def test_interrupted_process_cannot_expose_its_completed_child(tmp_path, monkeypatch):
    protocol_path, skill, wrapper, calls = setup(
        tmp_path,
        monkeypatch,
        evaluation_outcome="completed",
        interrupted_after_child=True,
    )
    result = module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    assert result.kind == module.PROCESS_KIND
    assert result.metrics["process_complete"] is False
    assert result.metrics["forced_interruption"] is True
    assert len(calls) == 1


def test_interrupted_unsealed_process_blocks_automatic_retry(tmp_path, monkeypatch):
    protocol_path, skill, wrapper, calls = setup(tmp_path, monkeypatch)
    store = EvidenceStore(tmp_path / "evidence")
    training_run = (
        store.directory(wrapper.run_id) / "training-evidence/runs" / wrapper.metrics["child_run_id"]
    )
    evaluation = module.SkillPhysicalEvaluationConfig(
        training_run=training_run,
        dataset_root=(tmp_path / "dataset").resolve(),
        skill_views_path=(tmp_path / "docs/views.json").resolve(),
        skill_id=skill,
        device="mps",
        max_actions=1900,
        execute_chunk_steps=2,
        wall_timeout_seconds=1200,
        evaluation_protocol_sha256="b" * 64,
        evaluation_protocol_file_sha256=module.digest_file(protocol_path),
    )
    interrupted = store.new_run()
    (interrupted / "config.json").write_text(
        module.SkillPhysicalProcessConfig(evaluation=evaluation).model_dump_json()
    )
    with pytest.raises(RuntimeError, match="manual adjudication"):
        module.run_skill_physical_protocol(protocol_path, skill, wrapper.run_id)
    assert calls == []


def test_protocol_run_cli_preserves_failed_component(tmp_path, monkeypatch, capsys):
    seen = []
    result = SimpleNamespace(outcome="failed", model_dump=lambda **kwargs: {"outcome": "failed"})
    monkeypatch.setattr(
        module,
        "run_skill_physical_protocol",
        lambda path, skill, attempt: seen.append((path, skill, attempt)) or result,
    )
    path = tmp_path / "protocol.json"
    assert (
        main(
            [
                "skill-physical-protocol-run",
                str(path),
                "--skill",
                "bar_place_and_return",
                "--training-attempt",
                "attempt-1",
            ]
        )
        == 1
    )
    assert seen == [(path, "bar_place_and_return", "attempt-1")]
    assert '"outcome": "failed"' in capsys.readouterr().out
