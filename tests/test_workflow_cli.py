"""Command wiring only; no models, rendering, or manipulation-quality claim."""

from types import SimpleNamespace

import pytest

from bimanual.cli import main


@pytest.mark.parametrize("in_process", [False, True])
@pytest.mark.parametrize("outcome,expected", [("completed", 0), ("failed", 1)])
def test_workflow_cli_forwards_limits_and_preserves_failure(
    tmp_path, monkeypatch, outcome, expected, in_process
):
    seen = []

    def execute(config, **kwargs):
        seen.append(config)
        return SimpleNamespace(outcome=outcome, model_dump=lambda **kw: {"outcome": outcome})

    target = (
        "bimanual.workflow_execution.run_workflow_execution"
        if in_process
        else "bimanual.workflow_process.run_workflow_process"
    )
    monkeypatch.setattr(target, execute)
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
            "--max-tokens",
            "200",
            *(["--in-process"] if in_process else []),
        ]
    )
    assert result == expected and len(seen) == 1
    config = seen[0] if in_process else seen[0].execution
    assert config.workflow_manifest == tmp_path / "cohort.json"
    assert config.planner_model_directory == tmp_path / "model"
    assert config.instruction == "Set the dinner table"
    assert config.policy_device == "cpu" and config.planner_device == "mps"
    assert config.camera_profile == "overhead1920_wrist480_v1"
    assert config.wall_timeout_seconds == 900 and config.step_timeout_seconds == 120
    assert config.max_tokens == 200


def test_workflow_create_forwards_corrective_location(tmp_path, monkeypatch):
    from bimanual import workflow_manifest

    seen = []

    def create(*args, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(report=lambda: {"profile": "dinner_development_workflow_v4"})

    monkeypatch.setattr(workflow_manifest, "create_workflow_manifest", create)
    args = [
        "workflow-create",
        "--dataset",
        str(tmp_path / "data"),
        "--skill-views",
        str(tmp_path / "views"),
        "--destination",
        str(tmp_path / "workflow"),
        "--handoff-corrective-dataset",
        str(tmp_path / "copy"),
    ]
    for index in range(7):
        args += ["--training-run", str(tmp_path / f"run-{index}")]
    assert main(args) == 0
    assert seen == [{"corrective_dataset_roots": {"handoff_transfer": tmp_path / "copy"}}]
