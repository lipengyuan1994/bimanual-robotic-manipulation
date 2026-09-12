from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bimanual.cli import main
from bimanual.evidence import EvidenceStore
from bimanual.planner import seal_model
from bimanual.scene_variant_protocol import create_dinner_perturbation_protocol
from bimanual.scene_variant_suite import prepare_scene_variant_suite
from bimanual.workflow_manifest import SKILLS
from bimanual.workflow_release_protocol import (
    WorkflowReleaseProtocol,
    create_workflow_release_protocol,
    load_workflow_release_protocol,
)


def _model(root):
    root.mkdir()
    (root / "config.json").write_text('{"model_type":"qwen3_vl"}')
    for name in ("tokenizer_config.json", "preprocessor_config.json"):
        (root / name).write_text("{}")
    (root / "model.safetensors").write_bytes(b"release protocol fixture")
    seal_model(root, "a" * 40)


def _workflow():
    return SimpleNamespace(
        bindings=tuple(SimpleNamespace(view=SimpleNamespace(skill_id=skill)) for skill in SKILLS),
        manifest=SimpleNamespace(
            manifest_sha256="f" * 64,
            execution_profile_sha256="e" * 64,
            execution=tuple(SimpleNamespace(skill_id=skill) for skill in SKILLS),
        ),
    )


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    import bimanual.workflow_release_protocol as module

    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text('{"fixture":"workflow"}')
    workflow = _workflow()
    monkeypatch.setattr(module, "load_workflow_manifest", lambda path: workflow)
    model = tmp_path / "model"
    _model(model)
    perturbation = tmp_path / "perturbation.json"
    create_dinner_perturbation_protocol(perturbation)
    store = EvidenceStore(tmp_path / "evidence")
    suite = prepare_scene_variant_suite(
        protocol_path=perturbation, store=store, project_root=tmp_path
    )
    return SimpleNamespace(
        workflow_path=workflow_path,
        workflow=workflow,
        model=model,
        perturbation=perturbation,
        suite=store.directory(suite.run_id),
        destination=tmp_path / "release.json",
    )


def test_release_protocol_freezes_candidate_model_scene_suite_and_runtime(inputs, capsys):
    value = inputs
    created = create_workflow_release_protocol(
        workflow_manifest=value.workflow_path,
        planner_model_root=value.model,
        scene_suite_run=value.suite,
        perturbation_protocol_path=value.perturbation,
        instruction="Set the dinner table and perform the hand-off.",
        destination=value.destination,
    )
    loaded = load_workflow_release_protocol(value.destination)
    assert loaded == created
    assert len(loaded.cases) == 16
    assert loaded.cases[0].case_id == "placement-29001"
    assert loaded.cases[-1].case_id == "combined-30010"
    assert loaded.policy_device == loaded.planner_device == "mps"
    assert loaded.camera_profile == "overhead1920_wrist480_v1"
    assert loaded.intel_validated is False
    assert loaded.release_success is None
    assert "workflow_release_protocol.py" in loaded.runtime_sources
    assert main(["workflow-release-check", str(value.destination)]) == 0
    assert json.loads(capsys.readouterr().out)["manifest_sha256"] == created.manifest_sha256


def test_changed_candidate_is_rejected_after_freeze(inputs):
    value = inputs
    create_workflow_release_protocol(
        workflow_manifest=value.workflow_path,
        planner_model_root=value.model,
        scene_suite_run=value.suite,
        perturbation_protocol_path=value.perturbation,
        instruction="Set the dinner table.",
        destination=value.destination,
    )
    value.workflow_path.write_text('{"fixture":"changed"}')
    with pytest.raises(ValueError, match="candidate changed"):
        load_workflow_release_protocol(value.destination)


def test_noncanonical_checkpoint_order_fails_before_protocol_creation(inputs, monkeypatch):
    import bimanual.workflow_release_protocol as module

    value = inputs
    bad = _workflow()
    bad.bindings = tuple(reversed(bad.bindings))
    monkeypatch.setattr(module, "load_workflow_manifest", lambda path: bad)
    with pytest.raises(ValueError, match="canonical seven-skill"):
        create_workflow_release_protocol(
            workflow_manifest=value.workflow_path,
            planner_model_root=value.model,
            scene_suite_run=value.suite,
            perturbation_protocol_path=value.perturbation,
            instruction="Set the dinner table.",
            destination=value.destination,
        )
    assert not value.destination.exists()


def test_protocol_body_cannot_claim_intel_or_release_success(inputs):
    value = inputs
    created = create_workflow_release_protocol(
        workflow_manifest=value.workflow_path,
        planner_model_root=value.model,
        scene_suite_run=value.suite,
        perturbation_protocol_path=value.perturbation,
        instruction="Set the dinner table.",
        destination=value.destination,
    )
    data = created.model_dump(mode="json")
    data["intel_validated"] = True
    with pytest.raises(ValueError):
        WorkflowReleaseProtocol.model_validate(data)
    data = created.model_dump(mode="json")
    data["release_success"] = True
    with pytest.raises(ValueError):
        WorkflowReleaseProtocol.model_validate(data)
