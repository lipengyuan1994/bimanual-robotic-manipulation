"""Nonblocking model generation; all simulation authority stays on the caller thread."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass

from bimanual.evidence import canonical


@dataclass(frozen=True)
class PlannerRunResult:
    job_id: str
    dispatch: object
    model_metrics: dict


class LocalPlannerRunner:
    """Call submit/poll/cancel serially on the worker thread with a preloaded model.

    A single model thread generates text from copied inputs. It never captures,
    steps or dispatches the simulation. Cancellation revokes authority immediately;
    an in-flight model call may finish computing, but its output is discarded.
    This class is not a worker-thread lock or a process-level crash supervisor.
    """

    def __init__(self, session, planner, *, max_tokens: int = 384):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 1024:
            raise ValueError("Planner token budget must be between one and 1024")
        self._session, self._planner, self._max_tokens = session, planner, max_tokens
        manifest = getattr(planner, "manifest", None)
        self._model_manifest_sha256 = (
            hashlib.sha256(canonical(manifest)).hexdigest() if manifest is not None else None
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-planner")
        self._pending = None
        self._closed = False

    def submit(self):
        if self._closed or self._pending is not None:
            raise RuntimeError("Planner runner is closed or already owns a pending job")
        job = self._session.begin()
        try:
            images = self._session.images(job.job_id)
            future = self._executor.submit(
                self._planner.generate, job.context, images, max_tokens=self._max_tokens
            )
        except BaseException as error:
            self._session.fail(job.job_id, error)
            raise
        self._pending = (job, future)
        return job

    def poll(self) -> PlannerRunResult | None:
        if self._pending is None:
            return None
        job, future = self._pending
        try:
            self._session.check_pending(job.job_id)
        except BaseException:
            self._pending = None
            future.cancel()
            raise
        if not future.done():
            return None
        self._pending = None
        try:
            text, metrics = future.result()
            if not isinstance(text, str) or not isinstance(metrics, dict):
                raise ValueError("Local planner returned malformed generation result")
            canonical(metrics)
        except BaseException as error:
            self._session.fail(job.job_id, error)
            raise
        metrics = deepcopy(metrics) | {"model_manifest_sha256": self._model_manifest_sha256}
        dispatch = self._session.complete(job.job_id, text, model_metrics=metrics)
        return PlannerRunResult(job.job_id, dispatch, deepcopy(metrics))

    def cancel(self, reason="Operator cancelled planning"):
        if self._pending is not None:
            job, future = self._pending
            self._pending = None
            try:
                self._session.cancel(job.job_id, reason)
            finally:
                future.cancel()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.cancel("Planner runner closed")
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)
