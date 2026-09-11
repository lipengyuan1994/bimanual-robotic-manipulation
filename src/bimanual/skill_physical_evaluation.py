"""Sealed, teacher-prepared physical evaluation for one learned dinner skill."""

from __future__ import annotations

import platform
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bimanual.contracts import Digest
from bimanual.dataset_export import CAMERA_FEATURES
from bimanual.dinner_control import DinnerControlWorker
from bimanual.evidence import EvidenceStore, Manifest, canonical, provenance
from bimanual.skill_executor import DinnerSkillExecutor
from bimanual.skill_policy import DinnerSkillPolicy
from bimanual.skill_registry import dinner_capability
from bimanual.skill_views import INTERVALS_V2
from bimanual.successor_readiness import load_successor_reference
from bimanual.supervisor import StepSpec, TaskSpec
from bimanual.teacher_prefix import TeacherPreparedDinnerControlWorker, load_teacher_prefix
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease

SKILLS = tuple(row[0] for row in INTERVALS_V2)


class SkillPhysicalEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    training_run: Path
    dataset_root: Path
    skill_views_path: Path
    skill_id: Literal[*SKILLS]
    device: Literal["cpu", "mps"] = "mps"
    max_actions: int = Field(default=2000, strict=True, ge=1, le=20000)
    execute_chunk_steps: int = Field(default=2, strict=True, ge=1, le=100)
    wall_timeout_seconds: float = Field(default=1200, gt=0, le=86400)
    evaluation_protocol_sha256: Digest | None = None
    evaluation_protocol_file_sha256: Digest | None = None

    @model_validator(mode="after")
    def paired_protocol_binding(self):
        if (self.evaluation_protocol_sha256 is None) != (
            self.evaluation_protocol_file_sha256 is None
        ):
            raise ValueError("Evaluation protocol body and file seals must be supplied together")
        return self


def _resolve(config: SkillPhysicalEvaluationConfig, root: Path) -> SkillPhysicalEvaluationConfig:
    return config.model_copy(
        update={
            "training_run": (root / config.training_run).resolve(),
            "dataset_root": (root / config.dataset_root).resolve(),
            "skill_views_path": (root / config.skill_views_path).resolve(),
        }
    )


def _confine(config: SkillPhysicalEvaluationConfig, evidence_root: Path) -> None:
    if any(
        evidence_root.resolve().is_relative_to(source)
        for source in (config.training_run, config.dataset_root, config.skill_views_path)
    ):
        raise ValueError("Evaluation evidence must be outside immutable checkpoint/dataset sources")


def _passes(result, *, final: bool) -> bool:
    return bool(
        result.state == "succeeded"
        and result.physical_success
        and (result.final_parking_ready if final else result.successor_ready)
    )


def run_skill_physical_evaluation(
    config: SkillPhysicalEvaluationConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
    model_job_lease: WorkerLease | None = None,
    model_job_lease_path: Path | None = None,
) -> Manifest:
    """Evaluate one learned skill after a real, explicitly disclosed teacher prefix.

    The teacher stops at the selected skill's frozen start boundary.  Every action
    after that boundary comes from the checkpoint.  This provides component-level
    evidence only; it cannot qualify the autonomous seven-skill workflow.
    """

    config = SkillPhysicalEvaluationConfig.model_validate(config.model_dump(mode="json"))
    project_root = Path(project_root).resolve()
    config = _resolve(config, project_root)
    _confine(config, store.root)
    store.root.mkdir(parents=True, exist_ok=True)
    expected_lease_path = (
        Path(model_job_lease_path).resolve()
        if model_job_lease_path is not None
        else (store.root / MODEL_JOB_LEASE).resolve()
    )
    owned = model_job_lease is None
    lease = model_job_lease or WorkerLease.acquire(expected_lease_path)
    directory = None
    worker: DinnerControlWorker | None = None
    try:
        lease.assert_path(expected_lease_path)
        directory = store.new_run()
        source = provenance(project_root)
        started = time.monotonic()
        final = config.skill_id == SKILLS[-1]
        metrics = {
            "state": "initializing",
            "skill_id": config.skill_id,
            "physical_success": False,
            "successor_ready": None if final else False,
            "final_parking_ready": False if final else None,
            "component_passed": False,
            "teacher_actions_used": None,
            "teacher_prefix_actions": None,
            "autonomous_skill_actions": 0,
            "independent_task_success": None,
            "autonomous_workflow_success": None,
            "release_qualified": False,
            "requested_device": config.device,
            "actual_policy_devices": None,
        }
        error_text = None
        try:
            if cancelled():
                raise InterruptedError("Evaluation cancelled before source verification")
            if platform.system() == "Darwin" and platform.machine() != "arm64":
                raise RuntimeError("Local evaluation requires native ARM64 Python")
            prefix = load_teacher_prefix(
                config.dataset_root, config.skill_views_path, skill_id=config.skill_id
            )
            reference = load_successor_reference(
                config.dataset_root,
                config.skill_views_path,
                skill_id=config.skill_id,
                final_parking=final,
            )
            metrics.update(
                teacher_actions_used=prefix.action_count > 0,
                teacher_prefix_actions=prefix.action_count,
                teacher_prefix_sha256=prefix.prefix_sha256,
                successor_reference_sha256=reference.reference_sha256,
            )
            (directory / "teacher-prefix.json").write_bytes(canonical(prefix.report()))
            (directory / "successor-reference.json").write_bytes(canonical(reference.report()))
            if cancelled():
                raise InterruptedError("Evaluation cancelled before policy load")
            policy = DinnerSkillPolicy(
                config.training_run,
                skill_id=config.skill_id,
                dataset_root=config.dataset_root,
                device=config.device,
            )
            devices = sorted({str(parameter.device) for parameter in policy._policy.parameters()})
            metrics["actual_policy_devices"] = devices
            if config.device == "mps" and devices not in (["mps"], ["mps:0"]):
                raise RuntimeError("MPS evaluation did not load the policy on MPS")
            (directory / "checkpoint-binding.json").write_bytes(canonical(policy.binding.report()))
            dummy = {"observation.state": np.zeros(12, dtype=np.float32)}
            dummy.update(
                {
                    name: np.zeros((3, 270, 480), dtype=np.float32)
                    for name in CAMERA_FEATURES.values()
                }
            )
            metrics["warmup_shape"] = list(policy.predict(dummy).shape)
            if cancelled() or time.monotonic() - started >= config.wall_timeout_seconds:
                raise TimeoutError("Evaluation stopped before physical worker initialization")
            index = SKILLS.index(config.skill_id)
            current = dinner_capability(config.skill_id)
            registry = [current]
            steps = [
                StepSpec(
                    step_id=config.skill_id,
                    capability_id=current.capability_id,
                    timeout_ns=int(config.wall_timeout_seconds * 1e9),
                    max_retries=0,
                )
            ]
            if not final:
                successor = dinner_capability(SKILLS[index + 1])
                registry.append(successor)
                steps.append(
                    StepSpec(
                        step_id=SKILLS[index + 1],
                        capability_id=successor.capability_id,
                        prerequisites=(config.skill_id,),
                        max_retries=0,
                    )
                )
            worker = TeacherPreparedDinnerControlWorker(
                directory / "worker",
                registry,
                prefix=prefix,
                cancelled=lambda: (
                    cancelled() or time.monotonic() - started >= config.wall_timeout_seconds
                ),
            )
            worker.supervisor.load_task(
                TaskSpec(
                    task_id=directory.name,
                    episode_id=worker.episode_id,
                    instruction_revision=0,
                    instruction=(
                        f"Teacher-prepared component evaluation for {config.skill_id}; "
                        "only checkpoint actions run after the frozen start boundary."
                    ),
                    steps=tuple(steps),
                )
            )
            observation = worker.capture()
            attempt = worker.supervisor.dispatch(observation)
            executor = DinnerSkillExecutor(
                worker,
                policy,
                max_actions=config.max_actions,
                successor_reference=reference,
            )
            executor.start(
                attempt.attempt_id,
                observation,
                execute_chunk_steps=config.execute_chunk_steps,
            )
            result = executor.tick()
            while result.state == "pending":
                if cancelled():
                    raise InterruptedError("Evaluation cancelled during learned execution")
                if time.monotonic() - started >= config.wall_timeout_seconds:
                    raise TimeoutError("Physical evaluation wall budget exceeded")
                result = executor.tick()
                (directory / "latest-result.json").write_bytes(canonical(asdict(result)))
            passed = _passes(result, final=final)
            metrics.update(asdict(result))
            metrics.update(
                state="completed" if passed else "failed",
                component_passed=passed,
                autonomous_skill_actions=result.applied_actions,
            )
            policy.binding.reverify()
            prefix.reverify()
            reference.reverify()
        except (Exception, KeyboardInterrupt) as error:
            error_text = traceback.format_exc()
            metrics.update(
                state="cancelled"
                if isinstance(error, (InterruptedError, KeyboardInterrupt))
                else "timed_out"
                if isinstance(error, TimeoutError)
                else "failed",
                error=f"{type(error).__name__}: {error}",
                component_passed=False,
            )
        finally:
            if worker is not None:
                try:
                    worker.close()
                except (Exception, KeyboardInterrupt) as cleanup:
                    metrics.update(
                        state="failed",
                        component_passed=False,
                        cleanup_error=f"{type(cleanup).__name__}: {cleanup}",
                    )
            metrics["wall_seconds"] = time.monotonic() - started
        if error_text is not None:
            (directory / "error.txt").write_text(error_text)
        (directory / "metrics.json").write_bytes(canonical(metrics))
        return store.seal(
            directory,
            kind="learned_skill_teacher_prepared_physical_evaluation",
            outcome="completed" if metrics["component_passed"] else metrics["state"],
            config=config.model_dump(mode="json"),
            metrics=metrics,
            source=source,
            claims=(
                ["One teacher-prepared authored-scene skill passed physical and readiness checks"]
                if metrics["component_passed"]
                else []
            ),
        )
    finally:
        if owned:
            lease.close()
