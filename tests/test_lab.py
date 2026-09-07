import csv
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from bimanual.evidence import EvidenceStore
from bimanual.lab import LabConfig, run_lab, simulate

ROOT = Path(__file__).resolve().parents[1]


def test_repeatable_trace_and_real_dynamics():
    config = LabConfig(seed=7, seconds=1, render=False)
    first, _, _ = simulate(config)
    second, _, _ = simulate(config)
    different_seed, _, _ = simulate(config.model_copy(update={"seed": 8}))
    stronger_damping, _, _ = simulate(config.model_copy(update={"damping": 0.8}))
    assert first == second
    assert first != different_seed
    assert first != stronger_damping
    assert first[0]["angle_rad"] != first[-1]["angle_rad"]
    assert len(first) == 21
    np.testing.assert_allclose([row["simulation_seconds"] for row in first], np.arange(21) / 20)


@pytest.mark.parametrize(
    "change", [{"seconds": 0}, {"seed": -1}, {"torque": 1}, {"damping": float("nan")}]
)
def test_invalid_lab_configuration(change):
    with pytest.raises(ValidationError):
        LabConfig(**change)


def test_lab_records_truthful_reproducible_evidence(tmp_path):
    store = EvidenceStore(tmp_path)
    result = run_lab(LabConfig(seconds=1, render=False), store=store, project_root=ROOT)
    verified = store.verify(result.run_id)
    assert verified.kind == "preparation_pendulum"
    assert verified.metrics["manipulation_success"] is None
    assert "offscreen_render" not in verified.claims
    assert verified.provenance["source_files"]["src/bimanual/lab.py"]
    with (store.directory(result.run_id) / "trajectory.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 21
    assert float(rows[-1]["simulation_seconds"]) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "failure,outcome",
    [(RuntimeError("render unavailable"), "failed"), (KeyboardInterrupt(), "interrupted")],
)
def test_failed_and_interrupted_attempts_are_retained(tmp_path, monkeypatch, failure, outcome):
    def fail(_):
        raise failure

    monkeypatch.setattr("bimanual.lab.simulate", fail)
    store = EvidenceStore(tmp_path)
    with pytest.raises(type(failure)):
        run_lab(LabConfig(render=False), store=store, project_root=ROOT)
    run = store.list_runs()[0]
    assert run["outcome"] == outcome
    assert run["integrity"] == "verified"
    assert "error.txt" in run["files"]
    assert run["claims"] == []


@pytest.mark.render
def test_offscreen_render_contains_scene_and_motion(tmp_path):
    config = LabConfig(seconds=1)
    rows, frames, _ = simulate(config)
    assert len(frames) == len(rows) == 21
    pixels = np.asarray(frames[0])
    assert pixels.shape == (320, 480, 3)
    assert pixels.std() > 5
    assert np.mean(np.abs(pixels.astype(float) - np.asarray(frames[-1]))) > 0.05
