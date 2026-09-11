"""Synthetic sealed cohorts test lineage; no learned workflow is claimed."""

import hashlib
import json
from dataclasses import replace

import pytest
from test_skill_registry import dataset, training_fixture  # noqa: F401
from test_skill_views import synthetic_export  # noqa: F401

from bimanual.evidence import canonical
from bimanual.workflow_manifest import (
    SKILLS,
    WorkflowManifest,
    create_workflow_manifest,
    load_workflow_manifest,
    preload_workflow,
)


@pytest.fixture(scope="module")
def cohort(tmp_path_factory, dataset):  # noqa: F811
    root = tmp_path_factory.mktemp("workflow")
    runs = {skill: training_fixture(root / skill, dataset, skill=skill) for skill in SKILLS}
    return create_workflow_manifest(dataset[0], dataset[1], runs, root / "workflow.json")


def mutated(cohort, tmp_path, mutate):
    body = cohort.manifest.model_dump(mode="json", exclude={"manifest_sha256"})
    # Relocated diagnostic manifests explicitly resolve the original artifact paths.
    for name in ("dataset_root", "skill_views_path"):
        body[name] = str((cohort.path.parent / body[name]).resolve())
    for entry in body["checkpoints"]:
        entry["training_run"] = str((cohort.path.parent / entry["training_run"]).resolve())
    mutate(body)
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(body))
    return path


def test_complete_cohort_binds_seven_checkpoints_and_final_parking(cohort):
    assert tuple(b.view.skill_id for b in cohort.bindings) == SKILLS
    assert tuple(r.final_parking for r in cohort.successor_references) == (False,) * 6 + (True,)
    assert cohort.successor_references[-1].successor_skill_id is None
    assert cohort.reverify() == cohort
    report = cohort.report()
    assert report["release_available"] is False
    assert report["learned_workflow_success"] is None
    # File digests and canonical body seals have distinct names and meanings.
    assert (
        cohort.manifest.export_file_sha256 != cohort.successor_references[0].export_manifest_sha256
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b["checkpoints"].pop(),
        lambda b: b["checkpoints"].reverse(),
        lambda b: b["checkpoints"][1].update(skill_id=b["checkpoints"][0]["skill_id"]),
    ],
)
def test_incomplete_duplicate_or_reordered_cohort_rejected(cohort, tmp_path, mutation):
    path = mutated(cohort, tmp_path, mutation)
    with pytest.raises(ValueError):
        load_workflow_manifest(path)


@pytest.mark.parametrize("field", ["checkpoint_sha256", "training_manifest_sha256"])
def test_exact_checkpoint_identity_required(cohort, tmp_path, field):
    path = mutated(cohort, tmp_path, lambda b: b["checkpoints"][0].update({field: "0" * 64}))
    with pytest.raises(ValueError, match="identity"):
        load_workflow_manifest(path)


def test_changed_manifest_does_not_pass_old_body_seal(cohort):
    value = cohort.manifest.model_dump(mode="json")
    value["dataset_root"] += "-changed"
    with pytest.raises(ValueError, match="body seal"):
        WorkflowManifest.model_validate(value)


def test_dataset_hash_mismatch_stops_before_checkpoint_load(cohort, tmp_path, monkeypatch):
    path = mutated(cohort, tmp_path, lambda b: b.update(export_file_sha256="0" * 64))
    monkeypatch.setattr(
        "bimanual.workflow_manifest.load_skill_checkpoint",
        lambda *a, **k: pytest.fail("Must reject dataset before model intake"),
    )
    with pytest.raises(ValueError, match="dataset file digest"):
        load_workflow_manifest(path)


def test_missing_skill_cannot_create_manifest(cohort, tmp_path):
    with pytest.raises(ValueError, match="all seven"):
        create_workflow_manifest(tmp_path, tmp_path, {}, tmp_path / "missing.json")
    assert not (tmp_path / "missing.json").exists()


def test_existing_cohort_never_overwritten(cohort):
    with pytest.raises(FileExistsError):
        create_workflow_manifest(
            cohort.path.parent, cohort.path.parent, dict.fromkeys(SKILLS, cohort.path), cohort.path
        )


def test_invalid_verified_wrapper_rejected_before_model_loading(cohort, monkeypatch):
    monkeypatch.setattr(
        "bimanual.skill_policy.DinnerSkillPolicy",
        lambda *a, **k: pytest.fail("No model load before reverification"),
    )
    with pytest.raises(ValueError, match="changed"):
        preload_workflow(replace(cohort, file_sha256="0" * 64))


def test_preload_uses_pinned_bindings_in_order_and_no_inference(cohort, monkeypatch):
    calls = []
    by_id = {b.view.skill_id: b for b in cohort.bindings}

    class Policy:
        def __init__(self, run, *, skill_id, dataset_root, device):
            assert run == by_id[skill_id].training_run
            assert dataset_root == by_id[skill_id].dataset_root
            calls.append((skill_id, device))
            self.binding = by_id[skill_id]

    monkeypatch.setattr("bimanual.skill_policy.DinnerSkillPolicy", Policy)
    result = preload_workflow(cohort)
    assert calls == [(skill, "cpu") for skill in SKILLS]
    assert tuple(result.policies) == SKILLS
    with pytest.raises(TypeError):
        result.policies["handoff_transfer"] = None


def test_unsupported_device_rejected_without_loading(cohort):
    with pytest.raises(ValueError, match="devices"):
        preload_workflow(cohort, device="cuda")


def test_factories_bind_each_skill_and_ref_without_cross_worker_sharing(cohort, monkeypatch):
    from types import SimpleNamespace

    from bimanual.workflow_manifest import LoadedWorkflow

    worker = SimpleNamespace(
        supervisor=SimpleNamespace(snapshot=lambda: SimpleNamespace(active=None))
    )
    policies = {b.view.skill_id: SimpleNamespace(binding=b) for b in cohort.bindings}
    loaded = LoadedWorkflow(cohort, policies)
    monkeypatch.setattr("bimanual.skill_executor.DinnerSkillExecutor", lambda w, p, **k: (w, p, k))
    with pytest.raises(ValueError, match="already belong"):
        LoadedWorkflow(cohort, policies)
    factories = loaded.executor_factories(worker, max_actions=1200)
    for binding, ref in zip(cohort.bindings, cohort.successor_references, strict=True):
        w, policy, options = factories[binding.capability.capability_id]()
        assert w is worker and policy is policies[binding.view.skill_id]
        assert options == {"max_actions": 1200, "successor_reference": ref}
    with pytest.raises(ValueError, match="shared across workers"):
        loaded.executor_factories(object())
    policies[SKILLS[0]].binding = replace(cohort.bindings[0], checkpoint_sha256="0" * 64)
    with pytest.raises(ValueError, match="binding or ownership changed"):
        factories[cohort.bindings[0].capability.capability_id]()


def test_workflow_check_cli_preserves_quality_unknown(cohort, capsys):
    from bimanual.cli import main

    assert main(["workflow-check", str(cohort.path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["learned_workflow_success"] is None
    assert result["release_available"] is False
    assert len(result["checkpoints"]) == 7


def test_constructor_rejects_mismatched_policy_binding(cohort):
    from types import SimpleNamespace

    from bimanual.workflow_manifest import LoadedWorkflow

    policies = {b.view.skill_id: SimpleNamespace(binding=b) for b in cohort.bindings}
    policies[SKILLS[0]].binding = replace(cohort.bindings[0], checkpoint_sha256="0" * 64)
    with pytest.raises(ValueError, match="every pinned"):
        LoadedWorkflow(cohort, policies)
