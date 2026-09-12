"""Verify explicit server configuration without launching a worker or network listener."""

import pytest

from bimanual.cli import main
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_process import WorkflowProcessConfig


@pytest.mark.parametrize("configured", [False, True])
def test_serve_operator_configuration(tmp_path, monkeypatch, configured):
    seen = []
    sentinel = object()

    def app(root, artifacts, *, operator_config):
        seen.append((root, operator_config))
        return sentinel

    def serve(application, **kwargs):
        assert application is sentinel
        assert kwargs == {"host": "127.0.0.1", "port": 8769}

    monkeypatch.setattr("bimanual.api.create_app", app)
    monkeypatch.setattr("uvicorn.run", serve)
    config = WorkflowProcessConfig(
        execution=WorkflowExecutionConfig(
            workflow_manifest=tmp_path / "cohort.json",
            planner_model_directory=tmp_path / "model",
            instruction="initial",
        )
    )
    (tmp_path / "operator.json").write_text(config.model_dump_json())
    args = ["--project-root", str(tmp_path), "serve", "--port", "8769"]
    if configured:
        args += ["--operator-config", "operator.json"]
    assert main(args) == 0
    assert seen == [(tmp_path, config if configured else None)]


@pytest.mark.parametrize("content", ["{}", '{"execution":null}', "not json"])
def test_invalid_operator_config_never_starts_server(tmp_path, monkeypatch, content):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid configuration must not start the server")

    monkeypatch.setattr("uvicorn.run", forbidden)
    (tmp_path / "operator.json").write_text(content)
    assert (
        main(["--project-root", str(tmp_path), "serve", "--operator-config", "operator.json"]) == 1
    )
