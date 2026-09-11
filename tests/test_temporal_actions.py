import numpy as np
import pytest
from test_policy_rollout import observation

from bimanual.contracts import JointLimits, Observation
from bimanual.temporal_actions import GuardedTemporalActionQueue


def queue(**kwargs):
    return GuardedTemporalActionQueue(
        JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        np.zeros(12),
        "a" * 64,
        500_000_000,
        chunk_size=kwargs.get("chunk_size", 3),
        coefficient=kwargs.get("coefficient", 0.01),
    )


def now(obs):
    return obs.observed_monotonic_ns + 1_000_000


def changed(obs, **changes):
    raw = obs.model_dump(mode="json") | changes
    for frame in raw["frames"]:
        for key in ("sequence", "simulation_seconds", "observed_monotonic_ns"):
            frame[key] = raw[key]
    return Observation.model_validate(raw)


@pytest.fixture
def backend(monkeypatch):
    """Small lifecycle stub; actual ACT weighting parity is tested separately below."""
    import bimanual.temporal_actions as module

    instances = []

    class StubEnsembler:
        def __init__(self):
            self.calls = []
            self.previous = None
            self.resets = 0
            self.invalid_output = False

        def update(self, values):
            self.calls.append(values.copy())
            result = values[:1].copy()
            if self.previous is not None:
                result = (result + self.previous[1:2]) / 2
            self.previous = values.copy()
            if self.invalid_output:
                result[0, 11] = 2.0
            return result

        def reset(self):
            self.previous = None
            self.resets += 1

    def make(chunk_size, coefficient):
        instance = StubEnsembler()
        instances.append(instance)
        return instance

    monkeypatch.setattr(module, "_make_ensembler", make)
    return instances


def test_raw_forecast_and_averaged_action_are_preserved_before_ownership_mask(backend):
    q = queue()
    first = np.full((3, 12), 0.2)
    report = q.offer(first, observation(), now_ns=now(observation()))
    first[:] = 0.9
    assert report["raw_chunk"]["targets_rad"] == [[0.2] * 12] * 3
    np.testing.assert_array_equal(
        q.take(observation(), now_ns=now(observation())), [0.2] * 6 + [0.0] * 6
    )
    obs = observation(1)
    report = q.offer(np.full((3, 12), 0.6), obs, now_ns=now(obs))
    assert report["prediction_horizon_steps"] == 3 and report["execution_prefix_steps"] == 1
    assert report["discarded_forecast_steps"] == 0
    assert report["retained_for_temporal_ensemble_steps"] == 2
    assert report["temporal_ensemble"]["forecasts_since_reset"] == 2
    assert report["averaged_raw_chunk"]["targets_rad"] == [[0.4] * 12]
    np.testing.assert_array_equal(q.take(obs, now_ns=now(obs)), [0.4] * 6 + [0.0] * 6)
    assert not q.pending and len(backend[0].calls) == 2


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 2.0])
@pytest.mark.parametrize("column", [0, 11])
def test_invalid_future_forecast_never_reaches_ensemble(backend, invalid, column):
    q = queue()
    values = np.full((3, 12), 0.2)
    values[-1, column] = invalid
    with pytest.raises(ValueError):
        q.offer(values, observation(), now_ns=now(observation()))
    assert backend == [] and not q.pending
    assert q._ensembler is None


@pytest.mark.parametrize(
    "failure", ["horizon", "duplicate", "gap", "unconsumed", "stale", "capture", "simulation"]
)
def test_offer_error_clears_previous_history_and_pending_actions(backend, failure):
    q = queue()
    q.offer(np.full((3, 12), 0.2), observation(), now_ns=now(observation()))
    if failure != "unconsumed":
        q.take(observation(), now_ns=now(observation()))
    obs, values = observation(1), np.full((3, 12), 0.8)
    timestamp = now(obs)
    if failure == "horizon":
        values = np.zeros((2, 12))
    elif failure == "duplicate":
        obs = observation()
    elif failure == "gap":
        obs = observation(2)
        timestamp = now(obs)
    elif failure == "stale":
        timestamp = obs.observed_monotonic_ns + 500_000_000
    elif failure == "capture":
        obs = observation(1, timestamp=observation().observed_monotonic_ns)
    elif failure == "simulation":
        obs = changed(obs, simulation_seconds=0.0)
    with pytest.raises(ValueError):
        q.offer(values, obs, now_ns=timestamp)
    assert not q.pending and q._ensembler is None
    assert backend[0].previous is None and backend[0].resets == 1
    fresh = observation(3)
    q.offer(np.full((3, 12), 0.8), fresh, now_ns=now(fresh))
    np.testing.assert_array_equal(q.take(fresh, now_ns=now(fresh)), [0.8] * 6 + [0.0] * 6)


@pytest.mark.parametrize("context", ["episode", "instruction"])
def test_new_task_context_clears_unconsumed_old_forecast(backend, context):
    q = queue()
    q.offer(np.full((3, 12), 0.2), observation(), now_ns=now(observation()))
    obs = (
        observation(episode="new")
        if context == "episode"
        else changed(observation(), instruction_revision=1)
    )
    report = q.offer(np.full((3, 12), 0.8), obs, now_ns=now(obs))
    assert backend[0].resets == 1 and len(backend) == 2
    assert report["temporal_ensemble"]["forecasts_since_reset"] == 1
    np.testing.assert_array_equal(q.take(obs, now_ns=now(obs)), [0.8] * 6 + [0.0] * 6)


@pytest.mark.parametrize(
    "failure", ["cancel", "expiry", "identity", "modified_same_identity", "duplicate_take"]
)
def test_take_errors_clear_averaging_history(backend, failure):
    q = queue()
    obs = observation()
    q.offer(np.full((3, 12), 0.2), obs, now_ns=now(obs))
    current, timestamp, cancel = obs, now(obs), False
    if failure == "cancel":
        cancel = True
    elif failure == "expiry":
        timestamp = obs.observed_monotonic_ns + 500_000_000
    elif failure == "identity":
        current = observation(episode="other")
    elif failure == "modified_same_identity":
        current = changed(obs, joint_position_rad=[0.1] * 12)
    else:
        q.take(obs, now_ns=now(obs))
    with pytest.raises((ValueError, InterruptedError)):
        q.take(current, now_ns=timestamp, cancelled=cancel)
    assert not q.pending and q._ensembler is None and backend[0].resets == 1


def test_explicit_clear_resets_both_histories(backend):
    q = queue()
    q.offer(np.full((3, 12), 0.2), observation(), now_ns=now(observation()))
    q.clear()
    assert not q.pending and backend[0].resets == 1
    q.offer(np.full((3, 12), 0.7), observation(), now_ns=now(observation()))
    np.testing.assert_array_equal(
        q.take(observation(), now_ns=now(observation())), [0.7] * 6 + [0.0] * 6
    )


def test_invalid_averaged_masked_target_is_rejected_after_update(backend):
    q = queue()
    q.offer(np.full((3, 12), 0.2), observation(), now_ns=now(observation()))
    q.take(observation(), now_ns=now(observation()))
    backend[0].invalid_output = True
    obs = observation(1)
    with pytest.raises(ValueError, match="bounds"):
        q.offer(np.full((3, 12), 0.4), obs, now_ns=now(obs))
    assert len(backend[0].calls) == 2 and backend[0].resets == 1
    assert not q.pending and q._ensembler is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chunk_size": 0},
        {"chunk_size": 101},
        {"chunk_size": True},
        {"coefficient": float("nan")},
        {"coefficient": True},
        {"coefficient": -0.01},
        {"coefficient": 1.01},
    ],
)
def test_invalid_settings_rejected_without_loading_optional_runtime(kwargs, backend):
    with pytest.raises(ValueError):
        queue(**kwargs)
    assert not backend


@pytest.mark.parametrize("coefficient", [0.0, 0.01, 1.0])
def test_real_installed_lerobot_parity_and_reset(coefficient):
    torch = pytest.importorskip("torch")
    official = pytest.importorskip("lerobot.policies.act.modeling_act").ACTTemporalEnsembler
    q = queue(coefficient=coefficient)
    reference = official(coefficient, 3)
    generator = np.random.default_rng(81)
    for index in range(8):
        values = generator.uniform(-0.7, 0.7, size=(3, 12))
        obs = observation(index)
        expected = reference.update(torch.tensor(values, dtype=torch.float32).unsqueeze(0)).numpy()
        report = q.offer(values, obs, now_ns=now(obs))
        np.testing.assert_array_equal(report["averaged_raw_chunk"]["targets_rad"], expected)
        target = q.take(obs, now_ns=now(obs))
        np.testing.assert_array_equal(target[:6], expected[0, :6])
        np.testing.assert_array_equal(target[6:], np.zeros(6))
        assert report["temporal_ensemble"]["device"] == "cpu"
    q.clear()
    values = np.full((3, 12), 0.3)
    obs = observation(20)
    report = q.offer(values, obs, now_ns=now(obs))
    np.testing.assert_array_equal(
        report["averaged_raw_chunk"]["targets_rad"], values[:1].astype(np.float32)
    )


@pytest.mark.parametrize("arms", [("right",), ("left", "right")])
def test_temporal_queue_preserves_explicit_arm_ownership(backend, arms):
    control = GuardedTemporalActionQueue(
        JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        np.zeros(12),
        "a" * 64,
        500_000_000,
        chunk_size=3,
        coefficient=0.01,
        controlled_arms=arms,
    )
    report = control.offer(np.full((3, 12), 0.2), observation(), now_ns=now(observation()))
    actual = control.take(observation(), now_ns=now(observation()))
    np.testing.assert_allclose(actual[6:], 0.2)
    np.testing.assert_allclose(actual[:6], 0.2 if "left" in arms else 0.0)
    assert control.controlled_arms == arms
    assert report["ownership_mask"]["controlled_arms"] == list(arms)
    invalid = np.zeros((3, 12))
    invalid[-1, 0] = 2.0
    with pytest.raises(ValueError):
        control.offer(
            invalid,
            changed(
                observation(),
                sequence=1,
                simulation_seconds=0.05,
                observed_monotonic_ns=1_050_000_000,
            ),
            now_ns=1_060_000_000,
        )
    assert not control.pending and control._ensembler is None
