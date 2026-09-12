import hashlib

import numpy as np
import pytest
from PIL import Image

from bimanual.contracts import DemonstrationEpisode, EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder, require_successful_training_episode
from bimanual.dual_arm import CAMERAS, JOINT_ORDER


def raw_observation(sequence=0):
    return dict(
        schema_version=1,
        episode_id="real-episode",
        sequence=sequence,
        simulation_seconds=sequence / 20,
        observed_monotonic_ns=100 + sequence * 50_000_000,
        joint_order=list(JOINT_ORDER),
        joint_position_rad=np.zeros(12),
        joint_velocity_rad_s=np.zeros(12),
        camera_order=list(CAMERAS),
        rgb={
            camera: np.full((270, 480, 3), i + sequence, dtype=np.uint8)
            for i, camera in enumerate(CAMERAS)
        },
    )


@pytest.fixture
def recorder(tmp_path):
    artifact = tmp_path / "lineage.txt"
    artifact.write_text("fixture provenance")
    ref = dict(path=artifact.name, sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    lineage = EpisodeLineage(
        code_revision="a" * 40,
        source_sha256="b" * 64,
        scene=ref,
        config=ref,
        controller=ref,
        controller_kind="scripted_teacher",
        seed=7,
        split="train",
    )
    return DemonstrationRecorder(
        tmp_path,
        instruction="Pick the practice block",
        instruction_revision=0,
        lineage=lineage,
        joint_limits=JointLimits(lower_rad=[-1.0] * 12, upper_rad=[1.0] * 12),
    )


def test_record_lossless_images_and_confirmed_actions(recorder):
    first = raw_observation()
    recorder.record(first, np.full(12, 0.5))
    # External mutable simulator buffers cannot modify saved records or images.
    first["rgb"]["overhead"][:] = 255
    first["joint_position_rad"][:] = 1
    recorder.record(raw_observation(1), None)
    path = recorder.finalize(outcome="success", outcome_reason="Independent release check passed")
    episode = DemonstrationEpisode.model_validate_json(path.read_text())
    require_successful_training_episode(episode)
    assert episode.frames[0].action_rad == (0.5,) * 12
    assert episode.frames[1].action_rad is None
    assert episode.frames[0].observation.joint_position_rad == (0.0,) * 12
    with Image.open(recorder.root / episode.frames[0].observation.frames[0].artifact.path) as image:
        assert np.asarray(image).max() == 0
    assert len(list(recorder.image_root.glob("*.png"))) == 6
    assert "object_position" not in path.read_text()
    with pytest.raises(ValueError, match="terminated"):
        recorder.record(raw_observation(2), None)
    with pytest.raises(ValueError, match="finalized"):
        recorder.finalize(outcome="success", outcome_reason="again")


@pytest.mark.parametrize("outcome", ["failure", "cancelled"])
def test_pre_action_failures_retained_but_not_training_eligible(recorder, outcome):
    recorder.record(raw_observation(), None)
    path = recorder.finalize(outcome=outcome, outcome_reason="Object unavailable", interventions=1)
    episode = DemonstrationEpisode.model_validate_json(path.read_text())
    assert episode.outcome == outcome and len(episode.frames) == 1
    with pytest.raises(ValueError, match="rejects"):
        require_successful_training_episode(episode)


@pytest.mark.parametrize(
    "fault", ["camera_missing", "dtype", "shape", "truth", "sequence", "action", "joint_nan"]
)
def test_reject_invalid_input_before_writing_images(recorder, fault):
    observation = raw_observation()
    action = [0.0] * 12
    if fault == "camera_missing":
        observation["rgb"].pop("overhead")
    elif fault == "dtype":
        observation["rgb"]["overhead"] = np.zeros((270, 480, 3), dtype=np.float32)
    elif fault == "shape":
        observation["rgb"]["overhead"] = np.zeros((270, 480), dtype=np.uint8)
    elif fault == "truth":
        observation["object_position"] = [0, 0, 0]
    elif fault == "sequence":
        observation["sequence"] = 1
    elif fault == "action":
        action[0] = 2.0
    else:
        observation["joint_position_rad"][0] = np.nan
    with pytest.raises(ValueError):
        recorder.record(observation, action)
    assert not list(recorder.image_root.iterdir()) and not recorder.frames


def test_reject_finalize_without_terminal_observation(recorder):
    recorder.record(raw_observation(), [0.0] * 12)
    with pytest.raises(ValueError, match="Terminal"):
        recorder.finalize(outcome="success", outcome_reason="not yet")
    assert not (recorder.root / "demonstration" / "episode.json").exists()


def test_reject_partial_step_timing_without_fabricating_transition(recorder):
    recorder.record(raw_observation(), [0.0] * 12)
    partial = raw_observation(1)
    partial["simulation_seconds"] = 0.025
    with pytest.raises(ValueError, match="discontinuity"):
        recorder.record(partial, None)
    assert len(recorder.frames) == 1


def test_provenance_corruption_prevents_finalization(recorder):
    recorder.record(raw_observation(), None)
    (recorder.root / "lineage.txt").write_text("changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        recorder.finalize(outcome="failure", outcome_reason="missing object")
