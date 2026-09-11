"""Real continuous worker, injected cameras/policies and explicit outcome fixtures."""

import json
from functools import lru_cache
from threading import Event, Thread
from types import SimpleNamespace

import numpy as np
import pytest
from test_skill_views import synthetic_export  # noqa: F401

from bimanual.dinner_control import DinnerControlWorker
from bimanual.dual_arm import CAMERAS
from bimanual.evidence import digest_file
from bimanual.live_planning import LivePlanningSession
from bimanual.planner_runner import LocalPlannerRunner
from bimanual.skill_executor import DinnerSkillExecutor
from bimanual.skill_outcomes import SkillOutcome
from bimanual.skill_registry import dinner_capability
from bimanual.skill_views import create_skill_views
from bimanual.successor_readiness import load_successor_reference
from bimanual.supervisor import StepSpec, TaskSpec
from bimanual.workflow_runner import DinnerWorkflowRunner


@pytest.fixture(scope="module")
def references(synthetic_export, tmp_path_factory):  # noqa: F811
    path = tmp_path_factory.mktemp("workflow-source") / "views.json"
    create_skill_views(synthetic_export, path)

    @lru_cache
    def load(skill):
        return load_successor_reference(synthetic_export, path, skill_id=skill)

    return load


class HeldPolicy:
    def __init__(self, skill, reference):
        self.binding = SimpleNamespace(
            view=SimpleNamespace(skill_id=skill, parent_episode_id=reference.parent_episode_id),
            dataset_root=reference.dataset_root,
        )
        self.inputs = []

    def bind_control(self, control, attempt_id, **options):
        return control.bind(attempt_id, policy_sha256="a" * 64, chunk_size=2, **options)

    def predict(self, inputs):
        self.inputs.append(inputs)
        return np.tile(inputs["observation.state"], (2, 1))


def reply(context, *, kind=None):
    skill = "handoff_transfer" if not context.completed_steps else "bar_place_and_return"
    cap = dinner_capability(skill)
    request = cap.request(
        context.observation.episode_id,
        context.observation.instruction_revision,
        context.observation.sequence,
    ).model_dump(mode="json")
    if kind:
        request.update(skill=kind, arm="none", target=None, destination=None)
    return json.dumps(
        dict(
            schema_version=2,
            request=request,
            target_visibility="uncertain" if kind else "visible",
            visible_state="uncertain" if kind else "incomplete",
            visual_explanation="Injected lifecycle fixture, not measured model quality",
        )
    ), {}


@pytest.fixture
def setup(tmp_path, references):
    skills = ("handoff_transfer", "bar_place_and_return")
    caps = [dinner_capability(skill) for skill in skills]
    captures, prepared, policies = [], [], []

    def pixels(env):
        captures.append((env.sequence, len(prepared)))
        return {camera: np.zeros((270, 480, 3), np.uint8) for camera in CAMERAS}

    # Lifecycle assertions use explicit logical time. Slow CI filesystem/model imports
    # must not accidentally turn this into a wall-clock performance benchmark.
    clock = SimpleNamespace(now=1_000_000_000)

    def clock_ns():
        clock.now += 1000
        return clock.now

    worker = DinnerControlWorker(
        tmp_path / "worker", caps, render_capture=pixels, clock_ns=clock_ns
    )
    planner = SimpleNamespace(generate=lambda context, images, **kw: reply(context))
    local = LocalPlannerRunner(LivePlanningSession(worker), planner)
    factories = {}
    for skill, cap in zip(skills, caps, strict=True):
        reference = references(skill)

        def factory(skill=skill, ref=reference):
            policy = HeldPolicy(skill, ref)
            policies.append(policy)
            executor = DinnerSkillExecutor(worker, policy, max_actions=1, successor_reference=ref)
            prepared.append(executor)
            return executor

        factories[cap.capability_id] = factory
    runner = DinnerWorkflowRunner(worker, local, factories)

    def task(identity="task", revision=0, chain=False):
        steps = [
            StepSpec(
                step_id="handoff", capability_id=caps[0].capability_id, timeout_ns=120_000_000_000
            )
        ]
        if chain:
            steps.append(
                StepSpec(
                    step_id="place",
                    capability_id=caps[1].capability_id,
                    prerequisites=("handoff",),
                    timeout_ns=120_000_000_000,
                )
            )
        return TaskSpec(
            task_id=identity,
            episode_id=worker.episode_id,
            instruction_revision=revision,
            instruction="Fixture dinner sequence",
            steps=tuple(steps),
        )

    yield SimpleNamespace(
        worker=worker,
        clock=clock,
        runner=runner,
        local=local,
        planner=planner,
        captures=captures,
        prepared=prepared,
        policies=policies,
        task=task,
    )
    runner.close()
    worker.close()


def finish_model(setup):
    setup.local._pending[1].result(timeout=3)
    return setup.runner.tick()


def fixture_success(executor, monkeypatch):
    # This isolates workflow lifecycle; never reports actual grasp/readiness quality.
    executor.max_actions = 3
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome("succeeded", "Synthetic outcome for lifecycle only", {}),
    )

    class Ready:
        def __init__(self, *a, **kw):
            pass

        def consume(self, *a):
            return SimpleNamespace(
                state="ready",
                reason="Synthetic readiness",
                report=lambda: {"state": "ready", "fixture": True},
            )

    monkeypatch.setattr("bimanual.skill_executor.SuccessorReadinessMonitor", Ready)


def test_budget_failure_replans_from_owned_boundary_and_exhausts_two_retries(setup):
    s = setup
    s.runner.start(s.task())
    env = s.worker._env
    for attempt_number in range(1, 4):
        before = env.data.time
        assert s.runner.tick().state == "planning"
        job = s.local._pending[0]
        assert job.context.retry_number == attempt_number - 1
        assert job.boundary_kind == ("ready" if attempt_number == 1 else "recovery")
        assert finish_model(s).state == "executing"
        assert env.data.time == before
        assert s.runner.tick().state == "executing"
        assert env.data.time == pytest.approx(attempt_number * 0.05)
        s.runner.tick()
    result = s.runner.tick()
    assert result.state == "failed" and result.recovery_implemented
    assert result.attempt_count == 3 and not result.completed_steps
    assert s.worker._env is env and not s.worker.recovery_available()
    assert len(s.prepared) == 3 and not s.worker.control.pending
    assert [r.attempt.number for r in s.worker.supervisor.snapshot().attempts] == [1, 2, 3]
    for _ in range(3):
        assert s.runner.tick() == result


def test_two_steps_share_worker_and_require_new_planning_and_real_supervisor_finish(
    setup, monkeypatch
):
    s = setup
    s.runner.start(s.task(chain=True))
    env = s.worker._env
    s.runner.tick()
    finish_model(s)
    fixture_success(s.prepared[-1], monkeypatch)
    s.runner.tick()
    s.runner.tick()
    assert s.worker.supervisor.snapshot().completed_steps == ("handoff",)
    assert s.runner.tick().state == "planning"
    assert finish_model(s).state == "executing"
    fixture_success(s.prepared[-1], monkeypatch)
    s.runner.tick()
    s.runner.tick()
    result = s.runner.tick()
    assert result.state == "execution_complete" and result.execution_complete
    assert result.independent_task_success is None and result.attempt_count == 2
    assert s.worker._env is env and s.worker._env.sequence == 4
    assert len(s.prepared) == 2 and not s.worker.control.pending
    assert any(e.kind == "stationary_recapture" for e in s.worker.supervisor.snapshot().events)


@pytest.mark.parametrize("kind,state", [("stop", "cancelled"), ("clarify", "needs_clarification")])
def test_visual_stop_and_clarification_apply_no_actions(setup, kind, state):
    s = setup
    s.planner.generate = lambda context, images, **kw: reply(context, kind=kind)
    s.runner.start(s.task())
    s.runner.tick()
    result = finish_model(s)
    assert result.state == state and s.worker._env.sequence == 0
    assert not result.completed_steps and not s.policies[0].inputs


def test_cancel_during_model_compute_discards_late_result(setup):
    s = setup
    entered, release = Event(), Event()

    def model(context, images, **kw):
        entered.set()
        assert release.wait(10)
        return reply(context)

    s.planner.generate = model
    try:
        s.runner.start(s.task())
        s.runner.tick()
        future = s.local._pending[1]
        assert entered.wait(2)
        assert s.runner.cancel().state == "cancelled"
        release.set()
        future.result(timeout=3)
        assert s.runner.tick().state == "cancelled"
        assert s.worker._env.sequence == 0 and not s.worker.control.pending
    finally:
        release.set()


def test_explicit_replacement_preserves_scene_and_discards_old_model_output(setup):
    s = setup
    entered, release = Event(), Event()

    def model(context, images, **kw):
        entered.set()
        assert release.wait(10)
        return reply(context)

    s.planner.generate = model
    try:
        s.runner.start(s.task())
        s.runner.tick()
        future = s.local._pending[1]
        assert entered.wait(2)
        replacement = s.task("replacement", 1)
        assert s.runner.start(replacement).state == "ready"
        release.set()
        future.result(timeout=3)
        assert s.worker.supervisor.snapshot().task == replacement and s.worker._env.active
        assert s.worker._env.sequence == 0 and not s.worker.control.pending
        s.planner.generate = lambda context, images, **kw: reply(context)
        s.runner.tick()
        assert finish_model(s).state == "executing"
        assert s.worker.supervisor.snapshot().active.task_id == "replacement"
    finally:
        release.set()


def test_external_replacement_does_not_get_cancelled_by_old_workflow(setup):
    s = setup
    s.runner.start(s.task())
    s.runner.tick()
    s.worker.supervisor.load_task(s.task("external", 1))
    assert s.runner.tick().state == "replaced"
    assert s.worker.supervisor.snapshot().state == "ready" and s.worker._env.active


@pytest.mark.parametrize("event", ["planner_poll_requested", "planner_result", "execution_result"])
def test_persistence_failure_stops_before_any_subsequent_work(setup, monkeypatch, event):
    s = setup
    s.runner.start(s.task())
    s.runner.tick()
    if event == "execution_result":
        finish_model(s)
    else:
        s.local._pending[1].result(timeout=3)
    original = s.runner._write

    def write(kind, details):
        if kind == event:
            raise OSError("Fixture disk full")
        original(kind, details)

    monkeypatch.setattr(s.runner, "_write", write)
    with pytest.raises(OSError):
        s.runner.tick()
    assert s.runner.snapshot().state == "failed"
    assert s.worker.supervisor.snapshot().active is None and not s.worker.control.pending
    count = s.worker._env.sequence
    s.runner.tick()
    assert s.worker._env.sequence == count
    assert count == (1 if event == "execution_result" else 0)


def test_executor_cannot_claim_completion_without_supervisor_outcome(setup, monkeypatch):
    s = setup
    s.runner.start(s.task())
    s.runner.tick()
    finish_model(s)
    executor = s.prepared[-1]
    monkeypatch.setattr(
        executor,
        "tick",
        lambda: SimpleNamespace(
            attempt_id=s.worker.supervisor.snapshot().active.attempt_id, state="succeeded"
        ),
    )
    with pytest.raises(ValueError, match="canonical supervisor termination"):
        s.runner.tick()
    assert (
        s.runner.snapshot().state == "failed" and not s.worker.supervisor.snapshot().completed_steps
    )


def test_cross_thread_calls_rejected_and_no_model_work_started(setup):
    errors = []

    def other():
        try:
            setup.runner.tick()
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = Thread(target=other)
    thread.start()
    thread.join()
    assert errors and not setup.prepared and not setup.captures


def test_genuine_sealed_reference_uses_export_body_seal_not_json_file_hash(setup):
    s = setup
    s.runner.start(s.task())
    s.runner.tick()
    reference = s.prepared[0]._reference
    path = reference.dataset_root / "export_manifest.json"
    assert reference.export_manifest_sha256 == json.loads(path.read_text())["manifest_sha256"]
    assert reference.export_manifest_sha256 != digest_file(path)
    # The previous executor comparison falsely rejected this real sealed fixture.
    assert finish_model(s).state == "executing"


def test_invalid_replacement_preserves_existing_task_and_pending_planner(setup):
    s = setup
    original = s.task()
    s.runner.start(original)
    s.runner.tick()
    with pytest.raises(ValueError, match="new task ID"):
        s.runner.start(original)
    assert s.worker.supervisor.snapshot().task == original
    assert s.runner.snapshot().state == "planning" and s.local._pending is not None
    assert s.worker._env.active


def test_wrong_policy_factory_rejected_before_camera_capture(setup):
    s = setup
    cap = dinner_capability("handoff_transfer").capability_id
    other = dinner_capability("bar_place_and_return").capability_id
    from types import MappingProxyType

    s.runner.executors = MappingProxyType({cap: s.runner.executors[other]})
    s.runner.start(s.task())
    with pytest.raises(ValueError, match="registered capability"):
        s.runner.tick()
    assert not s.captures and s.worker._env.sequence == 0


@pytest.mark.parametrize("action", ["cancel", "replace", "stop"])
def test_recovery_boundary_is_revoked_by_authority_change(setup, action):
    s = setup
    s.runner.start(s.task())
    s.runner.tick()
    finish_model(s)
    s.runner.tick()
    s.runner.tick()
    assert s.worker.recovery_available()
    sequence = s.worker._env.sequence
    if action == "cancel":
        s.runner.cancel()
    elif action == "replace":
        s.worker.supervisor.load_task(s.task(identity="replacement", revision=1))
    else:
        s.worker._env.stop()
    assert not s.worker.recovery_available()
    assert s.worker._env.sequence == sequence


def test_deliberately_stale_dispatch_capture_still_stops_execution(setup):
    s = setup
    s.runner.start(s.task())
    s.runner.tick()
    finish_model(s)
    s.clock.now += 2_000_000_001
    with pytest.raises(ValueError, match="fresh camera capture"):
        s.runner.tick()
    assert s.worker._env.sequence == 0
    assert not s.worker._env.active
    assert s.runner.snapshot().state == "failed"
