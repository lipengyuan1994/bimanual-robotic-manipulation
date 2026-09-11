"""Reproduce a sealed, CPU-only phase error report from completed evaluation."""

import argparse
import json
from pathlib import Path

import numpy as np

from bimanual.evidence import EvidenceStore, provenance
from bimanual.phase_errors import summarize_phase_errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation_run")
    parser.add_argument("teacher_run")
    parser.add_argument("--artifacts", type=Path, default=Path(".artifacts"))
    args = parser.parse_args()
    store = EvidenceStore(args.artifacts)
    evaluation = store.verify(args.evaluation_run)
    teacher = store.verify(args.teacher_run)
    if (
        evaluation.kind != "dinner_handoff_recorded_policy_evaluation"
        or evaluation.outcome != "completed"
    ):
        raise ValueError("Requires a completed recorded handoff evaluation")
    if teacher.kind != "dinner_teacher" or teacher.outcome != "completed":
        raise ValueError("Requires a completed dinner teacher")
    rows = [
        json.loads(line)
        for line in (store.directory(evaluation.run_id) / "forecasts.jsonl")
        .read_text()
        .splitlines()
    ]
    directory = store.directory(teacher.run_id) / "demonstration"
    labels = [json.loads(line) for line in (directory / "phases.jsonl").read_text().splitlines()]
    frames = json.loads((directory / "episode.json").read_text())["frames"]
    for row in rows:
        index = row["parent_frame"]
        if not 0 <= index < len(frames) or labels[index]["observation_sequence"] != index:
            raise ValueError("Teacher frame mapping differs")
        if not np.allclose(row["expected_rad"][0], frames[index]["action_rad"], rtol=0, atol=1e-6):
            raise ValueError("Evaluation targets do not match teacher")
    report = summarize_phase_errors(
        rows,
        [x["phase"] for x in labels],
        start=evaluation.config["start"],
        end=evaluation.config["end"],
    )
    output = store.new_run()
    (output / "phase-errors.json").write_text(json.dumps(report, indent=2))
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    result = store.seal(
        output,
        kind="handoff_recorded_phase_errors",
        outcome="completed",
        config={
            "evaluation_run": evaluation.run_id,
            "evaluation_sha256": evaluation.manifest_sha256,
            "teacher_run": teacher.run_id,
            "teacher_sha256": teacher.manifest_sha256,
        },
        metrics={"frames": len(rows), "phases": report, "physical_success": None},
        source=provenance(Path.cwd()),
        claims=["Recorded training input errors only; no physical success claim"],
    )
    print(result.run_id)


if __name__ == "__main__":
    main()
