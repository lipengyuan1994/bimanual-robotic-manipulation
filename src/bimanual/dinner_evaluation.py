"""Re-score sealed dinner evidence without executing a robot or modifying its run."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from bimanual.dinner_outcomes import PROFILE, score_dinner_outcomes
from bimanual.evidence import EvidenceStore, Manifest, provenance


def _records(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


def _actions(path: Path, *, legacy: bool = True):
    for index, row in enumerate(_records(path)):
        if not legacy or (isinstance(row, dict) and "targets_rad" in row):
            yield row
        else:
            # Legacy teacher records explicitly acknowledge applied targets. Missing
            # acknowledgement must never be upgraded to an executed action.
            yield {
                "episode_id": row["episode_id"],
                "observation_sequence": index,
                "simulation_seconds_before": row["t"],
                "simulation_seconds_after": row["t"] + 0.05,
                "targets_rad": row["q"],
                "applied": row.get("applied") is True,
                "partial_physics": row.get("partial_physics", False),
            }


def _trace_layout(kind: str) -> dict:
    """Select declared producer layouts, never search for plausible alternate files."""
    if kind == "dinner_workflow_execution":
        return dict(
            profile="workflow_worker_v1",
            physics="worker/physics.jsonl",
            actions="worker/actions.jsonl",
            layout="worker/layout.json",
            scene="worker/scene.xml",
            legacy_actions=False,
        )
    return dict(
        profile="dinner_teacher_v1" if kind == "dinner_teacher" else "legacy_root_teacher_v1",
        physics="physics.jsonl.gz",
        actions="actions.jsonl",
        layout="teacher-assets/layout.json" if kind == "dinner_teacher" else "layout.json",
        legacy_actions=True,
    )


def _diagnostics(directory: Path, paths: dict, sealed_files: dict) -> dict:
    """Scan beyond any early scorer stop, retaining partial-action collisions."""
    result = {
        "physics_rows": 0,
        "forbidden_samples": 0,
        "action_rows": 0,
        "confirmed_actions": 0,
        "partial_actions": 0,
        "errors": [],
    }
    for kind in ("physics", "actions"):
        name = paths[kind]
        if name not in sealed_files:
            result["errors"].append(f"{name}: Selected artifact is absent from source seal")
            continue
        opener = gzip.open if name.endswith(".gz") else open
        try:
            with opener(directory / name, "rt") as stream:
                for number, line in enumerate(stream, 1):
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("Record must be an object")
                        if kind == "physics":
                            result["physics_rows"] += 1
                            if not isinstance(row.get("bad"), list):
                                raise ValueError("Missing or invalid contact list")
                            result["forbidden_samples"] += bool(row["bad"])
                        else:
                            result["action_rows"] += 1
                            result["confirmed_actions"] += row.get("applied") is True
                            result["partial_actions"] += row.get("partial_physics") is True
                    except (ValueError, TypeError) as exc:
                        result["errors"].append(f"{name}:{number}: {exc}")
        except (OSError, EOFError) as exc:
            result["errors"].append(f"{name}: {exc}")
    return result


def evaluate_dinner_run(
    run_id: str,
    *,
    store: EvidenceStore,
    project_root: Path,
    instrumentation_run: str | None = None,
) -> Manifest:
    """An integrity failure rejects input; a task failure produces a failed evaluation.

    Instrumentation is retained as a scoped declaration. Neither contact summaries
    nor this evaluator can establish the absence of unlogged simulator state edits.
    """
    source = store.verify(run_id)
    directory = store.directory(run_id)
    audit = store.verify(instrumentation_run) if instrumentation_run else None
    if audit is not None:
        if (
            audit.config.get("source_run") != run_id
            or audit.config.get("source_manifest_sha256") != source.manifest_sha256
        ):
            raise ValueError("Instrumentation audit does not bind this source manifest")
        metadata = audit.config.get("metadata", {})
        scope = audit.config.get("metadata_scope", "unspecified declaration provenance")
    else:
        metadata = source.metrics.get("instrumentation", {})
        scope = source.metrics.get(
            "instrumentation_evidence", "Source declaration provenance unspecified"
        )
    paths = _trace_layout(source.kind)
    diagnostics = _diagnostics(directory, paths, source.files)
    scene_binding_verified = None if "scene" not in paths else False
    try:
        missing = [
            paths[name]
            for name in (
                ("physics", "actions", "layout", "scene")
                if "scene" in paths
                else ("physics", "actions", "layout")
            )
            if paths[name] not in source.files
        ]
        if missing:
            raise ValueError("Selected artifacts absent from source seal: " + ", ".join(missing))
        layout = json.loads((directory / paths["layout"]).read_text())
        if "scene" in paths:
            if (
                not isinstance(layout, dict)
                or layout.get("scene_sha256") != source.files[paths["scene"]]
            ):
                raise ValueError("Workflow layout does not bind the sealed worker scene")
            scene_binding_verified = True
        score = score_dinner_outcomes(
            _records(directory / paths["physics"]),
            layout,
            metadata=metadata,
            actions=_actions(directory / paths["actions"], legacy=paths["legacy_actions"]),
        )
    except (ValueError, TypeError, KeyError, OSError, EOFError) as exc:
        score = {
            "profile": PROFILE,
            "independent_task_success": False,
            "failed_gates": ["input_error"],
            "input_error": f"{type(exc).__name__}: {exc}",
        }
    if store.verify(run_id).manifest_sha256 != source.manifest_sha256:
        raise ValueError("Source changed during evaluation")
    if audit is not None and store.verify(audit.run_id).manifest_sha256 != audit.manifest_sha256:
        raise ValueError("Instrumentation audit changed during evaluation")
    success = (
        source.outcome == "completed"
        and score["independent_task_success"]
        and not diagnostics["errors"]
        and diagnostics["forbidden_samples"] == 0
    )
    out = store.new_run()
    (out / "source-manifest.json").write_text(source.model_dump_json(indent=2))
    if audit is not None:
        (out / "instrumentation-manifest.json").write_text(audit.model_dump_json(indent=2))
    for module in ("dinner_evaluation.py", "dinner_outcomes.py", "dinner_scoring.py"):
        (out / module).write_bytes(Path(__file__).with_name(module).read_bytes())
    metrics = {
        "score": score,
        "full_trace_diagnostics": diagnostics,
        "source_outcome": source.outcome,
        "source_kind": source.kind,
        "source_error": source.metrics.get("error", source.metrics.get("reason")),
        "selected_trace_layout": paths,
        "scene_binding_verified": scene_binding_verified,
        "learned_execution_verified": False,
    }
    (out / "result.json").write_text(json.dumps(metrics, indent=2, allow_nan=False))
    return store.seal(
        out,
        kind="dinner_evaluation",
        outcome="completed" if success else "failed",
        config={
            "source_run": run_id,
            "source_manifest_sha256": source.manifest_sha256,
            "profile": PROFILE,
            "selected_trace_layout": paths,
            "instrumentation": metadata,
            "instrumentation_scope": scope,
            "instrumentation_run": instrumentation_run,
            "instrumentation_manifest_sha256": audit.manifest_sha256 if audit else None,
        },
        metrics=metrics,
        source=provenance(project_root),
        claims=[
            "Physical scoring of retained evidence; no new execution, generalization "
            "or learned-policy certification"
        ],
    )
