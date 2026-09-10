import hashlib

import pytest
from PIL import Image
from pydantic import ValidationError

from bimanual.contracts import (
    ActionChunk,
    Artifact,
    DemonstrationEpisode,
    JointLimits,
    Observation,
    SkillRequest,
    validate_episode_artifacts,
    validate_split_seeds,
)
from bimanual.dual_arm import CAMERAS, JOINT_ORDER


def observation(sequence=0, **changes):
    capture = dict(
        sequence=sequence,
        simulation_seconds=sequence / 20,
        observed_monotonic_ns=100 + sequence * 50_000_000,
    )
    result = dict(
        episode_id="episode-1",
        instruction_revision=0,
        **capture,
        joint_position_rad=[0.0] * 12,
        joint_velocity_rad_s=[0.0] * 12,
        frames=[
            dict(
                camera=name,
                **capture,
                artifact=dict(path=f"frame-{sequence}-{i}.png", sha256="a" * 64),
            )
            for i, name in enumerate(CAMERAS)
        ],
    )
    result.update(changes)
    return result


def episode(**changes):
    result = dict(
        episode_id="episode-1",
        instruction="Pick the practice block",
        instruction_revision=0,
        lineage=dict(
            code_revision="a" * 40,
            source_sha256="b" * 64,
            scene=dict(path="scene.xml", sha256="c" * 64),
            config=dict(path="config.json", sha256="d" * 64),
            controller=dict(path="teacher.py", sha256="e" * 64),
            controller_kind="scripted_teacher",
            seed=7,
            split="train",
        ),
        joint_limits=dict(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        outcome="success",
        outcome_reason="Independent evaluator reports stable release",
        interventions=0,
        frames=[
            dict(observation=observation(0), action_rad=[0.5] * 12),
            dict(observation=observation(1), action_rad=None),
        ],
    )
    result.update(changes)
    return result


def action(**changes):
    result = dict(
        episode_id="episode-1",
        instruction_revision=0,
        observation_sequence=0,
        observed_monotonic_ns=100,
        generated_monotonic_ns=110,
        expires_monotonic_ns=200,
        policy_sha256="a" * 64,
        targets_rad=[[0.5] * 12],
    )
    result.update(changes)
    return ActionChunk.model_validate(result)


def validate_action(chunk, **changes):
    context = dict(
        now_monotonic_ns=120, max_observation_age_ns=100, expected_policy_sha256="a" * 64
    )
    context.update(changes)
    chunk.validate_for(
        Observation.model_validate(observation()),
        JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
        **context,
    )


def test_json_roundtrip_and_immutable_records():
    original = DemonstrationEpisode.model_validate(episode())
    assert DemonstrationEpisode.model_validate_json(original.model_dump_json()) == original
    assert original.frames[0].observation.joint_order == JOINT_ORDER
    with pytest.raises(ValidationError):
        original.outcome = "failure"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True, "0.5"])
def test_nonfinite_observations_and_actions_rejected(bad):
    with pytest.raises(ValidationError):
        Observation.model_validate(observation(joint_position_rad=[bad] * 12))
    with pytest.raises(ValidationError):
        action(targets_rad=[[bad] * 12])


@pytest.mark.parametrize(
    "changes",
    [
        {"object_positions": {"block": [0, 0, 0]}},
        {"teacher_truth": {}},
        {"joint_order": list(reversed(JOINT_ORDER))},
        {"joint_position_rad": [0.0] * 11},
        {"sequence": True},
        {"schema_version": 2},
    ],
)
def test_policy_boundary_and_mappings(changes):
    with pytest.raises(ValidationError):
        Observation.model_validate(observation(**changes))


def test_camera_order_identity_and_timestamp():
    for field, value in (
        ("sequence", 1),
        ("simulation_seconds", 0.05),
        ("observed_monotonic_ns", 99),
        ("camera", "right/wrist_cam"),
    ):
        data = observation()
        data["frames"][0][field] = value
        with pytest.raises(ValidationError):
            Observation.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"instruction_revision": 1},
        {"episode_id": "old"},
        {"observation_sequence": 1},
        {"observed_monotonic_ns": 99},
        {"policy_sha256": "b" * 64},
        {"targets_rad": [[0.5] * 12, [2.0] * 12]},
    ],
)
def test_reject_entire_chunk_on_stale_identity_or_later_invalid_target(changes):
    validate_action(action())
    with pytest.raises(ValueError):
        validate_action(action(**changes))


@pytest.mark.parametrize(
    "context",
    [
        {"now_monotonic_ns": 200},
        {"now_monotonic_ns": 109},
        {"max_observation_age_ns": 10},
        {"max_observation_age_ns": 0},
    ],
)
def test_action_freshness(context):
    with pytest.raises(ValueError):
        validate_action(action(), **context)


@pytest.mark.parametrize(
    "changes",
    [
        {"skill": "teleport"},
        {"target": "unknown"},
        {"world_position": [0, 0, 0]},
        {"arm": "both"},
        {"destination": "table"},
    ],
)
def test_malformed_planner_output_rejected(changes):
    request = dict(
        episode_id="episode-1",
        instruction_revision=0,
        observation_sequence=0,
        skill="pick",
        arm="left",
        target="spoon",
        explanation="Spoon is visible",
    )
    request.update(changes)
    with pytest.raises(ValidationError):
        SkillRequest.model_validate(request)


def test_handoff_and_clarification_semantics():
    base = dict(episode_id="episode-1", instruction_revision=0, observation_sequence=0)
    SkillRequest(
        **base,
        skill="handoff",
        arm="both",
        target="spoon",
        destination="right_gripper",
        explanation="Right arm will receive spoon",
    )
    SkillRequest(**base, skill="clarify", arm="none", explanation="Which cup?")
    with pytest.raises(ValidationError):
        SkillRequest(**base, skill="clarify", arm="none", target="cup", explanation="Which?")


@pytest.mark.parametrize("fault", ["gap", "clock", "terminal", "missing_action", "bounds"])
def test_episode_transition_alignment(fault):
    data = episode()
    if fault == "gap":
        data["frames"][1]["observation"] = observation(2)
    elif fault == "clock":
        data["frames"][1]["observation"] = observation(1, observed_monotonic_ns=99)
    elif fault == "terminal":
        data["frames"][1]["action_rad"] = [0.0] * 12
    elif fault == "missing_action":
        data["frames"][0]["action_rad"] = None
    else:
        data["frames"][0]["action_rad"] = [2.0] * 12
    with pytest.raises(ValidationError):
        DemonstrationEpisode.model_validate(data)


def test_failures_and_interventions_retained_and_seed_leakage_rejected():
    failed = DemonstrationEpisode.model_validate(
        episode(outcome="failure", outcome_reason="Failed physical hold", interventions=1)
    )
    assert failed.interventions == 1 and failed.outcome == "failure"
    data = episode()
    data["episode_id"] = "episode-2"
    for frame in data["frames"]:
        frame["observation"]["episode_id"] = "episode-2"
    data["lineage"]["split"] = "test"
    test_episode = DemonstrationEpisode.model_validate(data)
    with pytest.raises(ValueError, match="Seed leakage"):
        validate_split_seeds((failed, test_episode))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_split_seeds((failed, failed))


@pytest.mark.parametrize("path", ["../scene", "/scene", "a/../scene", "a\\scene", "", "."])
def test_artifact_paths_confined(path):
    with pytest.raises(ValidationError):
        Artifact(path=path, sha256="a" * 64)


def test_verify_files_and_decode_actual_images(tmp_path):
    data = episode()
    for name in ("scene", "config", "controller"):
        ref = data["lineage"][name]
        (tmp_path / ref["path"]).write_text("fixture")
        ref["sha256"] = hashlib.sha256(b"fixture").hexdigest()
    for frame in data["frames"]:
        for camera in frame["observation"]["frames"]:
            path = tmp_path / camera["artifact"]["path"]
            Image.new("RGB", (480, 270)).save(path)
            camera["artifact"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = DemonstrationEpisode.model_validate(data)
    validate_episode_artifacts(record, tmp_path)
    path = tmp_path / data["frames"][0]["observation"]["frames"][0]["artifact"]["path"]
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_episode_artifacts(record, tmp_path)


def test_image_encoding_not_just_digest_checked(tmp_path):
    data = episode()
    (tmp_path / "wrong.png").write_bytes(b"valid hash but invalid image")
    digest = hashlib.sha256((tmp_path / "wrong.png").read_bytes()).hexdigest()
    reference = dict(path="wrong.png", sha256=digest)
    for name in ("scene", "config", "controller"):
        data["lineage"][name] = reference
    for frame in data["frames"]:
        for camera in frame["observation"]["frames"]:
            camera["artifact"] = reference
    with pytest.raises(OSError):
        validate_episode_artifacts(DemonstrationEpisode.model_validate(data), tmp_path)


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    (root / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        Artifact(path="escape", sha256=hashlib.sha256(b"outside").hexdigest()).verify(root)


def test_zero_transition_failure_is_retained():
    data = episode(outcome="failure", outcome_reason="Object missing before first action")
    data["frames"] = [dict(observation=observation(0), action_rad=None)]
    record = DemonstrationEpisode.model_validate(data)
    assert len(record.frames) == 1
