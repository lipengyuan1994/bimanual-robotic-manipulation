"""Single local workflow job ownership; finished execution is not task success."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bimanual.evidence import EvidenceStore, canonical
from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process

_PROFILE = "operator_job_journal_v1"
_MAX_RECORD_BYTES = 16_384
_MAX_POINTER_BYTES = 1_024
_MAX_RECORDS = 10_000
_STATES = Literal[
    "active",
    "stopping",
    "finished",
    "failed",
    "cancelled",
    "needs_clarification",
    "recovery_required",
]


@dataclass(frozen=True)
class OperatorJob:
    job_id: str
    state: _STATES
    instruction: str
    run_id: str | None = None
    run_outcome: str | None = None
    error: str | None = None
    independent_task_success: None = None
    progress: dict | None = None

    def report(self) -> dict:
        return asdict(self)


class _JournalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1
    profile: Literal["operator_job_journal_v1"] = _PROFILE
    record_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    created_at: str = Field(min_length=1, max_length=64)
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    state: _STATES
    instruction: str = Field(min_length=1, max_length=4096)
    run_id: str | None = Field(default=None, max_length=128)
    run_outcome: str | None = Field(default=None, max_length=128)
    error: str | None = Field(default=None, max_length=4096)
    previous_record_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_record(self):
        body = self.model_dump(mode="json", exclude={"record_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.record_sha256:
            raise ValueError("Operator job record seal mismatch")
        paired = self.run_id is not None and self.run_outcome is not None
        if (self.run_id is None) != (self.run_outcome is None):
            raise ValueError("Operator run identity and outcome must be paired")
        if self.state in {"active", "stopping", "recovery_required"} and paired:
            raise ValueError("Nonterminal operator state cannot claim a run identity")
        if self.state in {"finished", "cancelled", "needs_clarification"} and not paired:
            raise ValueError("Verified terminal operator state requires a run identity")
        return self


def _read_regular_json(path: Path, *, limit: int) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Operator state must be a regular file")
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Operator state is oversized")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Operator state must be an object")
    canonical(value)
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _replace_pointer(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        _write_once(temporary, value)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class OperatorJobs:
    """Server-owned settings; callers can submit instructions and stop their job.

    The background thread owns the existing bounded process runner. Stop requests
    are acknowledged as stopping until that runner returns and its evidence is
    verified. Closing permanently prevents new work. A small durable journal makes
    an interrupted prior owner visible after restart; it never resumes that work.
    """

    def __init__(
        self,
        config: WorkflowProcessConfig,
        *,
        store: EvidenceStore,
        project_root: Path,
        _runner=run_workflow_process,
    ):
        self._config = WorkflowProcessConfig.model_validate(config.model_dump())
        self._store = store
        self._root = project_root.resolve()
        self._runner = _runner
        self._lock = Lock()
        self._job: OperatorJob | None = None
        self._thread: Thread | None = None
        self._cancel: Event | None = None
        self._closed = False
        self._journal_root = self._store.root / "operator-jobs"
        self._records = self._journal_root / "records"
        self._pointer = self._journal_root / "current.json"
        self._record_sha256: str | None = None
        self._journal_error: str | None = None
        self._restore()

    def _prepare_journal(self) -> None:
        for path in (self._journal_root, self._records):
            if path.is_symlink():
                raise ValueError("Operator journal directory cannot be a symlink")
            path.mkdir(parents=True, exist_ok=True)
            if not path.is_dir() or not path.resolve().is_relative_to(self._store.root):
                raise ValueError("Operator journal escapes the evidence root")

    def _load_current(self) -> _JournalRecord | None:
        self._prepare_journal()
        if not self._pointer.exists() and not self._pointer.is_symlink():
            if any(self._records.iterdir()):
                raise ValueError("Operator records exist without a current pointer")
            return None
        pointer = _read_regular_json(self._pointer, limit=_MAX_POINTER_BYTES)
        if (
            set(pointer) != {"profile", "record_id", "record_sha256"}
            or pointer.get("profile") != _PROFILE
        ):
            raise ValueError("Operator current pointer is invalid")
        record_id = pointer.get("record_id")
        if (
            not isinstance(record_id, str)
            or len(record_id) != 32
            or any(value not in "0123456789abcdef" for value in record_id)
        ):
            raise ValueError("Invalid operator record id")
        paths = list(self._records.iterdir())
        if len(paths) > _MAX_RECORDS:
            raise ValueError("Operator journal has too many records")
        records: dict[str, _JournalRecord] = {}
        by_sha256: dict[str, _JournalRecord] = {}
        for path in paths:
            if path.is_symlink() or path.suffix != ".json":
                raise ValueError("Operator journal contains an invalid record path")
            candidate = _JournalRecord.model_validate(
                _read_regular_json(path, limit=_MAX_RECORD_BYTES)
            )
            if path.name != f"{candidate.record_id}.json" or candidate.record_id in records:
                raise ValueError("Operator record identity is invalid or duplicated")
            if candidate.record_sha256 in by_sha256:
                raise ValueError("Operator record seal is duplicated")
            records[candidate.record_id] = candidate
            by_sha256[candidate.record_sha256] = candidate
        record = records.get(record_id)
        if record is None:
            raise ValueError("Operator current record is missing")
        if record.record_id != record_id or pointer.get("record_sha256") != record.record_sha256:
            raise ValueError("Operator pointer and record identity disagree")
        visited: set[str] = set()
        cursor = record
        while True:
            if cursor.record_sha256 in visited:
                raise ValueError("Operator journal chain contains a cycle")
            visited.add(cursor.record_sha256)
            previous = cursor.previous_record_sha256
            if previous is None:
                break
            cursor = by_sha256.get(previous)
            if cursor is None:
                raise ValueError("Operator journal chain has a missing predecessor")
        if len(visited) != len(records):
            raise ValueError("Operator journal contains orphaned records")
        self._record_sha256 = record.record_sha256
        return record

    @staticmethod
    def _job_from_record(record: _JournalRecord) -> OperatorJob:
        return OperatorJob(
            job_id=record.job_id,
            state=record.state,
            instruction=record.instruction,
            run_id=record.run_id,
            run_outcome=record.run_outcome,
            error=record.error,
        )

    def _restore(self) -> None:
        try:
            record = self._load_current()
            if record is None:
                return
            job = self._job_from_record(record)
            if record.run_id is not None:
                verified = self._store.verify(record.run_id)
                if (
                    verified.kind != "dinner_workflow_process"
                    or verified.outcome != record.run_outcome
                ):
                    raise ValueError("Recorded operator run identity is not verified")
            if job.state in {"active", "stopping"}:
                job = replace(
                    job,
                    state="recovery_required",
                    error=(
                        "Operator server restarted before the workflow result was verified; "
                        "inspect evidence before starting a replacement."
                    ),
                )
                self._publish(job)
            self._job = job
        except (OSError, ValueError, RuntimeError) as error:
            self._journal_error = f"{type(error).__name__}: {error}"
            self._job = OperatorJob(
                "0" * 32,
                "recovery_required",
                "Operator journal unavailable",
                error="Operator journal is invalid or unavailable; repair it before starting work.",
            )

    def _publish(self, job: OperatorJob) -> None:
        self._prepare_journal()
        record_id = uuid4().hex
        fields = {
            "schema_version": 1,
            "profile": _PROFILE,
            "record_id": record_id,
            "created_at": datetime.now(UTC).isoformat(),
            "job_id": job.job_id,
            "state": job.state,
            "instruction": job.instruction,
            "run_id": job.run_id,
            "run_outcome": job.run_outcome,
            "error": job.error,
            "previous_record_sha256": self._record_sha256,
        }
        record = _JournalRecord.model_validate(
            fields | {"record_sha256": hashlib.sha256(canonical(fields)).hexdigest()}
        )
        _write_once(self._records / f"{record_id}.json", record.model_dump(mode="json"))
        _replace_pointer(
            self._pointer,
            {
                "profile": _PROFILE,
                "record_id": record.record_id,
                "record_sha256": record.record_sha256,
            },
        )
        self._record_sha256 = record.record_sha256

    def snapshot(self) -> OperatorJob | None:
        with self._lock:
            return self._job

    def start(self, instruction: str) -> OperatorJob:
        # Validate through the execution contract rather than bypassing model_copy.
        data = self._config.model_dump()
        data["execution"]["instruction"] = instruction
        config = WorkflowProcessConfig.model_validate(data)
        with self._lock:
            if self._closed:
                raise RuntimeError("Operator controller is closed")
            if self._journal_error is not None:
                raise RuntimeError("Operator journal requires recovery")
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("A workflow job is already active")
            event = Event()
            job = OperatorJob(uuid4().hex, "active", config.execution.instruction)
            thread = Thread(
                target=self._execute,
                args=(job, config, event),
                name=f"bimanual-operator-{job.job_id}",
                daemon=False,
            )
            self._publish(job)
            self._job, self._cancel, self._thread = job, event, thread
            try:
                thread.start()
            except BaseException:
                self._thread, self._cancel = None, None
                self._job = replace(job, state="failed", error="Could not start workflow job")
                self._publish(self._job)
                raise
            return job

    def stop(self, job_id: str) -> OperatorJob:
        with self._lock:
            if self._job is None or self._job.job_id != job_id:
                raise KeyError("No matching operator job")
            if self._job.state in {"active", "stopping"}:
                self._cancel.set()
                self._job = replace(self._job, state="stopping")
                self._publish(self._job)
            return self._job

    def _execute(self, job: OperatorJob, config: WorkflowProcessConfig, event: Event):
        def progress(value):
            with self._lock:
                if self._job is not None and self._job.job_id == job.job_id:
                    self._job = replace(self._job, progress=value)

        try:
            result = self._runner(
                config,
                store=self._store,
                project_root=self._root,
                cancelled=event.is_set,
                on_progress=progress,
            )
            verified = self._store.verify(result.run_id)
            if verified != result or result.kind != "dinner_workflow_process":
                raise ValueError("Unverified workflow process result")
            states = {
                "completed": "finished",
                "cancelled": "cancelled",
                "failed": "failed",
                "timed_out": "failed",
                "needs_clarification": "needs_clarification",
                "recovery_required": "failed",
                "replaced": "cancelled",
                "closed": "cancelled",
            }
            if result.outcome not in states:
                raise ValueError("Unsupported workflow process outcome")
            # A late stop cannot erase completed evidence or invent a cancelled run.
            state = states[result.outcome]
            reason = None
            if state in {"failed", "needs_clarification"}:
                reason = "Workflow time limit reached; inspect the recorded run before retrying."
                if result.outcome != "timed_out":
                    reason = next(
                        (
                            value[:2048]
                            for key in ("error", "child_verification_error", "child_reason")
                            if isinstance(value := result.metrics.get(key), str) and value.strip()
                        ),
                        "Workflow did not complete. Inspect the recorded run for details.",
                    )
            final = replace(
                job, state=state, run_id=result.run_id, run_outcome=result.outcome, error=reason
            )
        except BaseException as error:
            final = replace(job, state="failed", error=f"{type(error).__name__}: {error}")
        with self._lock:
            final = replace(final, progress=self._job.progress)
            try:
                self._publish(final)
            except BaseException as error:
                self._journal_error = f"{type(error).__name__}: {error}"
                final = replace(
                    job,
                    state="recovery_required",
                    error=(
                        "Workflow returned but its terminal operator record could not "
                        "be persisted; "
                        "inspect evidence before retrying."
                    ),
                    progress=final.progress,
                )
            self._job = final

    def close(self, timeout: float | None = None) -> None:
        with self._lock:
            self._closed = True
            thread = self._thread
            if self._job is not None and self._job.state in {"active", "stopping"}:
                self._cancel.set()
                self._job = replace(self._job, state="stopping")
                self._publish(self._job)
        if thread is not None:
            if timeout is None:
                timeout = (
                    self._config.cancellation_grace_seconds
                    # Guardian cancellation, then possible group exit and lease release.
                    + 4 * self._config.terminate_grace_seconds
                    + 10
                )
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("Workflow is still stopping; shutdown is not confirmed")
