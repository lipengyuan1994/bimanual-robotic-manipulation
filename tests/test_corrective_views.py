"""Small sealed RGB fixtures; no physics, policy or training jobs."""

import json

import pytest
from PIL import Image
from test_contracts import episode, observation

from bimanual.corrective_views import (
    corrective_action_window,
    create_corrective_views,
    load_corrective_views,
    validate_corrective_window,
)
from bimanual.evidence import EvidenceStore, canonical, digest_file


def source(store, *, seed=7, acquisition=1, mutation=None):
    root = store.new_run()
    config = dict(training_only=True, record_demonstration=True, variation_seed=seed)
    for name, content in [
        ("scene.xml", b"scene"),
        ("config.json", canonical(config)),
        ("controller.json", b"{}"),
    ]:
        (root / name).write_bytes(content)
    data = episode(episode_id=root.name, interventions=int(acquisition > 0))
    data["frames"] = [
        dict(
            observation=observation(i, episode_id=root.name),
            action_rad=[0.5] * 12 if i < 3 else None,
        )
        for i in range(4)
    ]
    data["lineage"]["seed"] = seed
    for name in ("scene", "config", "controller"):
        path = name + (".xml" if name == "scene" else ".json")
        data["lineage"][name] = dict(path=path, sha256=digest_file(root / path))
    for frame in data["frames"]:
        for camera in frame["observation"]["frames"]:
            path = root / camera["artifact"]["path"]
            Image.new("RGB", (480, 270)).save(path)
            camera["artifact"]["sha256"] = digest_file(path)
    rows = [
        dict(
            sequence=i,
            target=[0.5] * 12,
            measured=[0.0] * 12,
            training_eligible=i >= acquisition,
            applied=True,
            partial_physics=False,
            phase="feedback/acquisition" if i < acquisition else "handoff/left_approach",
        )
        for i in range(3)
    ]
    metrics = dict(
        goals_reached=3,
        physical_handoff_success=None,
        teacher_assistance=True,
        learned_execution=False,
        normal_reset=True,
        correction_start_action=acquisition,
        acquisition_actions=acquisition,
        actions=3,
        demonstration_path="demonstration/episode.json",
    )
    if mutation:
        mutation(data, rows, metrics)
    (root / "demonstration").mkdir()
    (root / "demonstration/episode.json").write_bytes(canonical(data))
    (root / "actions.jsonl").write_bytes(b"".join(canonical(r) + b"\n" for r in rows))
    return store.seal(
        root,
        kind="feedback_approach_teacher_recording",
        outcome="completed",
        config=config,
        metrics=metrics,
        source=dict(git_revision="a" * 40, source_sha256="b" * 64),
        claims=[],
    )


def test_multiple_sources_roundtrip_and_padding(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    a, b = source(store), source(store, seed=8, acquisition=0)
    path = tmp_path / "views.json"
    view = create_corrective_views(store, [a.run_id, b.run_id], path)
    assert load_corrective_views(path, store) == view
    assert [s.seed for s in view.sources] == [7, 8]
    assert view.task_scope == "approach_only" and view.independent_scene_count is None
    window = corrective_action_window(view.sources[0], 1, 3)
    assert window.parent_action_indices == (2, 2, 2)
    assert window.action_is_pad == (False, True, True)
    validate_corrective_window(view.sources[0], 1, window)
    with pytest.raises(ValueError, match="crosses"):
        validate_corrective_window(view.sources[1], 1, window)
    with pytest.raises(ValueError):
        corrective_action_window(view.sources[0], 2, 3)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d, r, m: r[0].update(applied=False),
        lambda d, r, m: r[1].update(partial_physics=True),
        lambda d, r, m: r[0].update(training_eligible=True),
        lambda d, r, m: r[1].update(target=[0.4] * 12),
        lambda d, r, m: r[1].update(measured=[0.1] * 12),
        lambda d, r, m: r[1].update(sequence=2),
        lambda d, r, m: d.update(interventions=0),
        lambda d, r, m: d["lineage"].update(split="test"),
        lambda d, r, m: d["lineage"].update(seed=8),
        lambda d, r, m: m.update(correction_start_action=0),
        lambda d, r, m: m.update(actions=2),
        lambda d, r, m: m.update(physical_handoff_success=True),
    ],
)
def test_reject_invalid_sealed_alignment(tmp_path, mutation):
    store = EvidenceStore(tmp_path / "evidence")
    run = source(store, mutation=mutation)
    with pytest.raises(ValueError):
        create_corrective_views(store, [run.run_id], tmp_path / "views.json")
    assert not (tmp_path / "views.json").exists()


def test_duplicate_sources_and_tampering(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    run = source(store)
    path = tmp_path / "views.json"
    with pytest.raises(ValueError, match="Duplicate"):
        create_corrective_views(store, [run.run_id, run.run_id], path)
    create_corrective_views(store, [run.run_id], path)
    data = json.loads(path.read_text())
    data["sources"][0]["start"] = 0
    path.write_bytes(canonical(data))
    with pytest.raises(ValueError, match="digest"):
        load_corrective_views(path, store)
    (store.directory(run.run_id) / "actions.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="digest"):
        create_corrective_views(store, [run.run_id], tmp_path / "other.json")
