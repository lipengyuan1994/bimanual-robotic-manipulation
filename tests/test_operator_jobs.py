"""Operator ownership tests with sealed CPU fixtures, not learned task execution."""

import json
from threading import Event, Thread

import pytest

from bimanual.evidence import EvidenceStore
from bimanual.operator_jobs import OperatorJob, OperatorJobs
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_process import WorkflowProcessConfig


def config():
    return WorkflowProcessConfig(
        execution=WorkflowExecutionConfig(
            workflow_manifest="cohort.json", planner_model_directory="model", instruction="initial"
        )
    )


def seal(store, outcome="completed", kind="dinner_workflow_process"):
    directory = store.new_run()
    (directory / "result.txt").write_text("CPU test fixture")
    return store.seal(
        directory, kind=kind, outcome=outcome, config={}, metrics={}, source={}, claims=[]
    )


def manager(tmp_path, runner):
    return OperatorJobs(
        config(), store=EvidenceStore(tmp_path / "evidence"), project_root=tmp_path, _runner=runner
    )


def test_only_one_active_job_stop_identity_and_verified_final(tmp_path):
    entered, release = Event(), Event()
    observed = []

    def runner(cfg, *, store, cancelled, **kwargs):
        observed.append(cfg.execution.instruction)
        entered.set()
        assert release.wait(5)
        return seal(store, "cancelled" if cancelled() else "completed")

    jobs = manager(tmp_path, runner)
    try:
        job = jobs.start("Set the table")
        assert entered.wait(5)
        with pytest.raises(RuntimeError, match="already active"):
            jobs.start("Second task")
        with pytest.raises(KeyError):
            jobs.stop("unrelated")
        assert jobs.snapshot().state == "active"
        assert jobs.stop(job.job_id).state == "stopping"
        assert jobs.stop(job.job_id).state == "stopping"
        release.set()
        jobs.close()
        final = jobs.snapshot()
        assert final.state == "cancelled" and final.run_outcome == "cancelled"
        assert final.run_id and final.independent_task_success is None
        assert jobs.stop(job.job_id) == final
        assert observed == ["Set the table"]
        with pytest.raises(RuntimeError, match="closed"):
            jobs.start("Another")
    finally:
        release.set()
        jobs.close()


@pytest.mark.parametrize("outcome,state", [("completed", "finished"), ("failed", "failed")])
def test_execution_outcomes_never_claim_independent_task_success(tmp_path, outcome, state):
    jobs = manager(tmp_path, lambda cfg, *, store, **kw: seal(store, outcome))
    jobs.start("Dinner")
    jobs.close()
    result = jobs.snapshot()
    assert result.state == state and result.run_outcome == outcome
    assert result.independent_task_success is None
    if outcome == "failed":
        assert result.error == "Workflow did not complete. Inspect the recorded run for details."
    else:
        assert result.error is None
    assert "independent_task_success" in result.report()


@pytest.mark.parametrize("fault", ["exception", "corrupt", "wrong_kind"])
def test_failure_is_visible_and_cannot_fabricate_a_finished_job(tmp_path, fault):
    def runner(cfg, *, store, **kwargs):
        if fault == "exception":
            raise OSError("fixture unavailable")
        result = seal(
            store, kind="unrelated" if fault == "wrong_kind" else "dinner_workflow_process"
        )
        if fault == "corrupt":
            (store.directory(result.run_id) / "result.txt").write_text("modified")
        return result

    jobs = manager(tmp_path, runner)
    jobs.start("Dinner")
    jobs.close()
    result = jobs.snapshot()
    assert result.state == "failed" and result.error and result.run_id is None
    assert result.independent_task_success is None


def test_close_timeout_does_not_claim_shutdown_or_accept_new_work(tmp_path):
    entered, release = Event(), Event()

    def runner(cfg, *, store, **kwargs):
        entered.set()
        assert release.wait(5)
        return seal(store)

    jobs = manager(tmp_path, runner)
    try:
        jobs.start("Dinner")
        assert entered.wait(5)
        with pytest.raises(TimeoutError, match="not confirmed"):
            jobs.close(timeout=0)
        assert jobs.snapshot().state == "stopping"
        with pytest.raises(RuntimeError, match="closed"):
            jobs.start("Replacement")
    finally:
        release.set()
        jobs.close()
    # The fixture ignored cancellation and finished; do not falsify its sealed outcome.
    assert jobs.snapshot().state == "finished"


def test_concurrent_start_cannot_create_two_workers(tmp_path):
    release, entered = Event(), Event()
    accepted, rejected = [], []

    def runner(cfg, *, store, **kwargs):
        entered.set()
        assert release.wait(5)
        return seal(store)

    jobs = manager(tmp_path, runner)

    def start():
        try:
            accepted.append(jobs.start("Dinner"))
        except RuntimeError as error:
            rejected.append(str(error))

    callers = [Thread(target=start) for _ in range(8)]
    try:
        for thread in callers:
            thread.start()
        for thread in callers:
            thread.join()
        assert entered.wait(5)
        assert len(accepted) == 1 and len(rejected) == 7
    finally:
        release.set()
        jobs.close()


def test_invalid_instruction_is_rejected_before_launch(tmp_path):
    def runner(*args, **kwargs):
        pytest.fail("Invalid instruction launched a job")

    jobs = manager(tmp_path, runner)
    with pytest.raises(ValueError):
        jobs.start("")
    assert jobs.snapshot() is None
    jobs.close()


def test_finished_worker_allows_new_job_without_reusing_stop_identity(tmp_path):
    jobs = manager(tmp_path, lambda cfg, *, store, **kw: seal(store))
    first = jobs.start("First")
    jobs._thread.join(timeout=5)
    assert jobs.snapshot().state == "finished"
    second = jobs.start("Second")
    assert first.job_id != second.job_id
    with pytest.raises(KeyError):
        jobs.stop(first.job_id)
    jobs.close()
    assert jobs.snapshot().job_id == second.job_id


def test_thread_start_failure_leaves_a_closeable_failed_job(tmp_path, monkeypatch):
    def fail_start(self):
        raise RuntimeError("fixture cannot start")

    monkeypatch.setattr(Thread, "start", fail_start)
    jobs = manager(tmp_path, lambda *args, **kw: pytest.fail("Unexpected execution"))
    with pytest.raises(RuntimeError, match="cannot start"):
        jobs.start("Dinner")
    assert jobs.snapshot().state == "failed"
    jobs.close()


def test_progress_does_not_replace_job_state_or_terminal_evidence(tmp_path):
    entered, release = Event(), Event()
    value = {"snapshot": {"state": "executing"}, "task_success_verified": False}

    def runner(cfg, *, store, on_progress, **kwargs):
        on_progress(value)
        entered.set()
        assert release.wait(5)
        return seal(store, "failed")

    jobs = manager(tmp_path, runner)
    jobs.start("fixture")
    assert entered.wait(5)
    assert jobs.snapshot().state == "active"
    assert jobs.snapshot().progress == value
    release.set()
    jobs.close()
    assert jobs.snapshot().state == "failed"
    assert jobs.snapshot().progress == value
    assert jobs.snapshot().independent_task_success is None


@pytest.mark.parametrize(
    "outcome,state",
    [
        ("timed_out", "failed"),
        ("needs_clarification", "needs_clarification"),
        ("recovery_required", "failed"),
        ("replaced", "cancelled"),
        ("closed", "cancelled"),
    ],
)
def test_terminal_outcomes_keep_verified_run_and_explanation(tmp_path, outcome, state):
    def runner(cfg, *, store, **kwargs):
        directory = store.new_run()
        return store.seal(
            directory,
            kind="dinner_workflow_process",
            outcome=outcome,
            config={},
            metrics={"child_reason": "Where should the cup go?"},
            source={},
            claims=[],
        )

    jobs = manager(tmp_path, runner)
    jobs.start("fixture")
    jobs.close()
    job = jobs.snapshot()
    assert job.state == state and job.run_id is not None
    assert job.run_outcome == outcome
    assert job.independent_task_success is None
    if outcome == "timed_out":
        assert "time limit" in job.error
    elif state in {"failed", "needs_clarification"}:
        assert job.error == "Where should the cup go?"


@pytest.mark.parametrize("state", ["active", "stopping"])
def test_restart_marks_unfinished_job_recovery_required_without_launch(tmp_path, state):
    evidence = tmp_path / "evidence"
    original = OperatorJobs(
        config(), store=EvidenceStore(evidence), project_root=tmp_path, _runner=None
    )
    original._publish(OperatorJob("a" * 32, state, "Set the table"))
    calls = []

    def runner(cfg, *, store, **kwargs):
        calls.append(cfg.execution.instruction)
        return seal(store)

    recovered = OperatorJobs(
        config(),
        store=EvidenceStore(evidence),
        project_root=tmp_path,
        _runner=runner,
    )

    job = recovered.snapshot()
    assert calls == []
    assert job.job_id == "a" * 32
    assert job.instruction == "Set the table"
    assert job.state == "recovery_required"
    assert job.run_id is None and job.independent_task_success is None
    assert "restarted" in job.error
    replacement = recovered.start("Deliberate replacement")
    recovered.close()
    assert replacement.job_id != job.job_id
    assert calls == ["Deliberate replacement"]


def test_verified_terminal_job_survives_restart(tmp_path):
    evidence = tmp_path / "evidence"
    first = manager(tmp_path, lambda cfg, *, store, **kw: seal(store))
    first.start("Dinner")
    first.close()
    expected = first.snapshot()
    calls = []

    restored = OperatorJobs(
        config(),
        store=EvidenceStore(evidence),
        project_root=tmp_path,
        _runner=lambda *args, **kwargs: calls.append(True),
    )
    assert restored.snapshot() == expected
    assert calls == []
    restored.close()


@pytest.mark.parametrize("fault", ["malformed", "oversized", "symlink"])
def test_invalid_persistent_state_fails_closed_without_launch(tmp_path, fault):
    journal = tmp_path / "evidence" / "operator-jobs"
    journal.mkdir(parents=True)
    pointer = journal / "current.json"
    if fault == "malformed":
        pointer.write_text("not json")
    elif fault == "oversized":
        pointer.write_bytes(b"{" + b"x" * 2048)
    else:
        target = tmp_path / "outside.json"
        target.write_text("{}")
        pointer.symlink_to(target)
    calls = []
    jobs = manager(tmp_path, lambda *args, **kwargs: calls.append(True))

    job = jobs.snapshot()
    assert job.state == "recovery_required"
    assert job.independent_task_success is None
    with pytest.raises(RuntimeError, match="journal requires recovery"):
        jobs.start("Replacement")
    assert calls == []
    jobs.close()


def test_missing_journal_predecessor_fails_closed(tmp_path):
    evidence = tmp_path / "evidence"
    original = OperatorJobs(
        config(), store=EvidenceStore(evidence), project_root=tmp_path, _runner=None
    )
    original._publish(OperatorJob("a" * 32, "active", "Set the table"))
    original._publish(OperatorJob("a" * 32, "stopping", "Set the table"))
    pointer = json.loads((evidence / "operator-jobs" / "current.json").read_text())
    records = list((evidence / "operator-jobs" / "records").glob("*.json"))
    predecessor = next(path for path in records if path.stem != pointer["record_id"])
    predecessor.unlink()

    restored = OperatorJobs(
        config(), store=EvidenceStore(evidence), project_root=tmp_path, _runner=None
    )
    assert restored.snapshot().state == "recovery_required"
    with pytest.raises(RuntimeError, match="journal requires recovery"):
        restored.start("Replacement")
