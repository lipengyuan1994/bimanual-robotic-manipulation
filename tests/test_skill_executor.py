from types import SimpleNamespace

import numpy as np
import pytest

from bimanual.dinner_control import DinnerControlWorker
from bimanual.dual_arm import CAMERAS
from bimanual.skill_executor import DinnerSkillExecutor
from bimanual.skill_registry import dinner_capability
from bimanual.supervisor import StepSpec, TaskSpec


class FixturePolicy:
    """Held joints only; this fixture is not a learned policy or successful grasp."""

    def __init__(self):
        self.binding = SimpleNamespace(view=SimpleNamespace(skill_id="handoff_transfer"))
        self.inputs = []

    def bind_control(self, control, attempt_id, **options):
        return control.bind(attempt_id, policy_sha256="a" * 64, chunk_size=2, **options)

    def predict(self, inputs):
        self.inputs.append(inputs)
        return np.tile(inputs["observation.state"], (2, 1))


@pytest.fixture
def setup(tmp_path, request):
    capability = dinner_capability("handoff_transfer")
    worker = DinnerControlWorker(
        tmp_path / "worker",
        [capability],
        render_capture=lambda env: {name: np.zeros((270, 480, 3), np.uint8) for name in CAMERAS},
    )
    worker.supervisor.load_task(
        TaskSpec(
            task_id="test",
            episode_id=worker.episode_id,
            instruction_revision=0,
            instruction="Fixture handoff",
            steps=(StepSpec(step_id="transfer", capability_id=capability.capability_id),),
        )
    )
    observation = worker.capture()
    attempt = worker.supervisor.dispatch(observation)
    policy = FixturePolicy()
    options = getattr(request, "param", {})
    configured_prefix = options.get("configured_execute_chunk_steps")
    executor = DinnerSkillExecutor(
        worker,
        policy,
        max_actions=options.get("max_actions", 1),
        **({"execute_chunk_steps": configured_prefix} if configured_prefix is not None else {}),
    )
    start_options = (
        {}
        if configured_prefix is not None
        else {"execute_chunk_steps": options.get("execute_chunk_steps", 1)}
    )
    executor.start(attempt.attempt_id, observation, **start_options)
    assert executor._monitor.max_actions == executor.max_actions + 1
    yield worker, executor, policy
    worker.close()


def test_real_step_remains_pending_and_budget_is_not_success(setup):
    worker, executor, policy = setup
    first = executor.tick()
    assert first.state == "pending" and first.applied_actions == 1
    assert worker._env.data.time == pytest.approx(0.05)
    assert set(policy.inputs[0]) == {
        "observation.state",
        "observation.images.overhead",
        "observation.images.left_wrist",
        "observation.images.right_wrist",
    }
    last = executor.tick()
    assert last.state == "failed" and "budget" in last.reason
    assert worker.supervisor.snapshot().completed_steps == ()
    assert not worker.control.pending
    assert executor.tick() == last
    assert len(policy.inputs) == 1


def test_cancellation_prevents_any_later_inference_or_action(setup):
    worker, executor, policy = setup
    worker.cancel("Operator stop")
    assert executor.tick().state == "failed"
    assert not policy.inputs and worker._env.data.time == 0
    assert worker.supervisor.snapshot().state == "cancelled"


def test_invalid_model_output_fails_attempt_without_physics(setup):
    worker, executor, policy = setup
    policy.predict = lambda inputs: np.full((2, 12), np.nan)
    with pytest.raises(ValueError):
        executor.tick()
    assert worker._env.data.time == 0
    assert worker.supervisor.snapshot().completed_steps == ()
    assert not worker.control.pending


def test_missing_physical_rows_cannot_report_success(setup, monkeypatch):
    worker, executor, _ = setup
    monkeypatch.setattr(executor, "_rows", lambda: [])
    result = executor.tick()
    assert result.state == "failed"
    assert worker.supervisor.snapshot().completed_steps == ()


def test_replacement_task_is_not_cancelled_by_old_executor(setup):
    worker, executor, policy = setup
    task = worker.supervisor.snapshot().task.model_copy(
        update={"task_id": "replacement", "instruction_revision": 1}
    )
    worker.supervisor.load_task(task)
    assert executor.tick().state == "failed"
    assert worker.supervisor.snapshot().state == "ready"
    assert worker.supervisor.snapshot().task.task_id == "replacement"
    assert not policy.inputs


def test_executor_is_single_attempt(setup):
    worker, executor, _ = setup
    active = worker.supervisor.snapshot().active
    with pytest.raises(RuntimeError, match="single-attempt"):
        executor.start(active.attempt_id, worker.capture())


def test_start_recaptures_after_slow_preflight_validation(tmp_path):
    capability = dinner_capability("handoff_transfer")
    worker = DinnerControlWorker(
        tmp_path / "worker",
        [capability],
        render_capture=lambda env: {name: np.zeros((270, 480, 3), np.uint8) for name in CAMERAS},
    )
    try:
        worker.supervisor.load_task(
            TaskSpec(
                task_id="recapture",
                episode_id=worker.episode_id,
                instruction_revision=0,
                instruction="Recapture before the physical policy boundary",
                steps=(StepSpec(step_id="transfer", capability_id=capability.capability_id),),
            )
        )
        original = worker.capture()
        attempt = worker.supervisor.dispatch(original)
        worker._clock = lambda: original.observed_monotonic_ns + 3_000_000_000
        worker.supervisor._clock = worker._clock
        executor = DinnerSkillExecutor(worker, FixturePolicy(), max_actions=1)
        executor.start(attempt.attempt_id, original)
        assert executor._next_observation.observed_monotonic_ns > original.observed_monotonic_ns
    finally:
        worker.close()


def test_cancellation_during_prediction_revokes_returned_forecast(setup):
    worker, executor, policy = setup

    def cancelled_prediction(inputs):
        worker.cancel("Stop during inference")
        return np.tile(inputs["observation.state"], (2, 1))

    policy.predict = cancelled_prediction
    with pytest.raises((ValueError, RuntimeError, InterruptedError)):
        executor.tick()
    assert worker._env.data.time == 0
    assert not worker.control.pending
    assert worker.supervisor.snapshot().state == "cancelled"


def test_prediction_that_outlives_camera_freshness_applies_no_action(setup):
    worker, executor, policy = setup
    original_clock = worker._clock

    def delayed_prediction(inputs):
        worker._clock = lambda: original_clock() + 3_000_000_000
        return np.tile(inputs["observation.state"], (2, 1))

    policy.predict = delayed_prediction
    with pytest.raises(ValueError, match="fresh"):
        executor.tick()
    assert worker._env.data.time == 0
    assert not worker.control.pending
    assert worker.supervisor.snapshot().completed_steps == ()


def test_terminal_monitor_result_finishes_only_after_confirmed_step(setup, monkeypatch):
    from bimanual.skill_outcomes import SkillOutcome

    worker, executor, policy = setup
    # Explicit monitor seam tests lifecycle only, not a one-step physical handoff.
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome(
            "succeeded",
            "Test monitor result, not physical task evidence",
            {"physics_rows": len(rows)},
        ),
    )
    result = executor.tick()
    assert result.state == "succeeded" and result.applied_actions == 1
    assert worker.supervisor.snapshot().completed_steps == ("transfer",)
    assert worker._terminal_observation.sequence == 1
    assert not worker.control.pending
    assert executor.tick() == result and len(policy.inputs) == 1


def test_record_failure_before_finish_cannot_advance_task(setup, monkeypatch):
    from bimanual.skill_outcomes import SkillOutcome

    worker, executor, _ = setup
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome("succeeded", "Fixture result", {}),
    )
    original = executor._write

    def failing_record(event, details):
        if event == "termination_requested":
            raise OSError("Injected full disk")
        return original(event, details)

    monkeypatch.setattr(executor, "_write", failing_record)
    with pytest.raises(OSError):
        executor.tick()
    assert worker.supervisor.snapshot().completed_steps == ()
    assert not worker.control.pending


def test_chained_attempt_requires_reference_before_binding(setup):
    worker, _, policy = setup
    old = worker.supervisor.snapshot().task
    first = old.steps[0]
    replacement = old.model_copy(
        update={
            "task_id": "chained",
            "instruction_revision": 1,
            "steps": (
                first,
                StepSpec(
                    step_id="next",
                    capability_id=first.capability_id,
                    prerequisites=(first.step_id,),
                ),
            ),
        }
    )
    worker.supervisor.load_task(replacement)
    observation = worker.capture()
    attempt = worker.supervisor.dispatch(observation)
    executor = DinnerSkillExecutor(worker, policy)
    with pytest.raises(ValueError, match="successor-readiness reference"):
        executor.start(attempt.attempt_id, observation)
    assert worker.control.binding is None
    assert worker._env.data.time == 0


def test_physical_milestone_keeps_same_attempt_until_readiness(setup, monkeypatch):
    import bimanual.skill_executor as module
    from bimanual.skill_outcomes import SkillOutcome

    worker, executor, policy = setup
    executor.max_actions = 4
    executor._reference = SimpleNamespace(
        final_parking=False
    )  # Explicit gate seam; no fabricated runtime reference.
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome("succeeded", "Fixture physical milestone", {}),
    )

    class Gate:
        def __init__(self, *args, **kwargs):
            self.count = 0

        def consume(self, action, rows, observation):
            self.count += 1
            assert len(rows) == 50 and observation.sequence == action["observation_sequence"] + 1
            state = "ready" if self.count == 2 else "pending"
            return SimpleNamespace(
                state=state, reason="Fixture readiness", report=lambda: {"state": state}
            )

    monkeypatch.setattr(module, "SuccessorReadinessMonitor", Gate)
    first = executor.tick()
    assert first.state == "pending" and first.physical_success and first.successor_ready is False
    assert worker.supervisor.snapshot().active is not None
    assert worker.supervisor.snapshot().completed_steps == ()
    monkeypatch.setattr(
        executor._monitor, "consume", lambda *a: pytest.fail("Terminal physical monitor reused")
    )
    assert executor.tick().state == "pending"
    final = executor.tick()
    assert final.state == "succeeded" and final.physical_success and final.successor_ready
    assert final.applied_actions == 3 and len(policy.inputs) == 3
    assert worker.supervisor.snapshot().completed_steps == ("transfer",)
    assert not worker.control.pending


def test_readiness_failure_preserves_physical_milestone(setup, monkeypatch):
    import bimanual.skill_executor as module
    from bimanual.skill_outcomes import SkillOutcome

    worker, executor, _ = setup
    executor.max_actions = 3
    executor._reference = SimpleNamespace(final_parking=False)
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome("succeeded", "Fixture physical milestone", {}),
    )
    gate = SimpleNamespace(
        consume=lambda *a: SimpleNamespace(
            state="failed", reason="Fixture lost support", report=lambda: {"state": "failed"}
        )
    )
    monkeypatch.setattr(module, "SuccessorReadinessMonitor", lambda *a, **kw: gate)
    executor.tick()
    final = executor.tick()
    assert final.state == "failed" and final.physical_success and final.successor_ready is False
    assert worker.supervisor.snapshot().completed_steps == ()
    assert not worker.control.pending


def test_final_parking_does_not_invent_a_successor(setup, monkeypatch):
    import bimanual.skill_executor as module
    from bimanual.skill_outcomes import SkillOutcome

    _, executor, _ = setup
    executor.max_actions = 3
    executor._reference = SimpleNamespace(final_parking=True)
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome("succeeded", "Fixture physical milestone", {}),
    )
    gate = SimpleNamespace(
        consume=lambda *a: SimpleNamespace(
            state="ready", reason="Fixture final parking", report=lambda: {"state": "ready"}
        )
    )
    monkeypatch.setattr(module, "SuccessorReadinessMonitor", lambda *a, **kw: gate)
    initial = executor.tick()
    assert initial.physical_success and initial.successor_ready is None
    final = executor.tick()
    assert final.state == "succeeded" and final.final_parking_ready is True
    assert final.successor_ready is None


def test_cancel_after_physical_success_preserves_milestone(setup, monkeypatch):
    import bimanual.skill_executor as module
    from bimanual.skill_outcomes import SkillOutcome

    worker, executor, policy = setup
    executor._reference = SimpleNamespace(final_parking=False)
    monkeypatch.setattr(
        executor._monitor,
        "consume",
        lambda action, rows: SkillOutcome("succeeded", "Fixture milestone", {}),
    )
    monkeypatch.setattr(module, "SuccessorReadinessMonitor", lambda *a, **kw: object())
    executor.tick()
    worker.cancel("Stop during retreat")
    final = executor.tick()
    assert final.state == "failed" and final.physical_success and final.successor_ready is False
    assert final.applied_actions == 1 and len(policy.inputs) == 1
    assert worker.supervisor.snapshot().state == "cancelled"
    assert worker.supervisor.snapshot().completed_steps == ()


@pytest.mark.parametrize("setup", [{"max_actions": 4, "execute_chunk_steps": 2}], indirect=True)
def test_chunk_prefix_reuses_forecast_but_advances_checked_actions(setup):
    worker, executor, policy = setup
    assert executor.tick().applied_actions == 1
    assert len(policy.inputs) == 1 and worker.control.pending
    assert executor.tick().applied_actions == 2
    assert len(policy.inputs) == 1 and not worker.control.pending
    assert executor.tick().applied_actions == 3
    assert len(policy.inputs) == 2
    worker.cancel("Stop fixture with queued action")
    before = worker._env.data.time
    assert not worker.control.pending
    assert executor.tick().state == "failed"
    assert worker._env.data.time == before


@pytest.mark.parametrize(
    "setup", [{"max_actions": 4, "configured_execute_chunk_steps": 2}], indirect=True
)
def test_constructor_profile_supplies_default_execution_prefix(setup):
    worker, executor, policy = setup
    assert executor.tick().applied_actions == 1
    assert executor.tick().applied_actions == 2
    assert len(policy.inputs) == 1 and not worker.control.pending
