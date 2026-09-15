"""Synthetic source integrity fixtures; scorer mocks are not manipulation evidence."""

import gzip
import json
import shutil

import pytest
from test_skill_views import make_synthetic_export

from bimanual.evidence import EvidenceStore, digest_file
from bimanual.visual_source import verify_visual_held_out_source, verify_visual_source
from bimanual.visual_training import create_visual_training_protocol
from bimanual.visual_variants import visual_variant


def write(path, value):
    path.write_text(json.dumps(value) + "\n")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    base = tmp_path_factory.mktemp("visual-source-template")
    return make_synthetic_export(base, "v2") / "raw_sources/000000"


def fixture(tmp_path, template, mutate=None, *, visual_seed=7, split="train"):
    store = EvidenceStore(tmp_path / "evidence")
    root = store.new_run()
    shutil.copytree(template, root, dirs_exist_ok=True)
    (root / "manifest.json").unlink()
    config = dict(recipe="v2", render=False, record_demonstration=True, visual_seed=visual_seed)
    scene, report = visual_variant((root / "scene.xml").read_text(), seed=visual_seed)
    (root / "scene.xml").write_text(scene)
    (root / "teacher-assets/scene.xml").write_text(scene)
    write(root / "teacher-assets/visual-variant.json", report)
    layout = json.loads((root / "teacher-assets/layout.json").read_text())
    layout["scene_sha256"] = report["variant_xml_sha256"]
    write(root / "teacher-assets/layout.json", layout)
    assets = json.loads((root / "teacher-assets/manifest.json").read_text())
    for name in ("scene.xml", "layout.json"):
        assets["files"][name] = digest_file(root / "teacher-assets" / name)
    write(root / "teacher-assets/manifest.json", assets)
    write(root / "config.json", config)
    controller = json.loads((root / "controller.json").read_text())
    controller.update(
        seed=visual_seed, split=split, visual_variant="teacher-assets/visual-variant.json"
    )
    write(root / "controller.json", controller)
    data = json.loads((root / "demonstration/episode.json").read_text())
    data["lineage"]["seed"] = visual_seed
    data["lineage"]["split"] = split
    for name in ("scene", "config", "controller"):
        data["lineage"][name]["sha256"] = digest_file(root / data["lineage"][name]["path"])
    write(root / "demonstration/episode.json", data)
    with gzip.open(root / "physics.jsonl.gz", "wt") as stream:
        stream.write("{}\n")
    if mutate:
        mutate(root)
    store.seal(
        root,
        kind="dinner_teacher",
        outcome="completed",
        config=config,
        metrics=dict(
            score=json.loads((root / "score.json").read_text()),
            independent_score=json.loads((root / "independent-score.json").read_text()),
            instrumentation={},
        ),
        source={"git_revision": "a" * 40, "source_sha256": "b" * 64},
        claims=[],
    )
    protocol = tmp_path / "protocol.json"
    create_visual_training_protocol(
        protocol, training_seeds=(7,), validation_seeds=(100,), test_seeds=(200,)
    )
    return root, protocol


def mock_scores(monkeypatch, root):
    from bimanual import visual_source

    monkeypatch.setattr(
        visual_source, "score_dinner", lambda *args: json.loads((root / "score.json").read_text())
    )
    monkeypatch.setattr(
        visual_source,
        "score_dinner_outcomes",
        lambda *args, **kwargs: json.loads((root / "independent-score.json").read_text()),
    )


def test_synthetic_recording_integrity_with_mocked_scorers(tmp_path, template, monkeypatch):
    root, protocol = fixture(tmp_path, template)
    mock_scores(monkeypatch, root)
    result = verify_visual_source(root, protocol_path=protocol)
    assert result.episode.lineage.seed == 7
    assert len(result.episode.frames) == 5050
    assert result.lerobot_decoded_parity is None
    assert result.physical_layout_count == 1


@pytest.mark.parametrize(
    "name",
    [
        "scene.xml",
        "teacher-assets/visual-variant.json",
        "teacher-assets/layout.json",
        "controller.json",
    ],
)
def test_resealed_wrong_visual_identity_rejected(tmp_path, template, name):
    def mutate(root):
        path = root / name
        if name == "scene.xml":
            path.write_text(path.read_text().replace('pos="', 'pos="0 ', 1))
        else:
            value = json.loads(path.read_text())
            value["seed" if name.endswith("controller.json") else "unexpected"] = 9
            write(path, value)

    root, protocol = fixture(tmp_path, template, mutate)
    with pytest.raises(ValueError):
        verify_visual_source(root, protocol_path=protocol)


def test_unsealed_camera_corruption_rejected(tmp_path, template):
    root, protocol = fixture(tmp_path, template)
    (root / "camera-0.png").write_bytes(b"not a PNG")
    with pytest.raises(ValueError, match="digest"):
        verify_visual_source(root, protocol_path=protocol)


def test_outside_training_allocation_rejected(tmp_path, template):
    root, _ = fixture(tmp_path, template)
    protocol = tmp_path / "other.json"
    create_visual_training_protocol(
        protocol, training_seeds=(8,), validation_seeds=(100,), test_seeds=(200,)
    )
    with pytest.raises(ValueError, match="allocation"):
        verify_visual_source(root, protocol_path=protocol)


def test_synthetic_physics_is_not_accepted_by_real_scorers(tmp_path, template):
    root, protocol = fixture(tmp_path, template)
    with pytest.raises(ValueError, match="recomputation"):
        verify_visual_source(root, protocol_path=protocol)


def test_intervened_episode_rejected(tmp_path, template):
    def mutate(root):
        path = root / "demonstration/episode.json"
        value = json.loads(path.read_text())
        value["interventions"] = 1
        write(path, value)

    root, protocol = fixture(tmp_path, template, mutate)
    with pytest.raises(ValueError, match="intervened"):
        verify_visual_source(root, protocol_path=protocol)


def test_resealed_partial_trajectory_rejected(tmp_path, template):
    def mutate(root):
        path = root / "actions.jsonl"
        path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")

    root, protocol = fixture(tmp_path, template, mutate)
    with pytest.raises(ValueError, match="complete v2"):
        verify_visual_source(root, protocol_path=protocol)


def test_held_out_validation_source_is_verified_but_not_training_authorized(
    tmp_path, template, monkeypatch
):
    root, protocol = fixture(tmp_path, template, visual_seed=100, split="validation")
    mock_scores(monkeypatch, root)
    result = verify_visual_held_out_source(root, protocol_path=protocol, split="validation")
    assert result.split == "validation"
    with pytest.raises(ValueError, match="training allocation"):
        verify_visual_source(root, protocol_path=protocol)


def test_held_out_split_and_seed_must_match_frozen_allocation(tmp_path, template, monkeypatch):
    root, protocol = fixture(tmp_path, template, visual_seed=100, split="validation")
    mock_scores(monkeypatch, root)
    with pytest.raises(ValueError, match="held-out allocation"):
        verify_visual_held_out_source(root, protocol_path=protocol, split="test")


def test_held_out_recording_requires_matching_controller_and_episode_split(
    tmp_path, template, monkeypatch
):
    def mutate(root):
        controller = json.loads((root / "controller.json").read_text())
        controller["split"] = "train"
        write(root / "controller.json", controller)
        data = json.loads((root / "demonstration/episode.json").read_text())
        data["lineage"]["controller"]["sha256"] = digest_file(root / "controller.json")
        write(root / "demonstration/episode.json", data)

    root, protocol = fixture(tmp_path, template, mutate=mutate, visual_seed=100, split="validation")
    mock_scores(monkeypatch, root)
    with pytest.raises(ValueError, match="controller lineage"):
        verify_visual_held_out_source(root, protocol_path=protocol, split="validation")


def test_held_out_verifier_refuses_train_split(tmp_path, template):
    root, protocol = fixture(tmp_path, template)
    with pytest.raises(ValueError, match="validation or test"):
        verify_visual_held_out_source(root, protocol_path=protocol, split="train")
