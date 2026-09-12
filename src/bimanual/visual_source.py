"""Verified visual teacher source intake; no LeRobot decoding or training."""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from bimanual.contracts import DemonstrationEpisode, validate_episode_artifacts
from bimanual.demonstrations import require_successful_training_episode
from bimanual.dinner_outcomes import score_dinner_outcomes
from bimanual.dinner_scoring import score_dinner
from bimanual.evidence import EvidenceStore, Manifest, digest_file
from bimanual.visual_training import load_visual_training_protocol
from bimanual.visual_variants import visual_variant


@dataclass(frozen=True)
class VerifiedVisualSource:
    root: Path
    manifest: Manifest
    episode: DemonstrationEpisode
    protocol_sha256: str
    episode_sha256: str
    physical_layout_count: int = 1
    lerobot_decoded_parity: None = None


def _json(path):
    return json.loads(path.read_text())


def _rows(path):
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rt") as stream:
        yield from (json.loads(line) for line in stream)


def verify_visual_source(run_root: Path, *, protocol_path: Path) -> VerifiedVisualSource:
    """Reverify frozen allocation, source integrity, visual regeneration and physics.

    Physics scores describe the logged simulation. Source instrumentation is a
    declaration, not detection of unlogged edits; RGB semantic grounding and
    decoded LeRobot parity require subsequent evaluation.
    """
    protocol = load_visual_training_protocol(protocol_path)
    root = Path(run_root).resolve(strict=True)
    if root.parent.name != "runs":
        raise ValueError("Expected a sealed evidence run under runs")
    store = EvidenceStore(root.parent.parent)
    source = store.verify(root.name)
    if source.kind != "dinner_teacher" or source.outcome != "completed":
        raise ValueError("Visual source requires completed dinner teacher evidence")
    config = _json(root / "config.json")
    protocol.require_training_seed(config.get("visual_seed"))
    if (
        config != source.config
        or config.get("recipe") != "v2"
        or config.get("record_demonstration") is not True
    ):
        raise ValueError("Visual source requires a recorded v2 teacher and matching config")
    seed = config["visual_seed"]
    assets = Path(str(files("bimanual") / "models/dinner_teacher_v2"))
    expected_scene, report = visual_variant((assets / "scene.xml").read_text(), seed=seed)
    if (root / "scene.xml").read_text() != expected_scene or (
        root / "teacher-assets/scene.xml"
    ).read_text() != expected_scene:
        raise ValueError("Visual scene differs from the pinned visual-only transformation")
    if _json(root / "teacher-assets/visual-variant.json") != report:
        raise ValueError("Visual variant report mismatch")
    expected_layout = _json(assets / "layout.json")
    expected_layout["scene_sha256"] = report["variant_xml_sha256"]
    layout = _json(root / "teacher-assets/layout.json")
    if layout != expected_layout:
        raise ValueError("Visual variant changed the physical layout")
    asset_manifest = _json(root / "teacher-assets/manifest.json")
    expected_assets = _json(assets / "manifest.json")
    expected_assets["files"]["scene.xml"] = digest_file(root / "teacher-assets/scene.xml")
    expected_assets["files"]["layout.json"] = digest_file(root / "teacher-assets/layout.json")
    if (
        asset_manifest != expected_assets
        or digest_file(root / "teacher-assets/plan.json.gz") != protocol.plan_sha256
    ):
        raise ValueError("Visual teacher assets or targets differ from pinned recipe")
    controller = _json(root / "controller.json")
    if (
        any(
            controller.get(key) != value
            for key, value in dict(
                kind="scripted_teacher",
                seed=seed,
                split="train",
                teacher_uses_simulator_truth=True,
                plan="teacher-assets/plan.json.gz",
                plan_sha256=protocol.plan_sha256,
                visual_variant="teacher-assets/visual-variant.json",
            ).items()
        )
        or type(controller.get("seed")) is not int
        or controller.get("teacher_uses_simulator_truth") is not True
    ):
        raise ValueError("Visual controller lineage mismatch")
    episode_path = root / "demonstration/episode.json"
    episode = DemonstrationEpisode.model_validate_json(episode_path.read_bytes())
    require_successful_training_episode(episode)
    lineage = episode.lineage
    if (
        (lineage.seed, lineage.split, lineage.controller_kind)
        != (seed, "train", "scripted_teacher")
        or lineage.code_revision != source.provenance.get("git_revision")
        or lineage.source_sha256 != source.provenance.get("source_sha256")
    ):
        raise ValueError("Visual episode source lineage mismatch")
    if (lineage.scene.path, lineage.config.path, lineage.controller.path) != (
        "scene.xml",
        "config.json",
        "controller.json",
    ):
        raise ValueError("Unsupported visual episode lineage paths")
    validate_episode_artifacts(episode, root)
    plan = json.loads(gzip.decompress((root / "teacher-assets/plan.json.gz").read_bytes()))
    actions = list(_rows(root / "actions.jsonl"))
    phases = list(_rows(root / "demonstration/phases.jsonl"))
    if len(actions) != 5049 or len(episode.frames) != 5050 or len(phases) != 5050:
        raise ValueError("Visual source must preserve the complete v2 trajectory")
    for index, (frame, phase) in enumerate(zip(episode.frames, phases, strict=True)):
        final = index == 5049
        obs = frame.observation
        step = plan["steps"][min(index, 5048)]
        if (
            obs.sequence != index
            or not math.isclose(obs.simulation_seconds, index / 20, abs_tol=1e-8, rel_tol=0)
            or phase.get("episode_id") != episode.episode_id
            or type(phase.get("observation_sequence")) is not int
            or phase["observation_sequence"] != index
            or type(phase.get("simulation_seconds")) not in (int, float)
            or phase.get("simulation_seconds") != obs.simulation_seconds
            or phase.get("phase") != step["phase"]
            or phase.get("terminal") is not final
            or phase.get("transition_applied") is not (not final)
        ):
            raise ValueError("Visual source phase/time mapping mismatch")
        if final:
            if (
                frame.action_rad is not None
                or phase.get("boundary") != "last_complete_control_boundary"
            ):
                raise ValueError("Invalid terminal visual observation")
        else:
            action = actions[index]
            targets = action.get("q")
            if (
                not isinstance(targets, list)
                or len(targets) != 12
                or any(
                    type(value) not in (int, float) or not math.isfinite(value) for value in targets
                )
                or type(action.get("t")) not in (int, float)
            ):
                raise ValueError("Malformed visual action targets or timestamp")
            if (
                action.get("applied") is not True
                or action.get("episode_id") != episode.episode_id
                or action.get("q") != step["q"]
                or list(frame.action_rad) != step["q"]
                or action.get("phase") != step["phase"]
                or action.get("t") != obs.simulation_seconds
            ):
                raise ValueError("Visual recording targets differ from applied teacher plan")
    score = score_dinner(_rows(root / "physics.jsonl.gz"), iter(actions), layout)
    independent = score_dinner_outcomes(
        _rows(root / "physics.jsonl.gz"),
        layout,
        metadata=source.metrics.get("instrumentation", {}),
        actions=iter(actions),
    )
    if (
        score != _json(root / "score.json")
        or score != source.metrics.get("score")
        or score.get("full_workflow_success") is not True
        or independent != _json(root / "independent-score.json")
        or independent != source.metrics.get("independent_score")
        or independent.get("independent_task_success") is not True
    ):
        raise ValueError("Visual source physical scores failed independent recomputation")
    if (
        store.verify(root.name) != source
        or load_visual_training_protocol(protocol_path) != protocol
    ):
        raise ValueError("Visual source or allocation changed during verification")
    return VerifiedVisualSource(
        root, source, episode, protocol.manifest_sha256, digest_file(episode_path)
    )
