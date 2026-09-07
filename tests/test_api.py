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
