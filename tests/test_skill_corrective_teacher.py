import json
from pathlib import Path

import numpy as np
import pytest

from bimanual import skill_corrective_teacher as teacher_module
from bimanual.evidence import EvidenceStore
from bimanual.skill_corrective_protocol import SkillCorrectiveCollectionProtocol
from bimanual.skill_corrective_teacher import (
    KIND,
    MAX_ACQUISITION_DELTA_RAD,
    REQUEST,
    _acquisition_targets,
    _case_rows,
    _reservation_name,
    build_skill_corrective_request,
    run_skill_corrective_case,
)

PROTOCOL = (
    Path(__file__).parents[1] / "docs/experiments/six-skill-corrective-collection-protocol-v1.json"
)


@pytest.fixture
def static_protocol(monkeypatch):
    """Exercise coordinator behavior without relying on ignored field evidence."""
    protocol = SkillCorrectiveCollectionProtocol.model_validate_json(PROTOCOL.read_bytes())
    monkeypatch.setattr(
        teacher_module,
        "load_skill_corrective_collection_protocol",
        lambda _path: protocol,
    )
    return protocol


def test_frozen_cases_are_complete_and_approach_assignment_is_deterministic(static_protocol):
    rows = _case_rows(static_protocol)
    assert len(rows) == 20
    assert len({row["case_id"] for row in rows}) == 20
    assert all(row["teacher_assisted"] and not row["learned_execution"] for row in rows)
    assert all(row["training_eligible"] is False for row in rows)
    approach = [row["skill_id"] for row in rows if row["family_id"] == "approach_contact"]
    assert approach == [
        "cup_pick_place",
        "plate_pick_place",
        "fork_retrieve_place",
        "cup_pick_place",
        "plate_pick_place",
    ]


def test_request_binds_exact_case_and_protocol(static_protocol):
    request = build_skill_corrective_request(PROTOCOL, "bar_contact_avoidance-51000")
    assert request["case"]["skill_id"] == "bar_place_and_return"
    assert request["case"]["training_eligible"] is False
    assert request["training_only"] is True
    with pytest.raises(ValueError, match="not in"):
        build_skill_corrective_request(PROTOCOL, "bar_contact_avoidance-0")


def test_acquisition_is_one_bounded_probe_and_exact_measured_state_recovery():
    measured = np.linspace(-0.4, 0.4, 12)
    probe, recovery = _acquisition_targets(measured, seed=51000, family_id="bar_contact_avoidance")
    assert recovery.tolist() == measured.tolist()
    assert (abs(probe - measured) <= MAX_ACQUISITION_DELTA_RAD).all()
    assert (probe[:6] == measured[:6]).all()


def test_existing_incomplete_reservation_is_never_retried(tmp_path, static_protocol):
    request = build_skill_corrective_request(PROTOCOL, "bar_contact_avoidance-51000")
    store = EvidenceStore(tmp_path / "evidence")
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    directory.mkdir(parents=True)
    (directory / REQUEST).write_text(json.dumps(request))
    with pytest.raises(RuntimeError, match="consumes"):
        run_skill_corrective_case(
            PROTOCOL, request["case_id"], store=store, project_root=Path.cwd()
        )


def test_existing_different_request_is_rejected(tmp_path, static_protocol):
    request = build_skill_corrective_request(PROTOCOL, "bar_contact_avoidance-51000")
    store = EvidenceStore(tmp_path / "evidence")
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    directory.mkdir(parents=True)
    (directory / REQUEST).write_text(json.dumps(request | {"case_id": "contradiction"}))
    with pytest.raises(ValueError, match="contradicts"):
        run_skill_corrective_case(
            PROTOCOL, request["case_id"], store=store, project_root=Path.cwd()
        )


def test_kind_is_not_handoff_continuity_kind():
    assert KIND == "six_skill_corrective_teacher_recording"


def test_cancelled_case_is_sealed_and_then_consumed(tmp_path, static_protocol):
    store = EvidenceStore(tmp_path / "evidence")
    result = run_skill_corrective_case(
        PROTOCOL,
        "bar_contact_avoidance-51000",
        store=store,
        project_root=Path.cwd(),
        cancelled=lambda: True,
    )
    assert result.kind == KIND
    assert result.outcome == "failed"
    assert result.metrics["error"].startswith("InterruptedError:")
    assert result.metrics["prefix_actions"] == 0
    assert result.metrics["training_eligible"] is False
    assert (
        run_skill_corrective_case(
            PROTOCOL,
            "bar_contact_avoidance-51000",
            store=store,
            project_root=Path.cwd(),
        )
        == result
    )
