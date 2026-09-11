"""Evidence-boundary tests; physical predicates have their own trace fixtures."""

import gzip
import json

import pytest

from bimanual.dinner_evaluation import _actions, evaluate_dinner_run
from bimanual.evidence import EvidenceStore

META = dict(
    physics_hz=1000, object_state_edits=0, artificial_attachments=0, external_object_force_samples=0
)


def source(tmp_path, *, instrumentation=True, malformed=False, outcome="failed"):
    store = EvidenceStore(tmp_path / "evidence")
    directory = store.new_run()
    (directory / "layout.json").write_text("{}")
    (directory / "actions.jsonl").write_text(
        json.dumps(dict(episode_id="episode", t=0, q=[0] * 12, applied=False, partial_physics=True))
        + "\n"
    )
    with gzip.open(directory / "physics.jsonl.gz", "wt") as stream:
        if malformed:
            stream.write("broken\n")
        stream.write(json.dumps({"bad": [["plate", "cabinet"]]}) + "\n")
    manifest = store.seal(
        directory,
        kind="teacher_fixture",
        outcome=outcome,
        config={},
        metrics={"instrumentation": META} if instrumentation else {},
        source={},
        claims=[],
    )
    return store, manifest


def evaluate(store, manifest, tmp_path, **kwargs):
    return evaluate_dinner_run(manifest.run_id, store=store, project_root=tmp_path, **kwargs)


def test_partial_collision_survives_scorer_early_exit(tmp_path):
    store, manifest = source(tmp_path)
    result = evaluate(store, manifest, tmp_path)
    assert result.outcome == "failed"
    assert result.metrics["full_trace_diagnostics"]["forbidden_samples"] == 1
    assert result.metrics["full_trace_diagnostics"]["partial_actions"] == 1
    assert not result.metrics["score"]["independent_task_success"]
    assert store.verify(manifest.run_id) == manifest
    assert store.verify(result.run_id) == result


def test_malformed_trace_retains_following_collision(tmp_path):
    store, manifest = source(tmp_path, malformed=True)
    result = evaluate(store, manifest, tmp_path)
    assert result.metrics["full_trace_diagnostics"]["errors"]
    assert result.metrics["full_trace_diagnostics"]["forbidden_samples"] == 1


def test_missing_instrumentation_is_not_invented(tmp_path):
    store, manifest = source(tmp_path, instrumentation=False)
    result = evaluate(store, manifest, tmp_path)
    assert result.config["instrumentation"] == {}
    assert "instrumentation" in result.metrics["score"]["input_error"]


def test_unsealed_change_rejected(tmp_path):
    store, manifest = source(tmp_path)
    (store.directory(manifest.run_id) / "actions.jsonl").write_text("[]")
    with pytest.raises(ValueError, match="digest mismatch"):
        evaluate(store, manifest, tmp_path)


@pytest.mark.parametrize("linked", [True, False])
def test_audit_must_bind_source_manifest(tmp_path, linked):
    store, manifest = source(tmp_path, instrumentation=False)
    audit = store.seal(
        store.new_run(),
        kind="declaration",
        outcome="completed",
        config={
            "source_run": manifest.run_id,
            "source_manifest_sha256": manifest.manifest_sha256 if linked else "wrong",
            "metadata": META,
            "metadata_scope": "source inspected only",
        },
        metrics={},
        source={},
        claims=[],
    )
    if not linked:
        with pytest.raises(ValueError, match="does not bind"):
            evaluate(store, manifest, tmp_path, instrumentation_run=audit.run_id)
    else:
        result = evaluate(store, manifest, tmp_path, instrumentation_run=audit.run_id)
        assert result.config["instrumentation_scope"] == "source inspected only"
        assert result.config["instrumentation"] == META
        assert "instrumentation-manifest.json" in result.files


def test_legacy_missing_acknowledgement_stays_unconfirmed(tmp_path):
    path = tmp_path / "actions.jsonl"
    path.write_text(json.dumps(dict(episode_id="e", t=0, q=[0] * 12)))
    assert next(_actions(path))["applied"] is False


@pytest.mark.parametrize("outcome,expected", [("failed", "failed"), ("completed", "completed")])
def test_source_failure_cannot_be_promoted(tmp_path, monkeypatch, outcome, expected):
    store, manifest = source(tmp_path, outcome=outcome)
    # Isolate wrapper status policy; this is not physical success evidence.
    monkeypatch.setattr(
        "bimanual.dinner_evaluation.score_dinner_outcomes",
        lambda *a, **k: {"independent_task_success": True},
    )
    monkeypatch.setattr(
        "bimanual.dinner_evaluation._diagnostics", lambda *a: {"errors": [], "forbidden_samples": 0}
    )
    result = evaluate(store, manifest, tmp_path)
    assert result.outcome == expected
    assert result.metrics["source_outcome"] == outcome
    assert result.metrics["learned_execution_verified"] is False


def test_cli_returns_failed_evaluation_json(tmp_path, capsys):
    from bimanual.cli import main

    store, manifest = source(tmp_path)
    code = main(
        [
            "--project-root",
            str(tmp_path),
            "--artifacts",
            str(store.root),
            "dinner-evaluate",
            manifest.run_id,
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["kind"] == "dinner_evaluation"
    assert result["outcome"] == "failed"
