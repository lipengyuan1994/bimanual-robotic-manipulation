from dataclasses import FrozenInstanceError, dataclass

import numpy as np
import pytest

from bimanual.contracts import JointLimits, Observation
from bimanual.dual_arm import CAMERAS
from bimanual.supervised_control import SupervisedPolicyControl
from bimanual.supervisor import Capability, StepSpec, TaskSpec


@dataclass
class Clock:
    now: int = 100

    def __call__(self):
        return self.now


def observation(sequence=0, captured=100, revision=0):
    capture = dict(
        sequence=sequence, observed_monotonic_ns=captured, simulation_seconds=sequence / 20
    )
    return Observation(
        episode_id="episode",
        instruction_revision=revision,
        **capture,
        joint_position_rad=[0.0] * 12,
        joint_velocity_rad_s=[0.0] * 12,
        frames=[
            dict(
                camera=camera, **capture, artifact=dict(path=f"{sequence}-{i}.png", sha256="a" * 64)
            )
            for i, camera in enumerate(CAMERAS)
        ],
    )


def task(identity="task", revision=0):
    return TaskSpec(
        task_id=identity,
        episode_id="episode",
        instruction_revision=revision,
        instruction="Exercise a registered test capability",
        steps=(StepSpec(step_id="step", capability_id="test-capability", timeout_ns=50),),
    )


def setup(arm="left", shared=True):
    clock = Clock()
    capability = Capability(
        capability_id="test-capability",
        skill="handoff" if arm == "both" else "pick",
        arm=arm,
        target="practice_block",
        destination="right_gripper" if arm == "both" else None,
        shared_workspace=shared,
    )
    control = SupervisedPolicyControl([capability], clock_ns=clock, max_observation_age_ns=20)
    control.supervisor.load_task(task())
    attempt = control.supervisor.dispatch(observation())
    return control, clock, attempt


def bind(control, attempt_id, **kwargs):
    options = dict(
        hold_targets=np.full(12, 0.2),
        limits=JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        policy_sha256="b" * 64,
        chunk_size=3,
        execute_chunk_steps=3,
    )
    return control.bind(attempt_id, **(options | kwargs))


@pytest.mark.parametrize(
    "arm,owned", [("left", ("left",)), ("right", ("right",)), ("both", ("left", "right"))]
)
def test_canonical_arm_ownership_and_held_targets(arm, owned):
    control, _, attempt = setup(arm)
    hold = np.full(12, 0.2)
    binding = bind(control, attempt.attempt_id, hold_targets=hold)
    hold[:] = 0.8
    assert binding.controlled_arms == owned
    with pytest.raises(FrozenInstanceError):
        binding.controlled_arms = ("left", "right")
    report = control.offer(attempt.attempt_id, np.full((3, 12), 0.4), observation())
    assert report["attempt_id"] == attempt.attempt_id
    assert report["raw_chunk"]["targets_rad"] == [[0.4] * 12] * 3
    actual = control.take(attempt.attempt_id, observation())
    expected = [0.4 if "left" in owned else 0.2] * 6 + [0.4 if "right" in owned else 0.2] * 6
    np.testing.assert_array_equal(actual, expected)


def test_authorizes_all_canonical_arms_and_shared_workspace(monkeypatch):
    control, _, attempt = setup("both")
    bind(control, attempt.attempt_id)
    calls = []
    original = control.supervisor.authorize

    def authorize(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(control.supervisor, "authorize", authorize)
    control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    control.take(attempt.attempt_id, observation())
    assert (
        calls
        == [
            {},
            {"arm": "left", "shared_workspace": True},
            {"arm": "right", "shared_workspace": True},
        ]
        * 2
    )


@pytest.mark.parametrize("event", ["cancel", "replace", "timeout", "finish"])
def test_supervisor_lifecycle_clears_bound_actions(event):
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    assert len(control.pending) == 3
    clock.now = 110
    if event == "cancel":
        control.supervisor.cancel()
    elif event == "replace":
        control.supervisor.load_task(task("replacement", 1))
    elif event == "timeout":
        clock.now = 150
        control.supervisor.tick()
    else:
        control.supervisor.finish(
            attempt.attempt_id,
            observation(1, 110),
            executor_outcome="succeeded",
            reason="Executor fixture completed",
        )
    assert control.binding is None and not control.pending
    with pytest.raises(RuntimeError):
        control.take(attempt.attempt_id, observation())
    assert control.supervisor.snapshot().evaluation_success is None


def test_invalid_forecast_is_failed_attempt_and_requires_supervisor_retry():
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    targets = np.zeros((3, 12))
    targets[-1, -1] = 2.0  # Even the unowned future tail must be valid.
    with pytest.raises(ValueError):
        control.offer(attempt.attempt_id, targets, observation())
    snapshot = control.supervisor.snapshot()
    assert snapshot.active is None and snapshot.attempts[-1].outcome == "failed"
    assert snapshot.state == "awaiting_observation"
    assert not control.pending and control.binding is None
    with pytest.raises(RuntimeError, match="canonical active"):
        bind(control, attempt.attempt_id)
    with pytest.raises(ValueError, match="new observation"):
        control.supervisor.dispatch(observation())
    clock.now = 110
    second = control.supervisor.dispatch(observation(1, 110))
    assert second.number == 2 and second.attempt_id != attempt.attempt_id
    bind(control, second.attempt_id)
    control.offer(second.attempt_id, np.zeros((3, 12)), observation(1, 110))
    assert len(control.pending) == 3


def test_stale_observation_preserves_supervisor_failure():
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    clock.now = 121
    with pytest.raises(ValueError, match="stale"):
        control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    attempts = control.supervisor.snapshot().attempts
    assert len(attempts) == 1 and attempts[0].outcome == "failed"
    assert "Rejected execution context" in attempts[0].reason


def test_take_enforces_original_forecast_expiration_after_fresh_capture():
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    control.take(attempt.attempt_id, observation())
    clock.now = 121
    with pytest.raises(ValueError, match="Expired"):
        control.take(attempt.attempt_id, observation(1, 121))
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"
    assert not control.pending


def test_rebind_cannot_change_policy_inside_attempt():
    control, _, attempt = setup()
    bind(control, attempt.attempt_id)
    with pytest.raises(RuntimeError, match="rebind"):
        bind(control, attempt.attempt_id, policy_sha256="c" * 64)
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"
    assert control.binding is None


def test_mutated_caller_attempt_is_not_accepted_as_ownership():
    control, _, attempt = setup()
    forged = attempt.model_copy(update={"arms": ("left", "right")})
    with pytest.raises(RuntimeError, match="canonical active"):
        bind(control, forged)
    assert bind(control, forged.attempt_id).controlled_arms == ("left",)


def test_invalid_binding_fails_attempt_without_hidden_retry():
    control, _, attempt = setup()
    with pytest.raises(ValueError, match="Hold targets"):
        bind(control, attempt.attempt_id, hold_targets=np.zeros(2))
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"
    with pytest.raises(RuntimeError, match="canonical active"):
        bind(control, attempt.attempt_id)


def test_invalid_forecasts_exhaust_only_declared_supervisor_attempts():
    control, clock, attempt = setup()
    for number in range(3):
        current = observation(number, 100 + number * 10)
        clock.now = current.observed_monotonic_ns
        if number:
            attempt = control.supervisor.dispatch(current)
        bind(control, attempt.attempt_id)
        with pytest.raises(ValueError):
            control.offer(attempt.attempt_id, np.full((3, 12), float("nan")), current)
    snapshot = control.supervisor.snapshot()
    assert snapshot.state == "failed" and len(snapshot.attempts) == 3
    assert all(result.outcome == "failed" for result in snapshot.attempts)
    clock.now = 130
    with pytest.raises(RuntimeError, match="not ready"):
        control.supervisor.dispatch(observation(3, 130))


def test_manual_clear_cannot_reset_binding_retry_budget():
    control, _, attempt = setup()
    bind(control, attempt.attempt_id)
    control.clear()
    with pytest.raises(RuntimeError, match="rebind"):
        bind(control, attempt.attempt_id)
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"


@pytest.mark.parametrize("operation", ["offer", "take"])
def test_deadline_crossed_between_authorization_and_queue_operation(operation):
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    current = observation(1, 145)
    clock.now = 145
    if operation == "take":
        control.offer(attempt.attempt_id, np.zeros((3, 12)), current)
    moments = iter([145, 145, 151])

    def stepping_clock():
        clock.now = next(moments, clock.now)
        return clock.now

    control._clock = stepping_clock
    control.supervisor._clock = stepping_clock
    with pytest.raises(TimeoutError, match="deadline"):
        if operation == "offer":
            control.offer(attempt.attempt_id, np.zeros((3, 12)), current)
        else:
            control.take(attempt.attempt_id, current)
    snapshot = control.supervisor.snapshot()
    assert len(snapshot.attempts) == 1
    assert snapshot.attempts[0].outcome == "timed_out"
    assert snapshot.attempts[0].ended_ns == 151
    assert snapshot.active is None and not control.pending


def test_forecast_cannot_replace_pending_targets():
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    control.take(attempt.attempt_id, observation())
    clock.now = 105
    with pytest.raises(ValueError, match="unconsumed"):
        control.offer(attempt.attempt_id, np.zeros((3, 12)), observation(1, 105))
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"
    assert not control.pending


def test_drained_forecast_cannot_reuse_same_observation():
    control, _, attempt = setup()
    bind(control, attempt.attempt_id, execute_chunk_steps=1)
    control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    control.take(attempt.attempt_id, observation())
    assert not control.pending
    with pytest.raises(ValueError, match="next fresh"):
        control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"


def test_drained_forecast_requires_exact_next_sequence():
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id, execute_chunk_steps=1)
    control.offer(attempt.attempt_id, np.zeros((3, 12)), observation())
    control.take(attempt.attempt_id, observation())
    clock.now = 105
    with pytest.raises(ValueError, match="next fresh"):
        control.offer(attempt.attempt_id, np.zeros((3, 12)), observation(2, 105))
    assert control.supervisor.snapshot().attempts[-1].outcome == "failed"


def test_drain_then_fresh_forecast_preserves_progress_across_chunks():
    control, clock, attempt = setup()
    bind(control, attempt.attempt_id)
    control.offer(attempt.attempt_id, np.full((3, 12), 0.4), observation())
    for sequence in range(3):
        clock.now = 100 + sequence * 5
        control.take(attempt.attempt_id, observation(sequence, clock.now))
    assert not control.pending
    clock.now = 115
    fresh = observation(3, 115)
    control.offer(attempt.attempt_id, np.full((3, 12), 0.5), fresh)
    np.testing.assert_array_equal(control.take(attempt.attempt_id, fresh), [0.5] * 6 + [0.2] * 6)
    assert len(control.pending) == 2
    assert control.supervisor.snapshot().active.attempt_id == attempt.attempt_id


@pytest.mark.parametrize("event", ["cancel", "replace", "timeout", "finish", "invalid"])
def test_temporal_history_is_cleared_with_lifecycle(monkeypatch, event):
    class FakeEnsembler:
        resets = 0

        def update(self, targets):
            return targets[:1].copy()

        def reset(self):
            self.resets += 1

    ensemble = FakeEnsembler()
    monkeypatch.setattr("bimanual.temporal_actions._make_ensembler", lambda *args: ensemble)
    control, clock, attempt = setup("right")
    bind(control, attempt.attempt_id, execute_chunk_steps=1, temporal_ensemble_coefficient=0.01)
    control.offer(attempt.attempt_id, np.full((3, 12), 0.4), observation())
    np.testing.assert_array_equal(
        control.take(attempt.attempt_id, observation()), [0.2] * 6 + [0.4] * 6
    )
    clock.now = 110
    if event == "cancel":
        control.supervisor.cancel()
    elif event == "replace":
        control.supervisor.load_task(task("replacement", 1))
    elif event == "timeout":
        clock.now = 150
        control.supervisor.tick()
    elif event == "finish":
        control.supervisor.finish(
            attempt.attempt_id,
            observation(1, 110),
            executor_outcome="succeeded",
            reason="Fixture completed",
        )
    else:
        with pytest.raises(ValueError):
            control.offer(attempt.attempt_id, np.full((3, 12), 2.0), observation(1, 110))
        assert control.supervisor.snapshot().attempts[-1].outcome == "failed"
    assert ensemble.resets == 1
    assert control.binding is None and not control.pending


@pytest.mark.parametrize("primary,auxiliary", [("left", "right"), ("right", "left")])
def test_registered_auxiliary_arm_reaches_queue_without_widening_planner(primary, auxiliary):
    capability = Capability(
        capability_id="test-capability",
        skill="place",
        arm=primary,
        target="practice_block",
        destination="table",
        auxiliary_arms=(auxiliary,),
    )
    control = SupervisedPolicyControl([capability], clock_ns=Clock())
    control.supervisor.load_task(task())
    proposal = capability.request("episode", 0, 0)
    attempt = control.supervisor.dispatch(observation(), proposal=proposal)
    assert attempt.request.arm == primary
    binding = bind(control, attempt.attempt_id)
    assert binding.controlled_arms == ("left", "right")
    forecast = np.full((3, 12), 0.4)
    control.offer(attempt.attempt_id, forecast, observation())
    np.testing.assert_array_equal(control.take(attempt.attempt_id, observation()), forecast[0])
    control.supervisor.cancel()
    assert control.binding is None and control.pending == ()
