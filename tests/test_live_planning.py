import json
from dataclasses import dataclass

import numpy as np
import pytest

from bimanual.dinner_control import DinnerControlWorker
from bimanual.dual_arm import CAMERAS
from bimanual.live_planning import LivePlanningSession
from bimanual.planner import planner_messages
from bimanual.supervisor import Capability, StepSpec, TaskSpec


@dataclass
class Clock:
    now: int = 1_000_000_000

    def __call__(self):
        return self.now


def task(episode, *, identity="task", revision=0):
    return TaskSpec(
        task_id=identity,
        episode_id=episode,
        instruction_revision=revision,
        instruction="Pick up the cup",
        steps=(
            StepSpec(step_id="first", capability_id="cup-right"),
            StepSpec(step_id="second", capability_id="cup-right", prerequisites=("first",)),
        ),
    )


@pytest.fixture
def setup(tmp_path):
    clock, captures = Clock(), []

    def synthetic_rgb(env):
        captures.append(env.sequence)
        return {name: np.full((270, 480, 3), index, np.uint8) for index, name in enumerate(CAMERAS)}

    worker = DinnerControlWorker(
        tmp_path / "worker",
        [Capability(capability_id="cup-right", skill="pick", arm="right", target="cup")],
        clock_ns=clock,
        render_capture=synthetic_rgb,
    )
    worker.supervisor.load_task(task(worker.episode_id))
    yield worker, LivePlanningSession(worker), clock, captures
    worker.close()


def response(job, skill="pick"):
    observation = job.context.observation
    actionable = skill == "pick"
    return json.dumps(
        {
            "schema_version": 2,
            "request": {
                "episode_id": observation.episode_id,
                "instruction_revision": observation.instruction_revision,
                "observation_sequence": observation.sequence,
                "skill": skill,
                "arm": "right" if actionable else "none",
                "target": "cup" if actionable else None,
                "destination": None,
                "explanation": "Fixture response; not measured model quality",
            },
            "target_visibility": "visible" if actionable else "uncertain",
            "visible_state": "incomplete" if actionable else "uncertain",
            "visual_explanation": "Synthetic images are a lifecycle test only",
        }
    )


def test_95_second_delay_requires_recapture_and_preserves_original(setup):
    worker, session, clock, captures = setup
    job = session.begin()
    original = job.context.observation
    job_bytes = (session.directory / job.job_id / "job.json").read_bytes()
    assert len(session.images(job.job_id)) == 3
    clock.now += 95_000_000_000
    with pytest.raises(ValueError, match="stale"):
        worker.supervisor.dispatch(original)
    result = session.complete(job.job_id, response(job), model_metrics={"inference_seconds": 95.0})
    current = result.execution_observation
    assert result.attempt.started_ns == clock.now and result.attempt.deadline_ns > clock.now
    assert current.observed_monotonic_ns - original.observed_monotonic_ns == 95_000_000_000
    assert current.sequence == original.sequence == 0 and current.simulation_seconds == 0
    assert worker._env.data.time == 0 and captures == [0, 0, 0]
    assert all(
        a.artifact.path != b.artifact.path and a.artifact.sha256 == b.artifact.sha256
        for a, b in zip(original.frames, current.frames, strict=True)
    )
    assert job_bytes == (session.directory / job.job_id / "job.json").read_bytes()
    record = json.loads(result.revalidation_path.read_text())
    assert record["original_observation"]["observed_monotonic_ns"] == original.observed_monotonic_ns
    assert record["authority"] == "worker_pause_revalidation"
    assert (
        record["camera_source"] == "injected_unverified" and record["manipulation_success"] is None
    )
    assert result.original_proposal.request.observation_sequence == original.sequence
    assert worker.supervisor.snapshot().evaluation_success is None
    saved = json.loads((session.directory / job.job_id / "model-response.json").read_text())
    assert saved["model_metrics"] == {"inference_seconds": 95.0}


def test_fixed_recorded_warmup_precedes_original_model_context(setup):
    worker, session, clock, captures = setup
    original_capture = worker._render_capture

    def cold_renderer(env):
        first = not captures
        images = original_capture(env)
        if first:
            images[CAMERAS[0]][0, 0, 0] += 1
        return images

    worker._render_capture = cold_renderer
    job = session.begin()
    assert captures == [0, 0]
    warmup, original = job.warmup_observation, job.context.observation
    assert warmup.sequence == original.sequence == 0
    assert warmup.simulation_seconds == original.simulation_seconds == 0
    assert warmup.joint_position_rad == original.joint_position_rad
    assert warmup.frames[0].artifact.sha256 != original.frames[0].artifact.sha256
    assert all(
        a.artifact.path != b.artifact.path
        for a, b in zip(warmup.frames, original.frames, strict=True)
    )
    assert all((worker.directory / f.artifact.path).is_file() for f in warmup.frames)
    saved = json.loads((session.directory / job.job_id / "job.json").read_text())
    assert saved["warmup_observation"] == warmup.model_dump(mode="json")
    assert np.asarray(session.images(job.job_id)[0])[0, 0, 0] == 0
    clock.now += 95_000_000_000
    result = session.complete(job.job_id, response(job))
    assert result.attempt is not None and captures == [0, 0, 0]
    assert (
        result.execution_observation.frames[0].artifact.sha256 == original.frames[0].artifact.sha256
    )
    assert worker._env.data.time == 0


def test_persistent_single_bit_variation_still_rejects_after_warmup(setup):
    worker, session, clock, captures = setup
    original_capture = worker._render_capture

    def changing_renderer(env):
        images = original_capture(env)
        images[CAMERAS[0]][0, 0, 0] = len(captures)
        return images

    worker._render_capture = changing_renderer
    job = session.begin()
    clock.now += 1
    with pytest.raises(ValueError, match="recapture"):
        session.complete(job.job_id, response(job))
    assert captures == [0, 0, 0]  # Fixed warm-up, never retry until pixels happen to match.
    assert worker.supervisor.snapshot().active is None and worker._env.data.time == 0


def test_hd_live_context_keeps_act_pixels_and_paused_dispatch_separate(setup):
    worker, _, clock, captures = setup
    hd_captures = []

    def overhead(env):
        hd_captures.append((env.sequence, float(env.data.time)))
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        image[0, 0, 0] = int(len(hd_captures) == 1)  # Retained cold-frame variation.
        return image

    worker._planner_render_capture = overhead
    session = LivePlanningSession(worker, camera_profile="overhead1920_wrist480_v1")
    physical_model = worker._model_digest()
    job = session.begin()
    assert captures == [0, 0] and hd_captures == [(0, 0), (0, 0)]
    assert job.original_capture.mode == "live_paused_v1"
    assert job.camera_source == "injected_unverified"
    images = session.images(job.job_id)
    assert [image.size for image in images] == [(1920, 1080), (480, 270), (480, 270)]
    assert np.asarray(images[0])[0, 0, 0] == 0
    assert planner_messages(job.context, images)
    policy = job.original_capture.policy_observation
    inputs = worker.policy_inputs(policy)
    assert inputs["observation.images.overhead"].shape == (3, 270, 480)
    assert set(inputs) == {
        "observation.state",
        "observation.images.overhead",
        "observation.images.left_wrist",
        "observation.images.right_wrist",
    }
    with pytest.raises(ValueError, match="exact current capture"):
        worker.policy_inputs(job.context.observation)
    calibration = json.loads(job.original_capture.calibration.verify(worker.directory).read_text())
    assert calibration["source_model_sha256"] == physical_model
    assert calibration["render_model_sha256"] != physical_model
    assert calibration["cameras"][0]["render_dimensions_wh"] == [1920, 1080]
    assert calibration["render_model_overrides"] == {"offwidth": 1920, "offheight": 1080}
    assert worker._model_digest() == physical_model
    clock.now += 95_000_000_000
    result = session.complete(job.job_id, response(job))
    assert result.attempt is not None and worker._env.data.time == 0
    assert result.execution_observation == worker._observation
    assert (
        result.execution_observation.frames[0].artifact.path
        != job.context.observation.frames[0].artifact.path
    )
    assert worker.policy_inputs(result.execution_observation)[
        "observation.images.overhead"
    ].shape == (3, 270, 480)
    record = json.loads(result.revalidation_path.read_text())
    assert record["fresh_planner_capture"]["mode"] == "live_paused_v1"
    assert (
        record["fresh_planner_capture"]["calibration"]["sha256"]
        == job.original_capture.calibration.sha256
    )
    assert len(hd_captures) == 3


@pytest.mark.parametrize(
    "fault",
    [
        "pixels",
        "render_model",
        "calibration",
        "profile",
        "policy_artifact",
    ],
)
def test_hd_changed_pixels_or_render_identity_rejects(setup, fault):
    worker, _, clock, _ = setup
    worker._planner_render_capture = lambda env: np.zeros((1080, 1920, 3), np.uint8)
    session = LivePlanningSession(worker, camera_profile="overhead1920_wrist480_v1")
    job = session.begin()
    clock.now += 95_000_000_000
    if fault == "pixels":

        def changed(env):
            pixels = np.zeros((1080, 1920, 3), np.uint8)
            pixels[0, 0, 0] = 1
            return pixels

        worker._planner_render_capture = changed
    elif fault == "render_model":
        worker._planner_model.geom_friction[0, 0] += 0.1
    elif fault == "calibration":
        (worker.directory / job.original_capture.calibration.path).write_text("{}")
    elif fault == "policy_artifact":
        (
            worker.directory / job.original_capture.policy_observation.frames[0].artifact.path
        ).write_bytes(b"changed original ACT camera")
    else:
        session.camera_profile = "policy480_v1"
    with pytest.raises(ValueError):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().active is None and worker._env.data.time == 0


def test_hd_rejects_upscaled_profile_shape_and_releases_pause(setup):
    worker, _, _, _ = setup
    worker._planner_render_capture = lambda env: np.zeros((270, 480, 3), np.uint8)
    session = LivePlanningSession(worker, camera_profile="overhead1920_wrist480_v1")
    with pytest.raises(ValueError, match="1920 x 1080"):
        session.begin()
    assert worker._planning_pause is None and worker._env.data.time == 0


@pytest.mark.parametrize("fault", ["state", "model", "task", "generation", "context", "pixels"])
def test_changed_pause_provenance_rejects_late_proposals(setup, fault):
    worker, session, clock, _ = setup
    job = session.begin()
    clock.now += 95_000_000_000
    if fault == "state":
        worker._env.data.qvel[0] += 0.01
    elif fault == "model":
        worker._env.model.geom_friction[0, 0] += 0.1
    elif fault == "task":
        worker.supervisor.load_task(task(worker.episode_id, identity="replacement", revision=1))
    elif fault == "generation":
        worker._generation = "replacement-generation"
    elif fault == "context":
        (session.directory / job.job_id / "job.json").write_text("{}")
    else:
        worker._render_capture = lambda env: {
            name: np.full((270, 480, 3), 255, np.uint8) for name in CAMERAS
        }
    with pytest.raises((ValueError, RuntimeError)):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().active is None and worker._env.data.time == 0
    assert (session.directory / job.job_id / "model-response.json").exists()
    assert (session.directory / job.job_id / "rejected.json").exists()
    with pytest.raises(RuntimeError, match="consumed"):
        session.complete(job.job_id, response(job))


def test_cancel_revokes_authority_before_model_returns(setup):
    worker, session, clock, _ = setup
    job = session.begin()
    session.cancel(job.job_id)
    clock.now += 95_000_000_000
    with pytest.raises(RuntimeError, match="cancelled"):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().state == "cancelled"
    assert not worker._env.active and not worker.control.pending


def test_cancelling_old_job_does_not_cancel_replacement_task(setup):
    worker, session, _, _ = setup
    job = session.begin()
    worker.supervisor.load_task(task(worker.episode_id, identity="replacement", revision=1))
    session.cancel(job.job_id)
    assert worker.supervisor.snapshot().state == "ready" and worker._env.active
    assert session.begin().context.observation.instruction_revision == 1


@pytest.mark.parametrize("skill,state", [("stop", "cancelled"), ("clarify", "needs_clarification")])
def test_stop_clarify_do_not_execute_or_claim_completion(setup, skill, state):
    worker, session, clock, _ = setup
    job = session.begin()
    clock.now += 95_000_000_000
    result = session.complete(job.job_id, response(job, skill))
    assert result.attempt is None and result.supervisor_state == state
    assert worker._env.data.time == 0 and not worker.control.pending
    assert not worker.supervisor.snapshot().completed_steps


def test_consumed_job_cannot_dispatch_twice(setup):
    worker, session, clock, _ = setup
    job = session.begin()
    with pytest.raises(RuntimeError, match="already owned"):
        session.begin()
    clock.now += 1
    session.complete(job.job_id, response(job))
    with pytest.raises(RuntimeError, match="consumed"):
        session.complete(job.job_id, response(job))
    assert len(worker.supervisor.snapshot().attempts) == 0


def test_external_model_failure_releases_pause_without_fake_attempt(setup):
    worker, session, _, _ = setup
    job = session.begin()
    session.fail(job.job_id, RuntimeError("model worker failed"))
    assert worker.supervisor.snapshot().active is None
    assert (session.directory / job.job_id / "model-error.json").exists()
    assert session.begin().job_id != job.job_id


def test_expired_planning_job_never_dispatches(setup):
    worker, session, clock, _ = setup
    job = session.begin()
    clock.now = job.deadline_ns
    with pytest.raises(TimeoutError, match="expired"):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().active is None


def test_failed_step_recovery_cannot_use_planning_pause(setup):
    worker, session, _, _ = setup
    observation = worker.capture()
    attempt = worker.supervisor.dispatch(observation)
    worker.supervisor.finish(
        attempt.attempt_id, observation, executor_outcome="failed", reason="Fixture failure"
    )
    assert worker.supervisor.snapshot().state == "awaiting_observation"
    with pytest.raises(RuntimeError, match="ready"):
        session.begin()


def test_successful_step_uses_stationary_transition_internally(setup):
    worker, session, clock, _ = setup
    before = worker.capture()
    attempt = worker.supervisor.dispatch(before)
    worker.bind(attempt.attempt_id, policy_sha256="a" * 64, chunk_size=1)
    worker.offer(attempt.attempt_id, np.tile(worker._env.home, (1, 1)), before)
    worker.step(attempt.attempt_id, before)
    clock.now += 50_000_000
    terminal = worker.capture()
    worker.finish(
        attempt.attempt_id,
        terminal,
        executor_outcome="succeeded",
        reason="Trusted fixture termination only",
    )
    clock.now += 1
    job = session.begin()
    clock.now += 95_000_000_000
    result = session.complete(job.job_id, response(job))
    assert result.attempt.step_id == "second"
    assert result.execution_observation.sequence == terminal.sequence
    assert worker._env.data.time == terminal.simulation_seconds
    assert any(
        event.kind == "stationary_recapture" for event in worker.supervisor.snapshot().events
    )


@pytest.mark.parametrize("fault", ["deadline", "task"])
def test_pending_poll_revokes_authority_before_model_finishes(setup, fault):
    worker, session, clock, _ = setup
    job = session.begin()
    if fault == "deadline":
        clock.now = job.deadline_ns
    else:
        worker.supervisor.load_task(task(worker.episode_id, identity="replacement", revision=1))
    with pytest.raises((TimeoutError, ValueError)):
        session.check_pending(job.job_id)
    with pytest.raises(RuntimeError, match="consumed"):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().active is None
    assert worker.supervisor.snapshot().state == "ready"
    assert worker._planning_pause is None


def test_job_deadline_crossing_during_recapture_prevents_dispatch(setup):
    worker, session, clock, _ = setup
    job = session.begin()
    clock.now = job.deadline_ns - 1
    original = worker._render_capture

    def slow_recapture(env):
        result = original(env)
        clock.now += 2
        return result

    worker._render_capture = slow_recapture
    with pytest.raises(TimeoutError, match="expired"):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().active is None
    assert worker._env.data.time == 0 and worker._planning_pause is None


def test_failed_dispatch_evidence_write_closes_new_attempt(setup, monkeypatch):
    worker, session, clock, _ = setup
    job = session.begin()
    clock.now += 1
    original = session._write

    def broken_write(job_id, filename, payload):
        if filename == "dispatch.json":
            raise OSError("disk fixture failure")
        return original(job_id, filename, payload)

    monkeypatch.setattr(session, "_write", broken_write)
    with pytest.raises(OSError, match="disk"):
        session.complete(job.job_id, response(job))
    snapshot = worker.supervisor.snapshot()
    assert snapshot.active is None and snapshot.attempts[-1].outcome == "failed"
    assert worker._env.data.time == 0 and not worker.control.pending


def test_reused_camera_paths_cannot_be_presented_as_recapture(setup, monkeypatch):
    worker, session, clock, _ = setup
    job = session.begin()
    clock.now += 1
    original = job.context.observation
    # A timestamp edit with the original artifact paths is not a new capture.
    altered = original.model_copy(
        update={
            "observed_monotonic_ns": clock.now,
            "frames": tuple(
                frame.model_copy(update={"observed_monotonic_ns": clock.now})
                for frame in original.frames
            ),
        }
    )
    monkeypatch.setattr(worker, "capture_planning_pause", lambda pause_id: altered)
    with pytest.raises(ValueError, match="recapture"):
        session.complete(job.job_id, response(job))
    assert worker.supervisor.snapshot().active is None


@pytest.mark.render
def test_actual_camera_recovery_recaptures_without_unowned_physics(setup):
    worker, session, clock, _ = setup
    worker._render_capture = None
    before = worker.capture()
    attempt = worker.supervisor.dispatch(before)
    worker.bind(attempt.attempt_id, policy_sha256="a" * 64, chunk_size=1)
    worker.offer(attempt.attempt_id, np.tile(worker._env.home, (1, 1)), before)
    worker.step(attempt.attempt_id, before)
    clock.now += 50_000_000
    terminal = worker.capture()
    worker.finish(
        attempt.attempt_id,
        terminal,
        executor_outcome="failed",
        reason="Declared incomplete fixture, not learned recovery success",
        recoverable_failure=True,
    )
    assert worker.recovery_available()
    clock.now += 1
    job = session.begin()
    assert job.context.retry_number == 1
    assert job.failed_attempt_id == attempt.attempt_id
    clock.now += 1
    result = session.complete(job.job_id, response(job))
    assert result.attempt.number == 2
    assert result.attempt.step_id == attempt.step_id
    assert result.execution_observation.sequence == terminal.sequence
    assert worker._env.data.time == terminal.simulation_seconds
    assert all(
        fresh.artifact.path != old.artifact.path and fresh.artifact.sha256 == old.artifact.sha256
        for fresh, old in zip(result.execution_observation.frames, terminal.frames, strict=True)
    )
    assert len(worker.supervisor.snapshot().attempts) == 1
    assert not worker.recovery_available()
