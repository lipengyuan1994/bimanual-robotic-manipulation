from __future__ import annotations

import json

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.handoff_continuity_protocol import (
    HandoffContinuityCase,
    create_handoff_continuity_protocol,
    expected_cases,
    load_handoff_continuity_protocol,
)

FINDING = (
    "receiver close/shared hold through donor release, with the receiver gripper "
    "held closed and varied measured approach states"
)


def _diagnosis(tmp_path, *, promoted=False):
    store = EvidenceStore(tmp_path / "evidence")
    directory = store.new_run()
    (directory / "analysis.json").write_text("{}")
    result = store.seal(
        directory,
        kind="handoff_continuity_failure_analysis",
        outcome="completed",
        config={},
        metrics={
            "recommended_data_region": FINDING,
            "physical_success": False,
            "checkpoint_promoted": promoted,
        },
        source={},
        claims=[],
    )
    return store, result


def test_exact_nine_case_axis_allocation():
    cases = expected_cases()
    assert len(cases) == 9
    assert cases[0].receiver_joint_index is None and cases[0].offset_rad == 0
    assert [case.seed for case in cases] == list(range(41000, 41009))
    assert {(case.receiver_joint_index, case.offset_rad) for case in cases[1:]} == {
        (index, offset) for index in range(6, 10) for offset in (-0.015, 0.015)
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"case_id": "bad-zero", "seed": 1, "receiver_joint_index": 6},
        {"case_id": "bad-axis", "seed": 1, "receiver_joint_index": 6, "offset_rad": 0.01},
        {"case_id": "bad-index", "seed": 1, "receiver_joint_index": 5, "offset_rad": 0.015},
    ],
)
def test_case_contract_rejects_changed_envelope(kwargs):
    with pytest.raises(ValueError):
        HandoffContinuityCase(**kwargs)


def test_create_and_reverify_protocol(tmp_path):
    store, diagnosis = _diagnosis(tmp_path)
    path = tmp_path / "protocol.json"
    created = create_handoff_continuity_protocol(
        evidence_root=store.root,
        diagnosis_run_id=diagnosis.run_id,
        destination=path,
    )
    assert load_handoff_continuity_protocol(path) == created
    assert created.correction_scope == "receiver_close_shared_hold_donor_release"
    assert created.learned_execution is False
    assert created.release_qualified is False
    with pytest.raises(FileExistsError):
        create_handoff_continuity_protocol(
            evidence_root=store.root,
            diagnosis_run_id=diagnosis.run_id,
            destination=path,
        )


def test_protocol_body_mutation_is_rejected(tmp_path):
    store, diagnosis = _diagnosis(tmp_path)
    path = tmp_path / "protocol.json"
    create_handoff_continuity_protocol(
        evidence_root=store.root,
        diagnosis_run_id=diagnosis.run_id,
        destination=path,
    )
    payload = json.loads(path.read_text())
    payload["cases"][1]["offset_rad"] = -0.01
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_handoff_continuity_protocol(path)


def test_promoted_checkpoint_cannot_seed_correction_protocol(tmp_path):
    store, diagnosis = _diagnosis(tmp_path, promoted=True)
    with pytest.raises(ValueError, match="unpromoted"):
        create_handoff_continuity_protocol(
            evidence_root=store.root,
            diagnosis_run_id=diagnosis.run_id,
            destination=tmp_path / "protocol.json",
        )
