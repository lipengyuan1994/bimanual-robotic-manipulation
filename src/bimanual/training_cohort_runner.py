"""One explicit cohort skill per call; immutable attempts and conservative reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.evidence import EvidenceStore, canonical, digest_file, provenance
from bimanual.skill_registry import load_skill_checkpoint
from bimanual.training import ACTTrainingConfig, run_train
from bimanual.training_cohort import COHORT_SKILLS, load_training_cohort_protocol
from bimanual.worker_lease import MODEL_JOB_LEASE, WorkerLease

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KIND = "training_cohort_skill_attempt"
RELOAD_FLAGS = (
    "training_completed",
    "checkpoint_reload_verified",
    "processor_reload_verified",
    "sampler_reload_verified",
    "learning_rate_reload_verified",
    "temporal_loss_reload_verified",
)


def _read(path):
    value = json.loads(path.read_text())
    canonical(value)
    return value


def _validate_child(attempt, config):
    store = EvidenceStore(attempt / "training-evidence")
    children = list((store.root / "runs").glob("*"))
    if len(children) != 1 or not children[0].is_dir():
        raise ValueError("Attempt requires exactly one child training run")
    child = store.verify(children[0].name)
    if (
        child.kind != "act_training"
        or child.outcome != "completed"
        or child.config != config.model_dump(mode="json")
    ):
        raise ValueError("Child training kind, completion or exact config mismatch")
    if any(child.metrics.get(flag) is not True for flag in RELOAD_FLAGS):
        raise ValueError("Child training reload verification incomplete")
    steps = child.metrics.get("steps", [])
    if len(steps) != 20000 or any(
        type(row.get("step")) is not int or row["step"] != index
        for index, row in enumerate(steps, 1)
    ):
        raise ValueError("Child must complete exactly 20000 ordered updates")
    trace = [_read_line(line) for line in (children[0] / "steps.jsonl").read_text().splitlines()]
    if (
        trace != steps
        or _read(children[0] / "checkpoint/training_schedule.json").get("completed_updates")
        != 20000
    ):
        raise ValueError("Final checkpoint/update trace mismatch")
    binding = load_skill_checkpoint(
        children[0], skill_id=config.skill_id, dataset_root=config.dataset_path
    )
    if (
        binding.training_manifest_sha256 != child.manifest_sha256
        or binding.view.skill_id != config.skill_id
    ):
        raise ValueError("Child checkpoint binding mismatch")
    if binding.reverify() != binding:
        raise ValueError("Child checkpoint binding changed during verification")
    if store.verify(children[0].name) != child:
        raise ValueError("Child manifest changed during checkpoint verification")
    return child, binding


def _read_line(line):
    value = json.loads(line)
    canonical(value)
    return value


def _finish(store, attempt, metadata, config):
    metrics = dict(training_complete=False, physical_success=None, quality_claim=False)
    try:
        child, binding = _validate_child(attempt, config)
        metrics.update(
            training_complete=True,
            child_run_id=child.run_id,
            child_manifest_sha256=child.manifest_sha256,
            checkpoint_sha256=binding.checkpoint_sha256,
        )
    except (ValueError, OSError, KeyError, TypeError) as error:
        metrics["error"] = f"{type(error).__name__}: {error}"
    return store.seal(
        attempt,
        kind=KIND,
        outcome="completed" if metrics["training_complete"] else "failed",
        config=metadata,
        metrics=metrics,
        source=provenance(PROJECT_ROOT),
        claims=["Training and checkpoint verification only; no physical quality claim"],
    )


def run_training_cohort_skill(protocol_path, skill_id):
    """Run or reconcile one declared skill; never automatically retry a failed attempt.

    The caller starts a native training environment. A separate coordinator lease
    serializes scans and attempt allocation. One shared model lease is held through
    training, child verification and wrapper sealing; run_train borrows that lease.
    """
    protocol_path = Path(protocol_path).resolve()
    protocol = load_training_cohort_protocol(protocol_path)
    if skill_id not in COHORT_SKILLS:
        raise ValueError("Unknown six-skill cohort member")
    raw = protocol.configs[COHORT_SKILLS.index(skill_id)]
    config = ACTTrainingConfig.model_validate(
        raw
        | {
            "dataset_path": (protocol_path.parent / raw["dataset_path"]).resolve(),
            "skill_views_path": (protocol_path.parent / raw["skill_views_path"]).resolve(),
        }
    )
    store = EvidenceStore(protocol_path.parent / protocol.evidence_root)
    if store.root.is_relative_to(config.dataset_path):
        raise ValueError("Cohort evidence must be outside the immutable dataset")
    store.root.mkdir(parents=True, exist_ok=True)
    metadata = dict(
        protocol_sha256=protocol.manifest_sha256,
        protocol_file_sha256=digest_file(protocol_path),
        skill_id=skill_id,
        training=config.model_dump(mode="json"),
        runner_source_sha256=digest_file(Path(__file__)),
    )
    with WorkerLease.acquire(store.root / ".training-cohort-coordinator.lock"):
        # Keep ownership continuous; no release/reacquire gap before model launch.
        with WorkerLease.acquire(store.root / MODEL_JOB_LEASE) as model_lease:
            matches = []
            for path in (store.root / "runs").glob("*/cohort-attempt.json"):
                recorded = _read(path)
                if (
                    recorded.get("protocol_sha256") == protocol.manifest_sha256
                    and recorded.get("skill_id") == skill_id
                ):
                    matches.append((path.parent, recorded))
            if len(matches) > 1:
                raise RuntimeError("Ambiguous multiple cohort attempts; no automatic selection")
            if matches:
                attempt, recorded = matches[0]
                if (
                    recorded != metadata
                    or (attempt / "protocol.json").read_bytes() != protocol_path.read_bytes()
                ):
                    raise ValueError("Existing cohort attempt declaration changed")
                if (attempt / "manifest.json").exists():
                    wrapper = store.verify(attempt.name)
                    if (
                        wrapper.kind != KIND
                        or wrapper.config != metadata
                        or wrapper.outcome not in {"completed", "failed"}
                    ):
                        raise ValueError("Invalid sealed cohort attempt")
                    if wrapper.outcome == "completed":
                        child, binding = _validate_child(attempt, config)
                        if (
                            wrapper.metrics.get("child_manifest_sha256") != child.manifest_sha256
                            or wrapper.metrics.get("checkpoint_sha256") != binding.checkpoint_sha256
                        ):
                            raise ValueError("Completed cohort wrapper binding mismatch")
                    return wrapper
                return _finish(store, attempt, metadata, config)
            attempt = store.new_run()
            (attempt / "cohort-attempt.json").write_bytes(canonical(metadata))
            (attempt / "protocol.json").write_bytes(protocol_path.read_bytes())
            try:
                run_train(
                    config,
                    store=EvidenceStore(attempt / "training-evidence"),
                    project_root=PROJECT_ROOT,
                    model_job_lease_path=store.root / MODEL_JOB_LEASE,
                    model_job_lease=model_lease,
                )
            except (Exception, KeyboardInterrupt) as error:
                # Native/OS death leaves this directory unsealed for the next call.
                (attempt / "runner-error.json").write_bytes(
                    canonical({"error": f"{type(error).__name__}: {error}"})
                )
            return _finish(store, attempt, metadata, config)
