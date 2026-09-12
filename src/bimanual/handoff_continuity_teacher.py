"""Contact-only teacher collection for the diagnosed hand-off continuity interval."""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from collections.abc import Callable
from pathlib import Path

import numpy as np

from bimanual.contracts import Artifact, EpisodeLineage, JointLimits
from bimanual.demonstrations import DemonstrationRecorder
from bimanual.dinner_teacher import DinnerEnvironment, load_plan, phase_permissions
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.feedback_teacher import feedback_target
from bimanual.handoff_continuity_protocol import (
    PHASE_BOUNDARIES,
    HandoffContinuityCase,
    load_handoff_continuity_protocol,
)
from bimanual.teacher import check_carried_path, check_joint_path
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease

KIND = "handoff_receiver_continuity_teacher_recording"
REQUEST = "continuity-case-request.json"
HOLD_SAMPLES = 2000
GRIP_THRESHOLD = 0.01
MAX_OVERLAP_M = 0.0025


def _reservation_name(protocol_sha256: str, case_id: str) -> str:
    digest = hashlib.sha256(canonical([protocol_sha256, case_id])).hexdigest()[:24]
    return "handoff-continuity-" + digest


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


def _existing(store: EvidenceStore, request: dict) -> Manifest | None:
    directory = store.directory(
        _reservation_name(request["protocol_manifest_sha256"], request["case_id"])
    )
    if not directory.exists():
        return None
    try:
        recorded = json.loads((directory / REQUEST).read_bytes())
    except (OSError, ValueError) as error:
        raise RuntimeError("Continuity reservation requires manual adjudication") from error
    if recorded != request:
        raise ValueError("Existing continuity reservation contradicts the frozen case")
    if not (directory / "manifest.json").is_file():
        raise RuntimeError("Interrupted continuity collection requires manual adjudication")
    result = store.verify(directory.name)
    if result.kind != KIND or result.config != request:
        raise ValueError("Existing continuity result is invalid")
    return result


def _continuity_score(physics_path: Path, actions_path: Path) -> dict:
    actions = [json.loads(line) for line in actions_path.read_text().splitlines()]
    rows = [json.loads(line) for line in physics_path.read_text().splitlines()]
    confirmed = sum(action.get("applied") is True for action in actions)
    partial = sum(action.get("partial_physics") is True for action in actions)
    counts = {"donor": 0, "shared": 0, "receiver": 0}
    first = {"donor": None, "shared": None, "receiver": None}
    last = {"donor": None, "shared": None, "receiver": None}
    forbidden = acquisition_receiver_contacts = 0
    maximum_overlap = 0.0
    continuity_started = False
    continuity_lost = False
    for index, row in enumerate(rows):
        obj = row["objects"]["practice_object"]
        left = min(obj["forces"]["left"]) > GRIP_THRESHOLD
        right = min(obj["forces"]["right"]) > GRIP_THRESHOLD
        airborne = not obj["support"]
        phase = row["phase"]
        if phase == "handoff/left_hold" and left and not right and airborne:
            stage = "donor"
        elif phase == "handoff/both_hold" and left and right and airborne:
            stage = "shared"
        elif phase == "handoff/receiver_hold" and right and not left and airborne:
            stage = "receiver"
        else:
            stage = None
        if stage is not None:
            counts[stage] += 1
            first[stage] = index if first[stage] is None else first[stage]
            last[stage] = index
        if phase == "handoff/left_hold":
            continuity_started = True
        if continuity_started and (not airborne or not (left or right)):
            continuity_lost = True
        if phase == "handoff/receiver_acquisition" and any(
            force > GRIP_THRESHOLD for force in obj["forces"]["right"]
        ):
            acquisition_receiver_contacts += 1
        forbidden += bool(row["bad"])
        maximum_overlap = max(maximum_overlap, float(row["overlap"]))
    ordered = all(value is not None for value in first.values()) and (
        last["donor"] < first["shared"] < first["receiver"]
    )
    success = bool(
        confirmed == len(actions)
        and partial == 0
        and len(rows) == confirmed * 50
        and all(count >= HOLD_SAMPLES for count in counts.values())
        and ordered
        and not continuity_lost
        and not acquisition_receiver_contacts
        and forbidden == 0
        and maximum_overlap <= MAX_OVERLAP_M
    )
    return {
        "profile": "handoff_receiver_continuity_physical_score_v1",
        "physical_handoff_success": success,
        "action_rows": len(actions),
        "confirmed_actions": confirmed,
        "partial_actions": partial,
        "physics_rows": len(rows),
        "donor_only_samples": counts["donor"],
        "shared_grasp_samples": counts["shared"],
        "receiver_only_samples": counts["receiver"],
        "phases_ordered": ordered,
        "continuous_airborne_grip": continuity_started and not continuity_lost,
        "acquisition_receiver_contact_samples": acquisition_receiver_contacts,
        "forbidden_contact_samples": forbidden,
        "maximum_overlap_m": maximum_overlap,
    }


def run_handoff_continuity_case(
    protocol_path: Path,
    case_id: str,
    *,
    store: EvidenceStore,
    project_root: Path,
    cancelled: Callable[[], bool] = lambda: False,
) -> Manifest:
    """Collect one frozen case once; failed/interrupted cases remain consumed."""
    protocol_path = Path(protocol_path).resolve(strict=True)
    project_root = Path(project_root).resolve()
    protocol_file_sha256 = digest_file(protocol_path)
    protocol = load_handoff_continuity_protocol(protocol_path)
    selected = [case for case in protocol.cases if case.case_id == case_id]
    if len(selected) != 1:
        raise ValueError("Case id is not in the frozen continuity protocol")
    case: HandoffContinuityCase = selected[0]
    request = {
        "protocol_path": str(protocol_path),
        "protocol_file_sha256": protocol_file_sha256,
        "protocol_manifest_sha256": protocol.manifest_sha256,
        "case_id": case.case_id,
        "case": case.model_dump(mode="json"),
        "phase_boundaries": protocol.phase_boundaries,
        "correction_scope": protocol.correction_scope,
        "training_only": True,
    }
    store.root.mkdir(parents=True, exist_ok=True)
    with WorkerLease.acquire(store.root / ".handoff-continuity-coordinator.lock"):
        prior = _existing(store, request)
        if prior is not None:
            return prior
        model_lease = WorkerLease.acquire(store.root / MODEL_JOB_LEASE)
        directory = store.directory(_reservation_name(protocol.manifest_sha256, case.case_id))
        try:
            directory.parent.mkdir(parents=True, exist_ok=True)
            directory.mkdir(exist_ok=False)
            _write_durable(directory / REQUEST, request)
        except BaseException:
            model_lease.close()
            raise
        source = provenance(project_root)
        metrics = {
            "physical_handoff_success": False,
            "teacher_assistance": True,
            "learned_execution": False,
            "release_qualified": False,
            "object_state_edits": 0,
            "artificial_attachments": 0,
            "external_object_force_samples": 0,
            "prefix_actions": 0,
            "acquisition_actions": 0,
            "correction_actions": 0,
            "validation_actions": 0,
            "interventions": 1,
        }
        env = recorder = trace = actions = None
        pending = None
        partial = recording_failed = False
        outcome = "failed"

        def artifact(name: str) -> Artifact:
            return Artifact(path=name, sha256=digest_file(directory / name))

        def apply(target, phase, *, eligible, source_index=None, carried_arm=None):
            nonlocal pending, partial
            if cancelled():
                raise InterruptedError("Continuity collection cancelled")
            measured = env.data.qpos[env.qadr].copy()
            target = np.asarray(target, dtype=float)
            JointLimits(
                lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist()
            ).validate_targets(target.tolist())
            env.phase = phase
            if phase == "handoff/receiver_acquisition":
                env.active_contacts = {"left": {"practice_object"}}
            else:
                env.active_contacts, _, _ = phase_permissions(phase)
            if carried_arm is not None:
                check_carried_path(
                    env,
                    measured,
                    target,
                    env.allowed,
                    body_name="practice_object",
                    site_name=carried_arm + "/pinch",
                )
            else:
                check_joint_path(env, measured, target, env.allowed)
            pending = env.observe(render=True)
            row = {
                "sequence": env.sequence,
                "phase": phase,
                "measured": measured.tolist(),
                "targets_rad": target.tolist(),
                "source_plan_index": source_index,
                "training_eligible": eligible,
                "applied": False,
            }
            try:
                partial = True
                env.step(target, episode_id=env.episode_id, sequence=env.sequence)
                partial = False
                row["applied"] = True
                recorder.record(pending, target)
                pending = None
            finally:
                row["partial_physics"] = partial
                actions.write(canonical(row) + b"\n")

        try:
            assets = (protocol_path.parent / protocol.asset_root).resolve(strict=True)
            _, plan, _ = load_plan(assets)
            plan_rows = plan["steps"]
            (directory / "scene.xml").write_bytes((assets / "scene.xml").read_bytes())
            (directory / "layout.json").write_bytes((assets / "layout.json").read_bytes())
            (directory / "plan.json.gz").write_bytes((assets / "plan.json.gz").read_bytes())
            (directory / "protocol.json").write_bytes(protocol_path.read_bytes())
            (directory / "controller.json").write_bytes(
                canonical(
                    {
                        "kind": "scripted_teacher",
                        "profile": "handoff_receiver_continuity_teacher_v1",
                        "training_only": True,
                        "case_id": case.case_id,
                        "source_sha256": source["source_sha256"],
                    }
                )
            )
            trace = (directory / "physics.jsonl").open("x")
            actions = (directory / "actions.jsonl").open("xb")
            env = DinnerEnvironment((directory / "scene.xml").read_text(), trace, cancelled)
            limits = JointLimits(lower_rad=env.lower.tolist(), upper_rad=env.upper.tolist())
            recorder = DemonstrationRecorder(
                directory,
                instruction=(
                    "Transfer the practice bar from the left arm to the right arm while "
                    "maintaining continuous physical grip."
                ),
                instruction_revision=0,
                lineage=EpisodeLineage(
                    code_revision=source["git_revision"],
                    source_sha256=source["source_sha256"],
                    scene=artifact("scene.xml"),
                    config=artifact(REQUEST),
                    controller=artifact("controller.json"),
                    controller_kind="scripted_teacher",
                    seed=case.seed,
                    split="train",
                ),
                joint_limits=limits,
            )
            for index in range(PHASE_BOUNDARIES["teacher_prefix_end"]):
                step = plan_rows[index]
                _, carried, arm = phase_permissions(step["phase"])
                apply(
                    step["q"],
                    step["phase"],
                    eligible=False,
                    source_index=index,
                    carried_arm=arm if carried == "practice_object" else None,
                )
                metrics["prefix_actions"] += 1
            measured = env.data.qpos[env.qadr].copy()
            acquisition_goal = np.asarray(
                plan_rows[PHASE_BOUNDARIES["correction_teacher_goal"]]["q"], dtype=float
            )
            acquisition_goal[:6] = measured[:6]
            acquisition_goal[11] = measured[11]
            if case.receiver_joint_index is not None:
                acquisition_goal[case.receiver_joint_index] += case.offset_rad
            while np.max(np.abs(acquisition_goal - env.data.qpos[env.qadr])) > 0.01:
                target = feedback_target(
                    env.data.qpos[env.qadr].copy(), acquisition_goal, max_delta_rad=0.03
                )
                apply(
                    target,
                    "handoff/receiver_acquisition",
                    eligible=False,
                    carried_arm="left",
                )
                metrics["acquisition_actions"] += 1
                if metrics["acquisition_actions"] > 300:
                    raise TimeoutError("Receiver acquisition exceeded 300 actions")
            correction_goal = np.asarray(
                plan_rows[PHASE_BOUNDARIES["correction_teacher_goal"]]["q"], dtype=float
            )
            correction_goal[:6] = env.data.qpos[env.qadr][:6]
            correction_goal[11] = env.data.qpos[env.qadr][11]
            while np.max(np.abs(correction_goal - env.data.qpos[env.qadr])) > 0.01:
                target = feedback_target(
                    env.data.qpos[env.qadr].copy(), correction_goal, max_delta_rad=0.03
                )
                apply(target, "handoff/right_approach", eligible=True, carried_arm="left")
                metrics["correction_actions"] += 1
                if metrics["correction_actions"] > 300:
                    raise TimeoutError("Receiver correction exceeded 300 actions")
            for index in range(
                PHASE_BOUNDARIES["correction_replay_start"],
                PHASE_BOUNDARIES["correction_replay_end"],
            ):
                step = plan_rows[index]
                apply(
                    step["q"],
                    step["phase"],
                    eligible=True,
                    source_index=index,
                    carried_arm="right" if step["phase"] == "handoff/left_release" else "left",
                )
                metrics["correction_actions"] += 1
            for index in range(
                PHASE_BOUNDARIES["validation_tail_start"],
                PHASE_BOUNDARIES["validation_tail_end"],
            ):
                step = plan_rows[index]
                apply(
                    step["q"],
                    step["phase"],
                    eligible=False,
                    source_index=index,
                    carried_arm="right",
                )
                metrics["validation_actions"] += 1
            outcome = "completed"
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
                    terminal = pending if partial else env.observe(render=True)
                    recorder.record(terminal, None)
                    episode = recorder.finalize(
                        interventions=metrics["interventions"],
                        outcome={"completed": "success", "interrupted": "cancelled"}.get(
                            outcome, "failure"
                        ),
                        outcome_reason=metrics.get("error", "Continuity teacher completed"),
                    )
                    metrics["demonstration_path"] = episode.relative_to(directory).as_posix()
                except (Exception, KeyboardInterrupt) as error:
                    recording_failed = True
                    outcome = "failed"
                    metrics["recording_error"] = f"{type(error).__name__}: {error}"
            cleanup_errors = []
            for operation in ([env.stop, env.close] if env is not None else []) + [
                stream.close for stream in (actions, trace) if stream is not None
            ]:
                try:
                    operation()
                except (Exception, KeyboardInterrupt) as error:
                    cleanup_errors.append(f"{type(error).__name__}: {error}")
            if cleanup_errors:
                metrics["cleanup_errors"] = cleanup_errors
                outcome = "failed"
            model_lease.close()
        if (directory / "physics.jsonl").is_file() and (directory / "actions.jsonl").is_file():
            score = _continuity_score(directory / "physics.jsonl", directory / "actions.jsonl")
            metrics["independent_score"] = score
            metrics["physical_handoff_success"] = score["physical_handoff_success"]
            (directory / "independent-score.json").write_bytes(canonical(score) + b"\n")
            if not score["physical_handoff_success"]:
                outcome = "failed"
        if (
            digest_file(protocol_path) != protocol_file_sha256
            or load_handoff_continuity_protocol(protocol_path).manifest_sha256
            != protocol.manifest_sha256
        ):
            raise ValueError("Frozen continuity protocol changed during collection")
        return store.seal(
            directory,
            kind=KIND,
            outcome=outcome,
            config=request,
            metrics=metrics,
            source=source,
            claims=(
                ["Teacher-assisted contact hand-off correction source; no learned success"]
                if outcome == "completed"
                else []
            ),
        )
