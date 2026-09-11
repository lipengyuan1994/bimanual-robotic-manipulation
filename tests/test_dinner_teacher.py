"""Actor contract failures must stop and retain auditable partial evidence."""

import gzip
import json
import shutil
from pathlib import Path

import pytest

from bimanual.dinner_teacher import (
    ASSETS,
    DinnerTeacherConfig,
    load_plan,
    phase_permissions,
    run_dinner_teacher,
)
from bimanual.evidence import EvidenceStore


def test_packaged_plan_identity():
    manifest, plan, layout = load_plan()
    assert len(plan["steps"]) == 4819
    assert manifest["source_run"] == "20260911T011032-a9fda4aee41f"
    assert layout["plate_position_tolerance_m"] == 0.02


def test_corrupt_scene_rejected(tmp_path):
    shutil.copytree(ASSETS, tmp_path / "assets")
    with (tmp_path / "assets/scene.xml").open("a") as file:
        file.write("<!-- corrupt -->")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_plan(tmp_path / "assets")


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("plate/transition_home", ({}, None, "left")),
        ("plate/lower", ({"left": {"plate"}}, "plate", "left")),
        (
            "handoff/both_hold",
            ({"left": {"practice_object"}, "right": {"practice_object"}}, None, "left"),
        ),
        ("handoff/bar_transport", ({"right": {"practice_object"}}, "practice_object", "right")),
        ("utensils/fork_clearance", ({"left": {"fork"}}, "fork", "left")),
    ],
)
def test_phase_contact_ownership(phase, expected):
    assert phase_permissions(phase) == expected


def test_cancel_before_initialization_seals_failure(tmp_path):
    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False), store, Path.cwd(), cancelled=lambda: True
    )
    assert result.outcome == "interrupted"
    assert not result.claims
    assert not result.metrics["score"]["full_workflow_success"]
    store.verify(result.run_id)


def test_mid_step_cancellation_retains_partial_trace(tmp_path):
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 8

    store = EvidenceStore(tmp_path)
    result = run_dinner_teacher(
        DinnerTeacherConfig(render=False), store, Path.cwd(), cancelled=cancelled
    )
    assert result.outcome == "interrupted", result.metrics["error"]
    assert not result.claims
    assert not result.metrics["score"]["full_workflow_success"]
    run = store.directory(result.run_id)
    actions = [json.loads(line) for line in (run / "actions.jsonl").read_text().splitlines()]
    assert len(actions) == 1 and not actions[0]["applied"]
    with gzip.open(run / "physics.jsonl.gz", "rt") as file:
        rows = [json.loads(line) for line in file]
    assert 0 < len(rows) < 50
    store.verify(result.run_id)
