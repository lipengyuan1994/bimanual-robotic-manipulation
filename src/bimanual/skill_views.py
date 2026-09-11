"""Verified training views of one nominal dinner recording, never new scene samples."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from bimanual.contracts import Artifact, Contract, Counter, DemonstrationEpisode, Digest, Identifier
from bimanual.dual_arm import CAMERAS, JOINT_ORDER
from bimanual.evidence import Manifest, canonical, digest_file

INTERVALS = (
    ("handoff_transfer", 0, 630),
    ("bar_place_and_return", 630, 1570),
    ("cup_pick_place", 1570, 2089),
    ("plate_pick_place", 2089, 2851),
    ("drawer_open", 2851, 3411),
    ("spoon_retrieve_place", 3411, 4115),
    ("fork_retrieve_place", 4115, 4819),
)
BOUNDARY_PHASES = (
    ("handoff/settle", "handoff/receiver_hold"),
    ("handoff/donor_park", "handoff/receiver_return"),
    ("cup/transition_home", "cup/settled"),
    ("plate/transition_home", "plate/settled"),
    ("utensils/transition_home", "utensils/released_hold"),
    ("utensils/spoon_approach", "utensils/spoon_settled"),
    ("utensils/fork_approach", "utensils/fork_settled"),
)
# This view profile is specific to the existing authored teacher, not arbitrary scenes.
PLAN_SHA256 = "9fb9baa727c607bd7fd94db4309f99b0e386073dc9e70d0708db024ee5dc58f1"

INTERVALS_V2 = (
    ("handoff_transfer", 0, 630),
    ("bar_place_and_return", 630, 1580),
    ("cup_pick_place", 1580, 2099),
    ("plate_pick_place", 2099, 3081),
    ("drawer_open", 3081, 3641),
    ("spoon_retrieve_place", 3641, 4345),
    ("fork_retrieve_place", 4345, 5049),
)
PLAN_SHA256_V2 = "0c93816e3791ac577cc3284fc8b9932ee0e34a2f067eca805ad12f72117b9231"
PROFILES = {
    "dinner_nominal_skill_views_v1": (INTERVALS, PLAN_SHA256),
    "dinner_nominal_skill_views_v2": (INTERVALS_V2, PLAN_SHA256_V2),
}


class SkillView(Contract):
    skill_id: Identifier
    parent_episode_id: Identifier
    start: Counter
    end: Counter
    terminal_parent_frame: Counter

    @model_validator(mode="after")
    def fixed_interval(self):
        if (self.skill_id, self.start, self.end) not in (*INTERVALS, *INTERVALS_V2):
            raise ValueError("Unsupported skill interval or cross-skill range")
        if self.terminal_parent_frame != self.end:
            raise ValueError("Skill terminal must be the original parent end observation")
        return self


class SkillViews(Contract):
    profile: Literal["dinner_nominal_skill_views_v1", "dinner_nominal_skill_views_v2"] = (
        "dinner_nominal_skill_views_v1"
    )
    parent_run_id: Identifier
    parent_episode_id: Identifier
    parent_source_sha256: Digest
    source_manifest_sha256: Digest
    export_manifest_sha256: Digest
    seed: Literal[0] = 0
    split: Literal["train"] = "train"
    independent_scene_count: Literal[1] = 1
    parent_transitions: Literal[4819, 5049] = 4819
    derivation_source_sha256: Digest
    artifacts: tuple[Artifact, ...]
    views: tuple[SkillView, ...] = Field(min_length=7, max_length=7)
    manifest_sha256: Digest

    @model_validator(mode="after")
    def fixed_partition(self):
        intervals, _ = PROFILES[self.profile]
        if self.parent_transitions != intervals[-1][2]:
            raise ValueError("Profile and parent transition count disagree")
        if tuple((view.skill_id, view.start, view.end) for view in self.views) != intervals:
            raise ValueError("Skill views must partition the original nominal episode exactly")
        if any(view.parent_episode_id != self.parent_episode_id for view in self.views):
            raise ValueError("A skill view cannot invent a different parent episode")
        if len({artifact.path for artifact in self.artifacts}) != len(self.artifacts):
            raise ValueError("Duplicate skill-view artifact paths")
        return self


class ActionWindow(Contract):
    parent_observation_index: Counter
    parent_action_indices: tuple[Counter, ...]
    action_is_pad: tuple[StrictBool, ...]
    terminal_parent_frame: Counter


def action_window(view: SkillView, local_index: int, chunk_size: int) -> ActionWindow:
    """Indices only: preserve original observations and repeat the last in-skill action.

    Phase names are not returned; padding applies only to training targets. The
    terminal parent observation is evidence, never an additional action target.
    """
    view = SkillView.model_validate(dict(view))
    if type(local_index) is not int or not 0 <= local_index < view.end - view.start:
        raise ValueError("Local frame index is outside the skill view")
    if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
        raise ValueError("Action horizon must contain between one and 100 steps")
    parent = view.start + local_index
    return ActionWindow(
        parent_observation_index=parent,
        parent_action_indices=tuple(
            min(parent + offset, view.end - 1) for offset in range(chunk_size)
        ),
        action_is_pad=tuple(parent + offset >= view.end for offset in range(chunk_size)),
        terminal_parent_frame=view.end,
    )


def validate_action_window(view: SkillView, local_index: int, window: ActionWindow) -> None:
    """Reject caller-supplied windows that reach into a different skill or alter padding."""
    # JSON-mode serialization coerces malformed bool-as-int values to integers.
    window = ActionWindow.model_validate(dict(window))
    expected = action_window(view, local_index, len(window.parent_action_indices))
    if window != expected:
        raise ValueError("Action indices or padding cross the verified skill boundary")


def _lines(path: Path) -> list[dict]:
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def _verified_inputs(dataset_root: Path) -> dict:
    # No LeRobot/model import or export: validate the existing sealed dataset only.
    from bimanual.training import verify_training_dataset

    dataset_root = dataset_root.resolve(strict=True)
    exported = verify_training_dataset(dataset_root)
    if len(exported["episodes"]) != 1 or exported["frames"] not in (4819, 5049):
        raise ValueError("Skill views require one complete nominal dinner export")
    entry = exported["episodes"][0]
    relative = f"{entry['raw_root']}/manifest.json"
    raw_manifest_path = Artifact(path=relative, sha256=entry["evidence_manifest_sha256"]).verify(
        dataset_root
    )
    raw = raw_manifest_path.parent
    source = Manifest.model_validate_json(raw_manifest_path.read_text())
    if (
        hashlib.sha256(canonical(source.model_dump(exclude={"manifest_sha256"}))).hexdigest()
        != source.manifest_sha256
    ):
        raise ValueError("Original source manifest seal mismatch")
    if source.kind != "dinner_teacher" or source.outcome != "completed":
        raise ValueError("Only a completed dinner teacher recording can supply skill views")
    if source.metrics.get("score", {}).get("full_workflow_success") is not True:
        raise ValueError("Source dinner physics audit did not pass")
    for name, expected in source.files.items():
        Artifact(path=name, sha256=expected).verify(raw)
    actual = {
        p.relative_to(raw).as_posix()
        for p in raw.rglob("*")
        if p.is_file() and p != raw_manifest_path
    }
    if actual != set(source.files):
        raise ValueError("Copied source contains unsealed artifacts")
    episode = DemonstrationEpisode.model_validate_json(
        (raw / "demonstration/episode.json").read_text()
    )
    lineage = episode.lineage
    if (
        episode.outcome,
        episode.interventions,
        lineage.controller_kind,
        lineage.seed,
        lineage.split,
    ) != ("success", 0, "scripted_teacher", 0, "train"):
        raise ValueError("Skill views require successful fixed-seed0/train teacher evidence")
    if (
        lineage.code_revision != source.provenance.get("git_revision")
        or lineage.source_sha256 != source.provenance.get("source_sha256")
        or entry["lineage"] != lineage.model_dump()
    ):
        raise ValueError("Recording/export/source lineage mismatch")
    if (lineage.scene.path, lineage.config.path, lineage.controller.path) != (
        "scene.xml",
        "config.json",
        "controller.json",
    ):
        raise ValueError("Unsupported dinner controller lineage paths")
    for artifact in (lineage.scene, lineage.config, lineage.controller):
        artifact.verify(raw)
    controller = json.loads(lineage.controller.verify(raw).read_text())
    config = json.loads(lineage.config.verify(raw).read_text())
    if config.get("visual_seed") is not None:
        raise ValueError("Visual variants require a separate skill-view profile; not nominal data")
    if (
        controller.get("kind"),
        controller.get("seed"),
        controller.get("split"),
        controller.get("teacher_uses_simulator_truth"),
        controller.get("plan"),
    ) != ("scripted_teacher", 0, "train", True, "teacher-assets/plan.json.gz") or config.get(
        "record_demonstration"
    ) is not True:
        raise ValueError("Wrong dinner demonstration controller or recording configuration")
    if type(controller.get("seed")) is not int:
        raise ValueError("Controller seed must be the original integer seed0")
    score = json.loads((raw / "score.json").read_text())
    if score != source.metrics["score"] or score.get("full_workflow_success") is not True:
        raise ValueError("Stored physical audit disagrees with completed source")
    recipe = config.get("recipe", "v1")
    profile = f"dinner_nominal_skill_views_{recipe}"
    if profile not in PROFILES:
        raise ValueError("Unsupported dinner recipe")
    intervals, plan_sha256 = PROFILES[profile]
    transitions = intervals[-1][2]
    if exported["frames"] != transitions:
        raise ValueError("Recipe and exported transition count disagree")
    if recipe == "v2":
        independent = json.loads((raw / "independent-score.json").read_text())
        if (
            independent != source.metrics.get("independent_score")
            or independent.get("independent_task_success") is not True
        ):
            raise ValueError("V2 independent physical audit did not pass")
    plan_path = raw / "teacher-assets/plan.json.gz"
    assets = json.loads((raw / "teacher-assets/manifest.json").read_text())
    if (
        digest_file(plan_path) != plan_sha256
        or controller.get("plan_sha256") != plan_sha256
        or assets.get("files", {}).get("plan.json.gz") != plan_sha256
        or assets.get("action_count") != transitions
        or assets.get("files", {}).get("scene.xml") != lineage.scene.sha256
    ):
        raise ValueError("Unsupported authored dinner plan or scene identity")
    plan = json.loads(gzip.decompress(plan_path.read_bytes()))
    if (
        plan.get("physics_hz"),
        plan.get("control_hz"),
        plan.get("joint_order"),
        plan.get("camera_order"),
    ) != (1000, 20, list(JOINT_ORDER), list(CAMERAS)):
        raise ValueError("Wrong dinner plan timing or mapping")
    phases = _lines(raw / "demonstration/phases.jsonl")
    actions = _lines(raw / "actions.jsonl")
    if (
        len(phases) != transitions + 1
        or len(actions) != transitions
        or len(episode.frames) != transitions + 1
    ):
        raise ValueError("Incomplete phase, action or observation sequence")
    if len(plan["steps"]) != transitions:
        raise ValueError("Incomplete dinner plan")
    for index, (frame, sidecar) in enumerate(zip(episode.frames, phases, strict=True)):
        obs = frame.observation
        if type(sidecar.get("observation_sequence")) is not int or (
            sidecar.get("episode_id"),
            sidecar.get("observation_sequence"),
        ) != (
            episode.episode_id,
            index,
        ):
            raise ValueError("Phase sidecar episode/sequence mismatch")
        timestamp = sidecar.get("simulation_seconds")
        if (
            type(timestamp) not in (int, float)
            or not math.isfinite(timestamp)
            or timestamp != obs.simulation_seconds
        ):
            raise ValueError("Phase sidecar does not preserve observation time")
        if not math.isclose(obs.simulation_seconds, index / 20, rel_tol=0, abs_tol=1e-8):
            raise ValueError("Source recording is not a time-zero20Hz dinner trajectory")
        if sidecar.get("terminal") is not (index == transitions) or sidecar.get(
            "transition_applied"
        ) is not (index < transitions):
            raise ValueError("Incorrect terminal/applied sidecar marker")
        if index == transitions:
            if (
                frame.action_rad is not None
                or sidecar.get("phase") != plan["steps"][-1]["phase"]
                or sidecar.get("boundary") != "last_complete_control_boundary"
            ):
                raise ValueError("Dinner terminal must follow the last completed action")
            continue
        action, step = actions[index], plan["steps"][index]
        targets, timestamp = action.get("q"), action.get("t")
        if (
            not isinstance(targets, list)
            or len(targets) != 12
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in targets)
            or type(timestamp) not in (int, float)
            or not math.isfinite(timestamp)
        ):
            raise ValueError("Malformed applied action targets or timestamp")
        if action.get("applied") is not True or action.get("episode_id") != episode.episode_id:
            raise ValueError("Unapplied or foreign episode action in dinner source")
        if (
            sidecar.get("phase") != step["phase"]
            or action.get("phase") != step["phase"]
            or action.get("t") != obs.simulation_seconds
        ):
            raise ValueError("Phase/action/plan alignment mismatch")
        if action.get("q") != list(frame.action_rad) or action.get("q") != step["q"]:
            raise ValueError("Recorded action targets differ from applied authored plan")
    views = []
    for (skill, start, end), (first, last) in zip(intervals, BOUNDARY_PHASES, strict=True):
        if phases[start]["phase"] != first or phases[end - 1]["phase"] != last:
            raise ValueError("Skill partition does not match the phase sidecar")
        views.append(
            SkillView(
                skill_id=skill,
                parent_episode_id=episode.episode_id,
                start=start,
                end=end,
                terminal_parent_frame=end,
            )
        )
    names = (
        "manifest.json",
        "demonstration/episode.json",
        "demonstration/phases.jsonl",
        "actions.jsonl",
        "controller.json",
        "config.json",
        "scene.xml",
        "score.json",
        "teacher-assets/manifest.json",
        "teacher-assets/plan.json.gz",
    )
    if recipe == "v2":
        names += ("independent-score.json",)
    artifacts = [
        Artifact(
            path="export_manifest.json", sha256=digest_file(dataset_root / "export_manifest.json")
        )
    ]
    artifacts.extend(
        Artifact(path=f"{entry['raw_root']}/{name}", sha256=digest_file(raw / name))
        for name in names
    )
    return dict(
        profile=profile,
        parent_transitions=transitions,
        parent_run_id=source.run_id,
        parent_episode_id=episode.episode_id,
        parent_source_sha256=lineage.source_sha256,
        source_manifest_sha256=source.manifest_sha256,
        export_manifest_sha256=exported["manifest_sha256"],
        views=tuple(views),
        artifacts=tuple(artifacts),
    )


def create_skill_views(dataset_root: Path, manifest_path: Path) -> SkillViews:
    """Create an external immutable view manifest, without modifying or copying data."""
    dataset_root = dataset_root.resolve(strict=True)
    manifest_path = manifest_path.absolute()
    if manifest_path.exists() or manifest_path.is_symlink():
        raise FileExistsError("Skill-view manifest already exists")
    if manifest_path.resolve().is_relative_to(dataset_root):
        raise ValueError("Skill-view manifest must be outside the sealed dataset")
    inputs = _verified_inputs(dataset_root)
    body = SkillViews(
        **inputs, derivation_source_sha256=digest_file(Path(__file__)), manifest_sha256="0" * 64
    ).model_dump(mode="json", exclude={"manifest_sha256"})
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = SkillViews.model_validate(body)
    with manifest_path.open("x") as stream:
        stream.write(result.model_dump_json(indent=2) + "\n")
    return result


def load_skill_views(manifest_path: Path, *, dataset_root: Path) -> SkillViews:
    """Reverify all sealed provenance and boundaries before using a training view."""
    result = SkillViews.model_validate_json(manifest_path.read_text())
    body = result.model_dump(mode="json", exclude={"manifest_sha256"})
    if hashlib.sha256(canonical(body)).hexdigest() != result.manifest_sha256:
        raise ValueError("Skill-view manifest digest mismatch")
    expected = _verified_inputs(dataset_root)
    for name, value in expected.items():
        if getattr(result, name) != value:
            raise ValueError(f"Skill-view source linkage mismatch: {name}")
    return result
