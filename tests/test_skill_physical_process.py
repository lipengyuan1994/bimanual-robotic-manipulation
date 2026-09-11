"""Spawned CPU lifecycle fixtures; no model, rendering or physical execution."""

import multiprocessing as mp
import os
import signal
import time

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.skill_physical_evaluation import SkillPhysicalEvaluationConfig
from bimanual.skill_physical_process import (
    EVALUATION_KIND,
    SkillPhysicalProcessConfig,
    run_skill_physical_process,
)


def _seal(config, store, *, passed=True):
    directory = store.new_run()
    (directory / "fixture.txt").write_text("CPU process fixture; no physical evaluation")
    return store.seal(
        directory,
        kind=EVALUATION_KIND,
        outcome="completed" if passed else "failed",
        config=config.model_dump(mode="json"),
        metrics={
            "component_passed": passed,
            "independent_task_success": None,
            "autonomous_workflow_success": None,
            "release_qualified": False,
        },
        source={},
        claims=[],
    )


def normal(config, *, store, **kwargs):
    return _seal(config, store)


def failed(config, *, store, **kwargs):
    return _seal(config, store, passed=False)


def hung(config, *, store, **kwargs):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "physical-native-ready").write_text("CPU hang fixture")
    while True:
        time.sleep(1)


def settings(tmp_path, *, wall=5):
    return SkillPhysicalProcessConfig(
        evaluation=SkillPhysicalEvaluationConfig(
            training_run=tmp_path / "training",
            dataset_root=tmp_path / "dataset",
            skill_views_path=tmp_path / "views.json",
            skill_id="bar_place_and_return",
            device="cpu",
            wall_timeout_seconds=wall,
        ),
        cancellation_grace_seconds=0.15,
        terminate_grace_seconds=0.15,
        poll_interval_seconds=0.01,
    )


def run(tmp_path, entrypoint, *, wall=5, cancelled=lambda: False):
    store = EvidenceStore(tmp_path / "evidence")
    result = run_skill_physical_process(
        settings(tmp_path, wall=wall),
        store=store,
        project_root=tmp_path,
        cancelled=cancelled,
        _entrypoint=entrypoint,
    )
    assert store.verify(result.run_id) == result
    if result.metrics["child_pid"] is not None:
        assert result.metrics["child_reaped"]
        assert result.metrics["child_pid"] not in [child.pid for child in mp.active_children()]
        with pytest.raises(ProcessLookupError):
            os.kill(result.metrics["child_pid"], 0)
    return store, result


def test_normal_process_reverifies_child_without_task_claim(tmp_path):
    store, result = run(tmp_path, normal)
    assert result.outcome == "completed"
    assert result.metrics["process_complete"] and result.metrics["component_passed"]
    assert result.metrics["child_manifest_verified"] and result.metrics["child_reaped"]
    assert result.metrics["independent_task_success"] is None
    child = store.verify(result.metrics["child_run_id"])
    assert child.manifest_sha256 == result.metrics["child_manifest_sha256"]


def test_clean_failed_component_remains_failed_process_result(tmp_path):
    _, result = run(tmp_path, failed)
    assert result.outcome == "failed"
    assert result.metrics["process_complete"] is True
    assert result.metrics["component_passed"] is False
    assert result.metrics["forced_interruption"] is False


def test_hung_component_escalates_and_releases_shared_lease(tmp_path):
    start = time.monotonic()
    store, result = run(tmp_path, hung, wall=1.5)
    assert result.outcome == "timed_out"
    assert result.metrics["forced_interruption"] and result.metrics["terminate_sent"]
    assert result.metrics["kill_sent"] and not result.metrics["process_complete"]
    assert result.metrics["child_exitcode"] == -signal.SIGKILL
    assert time.monotonic() - start < 5
    from bimanual.worker_lease import WorkerLease

    with WorkerLease.acquire(store.root / ".model-job.lock"):
        pass


def test_prestart_cancel_never_spawns_component(tmp_path):
    _, result = run(tmp_path, normal, cancelled=lambda: True)
    assert result.outcome == "cancelled"
    assert result.metrics["child_pid"] is None
    assert result.metrics["child_run_id"] is None


def test_busy_model_lease_does_not_allocate_frozen_attempt(tmp_path):
    from bimanual.worker_lease import WorkerLease

    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir(parents=True)
    with WorkerLease.acquire(store.root / ".model-job.lock"):
        with pytest.raises(RuntimeError, match="still holds"):
            run_skill_physical_process(
                settings(tmp_path),
                store=store,
                project_root=tmp_path,
                _entrypoint=normal,
            )
    assert not (store.root / "runs").exists()


def physical_owner(root):
    from pathlib import Path

    root = Path(root)
    run_skill_physical_process(
        settings(root, wall=10),
        store=EvidenceStore(root / "evidence"),
        project_root=root,
        _entrypoint=hung,
    )


def test_parent_death_reaps_physical_worker_and_releases_lease(tmp_path):
    import json

    from bimanual.worker_lease import WorkerLease

    owner = mp.get_context("spawn").Process(target=physical_owner, args=(str(tmp_path),))
    owner.start()
    try:
        ready = tmp_path / "evidence/physical-native-ready"
        deadline = time.monotonic() + 8
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "Physical worker did not start within fixture budget"
        parent_runs = list((tmp_path / "evidence/runs").glob("*/guardian/worker.json"))
        assert len(parent_runs) == 1
        parent_run = parent_runs[0].parent.parent
        owner.kill()
        owner.join(3)
        assert owner.exitcode == -signal.SIGKILL
        terminal_path = parent_run / "guardian/terminal.json"
        deadline = time.monotonic() + 5
        while not terminal_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        terminal = json.loads(terminal_path.read_text())
        assert terminal["reason"] == "parent_lost"
        assert terminal["worker_reaped"] and terminal["forced_interruption"]
        assert terminal["terminate_sent"] and terminal["kill_sent"]
        with WorkerLease.acquire(tmp_path / "evidence/.model-job.lock"):
            pass
        assert not (parent_run / "manifest.json").exists()
    finally:
        if owner.is_alive():
            owner.kill()
        owner.join(3)
        owner.close()
