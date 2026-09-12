"""One-attempt, contact-only corrective sources for frozen dinner component cases.

This module deliberately does not export or train a policy.  It records a teacher
prefix, a bounded measured-state acquisition, and a replay interval in the real
``DinnerEnvironment``.  A later validator must independently accept a source before
any replay actions can become training labels.
"""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

from bimanual.contracts import Artifact, EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dinner_teacher import DinnerEnvironment, load_plan, phase_permissions
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.skill_corrective_protocol import load_skill_corrective_collection_protocol
from bimanual.skill_outcomes import SkillOutcomeMonitor
from bimanual.skill_views import INTERVALS_V2
from bimanual.teacher import check_carried_path, check_joint_path
from bimanual.worker_lease import WorkerLease

KIND = "six_skill_corrective_teacher_recording"
REQUEST = "corrective-case-request.json"
MAX_ACQUISITION_ACTIONS = 2
MAX_ACQUISITION_DELTA_RAD = 0.015

_INTERVALS = {
    skill: (start, end) for skill, start, end in INTERVALS_V2 if skill != "handoff_transfer"
}


def _reservation_name(protocol_sha256: str, case_id: str) -> str:
    return (
        "six-skill-corrective-"
        + hashlib.sha256(canonical([protocol_sha256, case_id])).hexdigest()[:24]
    )


def _write_durable(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _case_rows(protocol) -> tuple[dict, ...]:
    """Materialize the protocol's 20 cases without adding an unfrozen allocation file.

    The approach family has five total cases.  Its three named skills are assigned
    cyclically in frozen seed order, yielding two cup, two plate and one fork case.
    """
    rows: list[dict] = []
    for family in protocol.families:
        for ordinal, seed in enumerate(family.case_seeds):
            skill_id = family.skills[ordinal % len(family.skills)]
            rows.append(
                {
                    "case_id": f"{family.family_id}-{seed}",
                    "family_id": family.family_id,
                    "seed": seed,
                    "ordinal": ordinal,
                    "skill_id": skill_id,
                    "teacher_assisted": True,
                    "learned_execution": False,
                    "training_eligible": False,
                }
            )
    return tuple(rows)


def build_skill_corrective_request(protocol_path: Path, case_id: str) -> dict:
    """Return the immutable request for one exactly-once frozen corrective case."""
    protocol_path = Path(protocol_path).resolve(strict=True)
    protocol = load_skill_corrective_collection_protocol(protocol_path)
    matches = [case for case in _case_rows(protocol) if case["case_id"] == case_id]
    if len(matches) != 1:
        raise ValueError("Case id is not in the frozen six-skill corrective protocol")
    return {
        "protocol_path": str(protocol_path),
        "protocol_file_sha256": digest_file(protocol_path),
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case": matches[0],
        "case_id": case_id,
        "allocation_rule": protocol.allocation_rule,
        "recording_profile": "six_skill_corrective_teacher_v1",
        "training_only": True,
    }


def _existing(store: EvidenceStore, request: dict) -> Manifest | None:
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    if not directory.exists():
        return None
    try:
        recorded = json.loads((directory / REQUEST).read_bytes())
    except (OSError, ValueError) as error:
        raise RuntimeError("Corrective reservation requires manual adjudication") from error
    if recorded != request:
        raise ValueError("Existing corrective reservation contradicts its frozen case")
    if not (directory / "manifest.json").is_file():
        raise RuntimeError("Interrupted corrective collection consumes this case")
    result = store.verify(directory.name)
    if result.kind != KIND or result.config != request:
        raise ValueError("Existing corrective result is invalid")
    return result


def _acquisition_goal(measured: np.ndarray, *, seed: int, family_id: str) -> np.ndarray:
    """A small deterministic pre-replay displacement, never an object-state edit."""
    goal = measured.copy()
    rng = np.random.default_rng(seed)
    # Keep the perturbation local to the skill-owning arm.  The exact replay start
    # remains the measured-state goal, so acquisition frames cannot become labels.
    slices = {
        "bar_contact_avoidance": slice(6, 11),
        "approach_contact": slice(6, 11),
        "grasp_lift": slice(0, 5),
        "drawer_pull": slice(0, 5),
    }
    arm = slices[family_id]
    goal[arm] += rng.uniform(
        -MAX_ACQUISITION_DELTA_RAD, MAX_ACQUISITION_DELTA_RAD, arm.stop - arm.start
    )
    return goal


def _acquisition_targets(
    measured: np.ndarray, *, seed: int, family_id: str
) -> tuple[np.ndarray, np.ndarray]:
    """Return one bounded measured-state probe and its exact measured-state recovery.

    The teacher replays the frozen interval immediately after recovery.  It must not
    wait for a position servo to converge to an authored target: that is neither a
    measured-state acquisition nor a bounded correction, and it consumed a frozen
    case without producing a replay on the first field run.
    """
    baseline = np.asarray(measured, dtype=float).copy()
    if baseline.shape != (12,) or not np.isfinite(baseline).all():
        raise ValueError("Invalid measured state for corrective acquisition")
    return _acquisition_goal(baseline, seed=seed, family_id=family_id), baseline


def _score_monitor(monitor: SkillOutcomeMonitor, action: dict, rows: list[dict]) -> dict:
    outcome = monitor.consume(action, rows)
    return outcome.report()


def run_skill_corrective_case(
    protocol_path: Path,
    case_id: str,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
) -> Manifest:
    """Run one case once and preserve failures, prefixes and recordings for review."""
    protocol_path = Path(protocol_path).resolve(strict=True)
    project_root = Path(project_root).resolve()
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_skill_corrective_collection_protocol(protocol_path)
    request = build_skill_corrective_request(protocol_path, case_id)
    case = request["case"]
    start, end = _INTERVALS[case["skill_id"]]
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".six-skill-corrective-coordinator.lock"):
        prior = _existing(store, request)
        if prior is not None:
            return prior
        directory = store.directory(_reservation_name(protocol.manifest_sha256, case_id))
        directory.parent.mkdir(parents=True, exist_ok=True)
        directory.mkdir(exist_ok=False)
        _write_durable(directory / REQUEST, request)

        source = provenance(project_root)
        metrics: dict = {
            "teacher_assistance": True,
            "learned_execution": False,
            "training_eligible": False,
            "release_qualified": False,
            "object_state_edits": 0,
            "artificial_attachments": 0,
            "external_object_force_samples": 0,
            "prefix_actions": 0,
            "acquisition_actions": 0,
            "replay_actions": 0,
            "recording_complete": False,
            "physical_skill_success": False,
            "interventions": 1,
        }
        env = recorder = trace = actions = None
        pending = None
        partial = recording_failed = False
        monitor = None
        outcome = "failed"

        def artifact(name: str) -> Artifact:
            return Artifact(path=name, sha256=digest_file(directory / name))

        def apply(target, phase: str, *, segment: str, source_index: int | None = None) -> None:
            nonlocal pending, partial
            if cancelled():
                raise InterruptedError("Corrective collection cancelled")
            measured = env.data.qpos[env.qadr].copy()
            target = np.asarray(target, dtype=float)
            JointLimits(
                lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist()
            ).validate_targets(target.tolist())
            env.phase = phase
            env.active_contacts, carried, arm = phase_permissions(phase)
            if (
                source_index is not None
                and plan_rows[source_index].get("arm_object_contacts") == "none"
            ):
                env.active_contacts = {}
            if carried is not None:
                check_carried_path(
                    env, measured, target, env.allowed, body_name=carried, site_name=arm + "/pinch"
                )
            else:
                check_joint_path(env, measured, target, env.allowed)
            pending = env.observe(render=True)
            action = {
                "episode_id": env.episode_id,
                "observation_sequence": env.sequence,
                "simulation_seconds_before": float(env.data.time),
                "targets_rad": target.tolist(),
                "phase": phase,
                "segment": segment,
                "source_plan_index": source_index,
                # Every source starts ineligible.  The independent validator may
                # select replay actions later; acquisition is explicitly excluded.
                "training_eligible": False,
                "candidate_replay_action": segment == "replay",
                "applied": False,
            }
            try:
                partial = True
                env.step(target, episode_id=env.episode_id, sequence=env.sequence)
                partial = False
                action["applied"] = True
                recorder.record(pending, target)
                pending = None
            finally:
                action["simulation_seconds_after"] = float(env.data.time)
                action["partial_physics"] = partial
                actions.write(canonical(action) + b"\n")
            if monitor is not None and action["applied"]:
                # DinnerEnvironment writes exactly 50 1kHz rows per confirmed action.
                rows = list(trace_rows)
                metrics["latest_outcome"] = _score_monitor(monitor, action, rows)

        trace_rows: deque[dict] = deque(maxlen=50)

        class _Trace:
            def write(self, text: str) -> int:
                written = trace.write(text)
                trace_rows.append(json.loads(text))
                return written

            def flush(self) -> None:
                trace.flush()

            def close(self) -> None:
                trace.close()

        try:
            if cancelled():
                raise InterruptedError("Corrective collection cancelled")
            assets = (protocol_path.parent / protocol.asset_root).resolve(strict=True)
            _, plan, layout = load_plan(assets)
            plan_rows = plan["steps"]
            for name in ("scene.xml", "layout.json", "plan.json.gz"):
                (directory / name).write_bytes((assets / name).read_bytes())
            (directory / "protocol.json").write_bytes(protocol_path.read_bytes())
            (directory / "collection-segments.json").write_bytes(
                canonical(
                    {
                        "profile": request["recording_profile"],
                        "skill_id": case["skill_id"],
                        "prefix_source_interval": [0, start],
                        "acquisition_max_actions": MAX_ACQUISITION_ACTIONS,
                        "acquisition_training_eligible": False,
                        "replay_source_interval": [start, end],
                        "replay_training_eligible_until_validated": False,
                    }
                )
            )
            (directory / "controller.json").write_bytes(
                canonical(
                    {
                        "kind": "scripted_teacher",
                        "profile": request["recording_profile"],
                        "teacher_uses_simulator_truth": True,
                        "training_only": True,
                        "case_id": case_id,
                        "source_sha256": source["source_sha256"],
                    }
                )
            )
            trace = (directory / "physics.jsonl").open("x")
            actions = (directory / "actions.jsonl").open("xb")
            env = DinnerEnvironment((directory / "scene.xml").read_text(), _Trace(), cancelled)
            recorder = DemonstrationRecorder(
                directory,
                instruction=(
                    f"Perform the bounded corrective teacher replay for {case['skill_id']}."
                ),
                instruction_revision=0,
                lineage=EpisodeLineage(
                    code_revision=source["git_revision"],
                    source_sha256=source["source_sha256"],
                    scene=artifact("scene.xml"),
                    config=artifact(REQUEST),
                    controller=artifact("controller.json"),
                    controller_kind="scripted_teacher",
                    seed=case["seed"],
                    split="train",
                ),
                joint_limits=JointLimits(
                    lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist()
                ),
            )
            # Reconstruct state strictly through real contact physics; never restore object poses.
            for index, step in enumerate(plan_rows[:start]):
                apply(step["q"], step["phase"], segment="prefix", source_index=index)
                metrics["prefix_actions"] += 1
            acquisition, recovery = _acquisition_targets(
                env.data.qpos[env.qadr].copy(), seed=case["seed"], family_id=case["family_id"]
            )
            acquisition = np.clip(acquisition, env.lower, env.upper)
            for target in (acquisition, recovery):
                apply(
                    target,
                    plan_rows[start]["phase"],
                    segment="acquisition",
                    source_index=start,
                )
                metrics["acquisition_actions"] += 1
            monitor = SkillOutcomeMonitor(
                case["skill_id"],
                episode_id=env.episode_id,
                initial_sequence=env.sequence,
                initial_simulation_seconds=float(env.data.time),
                layout=layout,
                max_actions=2 * (end - start),
            )
            for index in range(start, end):
                step = plan_rows[index]
                apply(step["q"], step["phase"], segment="replay", source_index=index)
                metrics["replay_actions"] += 1
                if monitor.snapshot().state != "pending":
                    break
            score = monitor.snapshot().report()
            metrics["independent_score"] = score
            metrics["physical_skill_success"] = score["state"] == "succeeded"
            (directory / "independent-score.json").write_bytes(canonical(score) + b"\n")
            metrics["recording_complete"] = True
            outcome = "completed" if metrics["physical_skill_success"] else "failed"
        except (Exception, KeyboardInterrupt) as error:
            outcome = (
                "interrupted"
                if isinstance(error, (InterruptedError, KeyboardInterrupt))
                else "failed"
            )
            metrics["error"] = f"{type(error).__name__}: {error}"
            (directory / "error.txt").write_text(traceback.format_exc())
        finally:
            if recorder is not None and not recording_failed:
                try:
                    recorder.record(pending if partial else env.observe(render=True), None)
                    episode = recorder.finalize(
                        interventions=metrics["interventions"],
                        outcome={"completed": "success", "interrupted": "cancelled"}.get(
                            outcome, "failure"
                        ),
                        outcome_reason=metrics.get(
                            "error", "Corrective teacher recording complete"
                        ),
                    )
                    metrics["demonstration_path"] = episode.relative_to(directory).as_posix()
                    metrics["recorded_observations"] = len(recorder.frames)
                except (Exception, KeyboardInterrupt) as error:
                    recording_failed = True
                    outcome = "failed"
                    metrics["recording_error"] = f"{type(error).__name__}: {error}"
            cleanup = []
            for operation in ([env.stop, env.close] if env is not None else []) + [
                stream.close for stream in (actions, trace) if stream is not None
            ]:
                try:
                    operation()
                except (Exception, KeyboardInterrupt) as error:
                    cleanup.append(f"{type(error).__name__}: {error}")
            if cleanup:
                metrics["cleanup_errors"] = cleanup
                outcome = "failed"
        if digest_file(protocol_path) != protocol_file_sha256 or (
            load_skill_corrective_collection_protocol(protocol_path).manifest_sha256
            != protocol.manifest_sha256
        ):
            raise ValueError("Frozen corrective protocol changed during collection")
        claim = (
            "Teacher-assisted corrective source recorded; independent validation is required "
            + "before training"
        )
        return store.seal(
            directory,
            kind=KIND,
            outcome=outcome,
            config=request,
            metrics=metrics,
            source=source,
            claims=([claim] if outcome == "completed" else []),
        )
