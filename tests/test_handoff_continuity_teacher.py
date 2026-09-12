from __future__ import annotations

import json
from pathlib import Path

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.handoff_continuity_teacher import _continuity_score, run_handoff_continuity_case
from bimanual.worker_lease import WorkerLease

PROTOCOL = (
    Path(__file__).parents[1] / "docs/experiments/handoff-continuity-collection-protocol-v1.json"
)


def _write_trace(tmp_path, *, partial=False, forbidden=False, drop_grip=False):
    actions = tmp_path / "actions.jsonl"
    physics = tmp_path / "physics.jsonl"
    action_rows = []
    physics_rows = []
    stages = (
        ("handoff/left_hold", [1.0, 1.0], [0.0, 0.0]),
        ("handoff/both_hold", [1.0, 1.0], [1.0, 1.0]),
        ("handoff/receiver_hold", [0.0, 0.0], [1.0, 1.0]),
    )
    for action_index in range(120):
        phase, left, right = stages[action_index // 40]
        action_rows.append(
            {
                "applied": True,
                "partial_physics": partial and action_index == 119,
            }
        )
        for sample in range(50):
            sample_left = left
            sample_right = right
            if drop_grip and action_index == 60 and sample == 0:
                sample_left = sample_right = [0.0, 0.0]
            physics_rows.append(
                {
                    "phase": phase,
                    "bad": [["robot", "table"]] if forbidden and action_index == 60 else [],
                    "overlap": 0.0,
                    "objects": {
                        "practice_object": {
                            "forces": {"left": sample_left, "right": sample_right},
                            "support": [],
                        }
                    },
                }
            )
    actions.write_text("".join(json.dumps(row) + "\n" for row in action_rows))
    physics.write_text("".join(json.dumps(row) + "\n" for row in physics_rows))
    return physics, actions


def test_independent_continuity_score_requires_ordered_contact_holds(tmp_path):
    physics, actions = _write_trace(tmp_path)
    score = _continuity_score(physics, actions)
    assert score["physical_handoff_success"] is True
    assert score["donor_only_samples"] == 2000
    assert score["shared_grasp_samples"] == 2000
    assert score["receiver_only_samples"] == 2000
    assert score["continuous_airborne_grip"] is True


def test_partial_action_prevents_continuity_source_success(tmp_path):
    physics, actions = _write_trace(tmp_path, partial=True)
    score = _continuity_score(physics, actions)
    assert score["physical_handoff_success"] is False
    assert score["partial_actions"] == 1


def test_contact_loss_or_forbidden_contact_prevents_success(tmp_path):
    physics, actions = _write_trace(tmp_path, drop_grip=True)
    assert _continuity_score(physics, actions)["physical_handoff_success"] is False
    physics, actions = _write_trace(tmp_path, forbidden=True)
    score = _continuity_score(physics, actions)
    assert score["physical_handoff_success"] is False
    assert score["forbidden_contact_samples"] == 50


def test_unknown_case_allocates_no_evidence(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(ValueError, match="not in"):
        run_handoff_continuity_case(
            PROTOCOL, "receiver-unknown", store=store, project_root=Path.cwd()
        )
    assert not (store.root / "runs").exists()


def test_busy_model_job_consumes_no_continuity_case(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir(parents=True)
    with WorkerLease.acquire(store.root / ".model-job.lock"):
        with pytest.raises(RuntimeError, match="still holds"):
            run_handoff_continuity_case(
                PROTOCOL, "receiver-baseline", store=store, project_root=Path.cwd()
            )
    assert not (store.root / "runs").exists()
