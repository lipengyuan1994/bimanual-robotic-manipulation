import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bimanual.api import create_app
from bimanual.evidence import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(ROOT, tmp_path))


def test_health_and_status_do_not_claim_manipulation(client):
    assert client.get("/api/health").json()["control_available"] is False
    project = client.get("/api/project").json()
    assert project["manipulation_available"] is False
    assert sum(item["points"] for item in project["rubric"]) == 100
    assert client.post("/api/runs", json={"instruction": "move"}).status_code == 405


def test_document_navigation_and_path_confinement(client, tmp_path):
    response = client.get("/read/docs/STATUS.md")
    assert response.status_code == 200
    assert "Project status" in response.text
    assert client.get("/read/learning-records/0001-starting-point.md").status_code == 200
    assert client.get("/read/uv.lock").status_code == 404
    (tmp_path / "docs").mkdir()
    (tmp_path / "secret.json").write_text(json.dumps({"secret": "must not appear"}))
    restricted = TestClient(create_app(tmp_path, tmp_path / "artifacts"))
    assert restricted.get("/read/docs/%2e%2e/secret.json").status_code == 404
    assert client.get("/api/health", headers={"host": "external.invalid"}).status_code == 400


def test_artifacts_are_checked_before_serving(tmp_path):
    store = EvidenceStore(tmp_path)
    directory = store.new_run()
    (directory / "doctor.json").write_text('{"outcome":"passed"}')
    store.seal(
        directory,
        kind="preparation_runtime",
        outcome="passed",
        config={},
        metrics={},
        source={},
        claims=[],
    )
    client = TestClient(create_app(ROOT, tmp_path))
    url = f"/api/runs/{directory.name}/files/doctor.json"
    assert client.get(url).status_code == 200
    (directory / "doctor.json").write_text('{"outcome":"forged"}')
    assert client.get(url).status_code == 404
    assert client.get("/api/runs").json()[0]["integrity"] == "failed"


def test_operator_unconfigured_cannot_start_or_stop(client):
    assert client.get("/api/operator").json() == {
        "configured": False,
        "job": None,
        "task_success_verified": False,
    }
    headers = {"x-bimanual-operator": "1"}
    assert (
        client.post(
            "/api/operator/jobs", json={"instruction": "Dinner"}, headers=headers
        ).status_code
        == 503
    )
    assert client.post("/api/operator/jobs/missing/stop", headers=headers).status_code == 503


def test_operator_origin_ownership_and_shutdown(tmp_path):
    from threading import Event

    from bimanual.workflow_execution import WorkflowExecutionConfig
    from bimanual.workflow_process import WorkflowProcessConfig

    entered = Event()
    stopped = Event()

    def runner(config, *, store, cancelled, **kwargs):
        import time

        entered.set()
        deadline = time.monotonic() + 10
        while not cancelled() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cancelled()
        directory = store.new_run()
        result = store.seal(
            directory,
            kind="dinner_workflow_process",
            outcome="cancelled",
            config={},
            metrics={},
            source={},
            claims=[],
        )
        stopped.set()
        return result

    config = WorkflowProcessConfig(
        execution=WorkflowExecutionConfig(
            workflow_manifest=tmp_path / "cohort.json",
            planner_model_directory=tmp_path / "model",
            instruction="initial",
        )
    )
    app = create_app(ROOT, tmp_path / "evidence", operator_config=config, _operator_runner=runner)
    good = {"x-bimanual-operator": "1", "origin": "http://testserver"}
    with TestClient(app) as client:
        url = "/api/operator/jobs"
        body = {"instruction": "Set the table"}
        assert client.get("/api/health").json()["control_available"] is True
        assert client.post(url, json=body).status_code == 403
        for origin in (
            "null",
            "http://other.invalid",
            "https://testserver",
            "http://testserver:99",
        ):
            assert client.post(url, json=body, headers=good | {"origin": origin}).status_code == 403
        assert not entered.is_set()
        assert (
            client.post(
                url, json=body | {"workflow_manifest": "/tmp/other"}, headers=good
            ).status_code
            == 422
        )
        result = client.post(url, json=body, headers=good)
        assert result.status_code == 202
        job = result.json()
        assert entered.wait(5)
        assert client.post(url, json=body, headers=good).status_code == 409
        assert client.post(url + "/wrong/stop", headers=good).status_code == 404
        assert client.get("/api/operator").json()["job"]["job_id"] == job["job_id"]
        assert client.post(url + f"/{job['job_id']}/stop").status_code == 403
        result = client.post(url + f"/{job['job_id']}/stop", headers=good)
        assert result.status_code == 200
        assert result.json()["state"] == "stopping"
    assert stopped.is_set()
    # Lifespan shutdown waits for the background owner to finish and verify its seal.
    with TestClient(app) as client:
        status = client.get("/api/operator").json()
        assert status["job"]["state"] == "cancelled"
        assert status["job"]["independent_task_success"] is None
        assert status["task_success_verified"] is False
        assert client.post(url, json=body, headers=good).status_code == 409


def test_run_page_query_bounds_and_cursor(tmp_path):
    store = EvidenceStore(tmp_path)
    ids = []
    for _ in range(3):
        directory = store.new_run()
        store.seal(
            directory, kind="test", outcome="failed", config={}, metrics={}, source={}, claims=[]
        )
        ids.append(directory.name)
    ids.sort(reverse=True)
    with TestClient(create_app(ROOT, tmp_path)) as client:
        page = client.get("/api/runs", params={"limit": 2}).json()
        assert [r["run_id"] for r in page] == ids[:2]
        older = client.get("/api/runs", params={"limit": 2, "before": ids[1]}).json()
        assert [r["run_id"] for r in older] == ids[2:]
        assert all(r["outcome"] == "failed" for r in page + older)
        for limit in (0, 101, "invalid"):
            assert client.get("/api/runs", params={"limit": limit}).status_code == 422
