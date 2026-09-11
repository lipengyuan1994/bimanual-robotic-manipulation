import copy

import pytest

from bimanual.phase_errors import summarize_phase_errors


def records():
    return [
        {"parent_frame": i, "prediction_rad": [[i + 1.0] * 12], "expected_rad": [[0.0] * 12]}
        for i in range(3)
    ]


def test_summary_uses_targets_and_preserves_phase_counts():
    rows = records()
    rows[0]["first_abs_error_rad"] = [999.0] * 12
    result = summarize_phase_errors(rows, ["approach", "close", "close"], start=0, end=3)
    assert result[0]["mean_abs_rad"] == 1.0
    assert result[1]["frames"] == 2
    assert result[1]["mean_abs_rad"] == 2.5
    assert result[1]["max_abs_rad"] == 3.0
    assert result[1]["per_joint_mean_abs_rad"] == [2.5] * 12


def test_nonzero_skill_interval_uses_parent_phase_labels():
    rows = records()[1:]
    result = summarize_phase_errors(rows, ["outside", "close", "release"], start=1, end=3)
    assert [row["phase"] for row in result] == ["close", "release"]
    assert [row["mean_abs_rad"] for row in result] == [2.0, 3.0]


@pytest.mark.parametrize("start,end", [(True, 3), (0, 0), (-1, 3), (0, 4)])
def test_invalid_interval_is_rejected(start, end):
    with pytest.raises(ValueError):
        summarize_phase_errors(records(), ["a", "b", "b"], start=start, end=end)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "failed", "nan", "shape"])
def test_invalid_evidence_is_not_summarized_as_success(defect):
    rows = copy.deepcopy(records())
    if defect == "missing":
        rows.pop()
    elif defect == "duplicate":
        rows[1]["parent_frame"] = 0
    elif defect == "failed":
        rows[1]["error"] = "inference failed"
    elif defect == "nan":
        rows[1]["prediction_rad"][0][0] = float("nan")
    else:
        rows[1]["expected_rad"] = [[0.0]]
    with pytest.raises(ValueError):
        summarize_phase_errors(rows, ["a", "b", "b"], start=0, end=3)
