"""Small sealed fixtures for six-skill corrective replay selection."""

from __future__ import annotations

import pytest
from PIL import Image
from test_contracts import episode, observation

from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_corrective_teacher import KIND, REQUEST
from bimanual.skill_corrective_views import (
    corrective_action_window,
    create_skill_corrective_views,
    load_skill_corrective_views,
    validate_corrective_window,
)


def _source(store, monkeypatch, mutation=None):
    import bimanual.skill_corrective_views as module

    monkeypatch.setattr(
        module,
        "_score",
        lambda *args, **kwargs: {"profile": "dinner_skill_outcomes_v1", "state": "succeeded"},
    )
    root = store.directory("skill-corrective-fixture")
    root.mkdir(parents=True)
    case = dict(
        case_id="bar_contact_avoidance-51002",
        family_id="bar_contact_avoidance",
        skill_id="bar_place_and_return",
        seed=51002,
    )
    config = dict(case=case, case_id=case["case_id"], training_only=True)
    for name, content in (
        (REQUEST, canonical(config)),
        ("controller.json", b"{}"),
        ("scene.xml", b"scene"),
        ("layout.json", b"{}"),
        ("plan.json.gz", b"plan"),
        ("protocol.json", b"{}"),
        ("collection-segments.json", b"{}"),
    ):
        (root / name).write_bytes(content)
    data = episode(episode_id=root.name, interventions=1)
    data["lineage"]["seed"] = case["seed"]
    data["frames"] = [
        dict(
            observation=observation(index, episode_id=root.name),
            action_rad=[0.5] * 12 if index < 5 else None,
        )
        for index in range(6)
    ]
    for name, path in (
        ("scene", "scene.xml"),
        ("config", REQUEST),
        ("controller", "controller.json"),
    ):
        data["lineage"][name] = dict(path=path, sha256=digest_file(root / path))
    for frame in data["frames"]:
        for camera in frame["observation"]["frames"]:
            path = root / camera["artifact"]["path"]
            Image.new("RGB", (480, 270)).save(path)
            camera["artifact"]["sha256"] = digest_file(path)
    rows = [
        dict(
            episode_id=root.name,
            observation_sequence=index,
            targets_rad=[0.5] * 12,
            applied=True,
            partial_physics=False,
            segment="prefix" if index < 1 else "acquisition" if index < 3 else "replay",
            training_eligible=False,
            candidate_replay_action=index >= 3,
        )
        for index in range(5)
    ]
    score = {"profile": "dinner_skill_outcomes_v1", "state": "succeeded"}
    metrics = dict(
        teacher_assistance=True,
        learned_execution=False,
        training_eligible=False,
        release_qualified=False,
        physical_skill_success=True,
        recording_complete=True,
        object_state_edits=0,
        artificial_attachments=0,
        external_object_force_samples=0,
        prefix_actions=1,
        acquisition_actions=2,
        replay_actions=2,
        interventions=1,
        demonstration_path="demonstration/episode.json",
        independent_score=score,
    )
    if mutation:
        mutation(data, rows, metrics)
    (root / "physics.jsonl").write_text("{}\n" * 250)
    (root / "actions.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
    (root / "independent-score.json").write_bytes(canonical(score))
    (root / "demonstration").mkdir()
    (root / "demonstration/episode.json").write_bytes(canonical(data))
    return store.seal(
        root,
        kind=KIND,
        outcome="completed",
        config=config,
        metrics=metrics,
        source=dict(git_revision="a" * 40, source_sha256="b" * 64),
        claims=[],
    )


def test_view_selects_only_replay_and_pads(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "evidence")
    run = _source(store, monkeypatch)
    path = tmp_path / "views.json"
    view = create_skill_corrective_views(store, [run.run_id], path)
    assert load_skill_corrective_views(path, store) == view
    source = view.sources[0]
    assert (source.start, source.end) == (3, 5)
    window = corrective_action_window(source, 1, 3)
    assert window.parent_action_indices == (4, 4, 4)
    assert window.action_is_pad == (False, True, True)
    validate_corrective_window(source, 1, window)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data, rows, metrics: rows[3].update(candidate_replay_action=False),
        lambda data, rows, metrics: rows[1].update(training_eligible=True),
        lambda data, rows, metrics: rows[3].update(partial_physics=True),
        lambda data, rows, metrics: metrics.update(physical_skill_success=False),
        lambda data, rows, metrics: metrics.update(object_state_edits=1),
    ],
)
def test_invalid_source_is_rejected(tmp_path, monkeypatch, mutation):
    store = EvidenceStore(tmp_path / "evidence")
    run = _source(store, monkeypatch, mutation)
    with pytest.raises(ValueError):
        create_skill_corrective_views(store, [run.run_id], tmp_path / "views.json")
