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
