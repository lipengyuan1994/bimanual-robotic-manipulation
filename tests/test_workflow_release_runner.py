from __future__ import annotations

from types import SimpleNamespace

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.scene_variant_suite import SceneVariantSuiteEntry
from bimanual.workflow_release_runner import run_workflow_release_case
from bimanual.workflow_release_suite import _validate_wrapper


def _fixture(tmp_path, monkeypatch, *, score_success=True, process_error=False):
    import bimanual.workflow_release_runner as module

    protocol_path = tmp_path / "release.json"
    protocol_path.write_text('{"fixture":"release"}')
    workflow = tmp_path / "workflow.json"
    workflow.write_text("{}")
    model = tmp_path / "model"
    model.mkdir()
    suite = tmp_path / "scene-evidence" / "runs" / "suite"
    suite.mkdir(parents=True)
    scene = suite.parent / "scene-child"
    scene.mkdir()
    case = SceneVariantSuiteEntry(
        case_id="placement-29001",
        family="placement",
        seed=29001,
        run_id=scene.name,
        manifest_sha256="a" * 64,
        scene_sha256="b" * 64,
        layout_sha256="c" * 64,
    )
    protocol = SimpleNamespace(
        manifest_sha256="d" * 64,
        cases=(case,),
        scene_suite_run=str(suite.relative_to(tmp_path)),
        workflow_manifest=workflow.name,
        planner_model_root=model.name,
        instruction="Set the dinner table.",
        policy_device="mps",
        planner_device="mps",
        camera_profile="overhead1920_wrist480_v1",
        wall_timeout_seconds=1800,
        step_timeout_seconds=300,
        max_tokens=384,
        selection_rule="evaluate_every_frozen_scene_once_in_declared_order",
    )
    monkeypatch.setattr(module, "load_workflow_release_protocol", lambda path: protocol)
    calls = []

    def process(config, *, store, project_root):
        calls.append(config)
        if process_error:
            raise RuntimeError("simulated interruption")
        process_directory = store.new_run()
        child_store = EvidenceStore(process_directory / "child-evidence")
        child_directory = child_store.new_run()
        (child_directory / "fixture.txt").write_text("workflow trace")
        child = child_store.seal(
            child_directory,
            kind="dinner_workflow_execution",
            outcome="completed",
            config=config.execution.model_dump(mode="json"),
            metrics={
                "state": "execution_complete",
                "execution_complete": True,
                "independent_task_success": None,
            },
            source={},
            claims=[],
        )
        return store.seal(
            process_directory,
            kind="dinner_workflow_process",
            outcome="completed",
            config=config.model_dump(mode="json"),
            metrics={
                "child_run_id": child.run_id,
                "child_manifest_sha256": child.manifest_sha256,
                "child_manifest_verified": True,
                "child_outcome": child.outcome,
                "child_reaped": True,
                "child_exitcode": 0,
                "guardian_terminal_verified": True,
                "guardian_reaped": True,
                "guardian_exitcode": 0,
                "forced_interruption": False,
                "execution_complete": True,
            },
            source={},
            claims=[],
        )

    def evaluate(run_id, *, store, project_root):
        source = store.verify(run_id)
        directory = store.new_run()
        (directory / "source.txt").write_text(source.manifest_sha256)
        return store.seal(
            directory,
            kind="dinner_evaluation",
            outcome="completed" if score_success else "failed",
            config={"source_run": run_id},
            metrics={"score": {"independent_task_success": score_success}},
            source={},
            claims=[],
        )

    monkeypatch.setattr(module, "run_workflow_process", process)
    monkeypatch.setattr(module, "evaluate_dinner_run", evaluate)
    return protocol_path, protocol, EvidenceStore(tmp_path / "evidence"), calls


def test_runs_and_scores_one_frozen_case_exactly_once(tmp_path, monkeypatch):
    protocol_path, protocol, store, calls = _fixture(tmp_path, monkeypatch)
    first = run_workflow_release_case(
        protocol_path, "placement-29001", store=store, project_root=tmp_path
    )
    second = run_workflow_release_case(
        protocol_path, "placement-29001", store=store, project_root=tmp_path
    )
    assert first == second
    assert len(calls) == 1
    assert first.outcome == "completed"
    assert first.metrics["execution_complete"] is True
    assert first.metrics["process_transport_clean"] is True
    assert first.metrics["independent_task_success"] is True
    assert first.metrics["intel_validated"] is False
    assert first.metrics["release_success"] is None
    row = _validate_wrapper(store, first, protocol, protocol.cases[0])
    assert row["independent_task_success"] is True


def test_failed_independent_score_is_preserved(tmp_path, monkeypatch):
    protocol, _, store, calls = _fixture(tmp_path, monkeypatch, score_success=False)
    result = run_workflow_release_case(
        protocol, "placement-29001", store=store, project_root=tmp_path
    )
    assert len(calls) == 1
    assert result.outcome == "failed"
    assert result.metrics["execution_complete"] is True
    assert result.metrics["independent_task_success"] is False
    assert result.claims == []


def test_interrupted_reservation_blocks_automatic_retry(tmp_path, monkeypatch):
    protocol, _, store, calls = _fixture(tmp_path, monkeypatch, process_error=True)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_workflow_release_case(protocol, "placement-29001", store=store, project_root=tmp_path)
    with pytest.raises(RuntimeError, match="manual adjudication"):
        run_workflow_release_case(protocol, "placement-29001", store=store, project_root=tmp_path)
    assert len(calls) == 1


def test_unknown_case_fails_before_reservation(tmp_path, monkeypatch):
    protocol, _, store, calls = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not a member"):
        run_workflow_release_case(protocol, "mass-29001", store=store, project_root=tmp_path)
    assert calls == []
    assert not (store.root / "runs").exists()
