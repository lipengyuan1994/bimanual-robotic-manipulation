"""Spawned CPU guardian fixtures; no MuJoCo environment or real case is executed."""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import time
from pathlib import Path

import pytest

from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.handoff_continuity_process import (
    HandoffContinuityProcessConfig,
    run_handoff_continuity_process,
)
from bimanual.handoff_continuity_teacher import (
    KIND,
    REQUEST,
    _reservation_name,
)


def fixture_request(protocol_path, case_id):
    return {
        "protocol_path": str(Path(protocol_path).resolve(strict=True)),
        "protocol_file_sha256": digest_file(protocol_path),
        "protocol_manifest_sha256": "a" * 64,
        "case_id": case_id,
        "case": {"case_id": case_id, "seed": 1},
        "phase_boundaries": {"fixture": 1},
        "correction_scope": "cpu_fixture_only",
        "training_only": True,
    }


def _reserve_and_seal(protocol_path, case_id, *, store, success=True, kind=KIND):
    request = fixture_request(protocol_path, case_id)
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    (directory / REQUEST).write_bytes(canonical(request) + b"\n")
    (directory / "fixture.txt").write_text("CPU lifecycle fixture; no physical execution")
    return store.seal(
        directory,
        kind=kind,
        outcome="completed" if success else "failed",
        config=request,
        metrics={
            "physical_handoff_success": success,
            "independent_score": (
                {
                    "profile": "handoff_receiver_continuity_physical_score_v1",
                    "physical_handoff_success": True,
                }
                if success
                else None
            ),
            "teacher_assistance": True,
            "learned_execution": False,
            "release_qualified": False,
        },
        source={},
        claims=[],
    )


def normal(protocol_path, case_id, *, store, **kwargs):
    kwargs["model_job_lease"].assert_path(kwargs["model_job_lease_path"])
    return _reserve_and_seal(protocol_path, case_id, store=store)


def failed(protocol_path, case_id, *, store, **kwargs):
    return _reserve_and_seal(protocol_path, case_id, store=store, success=False)


def wrong_kind(protocol_path, case_id, *, store, **kwargs):
    return _reserve_and_seal(protocol_path, case_id, store=store, kind="untrusted_fixture")


def hung(protocol_path, case_id, *, store, **kwargs):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    request = fixture_request(protocol_path, case_id)
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    (directory / REQUEST).write_bytes(canonical(request) + b"\n")
    (store.root / "continuity-native-ready").write_text("CPU hang fixture")
    while True:
        time.sleep(1)


def settings(protocol_path, *, wall=5):
    return HandoffContinuityProcessConfig(
        protocol_path=protocol_path,
        case_id="receiver-baseline",
        wall_timeout_seconds=wall,
        cancellation_grace_seconds=0.15,
        terminate_grace_seconds=0.15,
        poll_interval_seconds=0.01,
    )


def run(tmp_path, entrypoint, *, wall=5, cancelled=lambda: False):
    store = EvidenceStore(tmp_path / "evidence")
    protocol = tmp_path / "continuity-protocol.json"
    protocol.write_text("{}")
    result = run_handoff_continuity_process(
        settings(protocol, wall=wall),
        store=store,
        project_root=Path(__file__).parents[1],
        cancelled=cancelled,
        _entrypoint=entrypoint,
        _request_builder=fixture_request,
    )
    assert store.verify(result.run_id) == result
    if result.metrics.get("child_pid") is not None:
        assert result.metrics["child_reaped"]
        with pytest.raises(ProcessLookupError):
            os.kill(result.metrics["child_pid"], 0)
    return store, result


def test_clean_child_is_reverified_before_process_completion(tmp_path):
    store, result = run(tmp_path, normal)
    assert result.outcome == "completed"
    assert result.metrics["process_complete"] is True
    assert result.metrics["physical_handoff_success"] is True
    assert result.metrics["child_manifest_verified"] is True
    child = store.verify(result.metrics["child_run_id"])
    assert child.manifest_sha256 == result.metrics["child_manifest_sha256"]
    assert (
        run_handoff_continuity_process(
            settings(tmp_path / "continuity-protocol.json"),
            store=store,
            project_root=Path(__file__).parents[1],
            _entrypoint=normal,
            _request_builder=fixture_request,
        )
        == child
    )


def test_clean_physical_failure_remains_a_completed_failed_process(tmp_path):
    _, result = run(tmp_path, failed)
    assert result.outcome == "failed"
    assert result.metrics["process_complete"] is True
    assert result.metrics["physical_handoff_success"] is False
    assert result.metrics["forced_interruption"] is False


def test_wrong_child_kind_cannot_support_parent_completion(tmp_path):
    _, result = run(tmp_path, wrong_kind)
    assert result.outcome == "failed"
    assert result.metrics["process_complete"] is False
    assert result.metrics["child_manifest_verified"] is False
    assert "kind/config" in result.metrics["child_verification_error"]


def test_busy_model_lease_allocates_no_case_or_process_run(tmp_path):
    from bimanual.worker_lease import WorkerLease

    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir(parents=True)
    (tmp_path / "continuity-protocol.json").write_text("{}")
    with WorkerLease.acquire(store.root / ".model-job.lock"):
        with pytest.raises(RuntimeError, match="still holds"):
            run_handoff_continuity_process(
                settings(tmp_path / "continuity-protocol.json"),
                store=store,
                project_root=Path(__file__).parents[1],
                _entrypoint=normal,
                _request_builder=fixture_request,
            )
    assert not (store.root / "runs").exists()


def test_protocol_cannot_be_inside_the_evidence_store(tmp_path):
    protocol = tmp_path / "protocol" / "continuity.json"
    protocol.parent.mkdir()
    protocol.write_text("{}")
    store = EvidenceStore(protocol.parent)

    with pytest.raises(ValueError, match="outside"):
        run_handoff_continuity_process(
            settings(protocol),
            store=store,
            project_root=Path(__file__).parents[1],
            _entrypoint=normal,
            _request_builder=fixture_request,
        )

    assert not (store.root / "runs").exists()


def test_native_hang_is_killed_with_bounded_lease_release(tmp_path):
    from bimanual.worker_lease import WorkerLease

    started = time.monotonic()
    store, result = run(tmp_path, hung, wall=1.5)
    assert result.outcome == "timed_out"
    assert result.metrics["forced_interruption"] and result.metrics["kill_sent"]
    assert result.metrics["process_complete"] is False
    assert time.monotonic() - started < 5
    with WorkerLease.acquire(store.root / ".model-job.lock"):
        pass


def continuity_owner(root):
    root = Path(root)
    protocol = root / "continuity-protocol.json"
    run_handoff_continuity_process(
        settings(protocol, wall=10),
        store=EvidenceStore(root / "evidence"),
        project_root=Path(__file__).parents[1],
        _entrypoint=hung,
        _request_builder=fixture_request,
    )


def test_parent_loss_reaps_hung_worker_and_preserves_consumed_reservation(tmp_path):
    import json

    from bimanual.worker_lease import WorkerLease

    owner = mp.get_context("spawn").Process(target=continuity_owner, args=(str(tmp_path),))
    (tmp_path / "continuity-protocol.json").write_text("{}")
    owner.start()
    try:
        ready = tmp_path / "evidence/continuity-native-ready"
        deadline = time.monotonic() + 8
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "Continuity fixture did not start within its CPU budget"
        guardians = list((tmp_path / "evidence/runs").glob("*/guardian/terminal.json"))
        assert guardians == []
        process_runs = list((tmp_path / "evidence/runs").glob("*/guardian/worker.json"))
        assert len(process_runs) == 1
        process_run = process_runs[0].parent.parent
        owner.kill()
        owner.join(3)
        terminal_path = process_run / "guardian/terminal.json"
        deadline = time.monotonic() + 5
        while not terminal_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        terminal = json.loads(terminal_path.read_text())
        assert terminal["reason"] == "parent_lost"
        assert terminal["worker_reaped"] and terminal["forced_interruption"]
        with WorkerLease.acquire(tmp_path / "evidence/.model-job.lock"):
            pass
        request = fixture_request(tmp_path / "continuity-protocol.json", "receiver-baseline")
        reservation = EvidenceStore(tmp_path / "evidence").directory(
            _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
        )
        assert (reservation / REQUEST).is_file()
        assert not (reservation / "manifest.json").exists()
        assert not (process_run / "manifest.json").exists()
    finally:
        if owner.is_alive():
            owner.kill()
        owner.join(3)
        owner.close()
