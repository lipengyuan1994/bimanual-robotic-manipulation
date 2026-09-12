"""Activation/rollback integrity fixtures; no model is loaded or executed."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimanual.workflow_deployment import (
    activate_workflow,
    active_workflow_path,
    deployment_report,
    load_active_workflow,
    rollback_workflow,
)


def verifier(monkeypatch, manifests):
    def load(path):
        path = Path(path).resolve()
        if path not in manifests:
            raise ValueError("Unknown fixture manifest")
        file_sha, body_sha = manifests[path]
        return SimpleNamespace(
            path=path,
            file_sha256=file_sha,
            manifest=SimpleNamespace(manifest_sha256=body_sha),
        )

    monkeypatch.setattr("bimanual.workflow_deployment.load_workflow_manifest", load)


def test_activation_is_idempotent_and_rollback_adds_auditable_generation(tmp_path, monkeypatch):
    one, two = (tmp_path / name for name in ("one.json", "two.json"))
    one.write_text("one")
    two.write_text("two")
    verifier(
        monkeypatch,
        {one.resolve(): ("1" * 64, "a" * 64), two.resolve(): ("2" * 64, "b" * 64)},
    )
    root = tmp_path / "deployment"
    assert load_active_workflow(root) is None
    first = activate_workflow(one, root)
    assert active_workflow_path(root) == one.resolve()
    assert activate_workflow(one, root) == first
    second = activate_workflow(two, root)
    assert second.previous_deployment_id == first.deployment_id
    rolled = rollback_workflow(root)
    assert rolled.action == "rollback"
    assert rolled.rollback_target_id == first.deployment_id
    assert rolled.previous_deployment_id == second.deployment_id
    assert rolled.previous_record_sha256 == second.record_sha256
    assert rolled.workflow_file_sha256 == first.workflow_file_sha256
    assert rolled.rollback_target_record_sha256 == first.record_sha256
    assert load_active_workflow(root) == rolled
    assert len(list((root / "deployments").glob("*.json"))) == 3
    report = deployment_report(rolled)
    assert report["model_loaded"] is False
    assert report["active"]["learned_workflow_success"] is None
    assert report["active"]["release_qualified"] is False
    assert report["active"]["intel_validated"] is False


def test_changed_active_manifest_fails_closed(tmp_path, monkeypatch):
    manifest = tmp_path / "workflow.json"
    manifest.write_text("before")
    values = {manifest.resolve(): ("1" * 64, "a" * 64)}
    verifier(monkeypatch, values)
    root = tmp_path / "deployment"
    activate_workflow(manifest, root)
    values[manifest.resolve()] = ("2" * 64, "a" * 64)
    with pytest.raises(ValueError, match="changed after deployment"):
        load_active_workflow(root)


def test_orphaned_prepared_record_requires_adjudication(tmp_path):
    root = tmp_path / "deployment"
    records = root / "deployments"
    records.mkdir(parents=True)
    (records / ("a" * 32 + ".json")).write_text("{}")
    with pytest.raises(RuntimeError, match="without an active pointer"):
        load_active_workflow(root)


def test_corrupt_pointer_and_missing_history_are_rejected(tmp_path):
    root = tmp_path / "deployment"
    root.mkdir()
    (root / "current.json").write_text(
        json.dumps({"profile": "wrong", "deployment_id": "a" * 32, "record_sha256": "b" * 64})
    )
    with pytest.raises(ValueError, match="pointer"):
        load_active_workflow(root)
    (root / "current.json").write_text(
        json.dumps(
            {
                "profile": "local_workflow_deployment_v1",
                "deployment_id": "a" * 32,
                "record_sha256": "b" * 64,
            }
        )
    )
    with pytest.raises(FileNotFoundError):
        load_active_workflow(root)


def test_rollback_reverifies_target_and_rejects_unknown_identity(tmp_path, monkeypatch):
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    one.write_text("one")
    two.write_text("two")
    values = {one.resolve(): ("1" * 64, "a" * 64), two.resolve(): ("2" * 64, "b" * 64)}
    verifier(monkeypatch, values)
    root = tmp_path / "deployment"
    first = activate_workflow(one, root)
    activate_workflow(two, root)
    values[one.resolve()] = ("3" * 64, "a" * 64)
    with pytest.raises(ValueError, match="changed after deployment"):
        rollback_workflow(root, first.deployment_id)
    with pytest.raises(ValueError, match="Invalid deployment id"):
        rollback_workflow(root, "../escape")


def test_record_or_pointer_seal_tampering_is_rejected(tmp_path, monkeypatch):
    manifest = tmp_path / "workflow.json"
    manifest.write_text("one")
    verifier(monkeypatch, {manifest.resolve(): ("1" * 64, "a" * 64)})
    root = tmp_path / "deployment"
    record = activate_workflow(manifest, root)
    record_path = root / "deployments" / f"{record.deployment_id}.json"
    value = json.loads(record_path.read_text())
    value["created_at"] = "changed"
    record_path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="record seal"):
        load_active_workflow(root)

    record_path.write_text(json.dumps(record.model_dump(mode="json")))
    pointer = json.loads((root / "current.json").read_text())
    pointer["record_sha256"] = "0" * 64
    (root / "current.json").write_text(json.dumps(pointer))
    with pytest.raises(ValueError, match="pointer and deployment"):
        load_active_workflow(root)


def test_cli_dispatch_uses_local_registry_without_claiming_quality(tmp_path, monkeypatch, capsys):
    from bimanual import workflow_deployment as module
    from bimanual.cli import main

    record = SimpleNamespace()
    monkeypatch.setattr(module, "activate_workflow", lambda path, root: record)
    monkeypatch.setattr(
        module,
        "deployment_report",
        lambda value: {"active": "fixture", "model_loaded": False},
    )
    assert main(["--project-root", str(tmp_path), "workflow-activate", "candidate.json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"active": "fixture", "model_loaded": False}


def test_workflow_run_requires_one_direct_or_deployed_manifest(tmp_path, monkeypatch, capsys):
    from bimanual.cli import main

    common = [
        "--project-root",
        str(tmp_path),
        "workflow-run",
        "--planner-model",
        "planner",
        "--instruction",
        "Dinner",
    ]
    assert main(common) == 1
    assert "exactly one" in json.loads(capsys.readouterr().out)["error"]
    assert main(common + ["direct.json", "--deployment-root", "deployment"]) == 1
    assert "exactly one" in json.loads(capsys.readouterr().out)["error"]
