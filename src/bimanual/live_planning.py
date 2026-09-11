"""Owned-pause planning lifecycle; model execution happens outside the worker actor."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from bimanual.contracts import Contract, Counter, Digest, Identifier, Observation, SkillRequest
from bimanual.dinner_control import DinnerControlWorker
from bimanual.evidence import canonical, digest_file
from bimanual.planner import PlannerContext, VisualProposal, camera_images, parse_proposal
from bimanual.supervisor import Attempt


class PlanningJob(Contract):
    job_id: Identifier
    pause_id: Identifier
    worker_generation: Identifier
    state_sha256: Digest
    model_sha256: Digest
    task_sha256: Digest
    created_ns: Counter
    deadline_ns: Counter
    camera_source: str = Field(min_length=1)
    warmup_observation: Observation
    context: PlannerContext


@dataclass(frozen=True)
class PlanningResult:
    job_id: str
    original_proposal: VisualProposal
    execution_observation: Observation
    attempt: Attempt | None
    supervisor_state: str
    revalidation_path: Path


class LivePlanningSession:
    """Single-actor orchestration, not a thread-safe executor or model quality claim.

    Call begin/images on the serialized worker, submit immutable context/images
    to an external model executor, and deliver its text to complete on that same
    actor. Do not run blocking model generation on the actor: cancellation and
    task replacement must remain responsive. No torch/model imports are needed.
    Only the existing 480px policy camera profile is supported by this bridge.
    Each begin records one fixed warm-up capture before the model context, even
    when the renderer already exists. This initializes cold rendering without
    hiding captures, changing physics, or relaxing subsequent pixel equality.
    """

    def __init__(self, worker: DinnerControlWorker, *, max_planning_ns: int = 300_000_000_000):
        if type(max_planning_ns) is not int or max_planning_ns <= 0:
            raise ValueError("Planning timeout must be a positive integer")
        self.worker = worker
        self.max_planning_ns = max_planning_ns
        self.directory = worker.directory / "planning"
        self.directory.mkdir(exist_ok=True)
        self._jobs: dict[str, tuple[PlanningJob, str]] = {}
        self._states: dict[str, str] = {}

    def _write(self, job_id: str, filename: str, payload) -> Path:
        path = self.directory / job_id / filename
        with path.open("xb") as stream:
            stream.write(canonical(payload))
        return path

    def _pending(self, job_id: str) -> PlanningJob:
        if job_id not in self._jobs or self._states[job_id] != "pending":
            raise RuntimeError("Unknown, cancelled, completed, or already consumed planning job")
        return self._jobs[job_id][0]

    def _release(self, job: PlanningJob):
        try:
            self.worker.release_planning_pause(job.pause_id)
        except RuntimeError:
            pass  # Cancellation/worker close may already have revoked this exact lease.

    def _check_job(self, job: PlanningJob):
        if self.worker._clock() >= job.deadline_ns:
            raise TimeoutError("Planning job expired; no execution authorized")
        if digest_file(self.directory / job.job_id / "job.json") != self._jobs[job.job_id][1]:
            raise ValueError("Immutable original planning context changed")
        pause = self.worker.check_planning_pause(job.pause_id)
        if any(
            pause[name] != getattr(job, name)
            for name in ("worker_generation", "state_sha256", "model_sha256", "task_sha256")
        ):
            raise ValueError("Original planning provenance no longer matches the worker")
        if self.worker._clock() >= job.deadline_ns:
            raise TimeoutError("Planning job expired during provenance verification")

    def check_pending(self, job_id: str) -> PlanningJob:
        """Poll authority while model computation continues outside the actor."""
        job = self._pending(job_id)
        try:
            self._check_job(job)
        except (Exception, KeyboardInterrupt) as error:
            self.fail(job_id, error)
            raise
        return job

    def begin(self) -> PlanningJob:
        pause = self.worker.acquire_planning_pause()
        try:
            warmup = self.worker.capture_planning_pause(pause["pause_id"])
            observation = self.worker.capture_planning_pause(pause["pause_id"])
            snapshot = self.worker.supervisor.snapshot()
            context = PlannerContext(
                observation=observation,
                instruction=snapshot.task.instruction,
                completed_steps=snapshot.completed_steps,
                available_skills=tuple(
                    sorted({c.skill for c in self.worker.supervisor.registry.values()})
                ),
            )
            now = self.worker._clock()
            job = PlanningJob(
                job_id=uuid.uuid4().hex,
                pause_id=pause["pause_id"],
                worker_generation=pause["worker_generation"],
                state_sha256=pause["state_sha256"],
                model_sha256=pause["model_sha256"],
                task_sha256=pause["task_sha256"],
                camera_source=pause["camera_source"],
                warmup_observation=warmup,
                created_ns=now,
                deadline_ns=now + self.max_planning_ns,
                context=context,
            )
            (self.directory / job.job_id).mkdir()
            path = self._write(job.job_id, "job.json", job.model_dump(mode="json"))
            self._jobs[job.job_id] = (job, digest_file(path))
            self._states[job.job_id] = "pending"
            return job
        except BaseException:
            self.worker.release_planning_pause(pause["pause_id"])
            raise

    def images(self, job_id: str):
        """Verified copies of the original camera pixels for external model generation."""
        job = self.check_pending(job_id)
        return camera_images(job.context, self.worker.directory)

    def cancel(self, job_id: str, reason: str = "Operator cancelled planning"):
        job = self._pending(job_id)
        self._states[job_id] = "cancelled"
        try:
            self.worker.check_planning_pause(job.pause_id)
        except (ValueError, RuntimeError, InterruptedError):
            self._release(job)  # A late old job must not cancel the replacement task.
        else:
            self.worker.cancel(reason)
        self._write(job_id, "cancelled.json", {"reason": reason, "at_ns": self.worker._clock()})

    def fail(self, job_id: str, error: BaseException):
        """Job/model failure ends authority without manufacturing an executor result."""
        job = self._pending(job_id)
        self._states[job_id] = "rejected"
        self._release(job)
        self._write(
            job_id,
            "model-error.json",
            {
                "error": f"{type(error).__name__}: {error}",
                "at_ns": self.worker._clock(),
                "manipulation_success": None,
            },
        )

    def complete(
        self, job_id: str, raw_model_text: str, *, model_metrics: dict | None = None
    ) -> PlanningResult:
        job = self._pending(job_id)
        self._states[job_id] = "completing"  # Every completion is single-use, including errors.
        attempt = None
        try:
            self._write(
                job_id,
                "model-response.json",
                {
                    "text": raw_model_text,
                    "received_ns": self.worker._clock(),
                    "model_metrics": model_metrics,
                },
            )
            self._check_job(job)
            proposal = parse_proposal(raw_model_text, job.context)
            camera_images(job.context, self.worker.directory)  # Verify original artifacts again.
            current = self.worker.capture_planning_pause(job.pause_id)
            original = job.context.observation
            if (
                current.episode_id != original.episode_id
                or current.instruction_revision != original.instruction_revision
                or current.sequence != original.sequence
                or current.simulation_seconds != original.simulation_seconds
                or current.joint_position_rad != original.joint_position_rad
                or current.joint_velocity_rad_s != original.joint_velocity_rad_s
                or current.observed_monotonic_ns <= original.observed_monotonic_ns
                or any(
                    a.camera != b.camera
                    or a.artifact.sha256 != b.artifact.sha256
                    or a.artifact.path == b.artifact.path
                    for a, b in zip(current.frames, original.frames, strict=True)
                )
            ):
                raise ValueError("Live recapture did not preserve unchanged paused sensor content")
            # This is a distinct worker-issued request, never relabeled model output.
            request = SkillRequest.model_validate(
                proposal.request.model_dump()
                | {
                    "episode_id": current.episode_id,
                    "instruction_revision": current.instruction_revision,
                    "observation_sequence": current.sequence,
                }
            )
            revalidation = {
                "schema_version": 1,
                "authority": "worker_pause_revalidation",
                "job_id": job_id,
                "pause_id": job.pause_id,
                "original_context_sha256": self._jobs[job_id][1],
                "original_proposal": proposal.model_dump(mode="json"),
                "original_observation": original.model_dump(mode="json"),
                "fresh_observation": current.model_dump(mode="json"),
                "execution_request": request.model_dump(mode="json"),
                "worker_generation": job.worker_generation,
                "state_sha256": job.state_sha256,
                "model_sha256": job.model_sha256,
                "task_sha256": job.task_sha256,
                "camera_source": job.camera_source,
                "camera_profile": job.context.camera_profile,
                "revalidated_ns": self.worker._clock(),
                "manipulation_success": None,
                "interpretation": (
                    "Unchanged paused scene; fresh capture authorizes dispatch checks, "
                    "not task success"
                ),
            }
            revalidation["sha256"] = hashlib.sha256(canonical(revalidation)).hexdigest()
            path = self._write(job_id, "revalidation.json", revalidation)
            self._check_job(job)  # Rendering and durable writes consume real wall time.
            attempt = self.worker.dispatch_planning_pause(
                job.pause_id, current, proposal=request, planning_deadline_ns=job.deadline_ns
            )
            state = self.worker.supervisor.snapshot().state
            self._write(
                job_id,
                "dispatch.json",
                {
                    "attempt": attempt.model_dump(mode="json") if attempt else None,
                    "supervisor_state": state,
                    "at_ns": self.worker._clock(),
                    "manipulation_success": None,
                },
            )
            self._states[job_id] = "completed"
            return PlanningResult(job_id, proposal, current, attempt, state, path)
        except (Exception, KeyboardInterrupt) as error:
            self._states[job_id] = "rejected"
            self._release(job)
            if attempt is not None:
                active = self.worker.supervisor.snapshot().active
                if active is not None and active.attempt_id == attempt.attempt_id:
                    try:
                        self.worker.finish(
                            attempt.attempt_id,
                            current,
                            executor_outcome="failed",
                            reason=f"Planning dispatch evidence failed: {error}"[:2048],
                        )
                    except (Exception, KeyboardInterrupt):
                        active = self.worker.supervisor.snapshot().active
                        if active is not None and active.attempt_id == attempt.attempt_id:
                            self.worker.cancel("Planning dispatch evidence failed")
            self._write(
                job_id,
                "rejected.json",
                {
                    "error": f"{type(error).__name__}: {error}",
                    "at_ns": self.worker._clock(),
                    "manipulation_success": None,
                },
            )
            raise
