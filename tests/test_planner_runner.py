from threading import Event, get_ident
from types import SimpleNamespace

import pytest

from bimanual.planner_runner import LocalPlannerRunner


class Session:
    def __init__(self):
        self.calls = []

    def begin(self):
        self.calls.append(("begin", get_ident()))
        return SimpleNamespace(job_id="job", context="context")

    def images(self, job):
        return ("copied-image",)

    def check_pending(self, job):
        self.calls.append(("check_pending", get_ident()))

    def complete(self, job, text, *, model_metrics=None):
        self.calls.append(("complete", get_ident()))
        return "dispatch"

    def cancel(self, job, reason):
        self.calls.append(("cancel", get_ident()))

    def fail(self, job, error):
        self.calls.append(("fail", get_ident()))


def test_model_thread_never_dispatches_and_poll_is_nonblocking():
    session, entered, release = Session(), Event(), Event()
    model_threads = []

    def generate(context, images, **kwargs):
        model_threads.append(get_ident())
        assert context == "context" and images == ("copied-image",)
        entered.set()
        assert release.wait(2)
        return "response", {"actual_device": "cpu"}

    runner = LocalPlannerRunner(session, SimpleNamespace(generate=generate))
    try:
        runner.submit()
        assert entered.wait(2)
        assert runner.poll() is None
        with pytest.raises(RuntimeError, match="pending"):
            runner.submit()
        release.set()
        runner._pending[1].result(timeout=2)
        result = runner.poll()
        assert result.dispatch == "dispatch" and result.model_metrics == {
            "actual_device": "cpu",
            "model_manifest_sha256": None,
        }
        assert all(thread == get_ident() for _, thread in session.calls)
        assert model_threads[0] != get_ident()
    finally:
        release.set()
        runner.close()


def test_cancel_revokes_authority_while_generation_is_running():
    session, entered, release = Session(), Event(), Event()

    def generate(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return "late response", {}

    runner = LocalPlannerRunner(session, SimpleNamespace(generate=generate))
    try:
        runner.submit()
        future = runner._pending[1]
        assert entered.wait(2)
        runner.cancel()
        assert session.calls[-1][0] == "cancel"
        release.set()
        future.result(timeout=2)
        assert runner.poll() is None
        assert not any(kind == "complete" for kind, _ in session.calls)
    finally:
        release.set()
        runner.close()


@pytest.mark.parametrize("result", [None, (42, {}), ("text", {"latency": float("nan")})])
def test_malformed_result_cannot_reach_dispatch(result):
    session = Session()
    runner = LocalPlannerRunner(session, SimpleNamespace(generate=lambda *a, **k: result))
    try:
        runner.submit()
        runner._pending[1].result(timeout=2)
        with pytest.raises((ValueError, TypeError)):
            runner.poll()
        assert session.calls[-1][0] == "fail"
        assert not any(kind == "complete" for kind, _ in session.calls)
    finally:
        runner.close()


def test_closed_runner_and_invalid_budget_reject_new_work():
    with pytest.raises(ValueError):
        LocalPlannerRunner(None, None, max_tokens=True)
    runner = LocalPlannerRunner(None, None)
    runner.close()
    with pytest.raises(RuntimeError, match="closed"):
        runner.submit()


def test_pending_job_expiry_revokes_late_generation():
    session, entered, release = Session(), Event(), Event()

    def generate(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return "late", {}

    runner = LocalPlannerRunner(session, SimpleNamespace(generate=generate))
    try:
        runner.submit()
        future = runner._pending[1]
        assert entered.wait(2)

        def expired(job):
            raise TimeoutError("Planning expired")

        session.check_pending = expired
        with pytest.raises(TimeoutError):
            runner.poll()
        release.set()
        future.result(timeout=2)
        assert runner.poll() is None
        assert not any(kind == "complete" for kind, _ in session.calls)
    finally:
        release.set()
        runner.close()
