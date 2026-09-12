from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.scene_variant_suite import SceneVariantSuiteEntry
from bimanual.workflow_release_runner import KIND as CASE_KIND
from bimanual.workflow_release_runner import REQUEST
from bimanual.workflow_release_suite import create_workflow_release_suite


def _cases():
    families = ("placement", "mass", "friction", "shape", "lighting", "background")
    rows = [
        SceneVariantSuiteEntry(
            case_id=f"{family}-29001",
            family=family,
            seed=29001,
            run_id=f"scene-{index}",
            manifest_sha256=f"{index + 1:064x}",
            scene_sha256=f"{index + 101:064x}",
            layout_sha256=f"{index + 201:064x}",
        )
        for index, family in enumerate(families)
    ]
    rows.extend(
        SceneVariantSuiteEntry(
            case_id=f"combined-{seed}",
            family="combined",
            seed=seed,
            run_id=f"scene-{seed}",
            manifest_sha256=f"{seed:064x}",
            scene_sha256=f"{seed + 100:064x}",
            layout_sha256=f"{seed + 200:064x}",
        )
        for seed in range(30001, 30011)
    )
    return tuple(rows)


def _setup(tmp_path, monkeypatch, *, count=16, failed_case=None):
    import bimanual.workflow_release_suite as module

    protocol_path = tmp_path / "release.json"
    protocol_path.write_text('{"fixture":"release"}')
    protocol = SimpleNamespace(
        manifest_sha256="d" * 64,
        selection_rule="evaluate_every_frozen_scene_once_in_declared_order",
        cases=_cases(),
    )
    monkeypatch.setattr(module, "load_workflow_release_protocol", lambda path: protocol)
    store = EvidenceStore(tmp_path / "evidence")
    expected = {}
    for case in protocol.cases[:count]:
        request = {
            "protocol_manifest_sha256": protocol.manifest_sha256,
            "case_id": case.case_id,
        }
        directory = store.new_run()
        (directory / REQUEST).write_text(json.dumps(request))
        wrapper = store.seal(
            directory,
            kind=CASE_KIND,
            outcome="failed" if case.case_id == failed_case else "completed",
            config=request,
            metrics={"case_id": case.case_id},
            source={},
            claims=[],
        )
        expected[case.case_id] = wrapper

    def validate(local_store, wrapper, loaded_protocol, case):
        assert local_store is store and loaded_protocol is protocol
        assert wrapper == expected[case.case_id]
        success = case.case_id != failed_case
        return {
            "case_id": case.case_id,
            "family": case.family,
            "seed": case.seed,
            "wrapper_run_id": wrapper.run_id,
            "wrapper_manifest_sha256": wrapper.manifest_sha256,
            "process_outcome": "completed",
            "execution_complete": True,
            "process_transport_clean": True,
            "evaluation_outcome": "completed" if success else "failed",
            "independent_task_success": success,
        }

    monkeypatch.setattr(module, "_validate_wrapper", validate)
    return protocol_path, protocol, store


def test_aggregates_all_cases_in_frozen_order_and_reuses_report(tmp_path, monkeypatch):
    protocol_path, protocol, store = _setup(tmp_path, monkeypatch)
    first = create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)
    second = create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)
    assert first == second
    assert first.outcome == "completed"
    assert first.metrics["successful_cases"] == 16
    assert first.metrics["local_prequalification_passed"] is True
    assert first.metrics["one_factor_diagnostics"]["successful_cases"] == 6
    assert first.metrics["combined_test_seeds"]["successful_cases"] == 10
    assert first.metrics["hackathon_10_seed_target_met"] is True
    assert first.metrics["release_success"] is None
    assert first.metrics["intel_validated"] is False
    assert [row["case_id"] for row in first.metrics["cases"]] == [
        case.case_id for case in protocol.cases
    ]


def test_missing_case_stops_without_partial_report(tmp_path, monkeypatch):
    protocol_path, _, store = _setup(tmp_path, monkeypatch, count=15)
    with pytest.raises(RuntimeError, match="missing"):
        create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)
    assert all(
        manifest.kind != "local_workflow_release_suite"
        for manifest in (
            store.verify(path.parent.name) for path in (store.root / "runs").glob("*/manifest.json")
        )
    )


def test_duplicate_case_stops_aggregation(tmp_path, monkeypatch):
    protocol_path, protocol, store = _setup(tmp_path, monkeypatch)
    case = protocol.cases[0]
    request = {
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case_id": case.case_id,
    }
    directory = store.new_run()
    (directory / REQUEST).write_text(json.dumps(request))
    store.seal(
        directory,
        kind=CASE_KIND,
        outcome="completed",
        config=request,
        metrics={"case_id": case.case_id},
        source={},
        claims=[],
    )
    with pytest.raises(RuntimeError, match="duplicated"):
        create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)


def test_existing_report_rechecks_later_duplicate(tmp_path, monkeypatch):
    protocol_path, protocol, store = _setup(tmp_path, monkeypatch)
    create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)
    case = protocol.cases[0]
    request = {
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case_id": case.case_id,
    }
    directory = store.new_run()
    (directory / REQUEST).write_text(json.dumps(request))
    store.seal(
        directory,
        kind=CASE_KIND,
        outcome="completed",
        config=request,
        metrics={"case_id": case.case_id},
        source={},
        claims=[],
    )
    with pytest.raises(RuntimeError, match="duplicated"):
        create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)


def test_failed_case_is_retained_without_local_pass_claim(tmp_path, monkeypatch):
    protocol_path, _, store = _setup(tmp_path, monkeypatch, failed_case="combined-30010")
    result = create_workflow_release_suite(protocol_path, store=store, project_root=tmp_path)
    assert result.outcome == "failed"
    assert result.metrics["successful_cases"] == 15
    assert result.metrics["failed_cases"] == 1
    assert result.metrics["one_factor_diagnostics"]["successful_cases"] == 6
    assert result.metrics["combined_test_seeds"]["successful_cases"] == 9
    assert result.metrics["hackathon_10_seed_target_met"] is False
    assert result.metrics["local_prequalification_passed"] is False
    assert result.claims == []
