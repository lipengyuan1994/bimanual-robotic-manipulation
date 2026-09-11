import hashlib
import json

import pytest

from bimanual.evidence import EvidenceStore, canonical


@pytest.fixture
def sealed(tmp_path):
    store = EvidenceStore(tmp_path)
    directory = store.new_run()
    (directory / "sample.txt").write_text("original measurement\n")
    store.seal(
        directory, kind="test", outcome="completed", config={}, metrics={}, source={}, claims=[]
    )
    return store, directory


def test_modified_missing_and_extra_files_are_detected(sealed):
    store, directory = sealed
    (directory / "sample.txt").write_text("changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        store.verify(directory.name)
    assert store.list_runs()[0]["integrity"] == "failed"
    (directory / "sample.txt").unlink()
    with pytest.raises(ValueError, match="missing"):
        store.verify(directory.name)
    (directory / "sample.txt").write_text("original measurement\n")
    (directory / "extra.txt").write_text("unsealed")
    with pytest.raises(ValueError, match="Unsealed"):
        store.verify(directory.name)


def test_sealed_run_cannot_be_overwritten(sealed):
    store, directory = sealed
    before = (directory / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        store.seal(
            directory, kind="test", outcome="failed", config={}, metrics={}, source={}, claims=[]
        )
    assert (directory / "manifest.json").read_bytes() == before


def test_manifest_tamper_and_path_escape(sealed):
    store, directory = sealed
    path = directory / "manifest.json"
    payload = json.loads(path.read_text())
    payload["outcome"] = "made_up_success"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Manifest digest"):
        store.verify(directory.name)
    payload["files"] = {"../../outside.txt": "irrelevant"}
    payload["manifest_sha256"] = hashlib.sha256(
        canonical({k: v for k, v in payload.items() if k != "manifest_sha256"})
    ).hexdigest()
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Invalid or missing"):
        store.verify(directory.name)


def test_optional_index_failure_does_not_lose_manifest(tmp_path):
    (tmp_path / "runs.sqlite3").write_text("not a sqlite database")
    store = EvidenceStore(tmp_path)
    directory = store.new_run()
    with pytest.warns(UserWarning, match="index update failed"):
        store.seal(
            directory, kind="test", outcome="completed", config={}, metrics={}, source={}, claims=[]
        )
    assert store.verify(directory.name).outcome == "completed"
    assert store.list_runs()[0]["integrity"] == "verified"


def test_run_pages_verify_only_selected_records_and_keep_failures(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path)
    ids = []
    for _ in range(5):
        directory = store.new_run()
        (directory / "value.txt").write_text("original")
        store.seal(
            directory, kind="test", outcome="completed", config={}, metrics={}, source={}, claims=[]
        )
        ids.append(directory.name)
    ids.sort(reverse=True)
    (store.directory(ids[1]) / "value.txt").write_text("corrupt")
    verified = []
    original = store.verify

    def verify(run_id):
        verified.append(run_id)
        return original(run_id)

    monkeypatch.setattr(store, "verify", verify)
    page = store.list_runs(limit=2)
    assert verified == ids[:2]
    assert [r["run_id"] for r in page] == ids[:2]
    assert [r["integrity"] for r in page] == ["verified", "failed"]
    verified.clear()
    older = store.list_runs(limit=2, before=page[-1]["run_id"])
    assert verified == ids[2:4]
    assert [r["run_id"] for r in older] == ids[2:4]
    assert len(store.list_runs()) == 5
    assert store.list_runs(limit=2, before=ids[-1]) == []


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5])
def test_invalid_run_page_limit(tmp_path, limit):
    with pytest.raises(ValueError, match="limit"):
        EvidenceStore(tmp_path).list_runs(limit=limit)
