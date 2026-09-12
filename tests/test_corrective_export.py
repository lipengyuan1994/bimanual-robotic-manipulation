"""Mock optional LeRobot; verify corrective mapping and failure preservation."""

import hashlib
import json

import numpy as np
import pytest
from test_corrective_views import source

from bimanual import corrective_export as module
from bimanual.corrective_views import create_corrective_views
from bimanual.evidence import EvidenceStore, canonical


class Tensor:
    def __init__(self, value):
        self.value = np.asarray(value)

    def numpy(self):
        return self.value

    def item(self):
        return self.value.item()

    def permute(self, *order):
        return Tensor(self.value.transpose(order))


@pytest.fixture
def mock_library(monkeypatch):
    datasets = {}

    class Dataset:
        corrupt = False

        def __new__(cls, *, root, **kwargs):
            return datasets[str(root)]

        @classmethod
        def create(cls, *, root, **kwargs):
            root.mkdir()
            (root / "meta").mkdir()
            (root / "data").mkdir()
            (root / "meta/info.json").write_text("{}")
            (root / "data/mock.parquet").write_text("mock optional LeRobot storage")
            obj = object.__new__(cls)
            obj.rows, obj.pending, obj.num_episodes = [], [], 0
            datasets[str(root)] = obj
            return obj

        def add_frame(self, frame):
            self.pending.append(frame)

        def save_episode(self):
            for local, frame in enumerate(self.pending):
                row = dict(frame)
                for key in ("action", "observation.state", "observation.velocity"):
                    row[key] = Tensor(row[key])
                for key in module.CAMERA_FEATURES.values():
                    row[key] = Tensor(row[key].transpose(2, 0, 1).astype(np.float32) / 255)
                row.update(
                    timestamp=Tensor(np.float32(local / 20)),
                    episode_index=Tensor(self.num_episodes),
                    frame_index=Tensor(local),
                    index=Tensor(len(self.rows)),
                )
                self.rows.append(row)
            self.pending = []
            self.num_episodes += 1

        def finalize(self):
            pass

        @property
        def num_frames(self):
            return len(self.rows)

        def __getitem__(self, index):
            row = dict(self.rows[index])
            if self.corrupt:
                row["action"] = Tensor(np.ones(12))
            return row

    monkeypatch.setattr(module, "_load_lerobot", lambda: Dataset)
    monkeypatch.setattr(module, "_require_offline_hub", lambda: None)
    return Dataset, datasets


def inputs(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    a, b = source(store), source(store, seed=8, acquisition=0)
    path = tmp_path / "views.json"
    create_corrective_views(store, [a.run_id, b.run_id], path)
    return store, path


def test_export_verify_and_unchanged_intervention(tmp_path, mock_library):
    store, path = inputs(tmp_path)
    root = module.export_corrective_dataset(path, store, tmp_path / "dataset", "local/corrective")
    payload = module.verify_corrective_dataset(root)
    assert payload["frames"] == 5
    assert [(e["dataset_start"], e["dataset_end"]) for e in payload["episodes"]] == [(0, 2), (2, 5)]
    assert [e["parent_start"] for e in payload["episodes"]] == [1, 0]
    raw = root / payload["episodes"][0]["raw_root"] / "demonstration/episode.json"
    assert json.loads(raw.read_text())["interventions"] == 1
    assert len(json.loads(raw.read_text())["frames"]) == 4
    with pytest.raises(FileExistsError):
        module.export_corrective_dataset(path, store, root, "local/corrective")


def test_failed_parity_retained_unsealed(tmp_path, mock_library):
    store, path = inputs(tmp_path)
    mock_library[0].corrupt = True
    root = tmp_path / "dataset"
    with pytest.raises(AssertionError):
        module.export_corrective_dataset(path, store, root, "local/corrective")
    assert (root / "EXPORT_FAILED.json").exists()
    assert not (root / "export_manifest.json").exists()


def test_verifier_rejects_resealed_index_mapping(tmp_path, mock_library):
    store, path = inputs(tmp_path)
    root = module.export_corrective_dataset(path, store, tmp_path / "dataset", "local/corrective")
    p = root / "export_manifest.json"
    data = json.loads(p.read_text())
    data["episodes"][0]["parent_start"] = 0
    data["manifest_sha256"] = hashlib.sha256(
        canonical({k: v for k, v in data.items() if k != "manifest_sha256"})
    ).hexdigest()
    p.write_bytes(canonical(data))
    with pytest.raises(ValueError, match="mapping"):
        module.verify_corrective_dataset(root)


def test_verifier_checks_decoded_rows_again(tmp_path, mock_library):
    store, path = inputs(tmp_path)
    root = module.export_corrective_dataset(path, store, tmp_path / "dataset", "local/corrective")
    mock_library[0].corrupt = True
    with pytest.raises(AssertionError):
        module.verify_corrective_dataset(root)


def test_native_guard_before_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    with pytest.raises(RuntimeError, match="native"):
        module.export_corrective_dataset("missing", None, tmp_path / "dataset", "local/corrective")
    assert not (tmp_path / "dataset").exists()


@pytest.mark.parametrize("value", [0.5, float("nan"), float("inf"), True])
def test_fractional_and_invalid_index_rejected(tmp_path, mock_library, value):
    store, path = inputs(tmp_path)
    root = module.export_corrective_dataset(path, store, tmp_path / "dataset", "local/corrective")
    mock_library[1][str(root)].rows[0]["index"] = Tensor(value)
    with pytest.raises(ValueError, match="index mapping"):
        module.verify_corrective_dataset(root)


def test_invalid_repo_rejected_before_loader(tmp_path, mock_library, monkeypatch):
    store, path = inputs(tmp_path)
    root = module.export_corrective_dataset(path, store, tmp_path / "dataset", "local/corrective")
    manifest = root / "export_manifest.json"
    data = json.loads(manifest.read_text())
    data["repo_id"] = "https://example.com/remote"
    data["manifest_sha256"] = hashlib.sha256(
        canonical({k: v for k, v in data.items() if k != "manifest_sha256"})
    ).hexdigest()
    manifest.write_bytes(canonical(data))
    monkeypatch.setattr(module, "_load_lerobot", lambda: pytest.fail("loader must not run"))
    with pytest.raises(ValueError, match="repo_id"):
        module.verify_corrective_dataset(root)


def test_offline_requirement_is_latched_before_import(monkeypatch):
    import sys
    from types import SimpleNamespace

    constants = SimpleNamespace(HF_HUB_OFFLINE=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(constants=constants))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(RuntimeError, match="before imports"):
        module._require_offline_hub()
    constants.HF_HUB_OFFLINE = True
    module._require_offline_hub()
    monkeypatch.delenv("HF_HUB_OFFLINE")
    with pytest.raises(RuntimeError):
        module._require_offline_hub()
