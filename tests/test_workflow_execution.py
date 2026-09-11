"""Orchestration fixtures only: no model, camera, or manipulation quality claim."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bimanual.workflow_execution as execution
from bimanual.evidence import EvidenceStore, canonical
from bimanual.skill_registry import dinner_capability
from bimanual.workflow_manifest import SKILLS
from bimanual.workflow_runner import WorkflowSnapshot


@pytest.fixture
def harness(monkeypatch, tmp_path):
    calls = []
    state = SimpleNamespace(
        terminal="needs_clarification",
        false_complete=False,
        error=None,
        close_error=False,
        worker=None,
    )
    config = execution.WorkflowExecutionConfig(
        workflow_manifest="cohort.json",
        planner_model_directory="qwen",
        instruction="Set the dinner table",
    )
    bindings = tuple(
        SimpleNamespace(
            view=SimpleNamespace(skill_id=skill),
            capability=dinner_capability(skill),
            dataset_root=tmp_path / "dataset",
            training_run=tmp_path / "training" / skill,
        )
        for skill in SKILLS
    )

    class Verified:
        def __init__(self):
            self.bindings = bindings
            self.manifest = SimpleNamespace(
                execution=tuple(
                    SimpleNamespace(
                        skill_id=skill,
                        model_dump=lambda skill=skill, **kwargs: {"skill_id": skill},
                    )
                    for skill in SKILLS
                ),
                execution_profile_sha256="e" * 64,
            )

        def report(self):
            return {"fixture": True, "skills": list(SKILLS)}

        def reverify(self):
            calls.append("reverify")
            return self

    def verify(path):
        calls.append("verify_cohort")
        return Verified()

    def verify_model(path):
        calls.append("verify_planner")
        return {"fixture": True}

    class Loaded:
        def executor_factories(self, worker, **kwargs):
            calls.append("factories")
            state.factory_options = kwargs
            return {
                cap.capability_id: lambda: None
                for cap in (dinner_capability(skill) for skill in SKILLS)
            }

    def preload(verified, *, device):
        calls.append("preload_policy")
        state.policy_device = device
        return Loaded()

    class Planner:
        def __init__(self, path, *, device):
            calls.append("preload_planner")
            self.manifest = {"fixture": True}
            state.planner_device = device

    class Worker:
        def __init__(self, directory, registry, **kwargs):
            calls.append("worker")
            directory.mkdir()
            self.directory, self.episode_id = directory, "same_episode"
            self.registry = tuple(registry)
            self.current = SimpleNamespace(state="idle", task=None, active=None, completed_steps=())
            self.current.model_dump = lambda **kwargs: {
                "state": self.current.state,
                "task": self.current.task.model_dump(mode="json") if self.current.task else None,
                "active": self.current.active,
                "completed_steps": self.current.completed_steps,
                "attempts": [],
                "events": [],
            }
            self.supervisor = SimpleNamespace(snapshot=lambda: self.current)
            (directory / "worker.json").write_bytes(
                canonical(
                    {
                        "teacher_schedule_used": False,
                        "instrumentation": execution.DINNER_WORKER_INSTRUMENTATION,
                    }
                )
            )
            state.worker = self

        def cancel(self, reason):
            calls.append("worker_cancel")
            self.current.state = "cancelled"

        def close(self):
            calls.append("worker_close")
            (self.directory / "closed.json").write_text('{"closed":true}')
            if state.close_error:
                raise RuntimeError("fixture close failed")

    class Session:
        def __init__(self, worker, **kwargs):
            calls.append("session")
            self.worker = worker
            state.session_options = kwargs

    class PlannerRunner:
        def __init__(self, session, planner, **kwargs):
            calls.append("planner_runner")
            self._pending = None
            state.planner_options = kwargs

        def close(self):
            calls.append("planner_close")

    class Workflow:
        def __init__(self, worker, runner, factories):
            calls.append("workflow")
            self.worker = worker

        def start(self, task):
            calls.append("start")
            state.task = task
            self.worker.current.task = task
            return self.snapshot("ready")

        def snapshot(self, current):
            return WorkflowSnapshot(
                "workflow",
                state.task.task_id,
                current,
                "fixture",
                current,
                SKILLS if current == "execution_complete" else (),
                0,
                None,
                None,
                current == "execution_complete",
            )

        def tick(self):
            calls.append("tick")
            if state.error:
                raise state.error
            if state.terminal == "execution_complete" and not state.false_complete:
                self.worker.current.state = "execution_complete"
                self.worker.current.completed_steps = SKILLS
            return self.snapshot(state.terminal)

        def cancel(self, reason):
            calls.append("workflow_cancel")
            self.worker.cancel(reason)

        def close(self):
            calls.append("workflow_close")

    def build_step_report(directory):
        calls.append("step_report")
        return SimpleNamespace(
            profile="fixture_step_report_v1",
            attempt_count=0,
            successful_attempts=0,
            failed_attempts=0,
            total_applied_actions=0,
            model_dump=lambda **kwargs: {
                "profile": "fixture_step_report_v1",
                "attempt_count": 0,
                "attempts": [],
                "independent_task_success": None,
            },
        )

    for name, value in dict(
        load_workflow_manifest=verify,
        verify_model=verify_model,
        preload_workflow=preload,
        LocalQwenPlanner=Planner,
        DinnerControlWorker=Worker,
        LivePlanningSession=Session,
        LocalPlannerRunner=PlannerRunner,
        DinnerWorkflowRunner=Workflow,
        build_workflow_step_report=build_step_report,
    ).items():
        monkeypatch.setattr(execution, name, value)
    store = EvidenceStore(tmp_path / "evidence")

    def run(**kwargs):
        result = execution.run_workflow_execution(
            config, store=store, project_root=tmp_path, **kwargs
        )
        assert store.verify(result.run_id) == result
        return result

    return SimpleNamespace(
        calls=calls, state=state, config=config, run=run, store=store, root=tmp_path
    )


def test_load_order_canonical_task_and_terminal_clarification(harness):
    h = harness
    result = h.run()
    assert h.calls[:7] == [
        "verify_cohort",
        "verify_planner",
        "preload_policy",
        "preload_planner",
        "reverify",
        "worker",
        "session",
    ]
    task = h.state.task
    assert task.episode_id == "same_episode" and task.instruction == h.config.instruction
    assert tuple(step.step_id for step in task.steps) == SKILLS
    assert all(step.max_retries == 2 for step in task.steps)
    assert all(step.timeout_ns == 300_000_000_000 for step in task.steps)
    assert [step.prerequisites for step in task.steps] == [()] + [(skill,) for skill in SKILLS[:-1]]
    assert h.state.factory_options == {}
    assert h.state.planner_options == {"max_tokens": 384}
    assert result.outcome == "needs_clarification"
    assert result.metrics["independent_task_success"] is None
    assert result.claims == []
    assert "worker/closed.json" in result.files
    assert h.calls[-4:] == ["workflow_close", "planner_close", "worker_close", "step_report"]


@pytest.mark.parametrize(
    "terminal",
    ["execution_complete", "cancelled", "replaced", "recovery_required", "failed", "closed"],
)
def test_preserves_terminal_state_without_quality_claim(harness, terminal):
    harness.state.terminal = terminal
    result = harness.run()
    assert result.outcome == ("completed" if terminal == "execution_complete" else terminal)
    assert result.metrics["execution_complete"] is (terminal == "execution_complete")
    assert result.metrics["independent_task_success"] is None


def test_false_completion_rejected_against_supervisor(harness):
    harness.state.terminal = "execution_complete"
    harness.state.false_complete = True
    result = harness.run()
    assert result.outcome == "failed" and not result.metrics["execution_complete"]
    assert "contradicts" in result.metrics["reason"]
    assert "worker_cancel" in harness.calls


@pytest.mark.parametrize(
    "where", ["load_workflow_manifest", "verify_model", "preload_workflow", "LocalQwenPlanner"]
)
def test_verification_and_preload_failures_sealed_without_worker(harness, monkeypatch, where):
    def fail(*args, **kwargs):
        raise ValueError("fixture setup failed")

    monkeypatch.setattr(execution, where, fail)
    result = harness.run()
    assert result.outcome == "failed" and "worker" not in harness.calls
    assert "error.txt" in result.files
    if where in {"load_workflow_manifest", "verify_model"}:
        assert "preload_policy" not in harness.calls and "preload_planner" not in harness.calls


def test_keyboard_interrupt_cancels_and_closes(harness):
    harness.state.error = KeyboardInterrupt()
    result = harness.run()
    assert result.outcome == "cancelled"
    assert "workflow_cancel" in harness.calls and "worker_cancel" in harness.calls
    assert harness.calls[-4:] == ["workflow_close", "planner_close", "worker_close", "step_report"]


def test_cancellation_before_any_loading_is_retained(harness):
    result = harness.run(cancelled=lambda: True)
    assert result.outcome == "cancelled" and harness.calls == []


def test_cleanup_error_cannot_report_complete(harness):
    harness.state.terminal = "execution_complete"
    harness.state.close_error = True
    result = harness.run()
    assert result.outcome == "failed" and not result.metrics["execution_complete"]
    assert result.metrics["state_before_cleanup_failure"] == "execution_complete"
    assert "worker.close" in result.metrics["cleanup_errors"][0]


def test_final_supervisor_write_failure_cannot_report_complete(harness, monkeypatch):
    harness.state.terminal = "execution_complete"
    original = Path.write_bytes

    def reject(path, data):
        if path.name == "final-supervisor.json":
            raise OSError("Injected final evidence failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", reject)
    result = harness.run()
    assert result.outcome == "failed" and result.claims == []
    assert "final_supervisor" in result.metrics["cleanup_errors"][0]


def test_step_report_failure_cannot_report_complete(harness, monkeypatch):
    harness.state.terminal = "execution_complete"

    def reject(directory):
        raise ValueError("Injected contradictory step evidence")

    monkeypatch.setattr(execution, "build_workflow_step_report", reject)
    result = harness.run()
    assert result.outcome == "failed" and not result.metrics["execution_complete"]
    assert result.metrics["state_before_cleanup_failure"] == "execution_complete"
    assert "step_report: ValueError" in result.metrics["cleanup_errors"][0]
    assert result.claims == []


def test_records_loaded_parameter_devices_without_guessing_from_request(harness, monkeypatch):
    original_loader = execution.preload_workflow
    original_planner = execution.LocalQwenPlanner

    def load(*args, **kwargs):
        loaded = original_loader(*args, **kwargs)
        loaded.policies = {
            skill: SimpleNamespace(
                _policy=SimpleNamespace(parameters=lambda: [SimpleNamespace(device="cpu")])
            )
            for skill in SKILLS
        }
        return loaded

    class Planner(original_planner):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.model = SimpleNamespace(parameters=lambda: [SimpleNamespace(device="cpu")])

    monkeypatch.setattr(execution, "preload_workflow", load)
    monkeypatch.setattr(execution, "LocalQwenPlanner", Planner)
    result = harness.run()
    assert result.metrics["actual_policy_devices"] == {skill: ["cpu"] for skill in SKILLS}
    assert result.metrics["actual_planner_device"] == ["cpu"]


def test_event_write_failure_prevents_model_loading(harness, monkeypatch):
    original = Path.open

    def reject(path, *args, **kwargs):
        if path.name == "execution-events.jsonl":
            raise OSError("Injected event persistence failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject)
    result = harness.run()
    assert result.outcome == "failed"
    assert "preload_policy" not in harness.calls and "worker" not in harness.calls


def test_overall_deadline_crossed_during_tick_discards_completion(harness, monkeypatch):
    h = harness
    h.state.terminal = "execution_complete"
    monkeypatch.setattr(execution.time, "monotonic", lambda: 2000.0 if "tick" in h.calls else 0.0)
    result = h.run()
    assert result.outcome == "timed_out" and not result.metrics["execution_complete"]
    assert "worker_cancel" in h.calls


def test_cohort_identity_mismatch_rejected_before_models(harness, monkeypatch):
    original = execution.load_workflow_manifest

    def wrong(path):
        value = original(path)
        value.bindings = tuple(reversed(value.bindings))
        return value

    monkeypatch.setattr(execution, "load_workflow_manifest", wrong)
    result = harness.run()
    assert result.outcome == "failed" and harness.calls == ["verify_cohort"]


def test_legacy_cohort_without_execution_profile_rejected_before_models(harness, monkeypatch):
    original = execution.load_workflow_manifest

    def legacy(path):
        value = original(path)
        value.manifest = SimpleNamespace(execution=None)
        return value

    monkeypatch.setattr(execution, "load_workflow_manifest", legacy)
    result = harness.run()
    assert result.outcome == "failed" and harness.calls == ["verify_cohort"]
    assert "execution profile" in result.metrics["reason"]


def test_task_file_and_events_are_part_of_the_seal(harness):
    result = harness.run()
    directory = harness.store.directory(result.run_id)
    task = json.loads((directory / "task.json").read_text())
    assert task["episode_id"] == result.metrics["episode_id"]
    assert {
        "execution-events.jsonl",
        "task.json",
        "workflow-snapshot.json",
        "cohort.json",
        "execution-profile.json",
        "planner-model.json",
        "step-report.json",
    } <= result.files.keys()
    assert result.metrics["execution_profile_sha256"] == "e" * 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_tokens", 0),
        ("wall_timeout_seconds", float("inf")),
        ("planner_device", "cuda"),
        ("instruction", ""),
        ("camera_profile", "unknown"),
    ],
)
def test_invalid_config_rejected(field, value):
    values = dict(workflow_manifest="cohort", planner_model_directory="model", instruction="Dinner")
    values[field] = value
    with pytest.raises(ValueError):
        execution.WorkflowExecutionConfig(**values)


@pytest.mark.parametrize(
    "relative_store",
    [
        "dataset",
        "dataset/nested/evidence",
        "corrections/evidence",
        "training/handoff_transfer",
        "training/handoff_transfer/checkpoint/evidence",
    ],
)
def test_immutable_source_store_rejected_before_any_output(harness, relative_store):
    h = harness
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
    if relative_store.startswith("corrections/"):
        body["profile"] = "dinner_development_workflow_v2"
        body["checkpoints"][0].update(
            corrective_dataset_root="corrections", corrective_export_file_sha256="e" * 64
        )
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    execution.WorkflowManifest.model_validate(body)
    (h.root / "cohort.json").write_bytes(canonical(body))
    source = h.root / relative_store
    source.mkdir(parents=True)
    (source / "keep.txt").write_text("immutable original")
    before = {
        path.relative_to(h.root).as_posix(): path.read_bytes()
        for path in h.root.rglob("*")
        if path.is_file()
    }
    directories = {
        path.relative_to(h.root).as_posix() for path in h.root.rglob("*") if path.is_dir()
    }
    with pytest.raises(ValueError, match="outside immutable cohort"):
        execution.run_workflow_execution(h.config, store=EvidenceStore(source), project_root=h.root)
    after = {
        path.relative_to(h.root).as_posix(): path.read_bytes()
        for path in h.root.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert directories == {
        path.relative_to(h.root).as_posix() for path in h.root.rglob("*") if path.is_dir()
    }
    assert h.calls == []  # Full verification and model loading were never entered.


@pytest.mark.parametrize("contents", [None, b"not a manifest"])
def test_unreadable_or_malformed_manifest_failure_retained_in_safe_store(
    harness, monkeypatch, contents
):
    from bimanual.workflow_manifest import load_workflow_manifest

    if contents is not None:
        (harness.root / "cohort.json").write_bytes(contents)
    monkeypatch.setattr(execution, "load_workflow_manifest", load_workflow_manifest)
    result = harness.run()
    assert result.outcome == "failed" and "error.txt" in result.files
    assert harness.calls == []


@pytest.mark.parametrize("late_cancel", [False, True, "revoke"])
def test_real_worker_planning_clarification_or_late_text_cannot_mutate_seal(
    harness, monkeypatch, late_cancel
):
    from threading import Event

    import numpy as np

    from bimanual.dinner_control import DinnerControlWorker
    from bimanual.dual_arm import CAMERAS
    from bimanual.live_planning import LivePlanningSession
    from bimanual.planner_runner import LocalPlannerRunner
    from bimanual.skill_executor import DinnerSkillExecutor
    from bimanual.workflow_runner import DinnerWorkflowRunner

    entered, release, finished = Event(), Event(), Event()
    workers = []

    def worker_factory(*args, **kwargs):
        worker = DinnerControlWorker(
            *args,
            **kwargs,
            render_capture=lambda env: {
                name: np.zeros((270, 480, 3), dtype=np.uint8) for name in CAMERAS
            },
        )
        workers.append(worker)
        return worker

    class Planner:
        manifest = {"fixture": True}

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, context, images, **kwargs):
            assert len(images) == 3
            entered.set()
            if late_cancel:
                assert release.wait(5)
            observed = context.observation
            text = json.dumps(
                dict(
                    schema_version=2,
                    request=dict(
                        episode_id=observed.episode_id,
                        instruction_revision=observed.instruction_revision,
                        observation_sequence=observed.sequence,
                        skill="clarify",
                        arm="none",
                        target=None,
                        destination=None,
                        explanation="Injected fixture needs clarification",
                    ),
                    target_visibility="uncertain",
                    visible_state="uncertain",
                    visual_explanation="Injected pixels and text; no model quality evidence",
                )
            )
            finished.set()
            return text, {"fixture": True}

    class Loaded:
        def executor_factories(self, worker, **kwargs):
            def fixture(skill):
                # The unstarted executor fixture is never asked to predict or score.
                # It lets the real runner exercise planning before choosing abstention.
                executor = object.__new__(DinnerSkillExecutor)
                executor.worker = worker
                executor.policy = SimpleNamespace(
                    binding=SimpleNamespace(view=SimpleNamespace(skill_id=skill))
                )
                executor._attempt = None
                return executor

            return {
                dinner_capability(skill).capability_id: lambda skill=skill: fixture(skill)
                for skill in SKILLS
            }

    class RevokingRunner(LocalPlannerRunner):
        def poll(self):
            if entered.is_set() and self._pending is not None:

                def reject(job_id):
                    self._session.cancel(job_id, "Injected pending-job revocation")
                    raise ValueError("Injected pending-job revocation")

                self._session.check_pending = reject
            return super().poll()

    for name, value in dict(
        DinnerControlWorker=worker_factory,
        LivePlanningSession=LivePlanningSession,
        LocalPlannerRunner=RevokingRunner if late_cancel == "revoke" else LocalPlannerRunner,
        DinnerWorkflowRunner=DinnerWorkflowRunner,
        LocalQwenPlanner=Planner,
        preload_workflow=lambda *args, **kwargs: Loaded(),
    ).items():
        monkeypatch.setattr(execution, name, value)
    try:
        result = harness.run(cancelled=lambda: late_cancel is True and entered.is_set())
        assert result.outcome == (
            "failed"
            if late_cancel == "revoke"
            else "cancelled"
            if late_cancel
            else "needs_clarification"
        )
        assert not result.metrics["execution_complete"]
        assert workers[0]._applied == 0 and workers[0]._closed
        assert "worker/summary.json" in result.files
        assert "final-supervisor.json" in result.files
        if late_cancel:
            assert result.metrics["background_text_generation_may_continue"]
            release.set()
            assert finished.wait(2)
            # There is no done callback writing a response into the sealed run.
            assert harness.store.verify(result.run_id) == result
            assert not any(name.endswith("model-response.json") for name in result.files)
        else:
            assert any(name.endswith("revalidation.json") for name in result.files)
    finally:
        release.set()
