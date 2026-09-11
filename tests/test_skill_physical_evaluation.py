"""CPU lifecycle fixtures; no learned model, rendering, or manipulation evidence."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_contracts import observation

from bimanual.cli import main
from bimanual.contracts import Observation
from bimanual.evidence import EvidenceStore
from bimanual.skill_executor import SkillExecutionResult
from bimanual.skill_physical_evaluation import (
    SkillPhysicalEvaluationConfig,
    run_skill_physical_evaluation,
)
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease


class Verified:
    action_count = 630
    prefix_sha256 = "a" * 64
    reference_sha256 = "b" * 64

    def report(self):
        return {"fixture": True, "release_qualified": False}

    def reverify(self):
        return self


class Binding:
    def report(self):
        return {"fixture": True, "learned_quality": None}

    def reverify(self):
        return self


class Policy:
    def __init__(self, *args, **kwargs):
        self.binding = Binding()
        self._policy = SimpleNamespace(parameters=lambda: ())

    def predict(self, inputs):
        assert set(inputs) == {
            "observation.state",
            "observation.images.overhead",
            "observation.images.left_wrist",
            "observation.images.right_wrist",
        }
        return np.zeros((10, 12), dtype=np.float32)


class Supervisor:
    def load_task(self, task):
        self.task = task

    def dispatch(self, observed):
        return SimpleNamespace(attempt_id="fixture-attempt")


class Worker:
    def __init__(self, directory, registry, **kwargs):
        self.directory = directory
        directory.mkdir(parents=True)
        self.episode_id = "episode-1"
        self.supervisor = Supervisor()
        self.closed = False

    def capture(self):
        return Observation.model_validate(observation())

    def close(self):
        self.closed = True


class PassingExecutor:
    def __init__(self, worker, policy, **kwargs):
        self.worker = worker

    def start(self, *args, **kwargs):
        pass

    def tick(self):
        return SkillExecutionResult(
            "fixture-attempt",
            "succeeded",
            "CPU lifecycle fixture",
            17,
            physical_success=True,
            successor_ready=True,
        )


def config(tmp_path):
    sources = [tmp_path / name for name in ("training", "dataset", "views.json")]
    sources[0].mkdir()
    sources[1].mkdir()
    sources[2].write_text("{}")
    return SkillPhysicalEvaluationConfig(
        training_run=sources[0],
        dataset_root=sources[1],
        skill_views_path=sources[2],
        skill_id="bar_place_and_return",
        device="cpu",
        wall_timeout_seconds=10,
    )


def install_fixtures(monkeypatch):
    monkeypatch.setattr(
        "bimanual.skill_physical_evaluation.load_teacher_prefix", lambda *a, **k: Verified()
    )
    monkeypatch.setattr(
        "bimanual.skill_physical_evaluation.load_successor_reference",
        lambda *a, **k: Verified(),
    )
    monkeypatch.setattr("bimanual.skill_physical_evaluation.DinnerSkillPolicy", Policy)
    monkeypatch.setattr(
        "bimanual.skill_physical_evaluation.TeacherPreparedDinnerControlWorker", Worker
    )
    monkeypatch.setattr("bimanual.skill_physical_evaluation.DinnerSkillExecutor", PassingExecutor)


def test_component_pass_requires_physics_and_readiness_and_stays_nonrelease(tmp_path, monkeypatch):
    install_fixtures(monkeypatch)
    store = EvidenceStore(tmp_path / "evidence")
    result = run_skill_physical_evaluation(config(tmp_path), store=store, project_root=Path.cwd())
    assert store.verify(result.run_id) == result
    assert result.outcome == "completed"
    assert result.metrics["component_passed"] is True
    assert result.metrics["physical_success"] is True
    assert result.metrics["successor_ready"] is True
    assert result.metrics["teacher_actions_used"] is True
    assert result.metrics["teacher_prefix_actions"] == 630
    assert result.metrics["autonomous_skill_actions"] == 17
    assert result.metrics["independent_task_success"] is None
    assert result.metrics["autonomous_workflow_success"] is None
    assert result.metrics["release_qualified"] is False


def test_missing_readiness_cannot_pass_or_claim_success(tmp_path, monkeypatch):
    install_fixtures(monkeypatch)

    class NoReadiness(PassingExecutor):
        def tick(self):
            return SkillExecutionResult(
                "fixture-attempt",
                "succeeded",
                "Physical-only fixture",
                17,
                physical_success=True,
                successor_ready=False,
            )

    monkeypatch.setattr("bimanual.skill_physical_evaluation.DinnerSkillExecutor", NoReadiness)
    result = run_skill_physical_evaluation(
        config(tmp_path), store=EvidenceStore(tmp_path / "evidence"), project_root=Path.cwd()
    )
    assert result.outcome == "failed"
    assert result.metrics["physical_success"] is True
    assert result.metrics["component_passed"] is False
    assert result.claims == []


def test_shared_model_lease_blocks_before_evidence_allocation(tmp_path, monkeypatch):
    install_fixtures(monkeypatch)
    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir()
    held = WorkerLease.acquire(store.root / MODEL_JOB_LEASE)
    try:
        with pytest.raises(RuntimeError, match="holds this lease"):
            run_skill_physical_evaluation(config(tmp_path), store=store, project_root=Path.cwd())
    finally:
        held.close()
    assert not (store.root / "runs").exists()


def test_output_nested_in_source_is_rejected_before_allocation(tmp_path):
    cfg = config(tmp_path)
    nested = EvidenceStore(cfg.dataset_root / "evaluation")
    with pytest.raises(ValueError, match="outside immutable"):
        run_skill_physical_evaluation(cfg, store=nested, project_root=Path.cwd())
    assert not nested.root.exists()


def test_cli_forwards_component_limits_and_preserves_failure(tmp_path, monkeypatch, capsys):
    seen = []
    result = SimpleNamespace(outcome="failed", model_dump=lambda **kwargs: {"outcome": "failed"})
    monkeypatch.setattr(
        "bimanual.skill_physical_evaluation.run_skill_physical_evaluation",
        lambda cfg, **kwargs: seen.append((cfg, kwargs["store"].root)) or result,
    )
    assert (
        main(
            [
                "--artifacts",
                str(tmp_path / "evidence"),
                "skill-physical-eval",
                "--training-run",
                str(tmp_path / "training"),
                "--dataset",
                str(tmp_path / "dataset"),
                "--skill-views",
                str(tmp_path / "views.json"),
                "--skill",
                "cup_pick_place",
                "--device",
                "cpu",
                "--max-actions",
                "700",
                "--execute-chunk-steps",
                "5",
                "--wall-timeout-seconds",
                "300",
            ]
        )
        == 1
    )
    cfg, evidence = seen[0]
    assert cfg.skill_id == "cup_pick_place" and cfg.device == "cpu"
    assert cfg.max_actions == 700 and cfg.execute_chunk_steps == 5
    assert cfg.wall_timeout_seconds == 300
    assert evidence == tmp_path / "evidence"
    assert '"outcome": "failed"' in capsys.readouterr().out
