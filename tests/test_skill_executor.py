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
def setup(tmp_path):
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
    executor = DinnerSkillExecutor(worker, policy, max_actions=1)
    executor.start(attempt.attempt_id, observation)
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
