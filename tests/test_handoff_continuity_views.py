"""Small source fixtures verify correction/validation separation without MuJoCo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image
from test_contracts import episode, observation

from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.handoff_continuity_protocol import HandoffContinuityCase
from bimanual.handoff_continuity_teacher import KIND, REQUEST
from bimanual.handoff_continuity_views import (
    continuity_action_window,
    create_handoff_continuity_views,
    load_handoff_continuity_views,
    validate_continuity_window,
)


def _score(action_rows=5):
    return {
        "profile": "handoff_receiver_continuity_physical_score_v1",
        "physical_handoff_success": True,
        "action_rows": action_rows,
        "confirmed_actions": action_rows,
        "partial_actions": 0,
        "physics_rows": action_rows * 50,
        "donor_only_samples": 2000,
        "shared_grasp_samples": 2000,
        "receiver_only_samples": 2000,
        "phases_ordered": True,
        "continuous_airborne_grip": True,
        "acquisition_receiver_contact_samples": 0,
        "forbidden_contact_samples": 0,
        "maximum_overlap_m": 0.0,
    }


def _source(store, monkeypatch, *, case_id="receiver-baseline", seed=41000, mutation=None):
    import bimanual.handoff_continuity_views as module

    case = HandoffContinuityCase(case_id=case_id, seed=seed)
    protocol = SimpleNamespace(
        manifest_sha256="a" * 64,
        phase_boundaries={"correction_replay_end": 530},
        cases=(case,),
    )
    monkeypatch.setattr(module, "load_handoff_continuity_protocol", lambda path: protocol)
    monkeypatch.setattr(module, "_continuity_score", lambda *args: _score())
    root = store.directory("continuity-fixture-" + case_id)
    root.mkdir(parents=True)
    protocol_path = root / "external-protocol.json"
    protocol_path.write_text("protocol")
    config = {
        "protocol_path": str(protocol_path),
        "protocol_file_sha256": digest_file(protocol_path),
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case_id": case.case_id,
        "case": case.model_dump(mode="json"),
        "phase_boundaries": protocol.phase_boundaries,
        "correction_scope": "receiver_close_shared_hold_donor_release",
        "training_only": True,
    }
    for name, value in (
        (REQUEST, canonical(config)),
        ("controller.json", b"{}"),
        ("scene.xml", b"scene"),
        ("layout.json", b"{}"),
        ("plan.json.gz", b"plan"),
        ("protocol.json", protocol_path.read_bytes()),
        ("physics.jsonl", b"{}\n"),
        ("independent-score.json", canonical(_score()) + b"\n"),
    ):
        (root / name).write_bytes(value)
    data = episode(episode_id=root.name, interventions=1)
    data["lineage"]["seed"] = seed
    data["lineage"]["code_revision"] = "b" * 40
    data["lineage"]["source_sha256"] = "c" * 64
    data["frames"] = [
        {
            "observation": observation(index, episode_id=root.name),
            "action_rad": [0.5] * 12 if index < 5 else None,
        }
        for index in range(6)
    ]
    for name, path in (
        ("scene", "scene.xml"),
        ("config", REQUEST),
        ("controller", "controller.json"),
    ):
        data["lineage"][name] = {"path": path, "sha256": digest_file(root / path)}
    for frame in data["frames"]:
        for camera in frame["observation"]["frames"]:
            path = root / camera["artifact"]["path"]
            Image.new("RGB", (480, 270)).save(path)
            camera["artifact"]["sha256"] = digest_file(path)
    rows = [
        {
            "sequence": index,
            "phase": (
                "handoff/receiver_acquisition"
                if index == 1
                else "handoff/right_approach"
                if index in (2, 3)
                else "handoff/receiver_hold"
            ),
            "measured": list(data["frames"][index]["observation"]["joint_position_rad"]),
            "targets_rad": [0.5] * 12,
            "source_plan_index": None,
            "training_eligible": index in (2, 3),
            "applied": True,
            "partial_physics": False,
        }
        for index in range(5)
    ]
    metrics = {
        "physical_handoff_success": True,
        "teacher_assistance": True,
        "learned_execution": False,
        "release_qualified": False,
        "object_state_edits": 0,
        "artificial_attachments": 0,
        "external_object_force_samples": 0,
        "prefix_actions": 1,
        "acquisition_actions": 1,
        "correction_actions": 2,
        "validation_actions": 1,
        "interventions": 1,
        "demonstration_path": "demonstration/episode.json",
        "independent_score": _score(),
    }
    if mutation:
        mutation(config, data, rows, metrics)
        (root / REQUEST).write_bytes(canonical(config))
    (root / "actions.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
    (root / "demonstration").mkdir()
    (root / "demonstration/episode.json").write_bytes(canonical(data))
    return store.seal(
        root,
        kind=KIND,
        outcome="completed",
        config=config,
        metrics=metrics,
        source={"git_revision": "b" * 40, "source_sha256": "c" * 64},
        claims=["Teacher-assisted contact hand-off correction source; no learned success"],
    )


def test_continuity_views_select_only_correction_and_pad_before_validation(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "evidence")
    source = _source(store, monkeypatch)
    path = tmp_path / "views.json"
    views = create_handoff_continuity_views(store, [source.run_id], path)
    assert load_handoff_continuity_views(path, store) == views
    selected = views.sources[0]
    assert (selected.start, selected.end, selected.validation_end) == (2, 4, 5)
    window = continuity_action_window(selected, 1, 3)
    assert window.parent_action_indices == (3, 3, 3)
    assert window.action_is_pad == (False, True, True)
    validate_continuity_window(selected, 1, window)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c, d, r, m: r[2].update(training_eligible=False),
        lambda c, d, r, m: r[4].update(training_eligible=True),
        lambda c, d, r, m: r[3].update(partial_physics=True),
        lambda c, d, r, m: r[2].update(targets_rad=[0.4] * 12),
        lambda c, d, r, m: d.update(interventions=0),
        lambda c, d, r, m: m.update(physical_handoff_success=False),
        lambda c, d, r, m: m.update(object_state_edits=1),
        lambda c, d, r, m: m.update(validation_actions=0),
    ],
)
def test_mutated_continuity_source_is_rejected(tmp_path, monkeypatch, mutation):
    store = EvidenceStore(tmp_path / "evidence")
    source = _source(store, monkeypatch, mutation=mutation)
    with pytest.raises(ValueError):
        create_handoff_continuity_views(store, [source.run_id], tmp_path / "views.json")


def test_duplicate_continuity_case_is_rejected(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "evidence")
    source = _source(store, monkeypatch)
    with pytest.raises(ValueError, match="Duplicate"):
        create_handoff_continuity_views(
            store, [source.run_id, source.run_id], tmp_path / "views.json"
        )
