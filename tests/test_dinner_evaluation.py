"""Evidence-boundary tests; physical predicates have their own trace fixtures."""

import gzip
import json

import pytest

from bimanual.dinner_evaluation import _actions, evaluate_dinner_run
from bimanual.evidence import EvidenceStore, digest_file

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


def workflow_source(
    tmp_path,
    *,
    instrumentation=False,
    outcome="failed",
    layout=True,
    malformed_physics=False,
    malformed_action=False,
    forbidden=True,
    partial=True,
    decoys=False,
    scene=True,
    scene_binding=True,
):
    from test_dinner_scoring import LAYOUT, row_for

    store = EvidenceStore(tmp_path / "evidence")
    directory = store.new_run()
    worker = directory / "worker"
    worker.mkdir()
    if scene:
        (worker / "scene.xml").write_text("<mujoco/>")
    if layout:
        scene_hash = digest_file(worker / "scene.xml") if scene and scene_binding else "0" * 64
        (worker / "layout.json").write_text(json.dumps(LAYOUT | {"scene_sha256": scene_hash}))
    rows = []
    if malformed_physics:
        rows.append("malformed physics")
    for index in range(50):
        row = row_for("ignored fixture phase")
        row["t"] = (index + 1) / 1000
        row["bad"] = [["arm", "table"]] if forbidden and index == 49 else []
        rows.append(json.dumps(row))
    (worker / "physics.jsonl").write_text("\n".join(rows) + "\n")
    action = dict(
        episode_id="workflow_episode",
        observation_sequence=0,
        simulation_seconds_before=0,
        simulation_seconds_after=0.05,
        targets_rad=[0.0] * 12,
        applied=not partial,
        partial_physics=partial,
    )
    (worker / "actions.jsonl").write_text(
        ("[]\n" if malformed_action else "") + json.dumps(action) + "\n"
    )
    if decoys:
        (directory / "layout.json").write_text(json.dumps(LAYOUT))
        (directory / "actions.jsonl").write_text("[]\n")
        with gzip.open(directory / "physics.jsonl.gz", "wt") as stream:
            stream.write("[]\n")
    metadata = {"reason": "Retained workflow failure", "execution_complete": outcome == "completed"}
    if instrumentation:
        metadata["instrumentation"] = META
    manifest = store.seal(
        directory,
        kind="dinner_workflow_execution",
        outcome=outcome,
        config={},
        metrics=metadata,
        source={},
        claims=[],
    )
    return store, manifest


def test_nested_workflow_scan_keeps_partial_forbidden_and_malformed_rows(tmp_path):
    store, manifest = workflow_source(
        tmp_path, malformed_physics=True, malformed_action=True, instrumentation=True, decoys=True
    )
    result = evaluate(store, manifest, tmp_path)
    assert result.outcome == "failed"
    diagnostic = result.metrics["full_trace_diagnostics"]
    assert diagnostic["physics_rows"] == 50
    assert diagnostic["forbidden_samples"] == 1
    assert diagnostic["partial_actions"] == 1
    assert any("worker/physics.jsonl:1" in error for error in diagnostic["errors"])
    assert any("worker/actions.jsonl:1" in error for error in diagnostic["errors"])
    assert result.metrics["selected_trace_layout"] == result.config["selected_trace_layout"]
    assert result.config["selected_trace_layout"] == dict(
        profile="workflow_worker_v1",
        physics="worker/physics.jsonl",
        actions="worker/actions.jsonl",
        layout="worker/layout.json",
        scene="worker/scene.xml",
        legacy_actions=False,
    )
    assert result.metrics["source_error"] == "Retained workflow failure"
    assert result.metrics["learned_execution_verified"] is False
    assert store.verify(manifest.run_id) == manifest
    assert store.verify(result.run_id) == result


@pytest.mark.parametrize("unsealed_layout", [False, True])
def test_workflow_requires_exact_sealed_worker_layout_without_root_fallback(
    tmp_path, unsealed_layout
):
    store, manifest = workflow_source(tmp_path, layout=False, decoys=True, instrumentation=True)
    if unsealed_layout:
        (store.directory(manifest.run_id) / "worker/layout.json").write_text("{}")
        with pytest.raises(ValueError, match="Unsealed files"):
            evaluate(store, manifest, tmp_path)
        return
    result = evaluate(store, manifest, tmp_path)
    assert result.outcome == "failed"
    assert "worker/layout.json" in result.metrics["score"]["input_error"]
    assert "source seal" in result.metrics["score"]["input_error"]
    # Even unavailable layout must not hide a later recorded forbidden contact.
    assert result.metrics["full_trace_diagnostics"]["forbidden_samples"] == 1


def test_completed_workflow_does_not_supply_missing_instrumentation_or_task_success(tmp_path):
    store, manifest = workflow_source(tmp_path, outcome="completed", forbidden=False, partial=False)
    result = evaluate(store, manifest, tmp_path)
    assert result.config["instrumentation"] == {}
    assert result.outcome == "failed"
    assert "instrumentation" in result.metrics["score"]["input_error"]
    assert result.metrics["source_outcome"] == "completed"
    assert result.metrics["learned_execution_verified"] is False


@pytest.mark.parametrize("linked", [True, False])
def test_workflow_optional_audit_requires_exact_source_binding(tmp_path, linked):
    store, manifest = workflow_source(tmp_path, outcome="completed", forbidden=False, partial=False)
    audit = store.seal(
        store.new_run(),
        kind="declaration",
        outcome="completed",
        config=dict(
            source_run=manifest.run_id,
            source_manifest_sha256=manifest.manifest_sha256 if linked else "0" * 64,
            metadata=META,
            metadata_scope="Explicit fixture declaration only",
        ),
        metrics={},
        source={},
        claims=[],
    )
    if not linked:
        with pytest.raises(ValueError, match="does not bind"):
            evaluate(store, manifest, tmp_path, instrumentation_run=audit.run_id)
    else:
        result = evaluate(store, manifest, tmp_path, instrumentation_run=audit.run_id)
        assert result.config["instrumentation"] == META
        assert result.config["instrumentation_manifest_sha256"] == audit.manifest_sha256
        assert "instrumentation-manifest.json" in result.files
        # Fifty idle fixture samples are not a completed dinner workflow.
        assert result.outcome == "failed"
        assert not result.metrics["score"]["independent_task_success"]


def test_modern_workflow_actions_never_receive_legacy_defaults(tmp_path):
    path = tmp_path / "actions.jsonl"
    record = dict(episode_id="e", t=0, q=[0] * 12, applied=True)
    path.write_text(json.dumps(record))
    assert next(_actions(path, legacy=False)) == record
    assert "partial_physics" not in next(_actions(path, legacy=False))


@pytest.mark.parametrize("scene,scene_binding", [(False, True), (True, False)])
def test_workflow_layout_must_bind_its_own_sealed_scene(tmp_path, scene, scene_binding):
    store, manifest = workflow_source(
        tmp_path,
        scene=scene,
        scene_binding=scene_binding,
        instrumentation=True,
        outcome="completed",
    )
    result = evaluate(store, manifest, tmp_path)
    assert result.outcome == "failed"
    assert result.metrics["scene_binding_verified"] is False
    assert "scene" in result.metrics["score"]["input_error"]
    assert result.metrics["full_trace_diagnostics"]["forbidden_samples"] == 1


def test_failed_workflow_cannot_be_promoted_by_positive_score(tmp_path, monkeypatch):
    store, manifest = workflow_source(
        tmp_path, instrumentation=True, forbidden=False, partial=False
    )
    # Isolate source-status policy only; this is not physical success evidence.
    monkeypatch.setattr(
        "bimanual.dinner_evaluation.score_dinner_outcomes",
        lambda *args, **kwargs: {"independent_task_success": True},
    )
    result = evaluate(store, manifest, tmp_path)
    assert result.outcome == "failed" and result.metrics["source_outcome"] == "failed"


def test_dinner_teacher_uses_packaged_layout_even_with_root_decoy(tmp_path, monkeypatch):
    store, old = source(tmp_path)
    directory = store.new_run()
    for name in ("physics.jsonl.gz", "actions.jsonl"):
        (directory / name).write_bytes((store.directory(old.run_id) / name).read_bytes())
    (directory / "teacher-assets").mkdir()
    (directory / "teacher-assets/layout.json").write_text('{"selected": true}')
    (directory / "layout.json").write_text('{"selected": false}')
    manifest = store.seal(
        directory,
        kind="dinner_teacher",
        outcome="failed",
        config={},
        metrics={"instrumentation": META},
        source={},
        claims=[],
    )

    def score(rows, layout, **kwargs):
        assert layout == {"selected": True}
        return {"independent_task_success": False}

    monkeypatch.setattr("bimanual.dinner_evaluation.score_dinner_outcomes", score)
    result = evaluate(store, manifest, tmp_path)
    assert result.config["selected_trace_layout"]["layout"] == "teacher-assets/layout.json"
