import json
import shutil
from pathlib import Path

import pytest
from PIL import Image
from test_contracts import episode

from bimanual.contracts import Observation
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import EvidenceStore, digest_file
from bimanual.planner_sensors import (
    PROFILES,
    SensorBundle,
    create_sensor_bundle,
    load_sensor_bundle,
    observation_digest,
)


@pytest.fixture
def source(tmp_path):
    store = EvidenceStore(tmp_path / "source")
    root = store.new_run()
    bodies = "".join(
        f'<body pos="{i * 0.01} 0 0"><joint name="{name}"/>'
        '<geom type="sphere" size=".01" mass=".1"/></body>'
        for i, name in enumerate(JOINT_ORDER)
    )
    cameras = "".join(f'<camera name="{name}" pos="0 0 1"/>' for name in CAMERAS)
    actuators = "".join(f'<position name="{name}" joint="{name}"/>' for name in JOINT_ORDER)
    (root / "scene.xml").write_text(
        f"<mujoco><worldbody>{bodies}{cameras}</worldbody><actuator>{actuators}</actuator></mujoco>"
    )
    for name in ("controller.json", "config.json", "LICENSE-SO101", "upstream.json", "teacher.py"):
        (root / name).write_text("Fixture only")
    data = episode()
    for kind in ("scene", "config", "controller"):
        artifact = data["lineage"][kind]
        artifact["sha256"] = digest_file(root / artifact["path"])
    for frame in data["frames"]:
        for index, camera in enumerate(frame["observation"]["frames"]):
            target = root / camera["artifact"]["path"]
            Image.new("RGB", (480, 270), (index * 50, 0, 0)).save(target)
            camera["artifact"]["sha256"] = digest_file(target)
    (root / "demonstration").mkdir()
    (root / "demonstration/episode.json").write_text(json.dumps(data))
    manifest = store.seal(
        root, kind="fixture", outcome="completed", config={}, metrics={}, source={}, claims=[]
    )
    return root, manifest, Observation.model_validate(data["frames"][0]["observation"])


@pytest.fixture
def fake_render(monkeypatch):
    import bimanual.planner_sensors as module

    calls = []

    def render(model, data, camera, dimensions):
        calls.append((camera, dimensions))
        return Image.new("RGB", dimensions, (CAMERAS.index(camera) * 50, 0, 0))

    monkeypatch.setattr(module, "_render", render)
    return calls


def build(tmp_path, source, profile="overhead960_wrist480_v1"):
    store = EvidenceStore(tmp_path / "output")
    result = create_sensor_bundle(source[0], profile=profile, store=store, project_root=tmp_path)
    return store, result


def load(root, source, **changes):
    args = dict(
        observation=source[2],
        source_run_id=source[1].run_id,
        source_manifest_sha256=source[1].manifest_sha256,
    )
    args.update(changes)
    return load_sensor_bundle(root, **args)


@pytest.mark.parametrize("profile", list(PROFILES))
def test_bundle_round_trip_has_separate_profile_and_exact_source(
    tmp_path, source, fake_render, profile
):
    store, result = build(tmp_path, source, profile)
    assert result.outcome == "completed", result.metrics
    root = store.directory(result.run_id)
    images = load(root, source)
    assert tuple(image.size for image in images) == PROFILES[profile]
    assert fake_render[:3] == [(name, (480, 270)) for name in CAMERAS]
    assert fake_render[3:] == [("overhead", PROFILES[profile][0])]
    bundle = SensorBundle.model_validate_json((root / "sensor-bundle.json").read_text())
    assert bundle.source_observation_sha256 == observation_digest(source[2])
    assert bundle.source_manifest_sha256 == source[1].manifest_sha256
    assert bundle.source_manifest.sha256 == digest_file(source[0] / "manifest.json")
    assert not bundle.live_dispatch_authorized and result.claims == []
    assert bundle.mode == "recorded_reset_only"
    assert source[2].frames[0].width == 480
    with pytest.raises(ValueError):
        bundle.profile = "overhead1920_wrist480_v1"


@pytest.mark.parametrize("change", ["episode", "timestamp", "joint", "source_id", "source_digest"])
def test_loader_requires_entire_observation_and_source_identity(
    tmp_path, source, fake_render, change
):
    store, result = build(tmp_path, source)
    updates = {}
    if change.startswith("source"):
        updates["source_run_id" if change == "source_id" else "source_manifest_sha256"] = "b" * 64
    else:
        data = source[2].model_dump(mode="json")
        if change == "episode":
            data["episode_id"] = "different"
        elif change == "joint":
            data["joint_position_rad"][0] = 0.1
        else:
            data["observed_monotonic_ns"] += 1
            for camera in data["frames"]:
                camera["observed_monotonic_ns"] += 1
        updates["observation"] = Observation.model_validate(data)
    with pytest.raises(ValueError, match="identity"):
        load(store.directory(result.run_id), source, **updates)


def reseal(store, result, mutate):
    original = store.directory(result.run_id)
    target = store.new_run()
    for path in original.iterdir():
        if path.name == "manifest.json":
            continue
        if path.is_dir():
            shutil.copytree(path, target / path.name)
        else:
            shutil.copyfile(path, target / path.name)
    data = json.loads((target / "sensor-bundle.json").read_text())
    mutate(target, data)
    (target / "sensor-bundle.json").write_text(json.dumps(data))
    store.seal(
        target,
        kind=result.kind,
        outcome=result.outcome,
        config=result.config,
        metrics=result.metrics,
        source={},
        claims=[],
    )
    return target


@pytest.mark.parametrize("change", ["mode", "dimensions", "calibration", "source_copy", "gray_png"])
def test_resealed_bad_content_is_rejected(tmp_path, source, fake_render, change):
    store, result = build(tmp_path, source)

    def mutate(root, data):
        if change == "mode":
            data["live_dispatch_authorized"] = True
        elif change == "dimensions":
            data["images"][0]["width"] = 480
        elif change == "source_copy":
            data["source_copies"] = data["source_copies"][1:]
        elif change == "calibration":
            path = root / data["calibration"]["path"]
            calibration = json.loads(path.read_text())
            calibration["cameras"][0]["fovy"] += 1
            path.write_text(json.dumps(calibration))
            data["calibration"]["sha256"] = digest_file(path)
        else:
            path = root / data["images"][0]["artifact"]["path"]
            Image.new("L", (960, 540)).save(path)
            data["images"][0]["artifact"]["sha256"] = digest_file(path)

    modified = reseal(store, result, mutate)
    with pytest.raises(ValueError):
        load(modified, source)


def test_corruption_rejected_by_outer_seal(tmp_path, source, fake_render):
    store, result = build(tmp_path, source)
    root = store.directory(result.run_id)
    (root / "images/0.png").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="digest"):
        load(root, source)


def test_baseline_mismatch_stops_before_high_resolution(tmp_path, source, monkeypatch):
    import bimanual.planner_sensors as module

    dimensions_seen = []

    def wrong(model, data, camera, dimensions):
        dimensions_seen.append(dimensions)
        return Image.new("RGB", dimensions, "white")

    monkeypatch.setattr(module, "_render", wrong)
    store, result = build(tmp_path, source)
    assert result.outcome == "failed" and "pixel-identical" in result.metrics["error"]
    assert dimensions_seen == [(480, 270)]
    assert "error.txt" in result.files
    store.verify(result.run_id)
    with pytest.raises(ValueError):
        load(store.directory(result.run_id), source)


def test_state_mutation_or_interrupt_is_sealed(tmp_path, source, monkeypatch):
    import bimanual.planner_sensors as module

    def wrong(model, data, camera, dimensions):
        data.qpos[0] += 0.01
        return Image.new("RGB", dimensions)

    monkeypatch.setattr(module, "_render", wrong)
    store, result = build(tmp_path, source)
    assert result.outcome == "failed" and "changed reset state" in result.metrics["error"]
    store.verify(result.run_id)

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "_render", interrupted)
    store, result = build(tmp_path, source)
    assert result.outcome == "interrupted"
    store.verify(result.run_id)


def test_unsupported_profile_fails_before_reconstruction(tmp_path):
    store, result = build(tmp_path, (Path("missing"),), profile="unknown")
    assert result.outcome == "failed" and "profile" in result.metrics["error"]
    store.verify(result.run_id)


def test_arbitrary_recorded_frames_cannot_be_reconstructed(tmp_path):
    from test_contracts import observation

    from bimanual.planner_sensors import _reset_model

    with pytest.raises(ValueError, match="sequence-zero"):
        _reset_model(tmp_path / "missing.xml", Observation.model_validate(observation(1)))


@pytest.mark.parametrize("real_renderer", [False, pytest.param(True, marks=pytest.mark.render)])
def test_sensor_bundle_passes_through_planner_copy_without_changing_policy_observation(
    tmp_path, source, monkeypatch, real_renderer
):
    import bimanual.planner as planner
    import bimanual.planner_sensors as sensors

    if real_renderer:
        # Construct a real rendered reset fixture before sealing; no archived user data needed.
        source_store = EvidenceStore(tmp_path / "rendered-source")
        recording = source_store.new_run()
        for path in source[0].iterdir():
            if path.name == "manifest.json":
                continue
            if path.is_dir():
                shutil.copytree(path, recording / path.name)
            else:
                shutil.copyfile(path, recording / path.name)
        model, data = sensors._reset_model(recording / "scene.xml", source[2])
        raw = json.loads((recording / "demonstration/episode.json").read_text())
        for frame in raw["frames"][0]["observation"]["frames"]:
            target = recording / frame["artifact"]["path"]
            sensors._render(model, data, frame["camera"], (480, 270)).save(target)
            frame["artifact"]["sha256"] = digest_file(target)
        (recording / "demonstration/episode.json").write_text(json.dumps(raw))
        manifest = source_store.seal(
            recording,
            kind="rendered_fixture",
            outcome="completed",
            config={},
            metrics={},
            source={},
            claims=[],
        )
        source = recording, manifest, Observation.model_validate(raw["frames"][0]["observation"])
    else:
        monkeypatch.setattr(
            sensors,
            "_render",
            lambda model, data, camera, dimensions: Image.new(
                "RGB", dimensions, (CAMERAS.index(camera) * 50, 0, 0)
            ),
        )
    store, bundle = build(tmp_path, source)
    assert bundle.outcome == "completed", bundle.metrics
    expected = load(store.directory(bundle.run_id), source)
    observed = []

    class StubPlanner:
        def __init__(self, *args, **kwargs):
            pass

        def generate(self, context, images, *, max_tokens):
            assert context.observation == source[2]
            assert context.camera_profile == "overhead960_wrist480_v1"
            assert [image.tobytes() for image in images] == [image.tobytes() for image in expected]
            observed.append(True)
            return json.dumps(
                {
                    "schema_version": 2,
                    "request": {
                        "episode_id": context.observation.episode_id,
                        "instruction_revision": 0,
                        "observation_sequence": 0,
                        "skill": "clarify",
                        "arm": "none",
                        "target": None,
                        "destination": None,
                        "explanation": "Fixture output only",
                    },
                    "target_visibility": "uncertain",
                    "visible_state": "uncertain",
                    "visual_explanation": "Fixture output only",
                }
            ), {"generation_budget_reached": False}

    monkeypatch.setattr(planner, "LocalQwenPlanner", StubPlanner)
    monkeypatch.setattr(planner, "verify_model", lambda root: {"fixture": True})
    result = planner.run_planner_probe(
        model_root=tmp_path / "missing-model",
        recording=source[0],
        frame=0,
        instruction="Inspect scene",
        device="cpu",
        store=store,
        project_root=tmp_path,
        sensor_bundle=store.directory(bundle.run_id),
    )
    assert result.outcome == "completed", result.metrics
    assert observed == [True]
    copied = store.directory(result.run_id) / "sensor-input/runs" / bundle.run_id
    assert [im.tobytes() for im in load(copied, source)] == [im.tobytes() for im in expected]
    assert not result.metrics["live_dispatch_authorized"] and result.claims == []
    store.verify(result.run_id)
