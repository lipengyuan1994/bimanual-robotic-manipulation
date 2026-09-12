from threading import Event, Thread

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.training import ACTTrainingConfig, run_train
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process


def config(tmp_path):
    return ACTTrainingConfig(dataset_path=tmp_path / "dataset")


def should_not_run(*args, **kwargs):
    raise AssertionError("A competing workflow must not launch its worker")


def test_training_owns_shared_model_lease_before_allocating_evidence(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "evidence")
    entered, release = Event(), Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return "finished"

    monkeypatch.setattr("bimanual.training._run_train", blocked)
    result = []
    thread = Thread(
        target=lambda: result.append(
            run_train(config(tmp_path), store=store, project_root=tmp_path)
        )
    )
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(RuntimeError, match="still holds"):
            run_train(config(tmp_path), store=store, project_root=tmp_path)
        assert list(store.root.glob("runs/*")) == []
        with pytest.raises(RuntimeError, match="still holds"):
            WorkerLease.acquire(store.root / MODEL_JOB_LEASE)
    finally:
        release.set()
        thread.join(5)
    assert result == ["finished"]
    with WorkerLease.acquire(store.root / MODEL_JOB_LEASE):
        pass


def test_workflow_and_training_use_the_same_lease_name():
    assert MODEL_JOB_LEASE == ".model-job.lock"


def test_nested_training_store_can_use_parent_model_lease(tmp_path, monkeypatch):
    parent = EvidenceStore(tmp_path / "evidence")
    parent.root.mkdir(parents=True)
    child = EvidenceStore(parent.root / "attempt/training-evidence")
    monkeypatch.setattr("bimanual.training._run_train", lambda *a, **k: "finished")
    lease_path = parent.root / MODEL_JOB_LEASE
    with WorkerLease.acquire(lease_path) as lease:
        with pytest.raises(RuntimeError, match="still holds"):
            run_train(
                config(tmp_path),
                store=child,
                project_root=tmp_path,
                model_job_lease_path=lease_path,
            )
        assert (
            run_train(
                config(tmp_path),
                store=child,
                project_root=tmp_path,
                model_job_lease_path=lease_path,
                model_job_lease=lease,
            )
            == "finished"
        )
    assert (
        run_train(
            config(tmp_path),
            store=child,
            project_root=tmp_path,
            model_job_lease_path=lease_path,
        )
        == "finished"
    )


def test_existing_model_lease_must_match_expected_path(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir(parents=True)
    monkeypatch.setattr("bimanual.training._run_train", lambda *a, **k: "finished")
    with WorkerLease.acquire(store.root / "other.lock") as lease:
        with pytest.raises(RuntimeError, match="expected lock"):
            run_train(
                config(tmp_path),
                store=store,
                project_root=tmp_path,
                model_job_lease_path=store.root / MODEL_JOB_LEASE,
                model_job_lease=lease,
            )


def test_training_lease_prevents_competing_workflow_worker(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir(parents=True)
    settings = WorkflowProcessConfig(
        execution=WorkflowExecutionConfig(
            workflow_manifest="cohort.json",
            planner_model_directory="model",
            instruction="lease fixture",
            wall_timeout_seconds=2,
            step_timeout_seconds=1,
        ),
        cancellation_grace_seconds=0.01,
        terminate_grace_seconds=0.05,
        poll_interval_seconds=0.01,
    )
    with WorkerLease.acquire(store.root / MODEL_JOB_LEASE):
        result = run_workflow_process(
            settings, store=store, project_root=tmp_path, _entrypoint=should_not_run
        )
    assert result.outcome == "failed"
    assert result.metrics["child_pid"] is None
    assert result.metrics["child_manifest_verified"] is False
    assert result.metrics["execution_complete"] is False
