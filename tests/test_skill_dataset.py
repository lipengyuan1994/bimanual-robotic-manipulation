import subprocess
import sys
from types import SimpleNamespace

import pytest

from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.skill_dataset import SkillDatasetView
from bimanual.skill_views import INTERVALS, SkillView


@pytest.fixture
def torch():
    return pytest.importorskip("torch")


@pytest.fixture
def parent(torch):
    class Rows:
        def __init__(self, indices, columns=None):
            self.indices = tuple(indices)
            self.columns = columns

        def select(self, indices):
            return Rows([self.indices[index] for index in indices], self.columns)

        def select_columns(self, columns):
            return Rows(self.indices, tuple(columns))

        def __getitem__(self, index):
            original = self.indices[index]
            result.numeric_reads.append((original, self.columns))
            return {"action": torch.arange(12, dtype=torch.float32) + original}

    class Parent:
        delta_timestamps = None
        meta = SimpleNamespace(stats={"images": "parent statistics"})
        hf_dataset = Rows(range(4819))

        def __init__(self):
            self.image_reads = []
            self.numeric_reads = []

        def __len__(self):
            return 4819

        def __getitem__(self, index):
            self.image_reads.append(index)
            self.last_item = {
                "observation.state": torch.full((12,), float(index)),
                **{
                    key: torch.full((3, 2, 4), float(index + camera))
                    for camera, key in enumerate(CAMERA_FEATURES.values())
                },
                "action": torch.full((12,), -999.0),
                "phase": "must not reach the model",
                "timestamp": index / 20,
                "observation.object_pose": torch.ones(7),
                "action_is_pad": torch.ones(10, dtype=torch.bool),
            }
            return self.last_item

    result = Parent()
    return result


def make_view(skill=2):
    name, start, end = INTERVALS[skill]
    return SkillView(
        skill_id=name,
        parent_episode_id="parent-dinner",
        start=start,
        end=end,
        terminal_parent_frame=end,
    )


@pytest.mark.parametrize("skill", range(7))
def test_boundary_padding_never_reads_next_skill(parent, torch, skill):
    view = make_view(skill)
    dataset = SkillDatasetView(parent, view, 10)
    sample = dataset[len(dataset) - 2]
    assert parent.image_reads == [view.end - 2]
    assert parent.numeric_reads == [(view.end - 2, ("action",)), (view.end - 1, ("action",))]
    assert sample["action_is_pad"].tolist() == [False, False] + [True] * 8
    expected = torch.stack(
        [
            torch.arange(12, dtype=torch.float32) + min(view.end - 2 + offset, view.end - 1)
            for offset in range(10)
        ]
    )
    assert torch.equal(sample["action"], expected)
    assert sample["action_is_pad"].dtype == torch.bool
    assert len(dataset) == view.end - view.start


def test_current_sensors_and_action_order_are_preserved_without_truth(parent, torch):
    view = make_view()
    dataset = SkillDatasetView(parent, view, 3)
    first = dataset[0]
    assert set(first) == {"observation.state", *CAMERA_FEATURES.values(), "action", "action_is_pad"}
    for key in ("observation.state", *CAMERA_FEATURES.values()):
        assert first[key] is parent.last_item[key]
    assert first["action_is_pad"].tolist() == [False] * 3
    assert parent.image_reads == [view.start]
    assert parent.numeric_reads == [(view.start + i, ("action",)) for i in range(3)]
    assert "phase" in parent.last_item  # No mutation of the underlying item.
    again = dataset[0]
    assert all(torch.equal(first[key], again[key]) for key in first)


def test_normalization_uses_selected_numeric_rows_and_declared_parent_images(parent):
    view = make_view()
    dataset = SkillDatasetView(parent, view, 10)
    assert dataset.meta is parent.meta
    assert dataset.hf_dataset.indices == tuple(range(view.start, view.end))
    assert dataset.normalization_provenance["image_statistics"] == "parent_training_dataset"
    assert dataset.normalization_provenance["numeric_statistics"] == "selected_skill_view_rows"
    with pytest.raises(TypeError):
        dataset.normalization_provenance["image_statistics"] = "view"


@pytest.mark.parametrize("deltas", [{}, {"action": [0.0, 0.05]}])
def test_rejects_parent_delta_expansion(parent, deltas):
    parent.delta_timestamps = deltas
    with pytest.raises(ValueError, match="delta_timestamps"):
        SkillDatasetView(parent, make_view(), 10)


@pytest.mark.parametrize("index", [-1, 519, True, 0.5])
def test_rejects_invalid_local_indices_before_parent_access(parent, index):
    dataset = SkillDatasetView(parent, make_view(), 10)
    with pytest.raises(ValueError, match="index"):
        dataset[index]
    assert parent.image_reads == [] and parent.numeric_reads == []


def test_rejects_already_chunked_numeric_actions(parent, torch):
    dataset = SkillDatasetView(parent, make_view(), 10)
    dataset._actions = [{"action": torch.zeros(10, 12)}]
    with pytest.raises(ValueError, match="unchunked"):
        dataset[0]


@pytest.mark.parametrize("chunk_size", [0, 101, True])
def test_rejects_invalid_horizon(parent, chunk_size):
    with pytest.raises(ValueError, match="horizon"):
        SkillDatasetView(parent, make_view(), chunk_size)


def test_rejects_truncated_parent(parent, monkeypatch):
    monkeypatch.setattr(type(parent), "__len__", lambda _: make_view().end - 1)
    with pytest.raises(ValueError, match="complete skill interval"):
        SkillDatasetView(parent, make_view(), 10)


def test_rejects_nonfinite_action(parent, torch):
    dataset = SkillDatasetView(parent, make_view(), 1)
    dataset._actions = [{"action": torch.full((12,), float("nan"))}]
    with pytest.raises(ValueError, match="non-finite"):
        dataset[0]


def test_import_does_not_load_torch():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import bimanual.skill_dataset; assert 'torch' not in sys.modules",
        ],
        check=True,
    )
