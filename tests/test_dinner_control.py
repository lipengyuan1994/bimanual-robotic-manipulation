import json
from dataclasses import dataclass
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest

from bimanual.dinner_control import DinnerControlWorker
from bimanual.dual_arm import CAMERAS
from bimanual.supervisor import Capability, StepSpec, TaskSpec


@dataclass
class Clock:
    now: int = 1_000_000_000

    def __call__(self):
        return self.now


@pytest.fixture
def worker(tmp_path):
    clock = Clock()
    cancellation = [False]
    captures = []

    def synthetic_rgb(env):
        captures.append((env.sequence, float(env.data.time)))
        return {
            camera: np.full((270, 480, 3), index * 40, np.uint8)
            for index, camera in enumerate(CAMERAS)
        }

    registry = [Capability(capability_id="cup-right", skill="pick", arm="right", target="cup")]
    instance = DinnerControlWorker(
        tmp_path / "worker",
        registry,
        clock_ns=clock,
        cancelled=lambda: cancellation[0],
        render_capture=synthetic_rgb,
    )
    instance.supervisor.load_task(
        TaskSpec(
            task_id="dinner",
            episode_id=instance.episode_id,
            instruction_revision=0,
            instruction="Exercise two declared fixture steps",
            steps=(
                StepSpec(step_id="one", capability_id="cup-right"),
                StepSpec(step_id="two", capability_id="cup-right", prerequisites=("one",)),
            ),
        )
    )
    yield instance, clock, cancellation, captures
    instance.close()


def start(worker):
    instance, _, _, _ = worker
    observation = instance.capture()
    attempt = instance.supervisor.dispatch(observation)
    instance.bind(attempt.attempt_id, policy_sha256="a" * 64, chunk_size=2, execute_chunk_steps=2)
    forecast = np.tile(instance._env.data.ctrl[instance._env.actuator_ids], (2, 1))
    instance.offer(attempt.attempt_id, forecast, observation)
    return attempt, observation, forecast


def test_real_mujoco_step_uses_continuous_environment_and_policy_boundary(worker):
    instance, clock, _, _ = worker
    attempt, before, _ = start(worker)
    identity = instance.episode_id
    original_env = instance._env
    inputs = instance.policy_inputs(before)
    assert set(inputs) == {
        "observation.state",
        "observation.images.overhead",
        "observation.images.left_wrist",
        "observation.images.right_wrist",
    }
    inputs["observation.state"][:] = 999  # Caller cannot alter the worker's raw capture.
    assert np.max(instance.policy_inputs(before)["observation.state"]) < 2
    assert instance.step(attempt.attempt_id, before)["applied"]
    clock.now += 50_000_000
    after = instance.capture()
    assert after.sequence == 1 and after.simulation_seconds == pytest.approx(0.05)
    assert instance._env is original_env and instance.episode_id == identity
    assert instance.step(attempt.attempt_id, after)["applied"]
    assert instance._env.sequence == 2
    instance._trace.flush()
    rows = [
        json.loads(line) for line in (instance.directory / "physics.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 100 and rows[-1]["t"] == pytest.approx(0.1)
    assert all(not row["bad"] for row in rows)
    assert not instance.control.pending
    assert instance.supervisor.snapshot().active is not None  # Exhaustion is not success.
    assert instance.supervisor.snapshot().evaluation_success is None
    assert (
        json.loads((instance.directory / "worker.json").read_text())["camera_source"]
        == "injected_unverified"
    )


@pytest.mark.parametrize(
    "fault", ["forged", "physical_state", "stale", "tampered_image", "wrong_attempt"]
)
def test_invalid_boundary_prevents_any_physics(worker, fault):
    instance, clock, _, _ = worker
    attempt, current, _ = start(worker)
    identifier = attempt.attempt_id
    if fault == "forged":
        current = current.model_copy(update={"joint_position_rad": (0.0,) * 12})
    elif fault == "physical_state":
        instance._env.data.qvel[0] += 0.01
    elif fault == "stale":
        clock.now += 2_000_000_001
    elif fault == "tampered_image":
        (instance.directory / current.frames[0].artifact.path).write_bytes(b"changed")
    else:
        identifier = "another-attempt"
    with pytest.raises((ValueError, RuntimeError)):
        instance.step(identifier, current)
    assert instance._env.data.time == 0
    assert not instance._env.active
    action = json.loads((instance.directory / "actions.jsonl").read_text().splitlines()[-1])
    assert action["applied"] is False and action["partial_physics"] is False


def test_cancellation_prevents_step_and_clears_controls(worker):
    instance, _, cancellation, _ = worker
    attempt, current, _ = start(worker)
    cancellation[0] = True
    with pytest.raises(InterruptedError):
        instance.step(attempt.attempt_id, current)
    assert instance._env.data.time == 0
    assert not instance.control.pending
    assert instance.supervisor.snapshot().attempts[-1].outcome == "cancelled"


def test_physical_contact_guard_retains_partial_failed_step(worker):
    instance, _, _, _ = worker
    env = instance._env
    # Fault injection before capture: an already penetrating cup/table contact.
    # This is fixture setup, never an operating-policy object move.
    address = env.model.jnt_qposadr[env.model.joint("cup/free").id]
    env.data.qpos[address + 2] -= 0.04
    mujoco.mj_forward(env.model, env.data)
    assert any(float(contact.dist) < -0.0025 for contact in env.data.contact)
    attempt, current, _ = start(worker)
    with pytest.raises(ValueError, match="contact guard"):
        instance.step(attempt.attempt_id, current)
    assert 0 < env.data.time < 0.05 and env.sequence == 0 and not env.active
    env.trace.flush()
    row = json.loads((instance.directory / "physics.jsonl").read_text().splitlines()[-1])
    assert row["overlap"] > 0.0025
    action = json.loads((instance.directory / "actions.jsonl").read_text().splitlines()[-1])
    assert action["applied"] is False and action["partial_physics"] is True
    assert instance.supervisor.snapshot().attempts[-1].outcome == "failed"


def test_stationary_transition_rerenders_without_reset_or_unowned_step(worker):
    instance, clock, _, captures = worker
    attempt, current, _ = start(worker)
    instance.step(attempt.attempt_id, current)
    clock.now += 50_000_000
    terminal = instance.capture()
    state = instance._token()
    identity = instance.episode_id
    instance.finish(
        attempt.attempt_id,
        terminal,
        executor_outcome="succeeded",
        reason="Trusted fixture termination; no manipulation claim",
    )
    clock.now += 1_000_000
    second = instance.dispatch_stationary(terminal)
    assert second.request.observation_sequence == terminal.sequence
    assert second.observation.simulation_seconds == terminal.simulation_seconds
    assert second.observation.observed_monotonic_ns > terminal.observed_monotonic_ns
    assert instance._token() == state and instance.episode_id == identity
    assert captures == [(0, 0.0), (1, pytest.approx(0.05)), (1, pytest.approx(0.05))]
    assert all(
        a.artifact.path != b.artifact.path
        for a, b in zip(terminal.frames, second.observation.frames, strict=True)
    )
    instance.bind(second.attempt_id, policy_sha256="b" * 64, chunk_size=1)
    instance.offer(
        second.attempt_id,
        np.tile(instance._env.data.ctrl[instance._env.actuator_ids], (1, 1)),
        second.observation,
    )
    instance.step(second.attempt_id, second.observation)
    assert instance._env.sequence == 2


def test_close_preserves_interrupted_attempt_without_success(worker):
    instance, _, _, _ = worker
    start(worker)
    instance.close()
    state = json.loads((instance.directory / "supervisor.json").read_text())
    assert state["attempts"][-1]["outcome"] == "cancelled"
    summary = json.loads((instance.directory / "summary.json").read_text())
    assert summary["manipulation_success"] is None


@pytest.mark.parametrize("field", ["friction", "camera", "limits"])
def test_model_mutation_prevents_stepping(worker, field):
    instance, _, _, _ = worker
    attempt, current, _ = start(worker)
    model = instance._env.model
    if field == "friction":
        model.geom_friction[0, 0] += 0.1
    elif field == "camera":
        model.cam_pos[0, 0] += 0.1
    else:
        model.actuator_ctrlrange[0, 1] += 0.1
    with pytest.raises(ValueError, match="model changed"):
        instance.step(attempt.attempt_id, current)
    assert instance._env.data.time == 0 and not instance._env.active


def test_capture_timestamp_starts_before_rendering(worker):
    instance, clock, _, _ = worker
    original = instance._render_capture
    started = clock.now

    def slow_render(env):
        pixels = original(env)
        clock.now += 2_000_000_001
        return pixels

    instance._render_capture = slow_render
    observation = instance.capture()
    assert observation.observed_monotonic_ns == started
    with pytest.raises(ValueError, match="fresh camera"):
        instance.policy_inputs(observation)
    assert instance._env.data.time == 0


def test_authored_scene_integrity_is_checked_without_loading_plan(tmp_path, monkeypatch):
    from bimanual import dinner_control

    assets = tmp_path / "assets"
    assets.mkdir()
    manifest = json.loads((dinner_control.ASSETS / "manifest.json").read_text())
    (assets / "manifest.json").write_text(json.dumps(manifest))
    (assets / "scene.xml").write_text("<mujoco/>")
    monkeypatch.setattr(dinner_control, "ASSETS", assets)
    with pytest.raises(ValueError, match="scene integrity"):
        DinnerControlWorker(tmp_path / "invalid-scene-worker", [])


@pytest.mark.parametrize("matched", [True, False])
def test_verified_skill_binding_delegation_without_model_loading(worker, matched):
    from bimanual.skill_policy import DinnerSkillPolicy

    instance, _, _, _ = worker
    observation = instance.capture()
    attempt = instance.supervisor.dispatch(observation)
    # Exercise the real bind_control contract with an explicit no-model test stub.
    policy = object.__new__(DinnerSkillPolicy)
    registered = instance.supervisor.registry["cup-right"]
    resets = []
    policy._policy = SimpleNamespace(reset=lambda: resets.append(True))
    policy.binding = SimpleNamespace(
        capability=registered if matched else registered.model_copy(update={"target": "plate"}),
        checkpoint_sha256="b" * 64,
        chunk_size=2,
    )
    if not matched:
        with pytest.raises(ValueError, match="Checkpoint skill"):
            instance.bind_skill(policy, attempt.attempt_id)
        assert not resets and instance._env.data.time == 0
        assert instance.supervisor.snapshot().attempts[-1].outcome == "failed"
    else:
        binding = instance.bind_skill(policy, attempt.attempt_id)
        assert resets == [True] and binding.policy_sha256 == "b" * 64
        np.testing.assert_array_equal(
            binding.hold_targets, instance._env.data.ctrl[instance._env.actuator_ids]
        )
        assert instance.control._queue.limits == instance.limits
        assert instance._env.active_contacts == {"right": {"cup"}}


def test_auxiliary_arm_ownership_does_not_grant_object_contact(tmp_path):
    from bimanual.skill_registry import dinner_capability

    capability = dinner_capability("plate_pick_place")
    clock = Clock()
    instance = DinnerControlWorker(
        tmp_path / "aux-worker",
        [capability],
        clock_ns=clock,
        render_capture=lambda env: {name: np.zeros((270, 480, 3), np.uint8) for name in CAMERAS},
    )
    try:
        instance.supervisor.load_task(
            TaskSpec(
                task_id="plate",
                episode_id=instance.episode_id,
                instruction_revision=0,
                instruction="Test canonical composite ownership",
                steps=(StepSpec(step_id="plate", capability_id=capability.capability_id),),
            )
        )
        observation = instance.capture()
        attempt = instance.supervisor.dispatch(observation)
        binding = instance.bind(attempt.attempt_id, policy_sha256="a" * 64, chunk_size=1)
        assert binding.controlled_arms == ("left", "right")
        assert instance._env.active_contacts == {"left": {"plate"}}
    finally:
        instance.close()
