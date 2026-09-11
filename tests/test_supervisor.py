from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from bimanual.contracts import Artifact, CameraFrame, Observation, SkillRequest
from bimanual.dual_arm import CAMERAS
from bimanual.supervisor import Capability, StepSpec, TaskSpec, TaskSupervisor, VisibleAssessment


@dataclass
class Clock:
    now: int = 100

    def __call__(self):
        return self.now


def observation(sequence=0, *, captured=100, revision=0, episode="episode"):
    return Observation(
        episode_id=episode,
        instruction_revision=revision,
        sequence=sequence,
        simulation_seconds=sequence * 0.05,
        observed_monotonic_ns=captured,
        joint_position_rad=[0.0] * 12,
        joint_velocity_rad_s=[0.0] * 12,
        frames=tuple(
            CameraFrame(
                camera=camera,
                sequence=sequence,
                simulation_seconds=sequence * 0.05,
                observed_monotonic_ns=captured,
                artifact=Artifact(path=f"{sequence}-{i}.png", sha256="0" * 64),
            )
            for i, camera in enumerate(CAMERAS)
        ),
    )


def task(*, identity="task", revision=0, steps=1, retries=2):
    plan = [
        StepSpec(step_id="drawer", capability_id="drawer-left", timeout_ns=50, max_retries=retries)
    ]
    if steps == 2:
        plan.append(
            StepSpec(
                step_id="pick", capability_id="spoon-left", prerequisites=("drawer",), timeout_ns=50
            )
        )
    return TaskSpec(
        task_id=identity,
        episode_id="episode",
        instruction_revision=revision,
        instruction="Set the table",
        steps=tuple(plan),
    )


@pytest.fixture
def core():
    clock, clears = Clock(), []
    registry = [
        Capability(capability_id="drawer-left", skill="open_drawer", arm="left", target="drawer"),
        Capability(
            capability_id="spoon-left",
            skill="pick",
            arm="left",
            target="spoon",
            shared_workspace=False,
        ),
    ]
    supervisor = TaskSupervisor(
        registry,
        clear_actions=lambda: clears.append(clock.now),
        clock_ns=clock,
        max_observation_age_ns=20,
    )
    return supervisor, clock, clears


def test_serial_executor_lifecycle_does_not_award_evaluation_success(core):
    supervisor, clock, clears = core
    supervisor.load_task(task(steps=2))
    first = supervisor.dispatch(observation())
    assert first.arms == ("left",) and first.shared_workspace
    with pytest.raises(RuntimeError, match="not ready"):
        supervisor.dispatch(observation())
    clock.now = 110
    status = supervisor.finish(
        first.attempt_id,
        observation(1, captured=110),
        executor_outcome="succeeded",
        reason="Executor completed drawer skill",
    )
    assert status.completed_steps == ("drawer",) and status.state == "ready"
    with pytest.raises(ValueError, match="new observation"):
        supervisor.dispatch(observation(1, captured=110))
    clock.now = 111
    second = supervisor.dispatch(observation(2, captured=111))
    assert not second.shared_workspace
    clock.now = 120
    status = supervisor.finish(
        second.attempt_id,
        observation(3, captured=120),
        executor_outcome="succeeded",
        reason="Executor completed pick",
    )
    assert status.state == "execution_complete" and status.evaluation_success is None
    assert len(status.attempts) == 2 and len(clears) >= 5
    with pytest.raises(ValidationError):
        status.attempts[0].reason = "rewritten"
    with pytest.raises(ValidationError):
        first.request.explanation = "rewritten"


def test_planner_text_and_visible_assessment_cannot_claim_completion(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    with pytest.raises(TypeError, match="planner text"):
        supervisor.dispatch(observation(), proposal="all done")
    wrong = SkillRequest(
        episode_id="episode",
        instruction_revision=0,
        observation_sequence=0,
        skill="pick",
        target="spoon",
        arm="left",
        explanation="The drawer is complete",
    )
    with pytest.raises(ValueError, match="next registered"):
        supervisor.dispatch(observation(), proposal=wrong)
    ticket = supervisor.dispatch(observation())
    clock.now = 110
    state = supervisor.finish(
        ticket.attempt_id,
        observation(1, captured=110),
        executor_outcome="failed",
        reason="Executor detected missing grasp",
        visible_assessment=VisibleAssessment(
            state="apparently_complete", explanation="The camera looks complete"
        ),
    )
    assert state.state == "awaiting_observation" and not state.completed_steps
    assert state.attempts[-1].visible_assessment.state == "apparently_complete"
    assert state.evaluation_success is None


def test_exactly_two_retries_require_post_failure_observations(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    for number in range(1, 4):
        sequence = (number - 1) * 2
        ticket = supervisor.dispatch(observation(sequence, captured=clock.now))
        assert ticket.number == number
        clock.now += 1
        final = observation(sequence + 1, captured=clock.now)
        state = supervisor.finish(
            ticket.attempt_id, final, executor_outcome="failed", reason="Failed grasp"
        )
        if number < 3:
            assert state.state == "awaiting_observation"
            with pytest.raises(ValueError, match="new observation"):
                supervisor.dispatch(final)
        clock.now += 1
    assert state.state == "failed" and len(state.attempts) == 3
    with pytest.raises(RuntimeError):
        supervisor.dispatch(observation(6, captured=clock.now))


@pytest.mark.parametrize("fault", ["old_capture", "old_sequence", "old_simulation"])
def test_retry_identity_cannot_be_forged_with_one_new_field(core, fault):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    clock.now = 110
    final = observation(1, captured=110)
    supervisor.finish(ticket.attempt_id, final, executor_outcome="failed", reason="Failed")
    clock.now = 111
    candidate = observation(2, captured=111)
    if fault == "old_capture":
        candidate = observation(2, captured=110)
    elif fault == "old_sequence":
        candidate = observation(1, captured=111)
    else:
        values = candidate.model_dump()
        values["simulation_seconds"] = final.simulation_seconds
        for frame in values["frames"]:
            frame["simulation_seconds"] = final.simulation_seconds
        candidate = Observation.model_validate(values)
    with pytest.raises(ValueError, match="new observation|reused|consistently"):
        supervisor.dispatch(candidate)


def test_deadline_rejects_late_completion_and_clears_actions(core):
    supervisor, clock, clears = core
    supervisor.load_task(task(retries=0))
    ticket = supervisor.dispatch(observation())
    clock.now = ticket.deadline_ns
    with pytest.raises(RuntimeError, match="active attempt"):
        supervisor.finish(
            ticket.attempt_id,
            observation(1, captured=clock.now),
            executor_outcome="succeeded",
            reason="Too late",
        )
    state = supervisor.snapshot()
    assert state.state == "failed" and state.attempts[-1].outcome == "timed_out"
    assert clears[-1] == clock.now


def test_tick_times_out_without_executor_response(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    clock.now = ticket.deadline_ns
    assert supervisor.tick().state == "awaiting_observation"
    clock.now += 1
    assert supervisor.dispatch(observation(1, captured=clock.now)).number == 2


def test_cancel_and_task_change_reject_old_tickets_and_preserve_history(core):
    supervisor, clock, clears = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    assert supervisor.cancel().state == "cancelled"
    assert supervisor.snapshot().attempts[-1].outcome == "cancelled"
    with pytest.raises(ValueError, match="newer instruction"):
        supervisor.load_task(task(identity="replacement"))
    supervisor.load_task(task(identity="replacement", revision=1))
    replacement = supervisor.dispatch(observation(revision=1))
    with pytest.raises(RuntimeError):
        supervisor.authorize(ticket.attempt_id, observation(revision=1))
    clock.now += 1
    supervisor.load_task(task(identity="third", revision=2))
    state = supervisor.snapshot()
    assert state.state == "ready" and len(state.tasks) == 3
    assert state.attempts[-1].attempt == replacement and state.attempts[-1].outcome == "cancelled"
    assert len(clears) >= 7


@pytest.mark.parametrize(
    "fault", ["stale", "future", "wrong_episode", "wrong_revision", "wrong_arm"]
)
def test_executor_authorization_rejects_bad_context(core, fault):
    supervisor, clock, clears = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    kwargs = {}
    captured, revision, episode = 100, 0, "episode"
    if fault == "stale":
        clock.now = 121
    if fault == "future":
        captured = 101
    if fault == "wrong_episode":
        episode = "different"
    if fault == "wrong_revision":
        revision = 1
    if fault == "wrong_arm":
        kwargs["arm"] = "right"
    count = len(clears)
    with pytest.raises(ValueError):
        supervisor.authorize(
            ticket.attempt_id,
            observation(captured=captured, revision=revision, episode=episode),
            **kwargs,
        )
    assert len(clears) == count + 1


def test_stale_planner_observation_keeps_action_freshness_bound(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    clock.now = 130
    with pytest.raises(ValueError, match="stale"):
        supervisor.dispatch(observation())
    assert supervisor.snapshot().active is None


def test_clarification_requires_new_task_revision(core):
    supervisor, _, clears = core
    supervisor.load_task(task())
    proposal = SkillRequest(
        episode_id="episode",
        instruction_revision=0,
        observation_sequence=0,
        skill="clarify",
        arm="none",
        explanation="Which drawer?",
    )
    assert supervisor.dispatch(observation(), proposal=proposal) is None
    assert supervisor.snapshot().state == "needs_clarification" and len(clears) == 2
    with pytest.raises(RuntimeError):
        supervisor.dispatch(observation())


def test_unreachable_is_terminal_and_unchanged_observation_cannot_complete(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    with pytest.raises(ValueError, match="post-action"):
        supervisor.finish(
            ticket.attempt_id, observation(), executor_outcome="succeeded", reason="No motion"
        )
    assert supervisor.snapshot().active is None
    clock.now = 101
    ticket = supervisor.dispatch(observation(1, captured=101))
    assert (
        supervisor.finish(
            ticket.attempt_id,
            observation(1, captured=101),
            executor_outcome="unreachable",
            reason="Object missing",
        ).state
        == "failed"
    )


def test_clock_regression_and_queue_failure_fail_closed(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    supervisor.dispatch(observation())
    clock.now = 99
    with pytest.raises(RuntimeError, match="clock"):
        supervisor.tick()
    assert supervisor.snapshot().state == "failed" and supervisor.snapshot().active is None

    def broken():
        raise OSError("cannot clear")

    another = TaskSupervisor([], clear_actions=broken, clock_ns=clock)
    with pytest.raises(RuntimeError, match="worker must stop"):
        another.cancel()
    assert another.snapshot().state == "failed"


def test_registry_dependencies_and_retry_budget_are_validated(core):
    supervisor, _, _ = core
    with pytest.raises(ValueError, match="unregistered"):
        supervisor.load_task(
            TaskSpec(
                task_id="unknown",
                episode_id="episode",
                instruction_revision=0,
                instruction="test",
                steps=(StepSpec(step_id="x", capability_id="not-installed"),),
            )
        )
    with pytest.raises(ValidationError):
        StepSpec(step_id="x", capability_id="x", max_retries=3)
    with pytest.raises(ValidationError):
        TaskSpec(
            task_id="bad",
            episode_id="episode",
            instruction_revision=0,
            instruction="test",
            steps=(StepSpec(step_id="x", capability_id="x", prerequisites=("later",)),),
        )
    with pytest.raises(ValidationError):
        Capability(capability_id="invalid", skill="handoff", arm="left", target="spoon")
    assert supervisor.snapshot().state == "idle"


def test_real_guarded_action_queue_is_cleared_on_cancel():
    import numpy as np

    from bimanual.contracts import JointLimits
    from bimanual.policy_rollout import GuardedActionQueue

    clock = Clock()
    queue = GuardedActionQueue(
        JointLimits(lower_rad=[-2.0] * 12, upper_rad=[2.0] * 12),
        np.zeros(12),
        "a" * 64,
        20,
    )
    supervisor = TaskSupervisor(
        [Capability(capability_id="drawer-left", skill="open_drawer", arm="left", target="drawer")],
        clear_actions=queue.clear,
        clock_ns=clock,
        max_observation_age_ns=20,
    )
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    queue.offer(np.zeros((10, 12)), observation(), now_ns=clock.now)
    assert len(queue.pending) == 10
    supervisor.cancel()
    assert not queue.pending and queue.chunk is None and queue.anchor is None
    with pytest.raises(RuntimeError):
        supervisor.authorize(ticket.attempt_id, observation())


def test_handoff_lease_reserves_both_arms():
    clock = Clock()
    supervisor = TaskSupervisor(
        [
            Capability(
                capability_id="transfer",
                skill="handoff",
                arm="both",
                target="practice_block",
                destination="right_gripper",
            )
        ],
        clear_actions=lambda: None,
        clock_ns=clock,
    )
    supervisor.load_task(
        TaskSpec(
            task_id="handoff",
            episode_id="episode",
            instruction_revision=0,
            instruction="Transfer the object",
            steps=(StepSpec(step_id="transfer", capability_id="transfer"),),
        )
    )
    ticket = supervisor.dispatch(observation())
    assert ticket.arms == ("left", "right") and ticket.shared_workspace
    assert (
        supervisor.authorize(ticket.attempt_id, observation(), arm="left", shared_workspace=True)
        == ticket
    )
    assert (
        supervisor.authorize(ticket.attempt_id, observation(), arm="right", shared_workspace=True)
        == ticket
    )


@pytest.mark.parametrize("change", ["capture", "simulation", "joints"])
def test_same_sequence_with_changed_content_fails_attempt(core, change):
    supervisor, clock, clears = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    clock.now = 101
    values = observation().model_dump()
    if change == "capture":
        values["observed_monotonic_ns"] = 101
        for frame in values["frames"]:
            frame["observed_monotonic_ns"] = 101
    elif change == "simulation":
        values["simulation_seconds"] = 0.05
        for frame in values["frames"]:
            frame["simulation_seconds"] = 0.05
    else:
        values["joint_position_rad"] = (0.1,) + tuple(values["joint_position_rad"])[1:]
    with pytest.raises(ValueError, match="reused"):
        supervisor.authorize(ticket.attempt_id, Observation.model_validate(values))
    state = supervisor.snapshot()
    assert state.active is None and state.state == "awaiting_observation"
    assert state.attempts[-1].outcome == "failed" and clears[-1] == 101
    with pytest.raises(RuntimeError, match="active attempt"):
        supervisor.authorize(ticket.attempt_id, observation(1, captured=101))
    clock.now = 102
    assert supervisor.dispatch(observation(1, captured=102)).number == 2


def test_stale_observation_closes_attempt_not_just_pending_queue(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    clock.now = 121
    with pytest.raises(ValueError, match="stale"):
        supervisor.authorize(ticket.attempt_id, observation())
    assert supervisor.snapshot().active is None
    assert supervisor.snapshot().attempts[-1].outcome == "failed"
    with pytest.raises(RuntimeError):
        supervisor.finish(
            ticket.attempt_id,
            observation(1, captured=121),
            executor_outcome="succeeded",
            reason="Cannot resume a rejected attempt",
        )


def test_malformed_executor_result_closes_attempt(core):
    supervisor, clock, _ = core
    supervisor.load_task(task())
    ticket = supervisor.dispatch(observation())
    clock.now = 110
    with pytest.raises(ValueError, match="explicit executor"):
        supervisor.finish(
            ticket.attempt_id,
            observation(1, captured=110),
            executor_outcome="planner says success",
            reason="Untrusted result",
        )
    state = supervisor.snapshot()
    assert state.active is None and state.attempts[-1].outcome == "failed"


def test_registry_auxiliary_ownership_does_not_change_planner_request():
    capability = Capability(
        capability_id="drawer-left",
        skill="open_drawer",
        arm="left",
        target="drawer",
        auxiliary_arms=("right",),
    )
    supervisor = TaskSupervisor([capability], clear_actions=lambda: None, clock_ns=Clock())
    supervisor.load_task(task())
    proposal = capability.request("episode", 0, 0)
    assert proposal.arm == "left" and "auxiliary_arms" not in proposal.model_dump()
    attempt = supervisor.dispatch(observation(), proposal=proposal)
    assert attempt.arms == ("left", "right")
    assert (
        supervisor.authorize(attempt.attempt_id, observation(), arm="right", shared_workspace=True)
        == attempt
    )
    assert Capability(
        capability_id="plain", skill="open_drawer", arm="left", target="drawer"
    ).execution_arms == ("left",)
    with pytest.raises(ValidationError):
        SkillRequest.model_validate(proposal.model_dump() | {"auxiliary_arms": ["right"]})
    with pytest.raises(ValidationError):
        SkillRequest.model_validate(proposal.model_dump() | {"arm": "both"})


@pytest.mark.parametrize(
    "fields",
    [
        {"auxiliary_arms": ("left",)},
        {"auxiliary_arms": ("right", "right")},
        {"auxiliary_arms": ("right",), "shared_workspace": False},
        {"auxiliary_arms": ("both",)},
    ],
)
def test_invalid_auxiliary_permissions_rejected(fields):
    with pytest.raises(ValidationError):
        Capability(capability_id="bad", skill="open_drawer", arm="left", target="drawer", **fields)


def test_auxiliary_arm_order_is_canonical():
    capability = Capability(
        capability_id="bar",
        skill="place",
        arm="right",
        target="practice_block",
        destination="table",
        auxiliary_arms=("left",),
    )
    assert capability.execution_arms == ("left", "right")
