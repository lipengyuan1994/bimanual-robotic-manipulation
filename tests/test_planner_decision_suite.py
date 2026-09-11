from __future__ import annotations

import json

from PIL import Image

from bimanual.cli import main
from bimanual.evidence import EvidenceStore, digest_file
from bimanual.planner import seal_model
from bimanual.planner_decision_suite import (
    create_planner_decision_protocol,
    load_planner_decision_protocol,
    run_planner_decision_suite,
)


def _model(root):
    root.mkdir()
    (root / "config.json").write_text('{"model_type":"qwen3_vl"}')
    for name in ("tokenizer_config.json", "preprocessor_config.json"):
        (root / name).write_text("{}")
    (root / "model.safetensors").write_bytes(b"fixture weights")
    seal_model(root, "a" * 40)


def _recording(root):
    from test_contracts import episode

    data = episode()
    store = EvidenceStore(root)
    directory = store.new_run()
    for item in data["frames"]:
        for index, frame in enumerate(item["observation"]["frames"]):
            target = directory / frame["artifact"]["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (480, 270), color=(index * 50, 0, 0)).save(target)
            frame["artifact"]["sha256"] = digest_file(target)
    for key in ("scene", "config", "controller"):
        target = directory / data["lineage"][key]["path"]
        target.write_text("planner suite fixture")
        data["lineage"][key]["sha256"] = digest_file(target)
    (directory / "demonstration").mkdir(exist_ok=True)
    (directory / "demonstration/episode.json").write_text(json.dumps(data))
    store.seal(
        directory,
        kind="planner_suite_test_recording",
        outcome="completed",
        config={},
        metrics={},
        source={"fixture": True},
        claims=[],
    )
    return directory


def _expected(skill="pick"):
    return {
        "schema_version": 1,
        "skill": skill,
        "arm": "right",
        "target": "cup",
        "destination": "table" if skill == "place" else None,
        "target_visibility": "visible",
        "visible_state": "incomplete",
    }


def _case(recording, case_id, expected=None):
    return {
        "schema_version": 1,
        "case_id": case_id,
        "recording": str(recording),
        "frame": 0,
        "instruction": "Pick up the visible cup.",
        "completed_steps": [],
        "retry_number": 0,
        "available_skills": ["pick", "place"],
        "accepted_decisions": [expected or _expected()],
    }


def _proposal(skill="pick"):
    return {
        "schema_version": 2,
        "request": {
            "schema_version": 1,
            "episode_id": "episode-1",
            "instruction_revision": 0,
            "observation_sequence": 0,
            "skill": skill,
            "arm": "right",
            "target": "cup",
            "destination": None,
            "explanation": "The cup is visible.",
        },
        "target_visibility": "visible",
        "visible_state": "incomplete",
        "visual_explanation": "The cup is visible on the table.",
    }


def _protocol(tmp_path, cases):
    model = tmp_path / "model"
    _model(model)
    spec = tmp_path / "cases.json"
    spec.write_text(json.dumps(cases))
    destination = tmp_path / "protocol.json"
    result = create_planner_decision_protocol(
        spec_path=spec, model_root=model, destination=destination
    )
    return destination, result


def test_protocol_freezes_model_recording_observation_and_expectation(tmp_path):
    recording = _recording(tmp_path / "source")
    protocol_path, created = _protocol(tmp_path, [_case(recording.relative_to(tmp_path), "cup")])
    loaded = load_planner_decision_protocol(protocol_path)
    assert loaded == created
    assert loaded.live_dispatch_authorized is False
    assert loaded.manipulation_success is None
    assert loaded.cases[0].source_run_id == recording.name
    assert loaded.cases[0].camera_profile == "policy480_v1"
    assert loaded.cases[0].accepted_decisions[0].skill == "pick"


def test_protocol_check_cli_reports_non_authorizing_scope(tmp_path, capsys):
    recording = _recording(tmp_path / "source")
    protocol_path, _ = _protocol(tmp_path, [_case(recording.relative_to(tmp_path), "cup")])
    assert main(["planner-suite-check", str(protocol_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["selection_rule"] == "evaluate_every_frozen_case_once"
    assert report["live_dispatch_authorized"] is False
    assert report["manipulation_success"] is None


def test_protocol_rejects_changed_source_before_inference(tmp_path, monkeypatch):
    import bimanual.planner_decision_suite as module

    recording = _recording(tmp_path / "source")
    protocol_path, _ = _protocol(tmp_path, [_case(recording.relative_to(tmp_path), "cup")])
    image = next(recording.rglob("*.png"))
    image.write_bytes(b"changed")

    class MustNotLoad:
        def __init__(self, *args, **kwargs):
            raise AssertionError("model loaded before source verification")

    monkeypatch.setattr(module, "LocalQwenPlanner", MustNotLoad)
    store = EvidenceStore(tmp_path / "results")
    result = run_planner_decision_suite(
        protocol_path=protocol_path,
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "failed"
    assert result.metrics["process_complete"] is False
    assert "digest" in result.metrics["error"].lower()
    assert result.claims == []


def test_suite_loads_once_retains_every_case_and_scores_without_robot_claims(tmp_path, monkeypatch):
    import bimanual.planner_decision_suite as module

    recording = _recording(tmp_path / "source")
    relative = recording.relative_to(tmp_path)
    cases = [_case(relative, "passes"), _case(relative, "wrong", _expected("place"))]
    protocol_path, _ = _protocol(tmp_path, cases)
    loads = []

    class StubPlanner:
        device = "cpu"
        dtype = "float32"
        load_seconds = 0.25

        def __init__(self, root, *, device):
            loads.append((root, device))

        def generate(self, context, images, *, max_tokens):
            assert len(images) == 3
            return json.dumps(_proposal()), {"generation_budget_reached": False}

    monkeypatch.setattr(module, "LocalQwenPlanner", StubPlanner)
    store = EvidenceStore(tmp_path / "results")
    result = run_planner_decision_suite(
        protocol_path=protocol_path,
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert len(loads) == 1
    assert result.outcome == "completed"
    assert result.metrics["process_complete"] is True
    assert result.metrics["case_count"] == 2
    assert result.metrics["passed_case_count"] == 1
    assert result.metrics["failed_case_count"] == 1
    assert result.metrics["all_cases_passed"] is False
    assert result.metrics["live_dispatch_authorized"] is False
    assert result.metrics["manipulation_success"] is None
    assert result.claims == []
    directory = store.directory(result.run_id)
    assert json.loads((directory / "cases/passes/evaluation.json").read_text())["passed"]
    wrong = json.loads((directory / "cases/wrong/evaluation.json").read_text())
    assert wrong["passed"] is False and wrong["mismatches"] == ["skill", "destination"]
    store.verify(result.run_id)


def test_malformed_case_does_not_hide_later_case(tmp_path, monkeypatch):
    import bimanual.planner_decision_suite as module

    recording = _recording(tmp_path / "source")
    relative = recording.relative_to(tmp_path)
    protocol_path, _ = _protocol(tmp_path, [_case(relative, "malformed"), _case(relative, "later")])

    class StubPlanner:
        device = "cpu"
        dtype = "float32"
        load_seconds = 0.1
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, context, images, *, max_tokens):
            self.calls += 1
            if self.calls == 1:
                return "not json", {"generation_budget_reached": False}
            return json.dumps(_proposal()), {"generation_budget_reached": False}

    monkeypatch.setattr(module, "LocalQwenPlanner", StubPlanner)
    store = EvidenceStore(tmp_path / "results")
    result = run_planner_decision_suite(
        protocol_path=protocol_path,
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "completed"
    assert result.metrics["failed_case_count"] == 1
    assert result.metrics["passed_case_count"] == 1
    directory = store.directory(result.run_id)
    assert (directory / "cases/malformed/error.txt").is_file()
    assert (directory / "cases/later/proposal.json").is_file()
