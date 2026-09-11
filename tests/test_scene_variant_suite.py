from __future__ import annotations

import json

import pytest

from bimanual.cli import main
from bimanual.evidence import EvidenceStore
from bimanual.scene_variant_protocol import (
    create_dinner_perturbation_protocol,
    create_scene_variant_bundle,
)
from bimanual.scene_variant_suite import (
    load_scene_variant_suite,
    prepare_scene_variant_suite,
)


def _protocol(tmp_path):
    path = tmp_path / "protocol.json"
    return path, create_dinner_perturbation_protocol(path)


def test_preparation_seals_all_six_diagnostics_and_ten_combined_inputs(tmp_path):
    protocol_path, protocol = _protocol(tmp_path)
    store = EvidenceStore(tmp_path / "evidence")
    result = prepare_scene_variant_suite(
        protocol_path=protocol_path, store=store, project_root=tmp_path
    )
    assert result.outcome == "prepared" and result.claims == []
    assert result.metrics["prepared_case_count"] == 16
    assert result.metrics["evaluation_attempted"] is False
    assert result.metrics["task_success"] is None
    manifest, index = load_scene_variant_suite(
        store.directory(result.run_id), protocol_path=protocol_path
    )
    assert manifest == result
    assert [entry.family for entry in index.entries[:6]] == list(protocol.families)
    assert [entry.seed for entry in index.entries[:6]] == [protocol.diagnostic_seed] * 6
    assert [entry.seed for entry in index.entries[6:]] == list(protocol.combined_test_seeds)
    assert len({entry.run_id for entry in index.entries}) == 16


def test_preparation_is_resumable_and_does_not_duplicate_children_or_report(tmp_path, capsys):
    protocol_path, protocol = _protocol(tmp_path)
    store = EvidenceStore(tmp_path / "evidence")
    first_child = create_scene_variant_bundle(
        protocol_path=protocol_path,
        family=protocol.families[0],
        seed=protocol.diagnostic_seed,
        store=store,
        project_root=tmp_path,
    )
    first = prepare_scene_variant_suite(
        protocol_path=protocol_path, store=store, project_root=tmp_path
    )
    second = prepare_scene_variant_suite(
        protocol_path=protocol_path, store=store, project_root=tmp_path
    )
    assert second == first
    assert (
        main(
            [
                "--project-root",
                str(tmp_path),
                "--artifacts",
                str(store.root),
                "scene-variant-suite-prepare",
                str(protocol_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["run_id"] == first.run_id
    _, index = load_scene_variant_suite(store.directory(first.run_id), protocol_path=protocol_path)
    assert index.entries[0].run_id == first_child.run_id
    kinds = [
        json.loads(path.read_text())["kind"] for path in store.root.glob("runs/*/manifest.json")
    ]
    assert kinds.count("dinner_scene_variant") == 16
    assert kinds.count("dinner_scene_variant_suite") == 1


def test_duplicate_matching_child_blocks_suite_instead_of_selecting_latest(tmp_path):
    protocol_path, protocol = _protocol(tmp_path)
    store = EvidenceStore(tmp_path / "evidence")
    for _ in range(2):
        create_scene_variant_bundle(
            protocol_path=protocol_path,
            family=protocol.families[0],
            seed=protocol.diagnostic_seed,
            store=store,
            project_root=tmp_path,
        )
    with pytest.raises(ValueError, match="Multiple prepared scenes"):
        prepare_scene_variant_suite(protocol_path=protocol_path, store=store, project_root=tmp_path)
    assert not any(
        json.loads(path.read_text())["kind"] == "dinner_scene_variant_suite"
        for path in store.root.glob("runs/*/manifest.json")
    )


def test_changed_child_is_rejected_by_suite_verifier(tmp_path):
    protocol_path, _ = _protocol(tmp_path)
    store = EvidenceStore(tmp_path / "evidence")
    result = prepare_scene_variant_suite(
        protocol_path=protocol_path, store=store, project_root=tmp_path
    )
    _, index = load_scene_variant_suite(store.directory(result.run_id), protocol_path=protocol_path)
    (store.directory(index.entries[0].run_id) / "scene.xml").write_text("<mujoco/>")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_scene_variant_suite(store.directory(result.run_id), protocol_path=protocol_path)
