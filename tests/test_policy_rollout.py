import copy
import json
from pathlib import Path

import numpy as np
import pytest

from bimanual.contracts import JointLimits, Observation
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import EvidenceStore
from bimanual.policy_rollout import (
    GuardedActionQueue,
    PolicyRolloutConfig,
    policy_inputs,
    run_policy_rollout,
)


def observation(sequence=0, episode="episode", timestamp=None):
    capture = dict(
        sequence=sequence,
        simulation_seconds=sequence / 20,
        observed_monotonic_ns=1_000_000_000 + sequence * 50_000_000
        if timestamp is None
        else timestamp,
    )
    return Observation(
        episode_id=episode,
        instruction_revision=0,
        **capture,
        joint_position_rad=[0.0] * 12,
        joint_velocity_rad_s=[0.0] * 12,
        frames=[
            dict(
                camera=camera, **capture, artifact=dict(path=f"frame-{index}.png", sha256="a" * 64)
            )
            for index, camera in enumerate(CAMERAS)
        ],
    )


@pytest.fixture
def queue():
    return GuardedActionQueue(
        JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        np.zeros(12),
        "a" * 64,
        500_000_000,
    )


def test_whole_chunk_validation_precedes_ownership_mask(queue):
    target = np.full((3, 12), 0.4)
    report = queue.offer(target, observation(), now_ns=1_010_000_000)
    assert report["raw_chunk"]["targets_rad"][0] == [0.4] * 12
    np.testing.assert_array_equal(
        queue.take(observation(), now_ns=1_020_000_000), [0.4] * 6 + [0.0] * 6
    )
    for invalid in (float("nan"), 2.0):
        target[2, 11] = invalid  # A later target for the masked arm is still rejected.
        with pytest.raises(ValueError):
            queue.offer(target, observation(), now_ns=1_010_000_000)
        assert not queue.pending


@pytest.mark.parametrize("fault", ["expiry", "identity", "sequence", "cancellation", "freshness"])
def test_pending_actions_discarded_on_invalid_context(queue, fault):
    queue.offer(np.full((3, 12), 0.4), observation(), now_ns=1_010_000_000)
    queue.take(observation(), now_ns=1_020_000_000)
    current = observation(1)
    now, cancelled = 1_100_000_000, False
    if fault == "expiry":
        now = 1_500_000_000
    elif fault == "identity":
        current = observation(1, episode="new-episode")
    elif fault == "sequence":
        current = observation(2)
    elif fault == "cancellation":
        cancelled = True
    else:
        current = observation(1, timestamp=1_200_000_000)
    with pytest.raises((ValueError, InterruptedError)):
        queue.take(current, now_ns=now, cancelled=cancelled)
    assert not queue.pending and queue.chunk is None


def test_perception_allowlist_never_supplies_truth_or_phase():
    raw = dict(
        schema_version=1,
        episode_id="episode",
        sequence=0,
        simulation_seconds=0.0,
        observed_monotonic_ns=1_000_000_000,
        joint_order=list(JOINT_ORDER),
        joint_position_rad=np.arange(12) / 20,
        joint_velocity_rad_s=np.ones(12),
        camera_order=list(CAMERAS),
        rgb={
            name: np.full((270, 480, 3), index * 40, np.uint8) for index, name in enumerate(CAMERAS)
        },
    )
    value = policy_inputs(raw)
    assert set(value) == {
        "observation.state",
        "observation.images.overhead",
        "observation.images.left_wrist",
        "observation.images.right_wrist",
    }
    assert value["observation.images.left_wrist"].shape == (3, 270, 480)
    np.testing.assert_allclose(value["observation.images.left_wrist"], 40 / 255)
    raw["joint_position_rad"][:] = 0
    assert value["observation.state"][1] == pytest.approx(0.05)
    for key in ("object_position", "stage", "teacher_target"):
        altered = copy.copy(raw)
        altered[key] = [0, 0, 0]
        with pytest.raises(ValueError, match="truth"):
            policy_inputs(altered)


def test_invalid_checkpoint_run_is_sealed_without_simulation(tmp_path):
    store = EvidenceStore(tmp_path)
    source = store.new_run()
    store.seal(
        source,
        kind="act_runtime_probe",
        outcome="completed",
        config={},
        metrics={},
        source={},
        claims=[],
    )
    result = run_policy_rollout(
        PolicyRolloutConfig(training_run=source), store=store, project_root=Path.cwd()
    )
    assert result.outcome == "failed"
    assert result.metrics["placement_success"] is False
    assert result.metrics["actual_device"] is None
    assert result.metrics["control_steps_applied"] == 0
    assert "completed ACT training" in result.metrics["error"]
    assert result.claims == []
    assert store.verify(result.run_id) == result
    metrics = json.loads((store.directory(result.run_id) / "metrics.json").read_text())
    assert metrics["evaluation_split"] == "training_scene_diagnostic"


def test_cancel_before_loading_or_rendering(tmp_path):
    store = EvidenceStore(tmp_path)
    result = run_policy_rollout(
        PolicyRolloutConfig(training_run=tmp_path / "not-created"),
        store=store,
        project_root=Path.cwd(),
        cancelled=lambda: True,
    )
    assert result.outcome == "interrupted"
    assert result.metrics["control_steps_applied"] == 0
    assert "before checkpoint loading" in result.metrics["error"]
    assert store.verify(result.run_id) == result


def test_terminal_capture_does_not_overwrite_pre_action_images(tmp_path):
    from bimanual.policy_rollout import save_observation

    (tmp_path / "observations").mkdir()
    (tmp_path / "terminal").mkdir()
    source = observation().model_dump()
    raw = {
        key: source[key]
        for key in (
            "schema_version",
            "episode_id",
            "sequence",
            "simulation_seconds",
            "observed_monotonic_ns",
            "joint_order",
            "joint_position_rad",
            "joint_velocity_rad_s",
        )
    }
    raw.update(
        camera_order=list(CAMERAS),
        rgb={name: np.zeros((270, 480, 3), np.uint8) for name in CAMERAS},
    )
    before = save_observation(raw, tmp_path)
    raw["rgb"]["overhead"][:] = 200
    after = save_observation(raw, tmp_path, prefix="terminal")
    assert before.frames[0].artifact.path != after.frames[0].artifact.path
    assert before.frames[0].artifact.sha256 != after.frames[0].artifact.sha256
    for record in (before, after):
        for frame in record.frames:
            frame.artifact.verify(tmp_path)


def test_long_forecast_executes_only_prefix_then_requires_replanning(queue):
    targets = np.linspace(0.1, 0.9, 100)[:, None] * np.ones((1, 12))
    report = queue.offer(targets, observation(), now_ns=1_001_000_000)
    assert report["prediction_horizon_steps"] == 100
    assert report["execution_prefix_steps"] == 10
    assert report["discarded_forecast_steps"] == 90
    assert len(report["accepted_chunk"]["targets_rad"]) == 100
    for index in range(10):
        value = queue.take(observation(index), now_ns=1_001_000_000 + index * 50_000_000)
        np.testing.assert_array_equal(value[:6], targets[index, :6])
    assert not queue.pending
    with pytest.raises(ValueError, match="No accepted action"):
        queue.take(observation(10), now_ns=1_501_000_000)
    assert queue.chunk is None
    new_report = queue.offer(np.full((100, 12), 0.3), observation(10), now_ns=1_501_000_000)
    assert new_report["accepted_chunk"]["observation_sequence"] == 10
    np.testing.assert_array_equal(queue.take(observation(10), now_ns=1_502_000_000)[:6], [0.3] * 6)


@pytest.mark.parametrize("column", [0, 11])
def test_invalid_unexecuted_forecast_tail_rejects_whole_offer(queue, column):
    targets = np.full((100, 12), 0.2)
    targets[99, column] = 2.0
    with pytest.raises(ValueError, match="bounds"):
        queue.offer(targets, observation(), now_ns=1_001_000_000)
    assert not queue.pending and queue.chunk is None


def test_prefix_does_not_extend_source_observation_expiry(queue):
    queue.offer(np.full((100, 12), 0.2), observation(), now_ns=1_001_000_000)
    with pytest.raises(ValueError, match="Expired"):
        queue.take(observation(), now_ns=1_500_000_000)
    assert not queue.pending


@pytest.mark.parametrize("value", [0, 101, True, 2.5])
def test_invalid_prefix_rejected(value, tmp_path):
    with pytest.raises(ValueError):
        PolicyRolloutConfig(training_run=tmp_path, execute_chunk_steps=value)
