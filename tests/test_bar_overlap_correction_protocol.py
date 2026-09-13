"""Contracts for isolated bar-overlap corrective collection profiles."""

import hashlib
from types import SimpleNamespace

import pytest

from bimanual import bar_overlap_correction_protocol as module
from bimanual.evidence import canonical


def _body(profile, *, source_interval, case_seeds):
    body = {
        "schema_version": 1,
        "profile": profile,
        "evidence_root": "artifacts",
        "diagnosis_run_id": "diagnosis",
        "diagnosis_manifest_sha256": "a" * 64,
        "evaluation_run_id": "evaluation",
        "evaluation_manifest_sha256": "b" * 64,
        "asset_root": "assets",
        "asset_manifest_sha256": "c" * 64,
        "plan_sha256": "d" * 64,
        "source_interval": source_interval,
        "case_seeds": case_seeds,
        "overlap_limit_m": 0.0025,
        "allocation_rule": "one_teacher_attempt_per_frozen_case_no_automatic_retry",
        "learned_execution": False,
        "release_qualified": False,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


def test_entry_contact_profile_binds_fresh_cases_and_policy_entry_window():
    protocol = module.BarOverlapCorrectionProtocol.model_validate(
        _body(
            "bar_left_contact_entry_protocol_v3",
            source_interval=(630, 1163),
            case_seeds=(54000, 54001, 54002, 54003, 54004),
        )
    )
    assert protocol.source_interval == (630, 1163)
    assert protocol.case_seeds[0] == 54000


def test_entry_contact_profile_rejects_the_old_transport_window():
    with pytest.raises(ValueError, match="allocation changed"):
        module.BarOverlapCorrectionProtocol.model_validate(
            _body(
                "bar_left_contact_entry_protocol_v3",
                source_interval=(770, 1163),
                case_seeds=(54000, 54001, 54002, 54003, 54004),
            )
        )


def test_placement_progress_profile_binds_fresh_cases_and_placement_tail():
    protocol = module.BarOverlapCorrectionProtocol.model_validate(
        _body(
            "bar_placement_progress_protocol_v4",
            source_interval=(770, 1163),
            case_seeds=(55000, 55001, 55002, 55003, 55004),
        )
    )
    assert protocol.source_interval == (770, 1163)
    assert protocol.case_seeds[0] == 55000


def test_placement_contact_profile_binds_fresh_cases_and_policy_entry_window():
    protocol = module.BarOverlapCorrectionProtocol.model_validate(
        _body(
            "bar_placement_contact_entry_protocol_v5",
            source_interval=(630, 1163),
            case_seeds=(56000, 56001, 56002, 56003, 56004),
        )
    )
    assert protocol.source_interval == (630, 1163)
    assert protocol.case_seeds[0] == 56000


def test_placement_progress_profile_requires_the_exact_progress_failure():
    component = {
        "skill_id": "bar_place_and_return",
        "physical_success": False,
        "recorded_autonomous_skill_actions": 1900,
        "rejected_action_log_actions": 0,
        "maximum_target_displacement_m": 0.23985196860361424,
        "forbidden_contact_events": [],
        "failure_reason": (
            "physical_milestone_incomplete: physical completion/readiness not reached "
            "within action budget"
        ),
        "evaluation_run_id": "evaluation",
        "evaluation_manifest_sha256": "b" * 64,
    }
    diagnosis = SimpleNamespace(
        kind="single_skill_physical_failure_analysis",
        outcome="completed",
        manifest_sha256=module.PLACEMENT_PROGRESS_FAILURE_ANALYSIS_MANIFEST_SHA256,
        metrics={"component": component},
    )
    evaluation = SimpleNamespace(manifest_sha256="b" * 64)

    class Store:
        def verify(self, run_id):
            return diagnosis if run_id == "diagnosis" else evaluation

    accepted, bound = module._verified_diagnosis(
        Store(), "diagnosis", profile="bar_placement_progress_protocol_v4"
    )
    assert accepted is diagnosis
    assert bound is evaluation

    component["maximum_target_displacement_m"] = 0.1
    with pytest.raises(ValueError, match="localized unpromoted"):
        module._verified_diagnosis(
            Store(), "diagnosis", profile="bar_placement_progress_protocol_v4"
        )


def test_entry_contact_profile_requires_the_exact_sealed_failure_signature():
    component = {
        "skill_id": "bar_place_and_return",
        "physical_success": False,
        "recorded_autonomous_skill_actions": 1,
        "rejected_action_log_actions": 1,
        "maximum_overlap_m": 0.0014421862329579455,
        "forbidden_contact_events": [{"bad": [["left/fixed_jaw_sph_tip2", "practice_object"]]}],
        "evaluation_run_id": "evaluation",
        "evaluation_manifest_sha256": "b" * 64,
    }
    diagnosis = SimpleNamespace(
        kind="single_skill_physical_failure_analysis",
        outcome="completed",
        manifest_sha256=module.ENTRY_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256,
        metrics={"component": component},
    )
    evaluation = SimpleNamespace(manifest_sha256="b" * 64)

    class Store:
        def verify(self, run_id):
            return diagnosis if run_id == "diagnosis" else evaluation

    accepted, bound = module._verified_diagnosis(
        Store(), "diagnosis", profile="bar_left_contact_entry_protocol_v3"
    )
    assert accepted is diagnosis
    assert bound is evaluation

    diagnosis.manifest_sha256 = "e" * 64
    with pytest.raises(ValueError, match="localized unpromoted"):
        module._verified_diagnosis(
            Store(), "diagnosis", profile="bar_left_contact_entry_protocol_v3"
        )


def test_placement_contact_profile_requires_the_exact_sealed_failure_signature():
    component = {
        "skill_id": "bar_place_and_return",
        "physical_success": False,
        "recorded_autonomous_skill_actions": 1,
        "rejected_action_log_actions": 1,
        "maximum_overlap_m": 0.0014311301641538956,
        "maximum_overtravel_m": 0.0,
        "forbidden_contact_events": [
            {"bad": [["left/fixed_jaw_sph_tip2", "practice_object"]]}
        ],
        "evaluation_run_id": "evaluation",
        "evaluation_manifest_sha256": "b" * 64,
    }
    diagnosis = SimpleNamespace(
        kind="single_skill_physical_failure_analysis",
        outcome="completed",
        manifest_sha256=module.PLACEMENT_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256,
        metrics={"component": component},
    )
    evaluation = SimpleNamespace(manifest_sha256="b" * 64)

    class Store:
        def verify(self, run_id):
            return diagnosis if run_id == "diagnosis" else evaluation

    accepted, bound = module._verified_diagnosis(
        Store(), "diagnosis", profile="bar_placement_contact_entry_protocol_v5"
    )
    assert accepted is diagnosis
    assert bound is evaluation

    component["maximum_overtravel_m"] = 0.01
    with pytest.raises(ValueError, match="localized unpromoted"):
        module._verified_diagnosis(
            Store(), "diagnosis", profile="bar_placement_contact_entry_protocol_v5"
        )
