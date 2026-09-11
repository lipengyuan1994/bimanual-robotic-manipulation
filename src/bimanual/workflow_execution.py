"""Supported continuous development workflow; execution is not an independent score."""

from __future__ import annotations

import json
import platform
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bimanual.dinner_control import DinnerControlWorker
from bimanual.evidence import EvidenceStore, Manifest, canonical, provenance
from bimanual.live_planning import LivePlanningSession
from bimanual.planner import LocalQwenPlanner, verify_model
from bimanual.planner_runner import LocalPlannerRunner
from bimanual.skill_registry import dinner_capability
from bimanual.supervisor import StepSpec, TaskSpec
from bimanual.workflow_manifest import (
    SKILLS,
    WorkflowManifest,
    load_workflow_manifest,
    preload_workflow,
)
from bimanual.workflow_progress import write_snapshot
from bimanual.workflow_runner import DinnerWorkflowRunner

TERMINAL_STATES = frozenset(
    {
        "execution_complete",
        "failed",
        "cancelled",
        "replaced",
        "needs_clarification",
        "recovery_required",
        "closed",
    }
)


class WorkflowExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    workflow_manifest: Path
    planner_model_directory: Path
    instruction: str = Field(min_length=1, max_length=4096)
    policy_device: Literal["cpu", "mps"] = "cpu"
    planner_device: Literal["cpu", "mps"] = "cpu"
    camera_profile: Literal["policy480_v1", "overhead1920_wrist480_v1"] = "policy480_v1"
    wall_timeout_seconds: float = Field(default=1800, gt=0, le=86400)
    step_timeout_seconds: float = Field(default=300, gt=0, le=86400)
    max_actions_per_skill: int = Field(default=2000, strict=True, ge=1, le=100000)
    max_tokens: int = Field(default=384, strict=True, ge=1, le=1024)

    @model_validator(mode="after")
    def timeout_bounds(self):
        if self.step_timeout_seconds > self.wall_timeout_seconds:
            raise ValueError("Step timeout cannot exceed overall wall timeout")
        return self


class _WallDeadline(Exception):
    pass


class _Cancelled(Exception):
    pass


def run_workflow_execution(
    config: WorkflowExecutionConfig,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
) -> Manifest:
    """Run on the caller's single owning thread, preserving every terminal outcome.

    Cancellation/deadlines are cooperative between blocking loads, captures and
    control ticks. They do not kill model kernels. After cancellation an already
    running text generator may finish; it owns copied inputs, never worker files,
    and no callback polls or dispatches it after the run is sealed.
    """
    project_root = Path(project_root).resolve()
    config = config.model_copy(
        update={
            "workflow_manifest": (project_root / config.workflow_manifest).resolve(),
            "planner_model_directory": (project_root / config.planner_model_directory).resolve(),
        }
    )
    if store.root.is_relative_to(config.planner_model_directory):
        raise ValueError("Evidence store must be outside the immutable planner model")
    # Inspect the self-sealed declaration before allocating any output. Full
    # source verification can fail (or be invalidated by our own writes) when an
    # output store is nested inside a dataset/training run. Ordinary missing or
    # malformed manifests still receive failure evidence in the requested store.
    try:
        declared = WorkflowManifest.model_validate_json(config.workflow_manifest.read_bytes())
    except (OSError, ValueError):
        declared = None
    if declared is not None:
        base = config.workflow_manifest.parent
        source_roots = [(base / declared.dataset_root).resolve()] + [
            (base / checkpoint.training_run).resolve() for checkpoint in declared.checkpoints
        ]
        if any(store.root.is_relative_to(path) for path in source_roots):
            raise ValueError("Evidence store must be outside immutable cohort sources")
    directory = store.new_run()
    started, source = time.monotonic(), provenance(project_root)
    deadline = started + config.wall_timeout_seconds
    worker = planner_runner = workflow = None
    generation_futures = []
    task = None
    error_text = None
    metrics = dict(
        state="initializing",
        execution_complete=False,
        independent_task_success=None,
        release_available=False,
        requested_policy_device=config.policy_device,
        requested_planner_device=config.planner_device,
        actual_policy_devices=None,
        actual_planner_device=None,
        timeout_semantics="cooperative_between_blocking_operations_including_preload",
        background_text_generation_may_continue=False,
        cleanup_errors=[],
    )

    def check():
        if cancelled():
            raise _Cancelled("Operator cancelled workflow")
        if time.monotonic() >= deadline:
            raise _WallDeadline("Overall cooperative wall deadline exceeded")

    def event(kind, **details):
        with (directory / "execution-events.jsonl").open("ab") as stream:
            stream.write(
                canonical(dict(event=kind, elapsed_seconds=time.monotonic() - started, **details))
                + b"\n"
            )
            stream.flush()

    def remember(snapshot):
        report = json.loads(canonical(asdict(snapshot)))
        if report["independent_task_success"] is not None:
            raise ValueError("Workflow orchestration cannot supply independent task success")
        write_snapshot(directory / "workflow-snapshot.json", report)
        metrics.update(state=snapshot.state, reason=snapshot.reason, workflow=report)

    def remember_generation():
        if planner_runner is not None and planner_runner._pending is not None:
            future = planner_runner._pending[1]
            if all(future is not seen for seen in generation_futures):
                generation_futures.append(future)

    try:
        (directory / "config.json").write_bytes(canonical(config.model_dump(mode="json")))
        check()
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            raise RuntimeError("Native ARM64 Python is required for local execution")
        # Both manifests must verify before any heavyweight model initialization.
        verified = load_workflow_manifest(config.workflow_manifest)
        registry = tuple(dinner_capability(skill) for skill in SKILLS)
        if (
            tuple(binding.view.skill_id for binding in verified.bindings) != SKILLS
            or tuple(binding.capability for binding in verified.bindings) != registry
        ):
            raise ValueError("Cohort does not match the canonical seven-step dinner workflow")
        for binding in verified.bindings:
            if any(
                store.root.is_relative_to(path)
                for path in (binding.dataset_root, binding.training_run)
            ):
                raise ValueError("Evidence store must be outside immutable cohort sources")
        (directory / "cohort.json").write_bytes(canonical(verified.report()))
        model_manifest = verify_model(config.planner_model_directory)
        (directory / "planner-model.json").write_bytes(canonical(model_manifest))
        check()
        event("sources_verified")
        loaded = preload_workflow(verified, device=config.policy_device)
        if hasattr(loaded, "policies"):
            metrics["actual_policy_devices"] = {
                skill: sorted({str(parameter.device) for parameter in policy._policy.parameters()})
                for skill, policy in loaded.policies.items()
            }
        check()
        event("policy_cohort_loaded")
        planner = LocalQwenPlanner(config.planner_model_directory, device=config.planner_device)
        if hasattr(planner, "model"):
            metrics["actual_planner_device"] = sorted(
                {str(parameter.device) for parameter in planner.model.parameters()}
            )
        if planner.manifest != model_manifest:
            raise ValueError("Planner manifest changed during preload")
        check()
        # Long model loads cannot silently invalidate the pinned cohort.
        verified.reverify()
        check()
        event("models_loaded_before_worker")
        worker = DinnerControlWorker(directory / "worker", registry, cancelled=cancelled)
        metrics["episode_id"] = worker.episode_id
        check()
        session = LivePlanningSession(
            worker,
            camera_profile=config.camera_profile,
            max_planning_ns=max(1, int(min(300, deadline - time.monotonic()) * 1e9)),
        )
        planner_runner = LocalPlannerRunner(session, planner, max_tokens=config.max_tokens)
        factories = loaded.executor_factories(worker, max_actions=config.max_actions_per_skill)
        workflow = DinnerWorkflowRunner(worker, planner_runner, factories)
        task = TaskSpec(
            task_id=directory.name,
            episode_id=worker.episode_id,
            instruction_revision=0,
            instruction=config.instruction,
            steps=tuple(
                StepSpec(
                    step_id=skill,
                    capability_id=capability.capability_id,
                    prerequisites=() if index == 0 else (SKILLS[index - 1],),
                    timeout_ns=max(1, int(config.step_timeout_seconds * 1e9)),
                    max_retries=2,
                )
                for index, (skill, capability) in enumerate(zip(SKILLS, registry, strict=True))
            ),
        )
        (directory / "task.json").write_bytes(canonical(task.model_dump(mode="json")))
        check()
        snapshot = workflow.start(task)
        remember(snapshot)
        while snapshot.state not in TERMINAL_STATES:
            check()
            remember_generation()
            snapshot = workflow.tick()
            remember_generation()
            # A blocking tick can overrun the deadline even when it reports completion.
            check()
            remember(snapshot)
            if snapshot.state == "planning":
                time.sleep(0.01)
        current = worker.supervisor.snapshot()
        if snapshot.state == "execution_complete":
            if (
                not snapshot.execution_complete
                or current.state != "execution_complete"
                or current.task != task
                or current.active is not None
                or tuple(current.completed_steps) != SKILLS
            ):
                raise ValueError("Workflow completion contradicts canonical supervisor evidence")
            metrics["execution_complete"] = True
        event("terminal", state=metrics["state"])
    except (Exception, KeyboardInterrupt) as error:
        remember_generation()
        error_text = traceback.format_exc()
        metrics.update(
            state="cancelled"
            if isinstance(error, (KeyboardInterrupt, _Cancelled))
            else "timed_out"
            if isinstance(error, _WallDeadline)
            else "failed",
            reason=f"{type(error).__name__}: {error}",
            execution_complete=False,
        )
        if workflow is not None:
            try:
                workflow.cancel(metrics["reason"][:2048])
            except (Exception, KeyboardInterrupt) as cleanup:
                metrics["cleanup_errors"].append(
                    f"workflow.cancel: {type(cleanup).__name__}: {cleanup}"
                )
        if worker is not None:
            try:
                worker.cancel(metrics["reason"][:2048])
            except (Exception, KeyboardInterrupt) as cleanup:
                metrics["cleanup_errors"].append(
                    f"worker.cancel: {type(cleanup).__name__}: {cleanup}"
                )
    finally:
        remember_generation()
        # Finish every artifact writer before sealing, even if another close fails.
        for name, resource in (
            ("workflow", workflow),
            ("planner_runner", planner_runner),
            ("worker", worker),
        ):
            if resource is not None:
                try:
                    resource.close()
                except (Exception, KeyboardInterrupt) as cleanup:
                    metrics["cleanup_errors"].append(
                        f"{name}.close: {type(cleanup).__name__}: {cleanup}"
                    )
        if worker is not None:
            try:
                (directory / "final-supervisor.json").write_bytes(
                    canonical(worker.supervisor.snapshot().model_dump(mode="json"))
                )
            except (Exception, KeyboardInterrupt) as cleanup:
                metrics["cleanup_errors"].append(
                    f"final_supervisor: {type(cleanup).__name__}: {cleanup}"
                )
        if metrics["cleanup_errors"]:
            metrics["state_before_cleanup_failure"] = metrics["state"]
            metrics.update(state="failed", execution_complete=False)
        metrics["background_text_generation_may_continue"] = any(
            not future.done() for future in generation_futures
        )
        metrics["total_seconds"] = time.monotonic() - started
    if error_text is not None:
        (directory / "error.txt").write_text(error_text)
    (directory / "metrics.json").write_bytes(canonical(metrics))
    return store.seal(
        directory,
        kind="dinner_workflow_execution",
        outcome="completed" if metrics["execution_complete"] else metrics["state"],
        config=config.model_dump(mode="json"),
        metrics=metrics,
        source=source,
        claims=["All seven supervised execution steps completed; independent task scoring not run"]
        if metrics["execution_complete"]
        else [],
    )
