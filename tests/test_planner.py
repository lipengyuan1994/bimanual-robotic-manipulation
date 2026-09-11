import json
from pathlib import Path

import pytest
from PIL import Image
from test_contracts import observation

from bimanual.contracts import Observation
from bimanual.evidence import EvidenceStore, digest_file
from bimanual.planner import (
    PlannerContext,
    camera_images,
    parse_proposal,
    planner_messages,
    run_planner_probe,
    seal_model,
    verify_model,
)


def context(**changes):
    return PlannerContext(
        observation=Observation.model_validate(observation()),
        instruction="Place the cup on the table",
        available_skills=("pick", "place"),
        **changes,
    )


def proposal(**changes):
    request = dict(
        episode_id="episode-1",
        instruction_revision=0,
        observation_sequence=0,
        skill="pick",
        arm="right",
        target="cup",
        destination=None,
        explanation="Pick up the cup before placing it.",
    )
    request.update(changes)
    return {
        "schema_version": 2,
        "request": request,
        "target_visibility": "visible",
        "visible_state": "incomplete",
        "visual_explanation": "The cup appears to be on the workbench.",
    }


def test_typed_proposal_is_only_a_proposal():
    value = parse_proposal(json.dumps(proposal()), context())
    assert value.request.skill == "pick"
    assert not hasattr(value, "success")
    assert not hasattr(value.request, "action")


@pytest.mark.parametrize("visibility", ["not_visible", "uncertain"])
def test_nonvisible_target_cannot_receive_manipulation_proposal(visibility):
    data = proposal()
    data["target_visibility"] = visibility
    data["request"]["explanation"] = "The object is not visible in the camera views."
    with pytest.raises(ValueError, match="visually confirmed"):
        parse_proposal(json.dumps(data), context())
    data["request"].update(skill="stop", arm="none", target=None)
    assert parse_proposal(json.dumps(data), context()).request.skill == "stop"


def test_proposal_version_and_completion_consistency():
    data = proposal()
    data["schema_version"] = 1
    with pytest.raises(ValueError):
        parse_proposal(json.dumps(data), context())
    data = proposal()
    del data["target_visibility"]
    with pytest.raises(ValueError):
        parse_proposal(json.dumps(data), context())
    data = proposal()
    data["visible_state"] = "apparently_complete"
    with pytest.raises(ValueError, match="completed-task"):
        parse_proposal(json.dumps(data), context())


@pytest.mark.parametrize(
    "change",
    [
        {"episode_id": "different"},
        {"instruction_revision": 1},
        {"observation_sequence": 1},
        {"skill": "pour"},
        {"skill": "open_drawer", "target": "drawer"},
        {"arm": "both"},
        {"target": "unknown"},
        {"object_position": [0, 0, 0]},
        {"instruction_revision": True},
    ],
)
def test_invalid_or_unavailable_proposals_are_rejected(change):
    with pytest.raises(ValueError):
        parse_proposal(json.dumps(proposal(**change)), context())


@pytest.mark.parametrize(
    "text",
    [
        "not JSON",
        "```json\n{}\n```",
        '{"request":{},"request":{}}',
        "{} {}",
        "x" * 16385,
    ],
)
def test_no_response_repair_or_duplicate_fields(text):
    with pytest.raises(ValueError):
        parse_proposal(text, context())


def test_model_cannot_award_completion_or_send_positions():
    data = proposal()
    data["success"] = True
    with pytest.raises(ValueError):
        parse_proposal(json.dumps(data), context())
    data = proposal(skill="stop", arm="none", target=None)
    data["visible_state"] = "apparently_complete"
    assert parse_proposal(json.dumps(data), context()).request.skill == "stop"


def test_prompt_boundary_uses_only_declared_context_and_ordered_images():
    ctx = context(completed_steps=("drawer opened",))
    images = tuple(Image.new("RGB", (480, 270), color=color) for color in ("red", "green", "blue"))
    messages = planner_messages(ctx, images)
    content = messages[1]["content"]
    state = json.loads(content[0]["text"])
    assert state["instruction"] == ctx.instruction
    assert "object_position" not in state
    assert "contacts" not in state
    assert [content[i]["text"] for i in (1, 3, 5)] == [
        "overhead",
        "left/wrist_cam",
        "right/wrist_cam",
    ]
    assert tuple(content[i]["image"] for i in (2, 4, 6)) == images
    with pytest.raises(ValueError):
        planner_messages(ctx, images[:2])


def test_camera_hash_and_format_checked_before_model_loading(tmp_path):
    data = observation()
    for frame in data["frames"]:
        target = tmp_path / frame["artifact"]["path"]
        Image.new("RGB", (480, 270)).save(target)
        frame["artifact"]["sha256"] = digest_file(target)
    ctx = PlannerContext(observation=data, instruction="Stop", available_skills=())
    assert len(camera_images(ctx, tmp_path)) == 3
    (tmp_path / data["frames"][0]["artifact"]["path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest"):
        camera_images(ctx, tmp_path)


def test_model_bundle_is_exact_and_immutable(tmp_path):
    (tmp_path / "config.json").write_text('{"model_type":"qwen3_vl"}')
    for name in ("tokenizer_config.json", "preprocessor_config.json"):
        (tmp_path / name).write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"test fixture, not actual weights")
    seal_model(tmp_path, "a" * 40)
    assert verify_model(tmp_path)["revision"] == "a" * 40
    with pytest.raises(FileExistsError):
        seal_model(tmp_path, "b" * 40)
    (tmp_path / "injected.json").write_text("{}")
    with pytest.raises(ValueError, match="Unmanifested"):
        verify_model(tmp_path)
    (tmp_path / "injected.json").unlink()
    (tmp_path / "model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest"):
        verify_model(tmp_path)


def test_bad_recorded_probe_is_retained_and_never_authorizes_actions(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=tmp_path / "model",
        recording=tmp_path / "missing",
        frame=0,
        instruction="Place the cup",
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "failed"
    assert result.metrics["live_dispatch_authorized"] is False
    assert result.metrics["manipulation_success"] is None
    assert "error.txt" in result.files
    store.verify(result.run_id)


@pytest.fixture
def sealed_recording(tmp_path):
    from test_contracts import episode

    data = episode()
    store = EvidenceStore(tmp_path / "source")
    directory = store.new_run()
    for item in data["frames"]:
        for index, frame in enumerate(item["observation"]["frames"]):
            target = directory / frame["artifact"]["path"]
            Image.new("RGB", (480, 270), color=(index * 50, 0, 0)).save(target)
            frame["artifact"]["sha256"] = digest_file(target)
    for key in ("scene", "config", "controller"):
        target = directory / data["lineage"][key]["path"]
        target.write_text("Fixture source only; no manipulation or model evidence")
        data["lineage"][key]["sha256"] = digest_file(target)
    (directory / "demonstration").mkdir()
    (directory / "demonstration/episode.json").write_text(json.dumps(data))
    store.seal(
        directory,
        kind="test_recording_fixture",
        outcome="completed",
        config={},
        source={"fixture": True},
        claims=[],
        metrics={},
    )
    return directory


def test_probe_binds_source_before_generation_changes_file(tmp_path, monkeypatch, sealed_recording):
    import importlib.metadata

    import bimanual.planner as module

    source_file = tmp_path / "example.py"
    source_file.write_text("before generation\n")
    before = digest_file(source_file)
    captured = []

    def source_snapshot(root):
        digest = digest_file(source_file)
        captured.append(digest)
        return {"source_files": {"example.py": digest}}

    class StubPlanner:
        manifest = {"fixture": "not model weights"}

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, context, images, *, max_tokens):
            assert len(images) == 3
            source_file.write_text("changed during generation\n")
            return json.dumps(proposal()), {"generation_budget_reached": False}

    monkeypatch.setattr(module, "provenance", source_snapshot)
    monkeypatch.setattr(module, "verify_model", lambda root: StubPlanner.manifest)
    monkeypatch.setattr(module, "LocalQwenPlanner", StubPlanner)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "test-fixture")
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=tmp_path / "model",
        recording=sealed_recording,
        frame=0,
        instruction="Pick the cup",
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "completed", result.metrics
    assert captured[0] == before
    assert result.provenance["source_files"]["example.py"] == before
    assert digest_file(source_file) != before
    assert "planner-source.py" in result.files
    assert result.claims == [] and result.metrics["live_dispatch_authorized"] is False
    assert result.metrics["manipulation_success"] is None
    store.verify(result.run_id)


@pytest.mark.parametrize("max_tokens", [0, -1, 1025, True])
def test_invalid_token_budget_is_rejected_before_model_construction(
    tmp_path, monkeypatch, max_tokens
):
    import bimanual.planner as module

    constructed = []

    def forbidden_constructor(*args, **kwargs):
        constructed.append(True)
        raise AssertionError("Invalid request must never initialize weights")

    monkeypatch.setattr(module, "LocalQwenPlanner", forbidden_constructor)
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=tmp_path / "model",
        recording=tmp_path / "missing",
        frame=0,
        instruction="Pick the cup",
        device="cpu",
        store=store,
        project_root=tmp_path,
        max_tokens=max_tokens,
    )
    assert result.outcome == "failed" and not constructed
    assert "output budget" in result.metrics["error"]
    assert result.claims == [] and result.metrics["live_dispatch_authorized"] is False
    store.verify(result.run_id)


@pytest.mark.parametrize("failure", ["token_budget", "malformed"])
def test_generated_response_failures_are_retained_without_claims(
    tmp_path, monkeypatch, sealed_recording, failure
):
    import bimanual.planner as module

    response = json.dumps(proposal()) if failure == "token_budget" else "{incomplete"

    class StubPlanner:
        manifest = {"fixture": "not model weights"}

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, context, images, *, max_tokens):
            return response, {"generation_budget_reached": failure == "token_budget"}

    monkeypatch.setattr(module, "LocalQwenPlanner", StubPlanner)
    monkeypatch.setattr(module, "verify_model", lambda root: StubPlanner.manifest)
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=tmp_path / "model",
        recording=sealed_recording,
        frame=0,
        instruction="Pick the cup",
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "failed" and result.claims == []
    assert result.metrics["planner_schema_valid"] is False
    assert result.metrics["live_dispatch_authorized"] is False
    directory = store.directory(result.run_id)
    assert (directory / "response.txt").read_text() == response
    assert "proposal.json" not in result.files
    assert "error.txt" in result.files
    store.verify(result.run_id)


def test_model_load_failure_retains_verified_manifest_and_versions(
    tmp_path, monkeypatch, sealed_recording
):
    import importlib.metadata

    import bimanual.planner as module

    manifest = {"fixture": "verified source, not model weights"}
    events = []

    def verify(root):
        events.append("verified")
        return manifest

    def load_failure(*args, **kwargs):
        assert events == ["transformers", "torch", "verified"]
        raise RuntimeError("Fixture model allocation failure")

    def version(name):
        events.append(name)
        return f"fixture-{name}"

    monkeypatch.setattr(module, "verify_model", verify)
    monkeypatch.setattr(module, "LocalQwenPlanner", load_failure)
    monkeypatch.setattr(importlib.metadata, "version", version)
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=tmp_path / "model",
        recording=sealed_recording,
        frame=0,
        instruction="Pick the cup",
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "failed"
    assert "Fixture model allocation failure" in result.metrics["error"]
    directory = store.directory(result.run_id)
    assert json.loads((directory / "model-manifest.json").read_text()) == manifest
    assert result.metrics["transformers_version"] == "fixture-transformers"
    assert result.metrics["torch_version"] == "fixture-torch"
    assert "response.txt" not in result.files
    assert result.claims == [] and result.metrics["live_dispatch_authorized"] is False
    store.verify(result.run_id)


def test_relative_probe_paths_resolve_against_project_root(tmp_path, monkeypatch, sealed_recording):
    import bimanual.planner as module

    assert Path.cwd().resolve() != tmp_path.resolve()
    checked = []
    loaded = []
    manifest = {"fixture": "not model weights"}

    def verify(root):
        checked.append(root)
        return manifest

    class StubPlanner:
        def __init__(self, root, **kwargs):
            loaded.append(root)

        def generate(self, context, images, *, max_tokens):
            return json.dumps(proposal()), {"generation_budget_reached": False}

    monkeypatch.setattr(module, "verify_model", verify)
    monkeypatch.setattr(module, "LocalQwenPlanner", StubPlanner)
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=Path("models/local"),
        recording=sealed_recording.relative_to(tmp_path),
        frame=0,
        instruction="Pick the cup",
        device="cpu",
        store=store,
        project_root=tmp_path,
    )
    assert result.outcome == "completed", result.metrics
    assert checked == loaded == [tmp_path / "models/local"]
    assert result.config["model_root"] == str(tmp_path / "models/local")
    assert result.config["recording"] == str(sealed_recording)
    store.verify(result.run_id)


@pytest.mark.parametrize(
    "profile,overhead",
    [
        ("policy480_v1", (480, 270)),
        ("overhead960_wrist480_v1", (960, 540)),
        ("overhead1920_wrist480_v1", (1920, 1080)),
    ],
)
def test_declared_camera_profile_matches_actual_pixels(profile, overhead):
    ctx = context(camera_profile=profile)
    images = (
        Image.new("RGB", overhead),
        Image.new("RGB", (480, 270)),
        Image.new("RGB", (480, 270)),
    )
    assert planner_messages(ctx, images)[1]["content"][2]["image"] is images[0]
    with pytest.raises(ValueError, match="camera profile"):
        planner_messages(ctx, (images[0].convert("L"), *images[1:]))
    with pytest.raises(ValueError, match="camera profile"):
        planner_messages(ctx, (images[0].resize((32, 32)), *images[1:]))


def test_processor_metrics_report_effective_resolution_not_file_size():
    from bimanual.planner import processor_image_metrics

    images = (
        Image.new("RGB", (1920, 1080)),
        Image.new("RGB", (480, 270)),
        Image.new("RGB", (480, 270)),
    )
    metrics = processor_image_metrics(
        images, [[1, 68, 120], [1, 16, 30], [1, 16, 30]], patch_size=16, merge_size=2
    )
    assert metrics["source_image_dimensions_wh"][0] == [1920, 1080]
    assert metrics["effective_image_dimensions_wh"] == [[1920, 1088], [480, 256], [480, 256]]
    assert metrics["vision_tokens_per_image"] == [2040, 120, 120]
    assert "object_position" not in metrics


@pytest.mark.parametrize(
    "grid",
    [
        [],
        [[1, 16, 30]],
        [[1, 0, 30]] * 3,
        [[2, 16, 30]] * 3,
        [[1, 15, 30]] * 3,
        [[True, 16, 30]] * 3,
    ],
)
def test_processor_metrics_reject_missing_or_invalid_grids(grid):
    from bimanual.planner import processor_image_metrics

    with pytest.raises(ValueError, match="image grid"):
        processor_image_metrics(
            (Image.new("RGB", (480, 270)),) * 3, grid, patch_size=16, merge_size=2
        )


def test_wrong_sensor_bundle_fails_before_weights_load(tmp_path, monkeypatch, sealed_recording):
    import bimanual.planner as module

    def forbidden(*args, **kwargs):
        raise AssertionError("Weights must not load for unverified sensor inputs")

    monkeypatch.setattr(module, "LocalQwenPlanner", forbidden)
    store = EvidenceStore(tmp_path / "evidence")
    result = run_planner_probe(
        model_root=tmp_path / "model",
        recording=sealed_recording,
        frame=0,
        instruction="Pick up the practice block.",
        device="cpu",
        store=store,
        project_root=tmp_path,
        sensor_bundle=tmp_path / "missing",
    )
    assert result.outcome == "failed"
    assert "Weights must not load" not in result.metrics["error"]
    assert result.metrics["live_dispatch_authorized"] is False
    assert "response.txt" not in result.files
    store.verify(result.run_id)
