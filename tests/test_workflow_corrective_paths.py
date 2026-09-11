"""Portable cohort path checks with registry stubs; no optional ML dependencies."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimanual import workflow_manifest as module
from bimanual.evidence import canonical


@pytest.fixture
def cohort_files(tmp_path, monkeypatch):
    root = tmp_path / "original"
    root.mkdir()
    (root / "dataset").mkdir()
    (root / "dataset/export_manifest.json").write_text("{}")
    (root / "views.json").write_text("{}")
    (root / "corrections").mkdir()
    (root / "corrections/export_manifest.json").write_text("correction export")
    views = tuple(SimpleNamespace(skill_id=skill) for skill in module.SKILLS)
    calls = []

    def load(training_run, *, skill_id, dataset_root, corrective_dataset_root=None):
        actual = None
        if skill_id == "handoff_transfer":
            actual = corrective_dataset_root or Path(training_run).parent / "corrections"
        calls.append((Path(training_run), actual))
        return SimpleNamespace(
            training_run=Path(training_run),
            dataset_root=dataset_root,
            training_manifest_sha256="a" * 64,
            checkpoint_sha256="b" * 64,
            view=views[module.SKILLS.index(skill_id)],
            corrective_dataset_root=actual,
        )

    monkeypatch.setattr(module, "load_skill_checkpoint", load)
    monkeypatch.setattr(
        module,
        "load_skill_views",
        lambda *a, **k: SimpleNamespace(
            views=views, export_manifest_sha256="c" * 64, parent_episode_id="episode"
        ),
    )
    monkeypatch.setattr(
        module,
        "load_successor_reference",
        lambda *a, **k: SimpleNamespace(
            export_manifest_sha256="c" * 64, parent_episode_id="episode"
        ),
    )
    runs = {skill: root / skill for skill in module.SKILLS}
    return root, runs, calls


def test_v2_copy_resolves_corrective_relative_path(cohort_files, tmp_path):
    root, runs, calls = cohort_files
    original = module.create_workflow_manifest(
        root / "dataset", root / "views.json", runs, root / "workflow.json"
    )
    assert original.manifest.profile == "dinner_development_workflow_v4"
    assert original.manifest.checkpoints[0].corrective_dataset_root == "corrections"
    copy = tmp_path / "moved"
    shutil.copytree(root, copy)
    moved = module.load_workflow_manifest(copy / "workflow.json")
    assert moved.bindings[0].corrective_dataset_root == copy / "corrections"
    assert calls[-7][1] == copy / "corrections"
    assert moved.manifest.manifest_sha256 == original.manifest.manifest_sha256


def test_v2_export_hash_rejected_before_binding(cohort_files):
    root, runs, calls = cohort_files
    module.create_workflow_manifest(
        root / "dataset", root / "views.json", runs, root / "workflow.json"
    )
    calls.clear()
    (root / "corrections/export_manifest.json").write_text("changed")
    with pytest.raises(ValueError, match="corrective export digest"):
        module.load_workflow_manifest(root / "workflow.json")
    assert not calls


def test_v1_body_has_no_new_null_fields():
    body = dict(
        schema_version=1,
        profile="dinner_development_workflow_v1",
        dataset_root="dataset",
        export_file_sha256="a" * 64,
        skill_views_path="views.json",
        skill_views_file_sha256="b" * 64,
        checkpoints=[
            dict(
                schema_version=1,
                skill_id=skill,
                training_run=skill,
                training_manifest_sha256="c" * 64,
                checkpoint_sha256="d" * 64,
            )
            for skill in module.SKILLS
        ],
    )
    digest = hashlib.sha256(canonical(body)).hexdigest()
    manifest = module.WorkflowManifest.model_validate(body | {"manifest_sha256": digest})
    assert (
        manifest.model_dump(mode="json", exclude={"manifest_sha256"}, exclude_none=True)
        == body
    )
    assert manifest.manifest_sha256 == digest


def test_v2_manifest_path_tamper_requires_new_seal(cohort_files):
    root, runs, _ = cohort_files
    module.create_workflow_manifest(
        root / "dataset", root / "views.json", runs, root / "workflow.json"
    )
    payload = json.loads((root / "workflow.json").read_text())
    payload["checkpoints"][0]["corrective_dataset_root"] = "other"
    with pytest.raises(ValueError, match="body seal"):
        module.WorkflowManifest.model_validate(payload)


def test_v2_wrong_resolved_binding_rejected(cohort_files, monkeypatch):
    root, runs, _ = cohort_files
    module.create_workflow_manifest(
        root / "dataset", root / "views.json", runs, root / "workflow.json"
    )
    original = module.load_skill_checkpoint

    def wrong(*args, **kwargs):
        binding = original(*args, **kwargs)
        binding.corrective_dataset_root = root / "other"
        return binding

    monkeypatch.setattr(module, "load_skill_checkpoint", wrong)
    with pytest.raises(ValueError, match="path differs"):
        module.load_workflow_manifest(root / "workflow.json")


def test_preload_forwards_override_only_for_corrective_binding(cohort_files, monkeypatch):
    from bimanual import skill_policy

    root, runs, _ = cohort_files
    verified = module.create_workflow_manifest(
        root / "dataset", root / "views.json", runs, root / "workflow.json"
    )
    received = []

    def policy(training_run, **kwargs):
        received.append(kwargs)
        return SimpleNamespace(binding=verified.bindings[module.SKILLS.index(kwargs["skill_id"])])

    monkeypatch.setattr(skill_policy, "DinnerSkillPolicy", policy)
    module.preload_workflow(verified)
    assert received[0]["corrective_dataset_root"] == root / "corrections"
    assert all("corrective_dataset_root" not in kwargs for kwargs in received[1:])
