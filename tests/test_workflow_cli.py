"""Command wiring only; no models, rendering, or manipulation-quality claim."""

from types import SimpleNamespace

import pytest

from bimanual.cli import main


@pytest.mark.parametrize("outcome,expected", [("completed", 0), ("failed", 1)])
def test_workflow_cli_forwards_limits_and_preserves_failure(
    tmp_path, monkeypatch, outcome, expected
):
    seen = []

    def execute(config, **kwargs):
        seen.append(config)
        return SimpleNamespace(outcome=outcome, model_dump=lambda **kw: {"outcome": outcome})

    monkeypatch.setattr("bimanual.workflow_execution.run_workflow_execution", execute)
    result = main(
        [
            "--artifacts",
            str(tmp_path / "evidence"),
            "workflow-run",
            str(tmp_path / "cohort.json"),
            "--planner-model",
            str(tmp_path / "model"),
            "--instruction",
            "Set the dinner table",
            "--policy-device",
            "cpu",
            "--planner-device",
            "mps",
            "--camera-profile",
            "overhead1920_wrist480_v1",
            "--wall-timeout-seconds",
            "900",
            "--step-timeout-seconds",
            "120",
            "--max-actions-per-skill",
            "800",
            "--max-tokens",
            "200",
        ]
    )
    assert result == expected and len(seen) == 1
    config = seen[0]
    assert config.workflow_manifest == tmp_path / "cohort.json"
    assert config.planner_model_directory == tmp_path / "model"
    assert config.instruction == "Set the dinner table"
    assert config.policy_device == "cpu" and config.planner_device == "mps"
    assert config.camera_profile == "overhead1920_wrist480_v1"
    assert config.wall_timeout_seconds == 900 and config.step_timeout_seconds == 120
    assert config.max_actions_per_skill == 800 and config.max_tokens == 200
