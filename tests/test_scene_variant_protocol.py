from __future__ import annotations

import json

import pytest

from bimanual.cli import main
from bimanual.evidence import EvidenceStore
from bimanual.scene_variant_protocol import (
    DEFAULT_COMBINED_TEST_SEEDS,
    DEFAULT_DIAGNOSTIC_SEED,
    create_dinner_perturbation_protocol,
    create_scene_variant_bundle,
    load_dinner_perturbation_protocol,
)
from bimanual.scene_variants import FAMILIES


def test_protocol_freezes_six_families_and_ten_unseen_combined_seeds(tmp_path):
    path = tmp_path / "protocol.json"
    created = create_dinner_perturbation_protocol(path)
    loaded = load_dinner_perturbation_protocol(path)
    assert loaded == created
    assert loaded.families == FAMILIES
    assert loaded.combined_test_seeds == DEFAULT_COMBINED_TEST_SEEDS
    assert len(set(loaded.combined_test_seeds)) == 10
    assert loaded.diagnostic_seed == DEFAULT_DIAGNOSTIC_SEED
    assert loaded.generated_scenes_validated is False
    assert loaded.task_success is None
    with pytest.raises(FileExistsError):
        create_dinner_perturbation_protocol(path)


def test_protocol_check_cli_keeps_task_success_unknown(tmp_path, capsys):
    path = tmp_path / "protocol.json"
    create_dinner_perturbation_protocol(path)
    assert main(["scene-variant-protocol-check", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["retain_every_attempt"] is True
    assert report["generated_scenes_validated"] is False
    assert report["task_success"] is None


@pytest.mark.parametrize(
    ("diagnostic", "combined"),
    [
        (1, tuple(range(1, 11))),
        (0, (2,) * 10),
        (0, tuple(range(9))),
        (True, tuple(range(10, 20))),
    ],
)
def test_invalid_allocations_fail_before_file_creation(tmp_path, diagnostic, combined):
    path = tmp_path / "protocol.json"
    with pytest.raises(ValueError):
        create_dinner_perturbation_protocol(
            path, diagnostic_seed=diagnostic, combined_test_seeds=combined
        )
    assert not path.exists()


@pytest.mark.parametrize("family", [*FAMILIES, "combined"])
def test_bundle_materializes_only_frozen_scene_and_keeps_success_unknown(tmp_path, family):
    protocol_path = tmp_path / "protocol.json"
    protocol = create_dinner_perturbation_protocol(protocol_path)
    seed = protocol.combined_test_seeds[0] if family == "combined" else protocol.diagnostic_seed
    store = EvidenceStore(tmp_path / "evidence")
    result = create_scene_variant_bundle(
        protocol_path=protocol_path,
        family=family,
        seed=seed,
        store=store,
        project_root=tmp_path,
    )
    assert result.kind == "dinner_scene_variant"
    assert result.outcome == "prepared"
    assert result.claims == []
    assert result.metrics["scene_compiles"] is True
    assert result.metrics["evaluation_attempted"] is False
    assert result.metrics["task_success"] is None
    directory = store.directory(result.run_id)
    report = json.loads((directory / "variant.json").read_text())
    assert report["requested_family"] == family
    assert (directory / "scene.xml").read_bytes() != (directory / "base-scene.xml").read_bytes()
    store.verify(result.run_id)


def test_bundle_rejects_unallocated_seed_and_family_without_allocating_run(tmp_path):
    protocol_path = tmp_path / "protocol.json"
    create_dinner_perturbation_protocol(protocol_path)
    store = EvidenceStore(tmp_path / "evidence")
    for family, seed in (("combined", 1), ("mass", 1), ("unknown", DEFAULT_DIAGNOSTIC_SEED)):
        with pytest.raises(ValueError):
            create_scene_variant_bundle(
                protocol_path=protocol_path,
                family=family,
                seed=seed,
                store=store,
                project_root=tmp_path,
            )
    assert not (store.root / "runs").exists()
