import json
from dataclasses import dataclass

import numpy as np
import pytest

from bimanual.dinner_control import DinnerControlWorker
from bimanual.dual_arm import CAMERAS
from bimanual.live_planning import LivePlanningSession
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
