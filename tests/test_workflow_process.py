"""Real spawned CPU fixtures only, not models, rendering or manipulation evidence."""

import hashlib
import multiprocessing as mp
import os
import signal
import time
from threading import Thread

import pytest

from bimanual.evidence import EvidenceStore, canonical
from bimanual.workflow_execution import WorkflowExecutionConfig
from bimanual.workflow_manifest import SKILLS
from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process


def _seal_fixture(config, store, *, state="execution_complete", contradiction=False):
    directory = store.new_run()
    (directory / "fixture.txt").write_text("CPU process fixture; no physical execution")
    return store.seal(
        directory,
        kind="dinner_workflow_execution",
        outcome="completed" if state == "execution_complete" else state,
        config=config.model_dump(mode="json"),
        metrics=dict(
            state=state,
            execution_complete=state == "execution_complete" and not contradiction,
            independent_task_success=None,
        ),
        source={},
        claims=[],
    )


def normal(config, *, store, **kwargs):
    return _seal_fixture(config, store)


def noisy(config, *, store, **kwargs):
    print("python-child-progress", flush=True)
    os.write(1, b"native-child-progress\n")
    return _seal_fixture(config, store)


def child_error(config, **kwargs):
    raise RuntimeError("CPU fixture exception")


def fabricated(config, **kwargs):
    class Result:
        run_id = "unsealed-claim"

    return Result()


def contradictory(config, *, store, **kwargs):
    return _seal_fixture(config, store, contradiction=True)


def failed(config, *, store, **kwargs):
    return _seal_fixture(config, store, state="failed")


def cooperative(config, *, store, cancelled, **kwargs):
    store.root.mkdir(parents=True)
    (store.root / "started.json").write_text("{}")
    while not cancelled():
        time.sleep(0.01)
    return _seal_fixture(config, store, state="cancelled")


def hung(config, *, store, **kwargs):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    store.root.mkdir(parents=True)
    (store.root / "started.json").write_text("{}")
    (store.root / "partial.jsonl").write_text('{"partial": true}\n')
    while True:
        time.sleep(1)


def sealed_then_hung_thread(config, *, store, **kwargs):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    result = _seal_fixture(config, store)
    Thread(target=lambda: time.sleep(300), daemon=False).start()
    return result


def damaged_seal(config, *, store, **kwargs):
    result = _seal_fixture(config, store)
    (store.directory(result.run_id) / "fixture.txt").write_text("changed")
    return result


def settings(*, wall=5, cancellation_grace=0.15):
    return WorkflowProcessConfig(
        execution=WorkflowExecutionConfig(
            workflow_manifest="cohort.json",
            planner_model_directory="model",
            instruction="Process fixture",
            wall_timeout_seconds=wall,
            step_timeout_seconds=min(1, wall),
        ),
        cancellation_grace_seconds=cancellation_grace,
        terminate_grace_seconds=0.15,
        poll_interval_seconds=0.01,
    )


def run(tmp_path, entrypoint, *, wall=5, cancelled=lambda: False, cancellation_grace=0.15):
    store = EvidenceStore(tmp_path / "evidence")
    result = run_workflow_process(
        settings(wall=wall, cancellation_grace=cancellation_grace),
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


def test_normal_spawn_requires_verified_child_and_same_interpreter(tmp_path):
    store, result = run(tmp_path, normal)
    assert result.outcome == "completed"
    assert result.metrics["execution_complete"] and result.metrics["child_manifest_verified"]
    assert result.metrics["independent_task_success"] is None
    assert result.metrics["start_method"] == "spawn" and not result.metrics["forced_interruption"]
    child_store = EvidenceStore(store.directory(result.run_id) / "child-evidence")
    child = child_store.verify(result.metrics["child_run_id"])
    assert child.manifest_sha256 == result.metrics["child_manifest_sha256"]


@pytest.mark.parametrize(
    "entrypoint", [child_error, fabricated, contradictory, damaged_seal, failed]
)
def test_error_unsealed_or_contradictory_child_cannot_succeed(tmp_path, entrypoint):
    _, result = run(tmp_path, entrypoint)
    assert result.outcome == "failed" and not result.metrics["execution_complete"]
    assert result.claims == []


def test_prestart_cancel_does_not_spawn(tmp_path):
    _, result = run(tmp_path, normal, cancelled=lambda: True)
    assert result.outcome == "cancelled" and result.metrics["child_pid"] is None


def test_running_cooperative_cancel_preserves_child_seal(tmp_path):
    # Exercise the production grace period, not the deliberately short escalation
    # fixture. A sealed child still needs time to finish interpreter shutdown.
    _, result = run(
        tmp_path,
        cooperative,
        cancelled=lambda: any(tmp_path.rglob("started.json")),
        cancellation_grace=WorkflowProcessConfig.model_fields["cancellation_grace_seconds"].default,
    )
    assert result.outcome == "cancelled"
    assert result.metrics["child_manifest_verified"]
    assert not result.metrics["forced_interruption"]


@pytest.mark.parametrize("operator_cancel", [False, True])
def test_hung_child_escalates_to_kill_and_reaps_partial_evidence(tmp_path, operator_cancel):
    start = time.monotonic()
    store, result = run(
        tmp_path,
        hung,
        wall=1.5,
        cancelled=lambda: operator_cancel and any(tmp_path.rglob("started.json")),
    )
    assert result.outcome == ("cancelled" if operator_cancel else "timed_out")
    assert result.metrics["forced_interruption"] and result.metrics["kill_sent"]
    assert result.metrics["terminate_sent"] and result.metrics["child_exitcode"] == -signal.SIGKILL
    assert not result.metrics["execution_complete"]
    assert "child-evidence/partial.jsonl" in result.files
    assert time.monotonic() - start < 5
    assert store.verify(result.run_id) == result


def test_completed_child_seal_with_blocked_thread_still_forced_interruption(tmp_path):
    store, result = run(tmp_path, sealed_then_hung_thread, wall=1.5)
    assert result.outcome == "timed_out" and result.metrics["forced_interruption"]
    assert (
        result.metrics["child_manifest_verified"] and result.metrics["child_outcome"] == "completed"
    )
    assert not result.metrics["execution_complete"]
    child = EvidenceStore(store.directory(result.run_id) / "child-evidence").verify(
        result.metrics["child_run_id"]
    )
    assert child.outcome == "completed"  # Parent never rewrites a sealed child.


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_parent_callback_error_also_stops_and_reaps_child(tmp_path, error):
    def cancelled():
        if any(tmp_path.rglob("started.json")):
            raise error("Injected parent failure")
        return False

    _, result = run(tmp_path, hung, cancelled=cancelled)
    assert result.outcome == ("cancelled" if error is KeyboardInterrupt else "failed")
    assert result.metrics["forced_interruption"]
    assert "parent-error.txt" in result.files


def test_child_python_and_native_progress_go_to_stderr(tmp_path, capfd):
    _, result = run(tmp_path, noisy)
    output = capfd.readouterr()
    assert output.out == ""
    assert "python-child-progress" in output.err
    assert "native-child-progress" in output.err
    assert result.outcome == "completed"


def test_real_entrypoint_missing_cohort_seals_child_failure_without_model_load(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    result = run_workflow_process(settings(), store=store, project_root=tmp_path)
    assert result.outcome == "failed"
    assert result.metrics["child_manifest_verified"] and result.metrics["child_reaped"]
    assert result.metrics["backend"] == "workflow_execution"
    child_store = EvidenceStore(store.directory(result.run_id) / "child-evidence")
    child = child_store.verify(result.metrics["child_run_id"])
    assert child.outcome == "failed"
    assert child.metrics["actual_policy_devices"] is None
    assert child.metrics["actual_planner_device"] is None
    assert "error.txt" in child.files
    assert not any(name.startswith("worker/") for name in child.files)
    assert store.verify(result.run_id) == result
    with pytest.raises(ProcessLookupError):
        os.kill(result.metrics["child_pid"], 0)


def test_invalid_config_rejected_before_outputs(tmp_path):
    invalid = settings().model_copy(update={"poll_interval_seconds": 0})
    with pytest.raises(ValueError):
        run_workflow_process(
            invalid, store=EvidenceStore(tmp_path / "output"), project_root=tmp_path
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "root", ["model", "dataset/evidence", "training/handoff_transfer/checkpoint/evidence"]
)
def test_immutable_source_output_confinement_before_allocation(tmp_path, root):
    body = dict(
        schema_version=1,
        profile="dinner_development_workflow_v1",
        dataset_root="dataset",
        export_file_sha256="a" * 64,
        skill_views_path="views.json",
        skill_views_file_sha256="b" * 64,
        checkpoints=[
            dict(
                schema_version=1,
                skill_id=skill,
                training_run=f"training/{skill}",
                training_manifest_sha256="c" * 64,
                checkpoint_sha256="d" * 64,
            )
            for skill in SKILLS
        ],
    )
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    (tmp_path / "cohort.json").write_bytes(canonical(body))
    with pytest.raises(ValueError, match="outside immutable"):
        run_workflow_process(
            settings(), store=EvidenceStore(tmp_path / root), project_root=tmp_path
        )
    assert not (tmp_path / root).exists()
