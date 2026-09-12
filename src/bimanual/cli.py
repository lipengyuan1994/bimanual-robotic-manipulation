from __future__ import annotations

import argparse
import contextlib
import json
import platform
import sys
from pathlib import Path


def emit(data: object) -> None:
    print(json.dumps(data, indent=2, allow_nan=False))


def invoke_with_diagnostics(function, *args, **kwargs):
    # Optional model libraries print progress even when their loggers are quiet.
    # Keep the CLI result parseable JSON; progress belongs on stderr.
    with contextlib.redirect_stdout(sys.stderr):
        return function(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bimanual project preparation tools")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifacts", type=Path, default=Path(".artifacts"))
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Probe native runtime, CPU, and optionally MPS")
    doctor.add_argument("--require-device", choices=["cpu", "mps"], default="cpu")
    doctor.add_argument("--record", action="store_true")
    lab = commands.add_parser("lab", help="Run the generic preparation pendulum (not a robot)")
    lab.add_argument("--seed", type=int, default=7)
    lab.add_argument("--seconds", type=int, default=4)
    lab.add_argument("--damping", type=float, default=0.1)
    lab.add_argument("--torque", type=float, default=0.2)
    lab.add_argument("--no-render", action="store_true")
    foundation = commands.add_parser(
        "sim", help="Run dual SO-101 foundation checks (no task policy)"
    )
    foundation.add_argument("--seconds", type=int, default=4)
    foundation.add_argument("--no-render", action="store_true")
    grasp = commands.add_parser("grasp", help="Contact-only teacher experiment, not learned policy")
    grasp.add_argument("--no-render", action="store_true")
    grasp.add_argument("--fault", choices=["missing-object", "skip-close"])
    grasp.add_argument("--arm", choices=["left", "right"], default="left")
    grasp.add_argument(
        "--record-demo", action="store_true", help="Record three raw cameras at 20 Hz"
    )
    grasp.add_argument(
        "--seed", type=int, default=0, help="Lineage label; no scene randomization yet"
    )
    grasp.add_argument("--split", choices=["train", "validation", "test"], default="train")
    grasp.add_argument(
        "--destination",
        nargs=2,
        type=float,
        metavar=("X", "Y"),
        help="World XY placement destination in metres",
    )
    commands.add_parser("status", help="Read the maintained project status")
    handoff = commands.add_parser("handoff", help="Physical teacher hand-off with ownership checks")
    handoff.add_argument("--no-render", action="store_true")
    handoff.add_argument("--fault", choices=["missing-object", "skip-receiver-close"])
    drawer = commands.add_parser(
        "drawer", help="Open and release a passive drawer through physical contact"
    )
    drawer.add_argument("--no-render", action="store_true")
    drawer.add_argument("--fault", choices=["missing-handle", "skip-close"])
    dinner = commands.add_parser(
        "dinner-teacher", help="Run the fixed-scene continuous dinner teacher"
    )
    dinner.add_argument("--no-render", action="store_true")
    dinner.add_argument("--recipe", choices=["v1", "v2"], default="v1")
    dinner.add_argument(
        "--visual-seed", type=int, help="Vary lighting/colors only; fixed physical layout"
    )
    dinner.add_argument(
        "--record-demonstration",
        action="store_true",
        help="Capture full-rate training cameras and actions independently of replay",
    )
    feedback = commands.add_parser(
        "feedback-approach", help="Collect training-only feedback approach evidence; no grasp"
    )
    feedback.add_argument("--record-demonstration", action="store_true")
    feedback.add_argument("--variation-seed", type=int, default=0)
    feedback.add_argument("--acquisition-offset-rad", type=float, default=0.0)
    continuity_protocol_create = commands.add_parser(
        "handoff-continuity-protocol-create",
        help="Freeze measured-state receiver continuity correction cases",
    )
    continuity_protocol_create.add_argument("--diagnosis-run", required=True)
    continuity_protocol_create.add_argument("--destination", type=Path, required=True)
    continuity_protocol_check = commands.add_parser(
        "handoff-continuity-protocol-check",
        help="Reverify a frozen hand-off continuity collection protocol",
    )
    continuity_protocol_check.add_argument("protocol", type=Path)
    continuity_run = commands.add_parser(
        "handoff-continuity-run", help="Collect one frozen hand-off continuity case once"
    )
    continuity_run.add_argument("protocol", type=Path)
    continuity_run.add_argument("case_id")
    continuity_views_create = commands.add_parser(
        "handoff-continuity-views-create",
        help="Pin verified receiver-continuity correction intervals",
    )
    continuity_views_create.add_argument("--run-id", action="append", required=True)
    continuity_views_create.add_argument("--destination", type=Path, required=True)
    continuity_views_check = commands.add_parser(
        "handoff-continuity-views-check",
        help="Reverify receiver-continuity sources and training boundaries",
    )
    continuity_views_check.add_argument("manifest", type=Path)
    continuity_export = commands.add_parser(
        "handoff-continuity-export",
        help="Export verified receiver-continuity intervals to local LeRobot",
    )
    continuity_export.add_argument("--views", type=Path, required=True)
    continuity_export.add_argument("--destination", type=Path, required=True)
    continuity_export.add_argument("--repo-id", required=True)
    continuity_export_check = commands.add_parser(
        "handoff-continuity-export-check",
        help="Reverify a local receiver-continuity LeRobot export",
    )
    continuity_export_check.add_argument("dataset", type=Path)
    corrective_create = commands.add_parser(
        "corrective-views-create", help="Pin verified approach correction intervals"
    )
    corrective_create.add_argument("--run-id", action="append", required=True)
    corrective_create.add_argument("--destination", type=Path, required=True)
    corrective_check = commands.add_parser(
        "corrective-views-check", help="Verify corrective source recordings and boundaries"
    )
    corrective_check.add_argument("manifest", type=Path)
    visual_protocol = commands.add_parser(
        "visual-protocol-check", help="Verify frozen visual seed allocation and source identities"
    )
    visual_protocol.add_argument("protocol", type=Path)
    visual_source = commands.add_parser(
        "visual-source-check", help="Verify a recorded visual teacher source before export"
    )
    visual_source.add_argument("run_root", type=Path)
    visual_source.add_argument("--protocol", type=Path, required=True)
    scene_protocol_create = commands.add_parser(
        "scene-variant-protocol-create", help="Freeze six-family dinner perturbation seeds"
    )
    scene_protocol_create.add_argument("--destination", type=Path, required=True)
    scene_protocol_check = commands.add_parser(
        "scene-variant-protocol-check", help="Verify the frozen dinner perturbation protocol"
    )
    scene_protocol_check.add_argument("protocol", type=Path)
    scene_variant_prepare = commands.add_parser(
        "scene-variant-prepare", help="Prepare one allocated dinner scene without evaluation"
    )
    scene_variant_prepare.add_argument("protocol", type=Path)
    scene_variant_prepare.add_argument(
        "--family",
        choices=["placement", "mass", "friction", "shape", "lighting", "background", "combined"],
        required=True,
    )
    scene_variant_prepare.add_argument("--seed", type=int, required=True)
    scene_variant_suite = commands.add_parser(
        "scene-variant-suite-prepare",
        help="Resume and index all sixteen frozen dinner perturbation scenes",
    )
    scene_variant_suite.add_argument("protocol", type=Path)
    cohort_create = commands.add_parser(
        "training-cohort-create", help="Freeze the remaining six ACT training configurations"
    )
    cohort_create.add_argument("--dataset", type=Path, required=True)
    cohort_create.add_argument("--skill-views", type=Path, required=True)
    cohort_create.add_argument("--destination", type=Path, required=True)
    for role in (
        "experiment-protocol",
        "training",
        "recorded",
        "physical-prefix2",
        "physical-prefix5",
    ):
        cohort_create.add_argument(f"--{role}-run", required=True)
    cohort_check = commands.add_parser(
        "training-cohort-check", help="Reverify a frozen six-skill training protocol"
    )
    cohort_check.add_argument("protocol", type=Path)
    cohort_run = commands.add_parser(
        "training-cohort-run", help="Run or reconcile one frozen ACT skill attempt"
    )
    cohort_run.add_argument("protocol", type=Path)
    cohort_run.add_argument("--skill", required=True)
    cohort_sequence = commands.add_parser(
        "training-cohort-run-all",
        help="Resume all six frozen ACT trainings serially; stop on first failure",
    )
    cohort_sequence.add_argument("protocol", type=Path)
    cohort_sequence.add_argument("--wait-for-active-seconds", type=float, default=0)
    skill_physical = commands.add_parser(
        "skill-physical-eval",
        help="Run one teacher-prepared learned-skill physical diagnostic",
    )
    skill_physical.add_argument("--training-run", type=Path, required=True)
    skill_physical.add_argument("--dataset", type=Path, required=True)
    skill_physical.add_argument("--skill-views", type=Path, required=True)
    skill_physical.add_argument("--skill", required=True)
    skill_physical.add_argument("--device", choices=["cpu", "mps"], default="mps")
    skill_physical.add_argument("--max-actions", type=int, default=2000)
    skill_physical.add_argument("--execute-chunk-steps", type=int, default=2)
    skill_physical.add_argument("--wall-timeout-seconds", type=float, default=1200)
    physical_protocol_create = commands.add_parser(
        "skill-physical-protocol-create",
        help="Freeze the six-skill teacher-prepared evaluation suite",
    )
    physical_protocol_create.add_argument("--training-cohort", type=Path, required=True)
    physical_protocol_create.add_argument("--destination", type=Path, required=True)
    physical_protocol_check = commands.add_parser(
        "skill-physical-protocol-check",
        help="Reverify the frozen teacher-prepared evaluation suite",
    )
    physical_protocol_check.add_argument("protocol", type=Path)
    physical_protocol_run = commands.add_parser(
        "skill-physical-protocol-run",
        help="Evaluate one completed cohort checkpoint under the frozen suite",
    )
    physical_protocol_run.add_argument("protocol", type=Path)
    physical_protocol_run.add_argument("--skill", required=True)
    physical_protocol_run.add_argument("--training-attempt", required=True)
    physical_protocol_sequence = commands.add_parser(
        "skill-physical-protocol-run-all",
        help="Resume all six frozen component evaluations after cohort training completes",
    )
    physical_protocol_sequence.add_argument("protocol", type=Path)
    physical_suite_report = commands.add_parser(
        "skill-physical-suite-report",
        help="Seal the complete frozen six-skill component result without workflow claims",
    )
    physical_suite_report.add_argument("protocol", type=Path)
    cohort_adjudicate = commands.add_parser(
        "training-cohort-adjudicate-preflight",
        help="Classify one zero-update MPS environment failure before a replacement",
    )
    cohort_adjudicate.add_argument("protocol", type=Path)
    cohort_adjudicate.add_argument("--attempt", required=True)
    handoff_analysis = commands.add_parser(
        "handoff-failure-analyze",
        help="Reproduce contact-stage findings from sealed learned hand-off failures",
    )
    handoff_analysis.add_argument("wrapper_run_ids", nargs="+")
    evaluation = commands.add_parser("dinner-evaluate", help="Re-score sealed dinner evidence")
    evaluation.add_argument("run_id")
    evaluation.add_argument("--instrumentation-run", help="Sealed declarations linked to this run")
    workflow_create = commands.add_parser(
        "workflow-create", help="Pin seven explicitly selected development skill checkpoints"
    )
    workflow_create.add_argument("--dataset", type=Path, required=True)
    workflow_create.add_argument("--skill-views", type=Path, required=True)
    workflow_create.add_argument("--destination", type=Path, required=True)
    workflow_create.add_argument(
        "--handoff-corrective-dataset",
        type=Path,
        help="Verified corrective dataset location to pin for handoff",
    )
    workflow_create.add_argument(
        "--training-run",
        type=Path,
        action="append",
        required=True,
        help="Repeat seven times: handoff, bar, cup, plate, drawer, spoon, fork",
    )
    workflow_check = commands.add_parser(
        "workflow-check", help="Verify a pinned skill cohort without loading models"
    )
    workflow_check.add_argument("manifest", type=Path)
    workflow_activate = commands.add_parser(
        "workflow-activate", help="Activate a fully verified local workflow manifest"
    )
    workflow_activate.add_argument("manifest", type=Path)
    workflow_activate.add_argument("--deployment-root", type=Path)
    workflow_deployment_status = commands.add_parser(
        "workflow-deployment-status", help="Reverify the active local workflow identity"
    )
    workflow_deployment_status.add_argument("--deployment-root", type=Path)
    workflow_rollback = commands.add_parser(
        "workflow-rollback", help="Return to a previously verified local workflow manifest"
    )
    workflow_rollback.add_argument("--deployment-root", type=Path)
    workflow_rollback.add_argument("--target-id")
    workflow_run = commands.add_parser(
        "workflow-run", help="Execute a verified local seven-skill workflow; not a quality approval"
    )
    workflow_run.add_argument("manifest", type=Path, nargs="?", help="Direct diagnostic manifest")
    workflow_run.add_argument(
        "--deployment-root", type=Path, help="Run the reverified active deployment"
    )
    workflow_run.add_argument("--planner-model", type=Path, required=True)
    workflow_run.add_argument(
        "--scene-variant", type=Path, help="Optional verified prepared perturbation run"
    )
    workflow_run.add_argument("--instruction", required=True)
    workflow_run.add_argument("--policy-device", choices=["cpu", "mps"], default="cpu")
    workflow_run.add_argument("--planner-device", choices=["cpu", "mps"], default="cpu")
    workflow_run.add_argument(
        "--camera-profile",
        choices=["policy480_v1", "overhead1920_wrist480_v1"],
        default="policy480_v1",
    )
    workflow_run.add_argument("--wall-timeout-seconds", type=float, default=1800)
    workflow_run.add_argument("--max-tokens", type=int, default=384)
    workflow_run.add_argument("--step-timeout-seconds", type=float, default=300)
    workflow_run.add_argument(
        "--in-process",
        action="store_true",
        help="Diagnostic mode: cooperative stops only; default uses an isolated process",
    )

    workflow_release_create = commands.add_parser(
        "workflow-release-create", help="Freeze a local candidate and all release-suite inputs"
    )
    workflow_release_create.add_argument("--workflow-manifest", type=Path, required=True)
    workflow_release_create.add_argument("--planner-model", type=Path, required=True)
    workflow_release_create.add_argument("--scene-suite-run", type=Path, required=True)
    workflow_release_create.add_argument("--perturbation-protocol", type=Path, required=True)
    workflow_release_create.add_argument("--instruction", required=True)
    workflow_release_create.add_argument("--destination", type=Path, required=True)
    workflow_release_check = commands.add_parser(
        "workflow-release-check", help="Verify a frozen local workflow release declaration"
    )
    workflow_release_check.add_argument("protocol", type=Path)
    workflow_release_run = commands.add_parser(
        "workflow-release-run", help="Execute and score one frozen local release scene once"
    )
    workflow_release_run.add_argument("protocol", type=Path)
    workflow_release_run.add_argument("case_id")
    workflow_release_suite = commands.add_parser(
        "workflow-release-suite", help="Aggregate all sixteen frozen local release outcomes"
    )
    workflow_release_suite.add_argument("protocol", type=Path)
    submission_check = commands.add_parser(
        "submission-check", help="Inspect local submission requirements without creating files"
    )
    submission_create = commands.add_parser(
        "submission-create", help="Create a verified local submission package"
    )
    submission_verify = commands.add_parser(
        "submission-verify", help="Reverify an existing local submission package"
    )
    for submission, required in ((submission_check, False), (submission_create, True)):
        submission.add_argument("--revision", required=required)
        submission.add_argument("--release-protocol", type=Path, required=required)
        submission.add_argument("--release-suite", type=Path, required=required)
        submission.add_argument("--interactive-url", required=required)
        submission.add_argument("--video", type=Path, required=required)
        submission.add_argument("--slides", type=Path, required=required)
        submission.add_argument("--cover", type=Path, required=required)
    submission_create.add_argument("--destination", type=Path, required=True)
    submission_verify.add_argument("package", type=Path)

    cup = commands.add_parser("cup", help="Physically carry and release a hollow cup upright")
    cup.add_argument("--no-render", action="store_true")
    cup.add_argument("--arm", choices=["left", "right"], default="left")
    cup.add_argument("--fault", choices=["missing-object", "skip-close"])
    plate = commands.add_parser("plate", help="Carry a plate from its rack onto the bare table")
    plate.add_argument("--no-render", action="store_true")
    plate.add_argument("--fault", choices=["missing-object", "skip-close"])
    utensils = commands.add_parser("utensils", help="Open the drawer and place both utensils")
    utensils.add_argument("--no-render", action="store_true")
    utensils.add_argument("--missing-object", choices=["spoon", "fork"])
    utensils.add_argument("--skip-close", choices=["spoon", "fork"])
    dataset_export = commands.add_parser(
        "dataset-export", help="Export verified recordings to local LeRobot v3"
    )
    dataset_export.add_argument("run_roots", type=Path, nargs="+")
    dataset_export.add_argument("--destination", type=Path, required=True)
    dataset_export.add_argument(
        "--repo-id", required=True, help="Local dataset identifier; nothing is uploaded"
    )
    dataset_export.add_argument("--comparison-run", type=Path, action="append", default=[])
    corrective_export = commands.add_parser(
        "corrective-export", help="Export verified correction intervals to local LeRobot"
    )
    corrective_export.add_argument("--views", type=Path, required=True)
    corrective_export.add_argument("--destination", type=Path, required=True)
    corrective_export.add_argument("--repo-id", required=True)
    corrective_verify = commands.add_parser(
        "corrective-export-check", help="Verify corrective export against original recordings"
    )
    corrective_verify.add_argument("dataset", type=Path)
    skill_views = commands.add_parser(
        "dataset-skill-views", help="Derive bounded training views from a verified dinner export"
    )
    skill_views.add_argument("--dataset", type=Path, required=True)
    skill_views.add_argument("--destination", type=Path, required=True)
    checkpoint = commands.add_parser(
        "skill-checkpoint", help="Verify a development dinner checkpoint; not a quality approval"
    )
    checkpoint.add_argument("training_run", type=Path)
    checkpoint.add_argument("--skill-id", required=True)
    checkpoint.add_argument("--dataset", type=Path, required=True)
    checkpoint.add_argument(
        "--corrective-dataset",
        type=Path,
        help="Explicit relocated copy of the same verified corrective dataset",
    )
    probe = commands.add_parser(
        "training-probe", help="ACT optimizer/inference runtime check, not task training"
    )
    probe.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    probe.add_argument("--architecture", choices=["small", "default"], default="small")
    probe.add_argument("--seed", type=int, default=0)
    probe.add_argument("--train-steps", type=int, default=1)
    probe.add_argument("--chunk-size", type=int, default=10)
    train = commands.add_parser("train", help="Train ACT on a verified local demonstration dataset")
    train.add_argument("--dataset", type=Path, required=True)
    train.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    train.add_argument("--architecture", choices=["small", "default"], default="small")
    train.add_argument("--steps", type=int, default=3)
    train.add_argument("--batch-size", type=int, default=1)
    train.add_argument("--chunk-size", type=int, default=10)
    train.add_argument("--seed", type=int, default=0)
    train.add_argument(
        "--sampling-profile",
        choices=["uniform", "approach_regions_v1", "approach_nominal_launch_v1"],
        default="uniform",
    )
    train.add_argument("--no-vae", action="store_true", help="Matched-initialization ACT ablation")
    train.add_argument("--dropout", type=float, default=0.1)
    train.add_argument(
        "--learning-rate-schedule", choices=["constant", "terminal_linear"], default="constant"
    )
    train.add_argument(
        "--temporal-loss-profile",
        choices=["uniform", "first_action_half_v1"],
        default="uniform",
        help="Experimental first-action weighting requires --no-vae and chunk size >=2",
    )
    train.add_argument(
        "--corrective-dataset",
        type=Path,
        help="Optional verified approach corrections; handoff skill only",
    )
    train.add_argument("--skill-views", type=Path)
    train.add_argument("--skill-id")
    train.add_argument("--sampling-protocol-run", type=Path)
    rollout = commands.add_parser(
        "policy-rollout", help="Evaluate an ACT checkpoint in its declared placement scene"
    )
    rollout.add_argument("training_run", type=Path)
    rollout.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    rollout.add_argument("--max-seconds", type=float, default=23)
    rollout.add_argument("--execute-chunk-steps", type=int, default=10)
    rollout.add_argument("--temporal-ensemble-coefficient", type=float)
    rollout.add_argument(
        "--no-replay", action="store_true", help="Keep policy cameras; omit display GIF"
    )
    planner = commands.add_parser(
        "planner-probe", help="Propose a skill from recorded cameras using local Qwen; no actions"
    )
    planner.add_argument("--model-root", type=Path, required=True)
    planner.add_argument("--recording", type=Path, required=True)
    planner.add_argument(
        "--sensor-bundle", type=Path, help="Verified reset-only planner sensor run"
    )
    planner.add_argument("--frame", type=int, default=0)
    planner.add_argument("--instruction", required=True)
    planner.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    planner.add_argument("--max-tokens", type=int, default=384)
    planner_suite_create = commands.add_parser(
        "planner-suite-create", help="Freeze source-bound visual-planner evaluation cases"
    )
    planner_suite_create.add_argument("--spec", type=Path, required=True)
    planner_suite_create.add_argument("--model-root", type=Path, required=True)
    planner_suite_create.add_argument("--destination", type=Path, required=True)
    planner_suite_check = commands.add_parser(
        "planner-suite-check", help="Verify a frozen visual-planner evaluation protocol"
    )
    planner_suite_check.add_argument("protocol", type=Path)
    planner_suite_run = commands.add_parser(
        "planner-suite-run", help="Run every frozen visual-planner case without dispatch"
    )
    planner_suite_run.add_argument("protocol", type=Path)
    planner_suite_run.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    planner_suite_run.add_argument("--max-tokens", type=int, default=384)
    sensors = commands.add_parser(
        "planner-sensors", help="Render verified reset-only higher-resolution planner cameras"
    )
    sensors.add_argument("--recording", type=Path, required=True)
    sensors.add_argument(
        "--profile", choices=["overhead960_wrist480_v1", "overhead1920_wrist480_v1"], required=True
    )
    commands.add_parser("docs-check", help="Validate local documentation links and rubric weights")
    evidence = commands.add_parser("evidence", help="List or verify sealed preparation runs")
    evidence.add_argument("operation", choices=["list", "verify"])
    evidence.add_argument("run_id", nargs="?")
    serve = commands.add_parser("serve", help="Serve the read-only project and learning portal")
    serve.add_argument("--port", type=int, default=8767)
    serve.add_argument(
        "--operator-config",
        type=Path,
        help="Opt in to local workflow control with a server-owned WorkflowProcessConfig JSON file",
    )
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    artifacts = args.artifacts if args.artifacts.is_absolute() else root / args.artifacts
    try:
        if platform.system() == "Darwin" and platform.machine() != "arm64":
            raise RuntimeError("Native arm64 Python is required on this Mac")
        from bimanual.evidence import EvidenceStore, provenance

        store = EvidenceStore(artifacts)
        if args.command == "doctor":
            from bimanual.doctor import diagnose

            report = diagnose(args.require_device)
            if args.record:
                directory = store.new_run()
                (directory / "doctor.json").write_text(json.dumps(report, indent=2) + "\n")
                manifest = store.seal(
                    directory,
                    kind="preparation_runtime",
                    outcome=report["outcome"],
                    config={"requested_device": args.require_device},
                    metrics=report,
                    source=provenance(root),
                    claims=["runtime_probe"] if report["outcome"] == "passed" else [],
                )
                report["run_id"] = manifest.run_id
            emit(report)
            return 0 if report["outcome"] == "passed" else 1
        if args.command == "lab":
            from bimanual.lab import LabConfig, run_lab

            result = run_lab(
                LabConfig(
                    seed=args.seed,
                    seconds=args.seconds,
                    damping=args.damping,
                    torque=args.torque,
                    render=not args.no_render,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
        elif args.command == "sim":
            from bimanual.dual_arm import FoundationConfig, run_foundation

            result = run_foundation(
                FoundationConfig(seconds=args.seconds, render=not args.no_render),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
        elif args.command == "grasp":
            from bimanual.grasp import GraspConfig, run_grasp

            result = run_grasp(
                GraspConfig(
                    render=not args.no_render,
                    missing_object=args.fault == "missing-object",
                    skip_close=args.fault == "skip-close",
                    arm=args.arm,
                    record_demo=args.record_demo,
                    seed=args.seed,
                    split=args.split,
                    destination_xy=tuple(args.destination)
                    if args.destination is not None
                    else None,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "plate":
            from bimanual.plate import PlateConfig, run_plate

            result = run_plate(
                PlateConfig(
                    render=not args.no_render,
                    missing_object=args.fault == "missing-object",
                    skip_close=args.fault == "skip-close",
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "utensils":
            from bimanual.utensils import UtensilConfig, run_utensils

            result = run_utensils(
                UtensilConfig(
                    render=not args.no_render,
                    missing_object=args.missing_object,
                    skip_close=args.skip_close,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "dinner-teacher":
            from bimanual.dinner_teacher import DinnerTeacherConfig, run_dinner_teacher

            result = run_dinner_teacher(
                DinnerTeacherConfig(
                    recipe=args.recipe,
                    render=not args.no_render,
                    record_demonstration=args.record_demonstration,
                    visual_seed=args.visual_seed,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "feedback-approach":
            from bimanual.feedback_teacher import FeedbackApproachConfig, run_feedback_approach

            result = run_feedback_approach(
                FeedbackApproachConfig(
                    record_demonstration=args.record_demonstration,
                    variation_seed=args.variation_seed,
                    acquisition_offset_rad=args.acquisition_offset_rad,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "handoff-continuity-protocol-create":
            from bimanual.handoff_continuity_protocol import (
                create_handoff_continuity_protocol,
            )

            result = create_handoff_continuity_protocol(
                evidence_root=store.root,
                diagnosis_run_id=args.diagnosis_run,
                destination=args.destination,
            )
            emit(result.model_dump(mode="json"))
        elif args.command == "handoff-continuity-protocol-check":
            from bimanual.handoff_continuity_protocol import (
                load_handoff_continuity_protocol,
            )

            result = load_handoff_continuity_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "handoff-continuity-run":
            from bimanual.handoff_continuity_process import (
                HandoffContinuityProcessConfig,
                run_handoff_continuity_process,
            )

            result = run_handoff_continuity_process(
                HandoffContinuityProcessConfig(
                    protocol_path=args.protocol,
                    case_id=args.case_id,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "handoff-continuity-views-create":
            from bimanual.handoff_continuity_views import create_handoff_continuity_views

            result = create_handoff_continuity_views(store, args.run_id, args.destination)
            emit(result.model_dump(mode="json"))
        elif args.command == "handoff-continuity-views-check":
            from bimanual.handoff_continuity_views import load_handoff_continuity_views

            result = load_handoff_continuity_views(args.manifest, store)
            emit(result.model_dump(mode="json"))
        elif args.command == "handoff-continuity-export":
            from bimanual.handoff_continuity_export import (
                export_handoff_continuity_dataset,
            )

            result = invoke_with_diagnostics(
                export_handoff_continuity_dataset,
                args.views,
                store,
                args.destination,
                args.repo_id,
            )
            emit({"dataset": str(result)})
        elif args.command == "handoff-continuity-export-check":
            from bimanual.handoff_continuity_export import (
                verify_handoff_continuity_dataset,
            )

            emit(invoke_with_diagnostics(verify_handoff_continuity_dataset, args.dataset))
        elif args.command == "corrective-views-create":
            from bimanual.corrective_views import create_corrective_views

            result = create_corrective_views(store, args.run_id, args.destination)
            emit(result.model_dump())
        elif args.command == "corrective-views-check":
            from bimanual.corrective_views import load_corrective_views

            result = load_corrective_views(args.manifest, store)
            emit(result.model_dump())
        elif args.command == "visual-protocol-check":
            from bimanual.visual_training import load_visual_training_protocol

            result = load_visual_training_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "visual-source-check":
            from bimanual.visual_source import verify_visual_source

            result = verify_visual_source(args.run_root, protocol_path=args.protocol)
            emit(
                dict(
                    outcome="verified",
                    run_id=result.manifest.run_id,
                    source_manifest_sha256=result.manifest.manifest_sha256,
                    protocol_sha256=result.protocol_sha256,
                    episode_sha256=result.episode_sha256,
                    physical_layout_count=result.physical_layout_count,
                    lerobot_decoded_parity=result.lerobot_decoded_parity,
                )
            )
        elif args.command == "scene-variant-protocol-create":
            from bimanual.scene_variant_protocol import create_dinner_perturbation_protocol

            result = create_dinner_perturbation_protocol(args.destination)
            emit(result.model_dump(mode="json"))
        elif args.command == "scene-variant-protocol-check":
            from bimanual.scene_variant_protocol import load_dinner_perturbation_protocol

            result = load_dinner_perturbation_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "scene-variant-prepare":
            from bimanual.scene_variant_protocol import create_scene_variant_bundle

            result = create_scene_variant_bundle(
                protocol_path=args.protocol,
                family=args.family,
                seed=args.seed,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
        elif args.command == "scene-variant-suite-prepare":
            from bimanual.scene_variant_suite import prepare_scene_variant_suite

            result = prepare_scene_variant_suite(
                protocol_path=args.protocol,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
        elif args.command == "training-cohort-create":
            from bimanual.training_cohort import create_training_cohort_protocol

            result = create_training_cohort_protocol(
                args.dataset,
                args.skill_views,
                {
                    "experiment_protocol": args.experiment_protocol_run,
                    "training": args.training_run,
                    "recorded": args.recorded_run,
                    "physical_prefix2": args.physical_prefix2_run,
                    "physical_prefix5": args.physical_prefix5_run,
                },
                store=store,
                destination=args.destination,
            )
            emit(result.model_dump(mode="json"))
        elif args.command == "training-cohort-check":
            from bimanual.training_cohort import load_training_cohort_protocol

            result = load_training_cohort_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "training-cohort-run":
            from bimanual.training_cohort_runner import run_training_cohort_skill

            result = run_training_cohort_skill(args.protocol, args.skill)
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "training-cohort-run-all":
            from bimanual.training_cohort_sequence import run_training_cohort_sequence

            result = invoke_with_diagnostics(
                run_training_cohort_sequence,
                args.protocol,
                wait_for_active_seconds=args.wait_for_active_seconds,
            )
            emit(result)
            return 0 if result["all_training_complete"] else 1
        elif args.command == "skill-physical-eval":
            from bimanual.skill_physical_evaluation import (
                SkillPhysicalEvaluationConfig,
                run_skill_physical_evaluation,
            )

            result = invoke_with_diagnostics(
                run_skill_physical_evaluation,
                SkillPhysicalEvaluationConfig(
                    training_run=args.training_run,
                    dataset_root=args.dataset,
                    skill_views_path=args.skill_views,
                    skill_id=args.skill,
                    device=args.device,
                    max_actions=args.max_actions,
                    execute_chunk_steps=args.execute_chunk_steps,
                    wall_timeout_seconds=args.wall_timeout_seconds,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "skill-physical-protocol-create":
            from bimanual.skill_physical_protocol import create_skill_physical_protocol

            result = create_skill_physical_protocol(args.training_cohort, args.destination)
            emit(result.model_dump(mode="json"))
        elif args.command == "skill-physical-protocol-check":
            from bimanual.skill_physical_protocol import load_skill_physical_protocol

            result = load_skill_physical_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "skill-physical-protocol-run":
            from bimanual.skill_physical_protocol_runner import (
                run_skill_physical_protocol,
            )

            result = invoke_with_diagnostics(
                run_skill_physical_protocol,
                args.protocol,
                args.skill,
                args.training_attempt,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "skill-physical-protocol-run-all":
            from bimanual.skill_physical_sequence import run_skill_physical_sequence

            result = invoke_with_diagnostics(run_skill_physical_sequence, args.protocol)
            emit(result)
            return 0 if result["evaluations_complete"] else 1
        elif args.command == "skill-physical-suite-report":
            from bimanual.skill_physical_suite import run_skill_physical_suite_report

            result = run_skill_physical_suite_report(args.protocol)
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "handoff-failure-analyze":
            from bimanual.handoff_failure_analysis import (
                HandoffFailureAnalysisConfig,
                analyse_handoff_failures,
            )

            result = analyse_handoff_failures(
                HandoffFailureAnalysisConfig(wrapper_run_ids=tuple(args.wrapper_run_ids)),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
        elif args.command == "dinner-evaluate":
            from bimanual.dinner_evaluation import evaluate_dinner_run

            result = evaluate_dinner_run(
                args.run_id,
                store=store,
                project_root=root,
                instrumentation_run=args.instrumentation_run,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "training-cohort-adjudicate-preflight":
            from bimanual.training_cohort_adjudication import (
                adjudicate_training_cohort_preflight,
            )

            result = adjudicate_training_cohort_preflight(args.protocol, args.attempt)
            emit(result.model_dump(exclude={"provenance"}))
        elif args.command == "workflow-create":
            from bimanual.workflow_manifest import SKILLS, create_workflow_manifest

            if len(args.training_run) != len(SKILLS):
                raise ValueError("Supply exactly seven ordered --training-run arguments")
            result = create_workflow_manifest(
                args.dataset,
                args.skill_views,
                dict(zip(SKILLS, args.training_run, strict=True)),
                args.destination,
                **(
                    {
                        "corrective_dataset_roots": {
                            "handoff_transfer": args.handoff_corrective_dataset
                        }
                    }
                    if args.handoff_corrective_dataset is not None
                    else {}
                ),
            )
            emit(result.report())
        elif args.command == "workflow-check":
            from bimanual.workflow_manifest import load_workflow_manifest

            emit(load_workflow_manifest(args.manifest).report())
        elif args.command in {
            "workflow-activate",
            "workflow-deployment-status",
            "workflow-rollback",
        }:
            from bimanual.workflow_deployment import (
                activate_workflow,
                deployment_report,
                load_active_workflow,
                rollback_workflow,
            )

            deployment_root = args.deployment_root or artifacts / "workflow-deployment"
            if not deployment_root.is_absolute():
                deployment_root = root / deployment_root
            if args.command == "workflow-activate":
                result = activate_workflow(args.manifest, deployment_root)
            elif args.command == "workflow-rollback":
                result = rollback_workflow(deployment_root, args.target_id)
            else:
                result = load_active_workflow(deployment_root)
            emit(deployment_report(result))
        elif args.command == "workflow-run":
            from bimanual.workflow_execution import WorkflowExecutionConfig, run_workflow_execution

            if (args.manifest is None) == (args.deployment_root is None):
                raise ValueError("Supply exactly one manifest or --deployment-root")
            workflow_manifest = args.manifest
            if args.deployment_root is not None:
                from bimanual.workflow_deployment import active_workflow_path

                deployment_root = args.deployment_root
                if not deployment_root.is_absolute():
                    deployment_root = root / deployment_root
                workflow_manifest = active_workflow_path(deployment_root)
            execution = WorkflowExecutionConfig(
                workflow_manifest=workflow_manifest,
                planner_model_directory=args.planner_model,
                scene_variant_run=args.scene_variant,
                instruction=args.instruction,
                policy_device=args.policy_device,
                planner_device=args.planner_device,
                camera_profile=args.camera_profile,
                wall_timeout_seconds=args.wall_timeout_seconds,
                step_timeout_seconds=args.step_timeout_seconds,
                max_tokens=args.max_tokens,
            )
            if args.in_process:
                function, config = run_workflow_execution, execution
            else:
                from bimanual.workflow_process import WorkflowProcessConfig, run_workflow_process

                function = run_workflow_process
                config = WorkflowProcessConfig(execution=execution)
            result = invoke_with_diagnostics(function, config, store=store, project_root=root)
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "workflow-release-create":
            from bimanual.workflow_release_protocol import create_workflow_release_protocol

            result = create_workflow_release_protocol(
                workflow_manifest=args.workflow_manifest,
                planner_model_root=args.planner_model,
                scene_suite_run=args.scene_suite_run,
                perturbation_protocol_path=args.perturbation_protocol,
                instruction=args.instruction,
                destination=args.destination,
            )
            emit(result.model_dump(mode="json"))
        elif args.command == "workflow-release-check":
            from bimanual.workflow_release_protocol import load_workflow_release_protocol

            result = load_workflow_release_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "workflow-release-run":
            from bimanual.workflow_release_runner import run_workflow_release_case

            result = run_workflow_release_case(
                args.protocol,
                args.case_id,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.metrics["independent_task_success"] is True else 1
        elif args.command == "workflow-release-suite":
            from bimanual.workflow_release_suite import create_workflow_release_suite

            result = create_workflow_release_suite(
                args.protocol,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.metrics["local_prequalification_passed"] is True else 1
        elif args.command in {"submission-check", "submission-create"}:
            from bimanual.submission_package import (
                SubmissionInputs,
                create_submission_package,
                inspect_submission_requirements,
            )

            inputs = SubmissionInputs(
                project_root=root,
                repository_revision=args.revision,
                release_protocol=args.release_protocol,
                release_suite=args.release_suite,
                interactive_url=args.interactive_url,
                video=args.video,
                slides=args.slides,
                cover=args.cover,
            )
            if args.command == "submission-check":
                report = inspect_submission_requirements(inputs)
                emit(report.model_dump(mode="json"))
                return 0 if report.complete else 1
            result = create_submission_package(inputs, args.destination)
            emit(result.model_dump(mode="json"))
        elif args.command == "submission-verify":
            from bimanual.submission_package import verify_submission_package

            result = verify_submission_package(args.package, project_root=root)
            emit(result.model_dump(mode="json"))
        elif args.command == "cup":
            from bimanual.cup import CupConfig, run_cup

            result = run_cup(
                CupConfig(
                    arm=args.arm,
                    render=not args.no_render,
                    missing_object=args.fault == "missing-object",
                    skip_close=args.fault == "skip-close",
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "drawer":
            from bimanual.drawer import DrawerConfig, run_drawer

            result = run_drawer(
                DrawerConfig(
                    render=not args.no_render,
                    missing_handle=args.fault == "missing-handle",
                    skip_close=args.fault == "skip-close",
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "handoff":
            from bimanual.handoff import HandoffConfig, run_handoff

            result = run_handoff(
                HandoffConfig(
                    render=not args.no_render,
                    missing_object=args.fault == "missing-object",
                    skip_receiver_close=args.fault == "skip-receiver-close",
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "policy-rollout":
            from bimanual.policy_rollout import PolicyRolloutConfig, run_policy_rollout

            result = invoke_with_diagnostics(
                run_policy_rollout,
                PolicyRolloutConfig(
                    training_run=args.training_run,
                    device=args.device,
                    max_seconds=args.max_seconds,
                    execute_chunk_steps=args.execute_chunk_steps,
                    temporal_ensemble_coefficient=args.temporal_ensemble_coefficient,
                    replay=not args.no_replay,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "train":
            from bimanual.training import ACTTrainingConfig, run_train

            result = invoke_with_diagnostics(
                run_train,
                ACTTrainingConfig(
                    dataset_path=args.dataset,
                    device=args.device,
                    architecture=args.architecture,
                    steps=args.steps,
                    batch_size=args.batch_size,
                    chunk_size=args.chunk_size,
                    seed=args.seed,
                    sampling_profile=args.sampling_profile,
                    use_vae=not args.no_vae,
                    dropout=args.dropout,
                    learning_rate_schedule=args.learning_rate_schedule,
                    temporal_loss_profile=args.temporal_loss_profile,
                    corrective_dataset_path=args.corrective_dataset,
                    skill_views_path=args.skill_views,
                    skill_id=args.skill_id,
                    sampling_protocol_run=args.sampling_protocol_run,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "training-probe":
            from bimanual.training_probe import TrainingProbeConfig, run_training_probe

            result = invoke_with_diagnostics(
                run_training_probe,
                TrainingProbeConfig(
                    device=args.device,
                    architecture=args.architecture,
                    seed=args.seed,
                    train_steps=args.train_steps,
                    chunk_size=args.chunk_size,
                ),
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "dataset-export":
            from bimanual.dataset_export import export_lerobot_dataset

            result = invoke_with_diagnostics(
                export_lerobot_dataset,
                tuple(args.run_roots),
                args.destination,
                repo_id=args.repo_id,
                comparison_run_roots=tuple(args.comparison_run),
            )
            emit({"destination": str(result), "manifest": str(result / "export_manifest.json")})
        elif args.command == "corrective-export":
            from bimanual.corrective_export import export_corrective_dataset

            result = invoke_with_diagnostics(
                export_corrective_dataset,
                args.views,
                store,
                args.destination,
                args.repo_id,
            )
            emit({"destination": str(result), "manifest": str(result / "export_manifest.json")})
        elif args.command == "corrective-export-check":
            from bimanual.corrective_export import verify_corrective_dataset

            emit(invoke_with_diagnostics(verify_corrective_dataset, args.dataset))
        elif args.command == "dataset-skill-views":
            from bimanual.skill_views import create_skill_views

            result = create_skill_views(args.dataset, args.destination)
            emit(result.model_dump(mode="json"))
        elif args.command == "skill-checkpoint":
            from bimanual.skill_registry import load_skill_checkpoint

            binding = load_skill_checkpoint(
                args.training_run,
                skill_id=args.skill_id,
                dataset_root=args.dataset,
                **(
                    {"corrective_dataset_root": args.corrective_dataset}
                    if args.corrective_dataset is not None
                    else {}
                ),
            )
            emit(binding.report())
        elif args.command == "status":
            emit(json.loads((root / "docs/project.json").read_text()))
        elif args.command == "planner-sensors":
            from bimanual.planner_sensors import create_sensor_bundle

            result = invoke_with_diagnostics(
                create_sensor_bundle,
                recording=args.recording,
                profile=args.profile,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "planner-probe":
            from bimanual.planner import run_planner_probe

            result = invoke_with_diagnostics(
                run_planner_probe,
                model_root=args.model_root,
                recording=args.recording,
                frame=args.frame,
                instruction=args.instruction,
                device=args.device,
                max_tokens=args.max_tokens,
                sensor_bundle=args.sensor_bundle,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "planner-suite-create":
            from bimanual.planner_decision_suite import create_planner_decision_protocol

            result = create_planner_decision_protocol(
                spec_path=args.spec,
                model_root=args.model_root,
                destination=args.destination,
            )
            emit(result.model_dump(mode="json"))
        elif args.command == "planner-suite-check":
            from bimanual.planner_decision_suite import load_planner_decision_protocol

            result = load_planner_decision_protocol(args.protocol)
            emit(result.model_dump(mode="json"))
        elif args.command == "planner-suite-run":
            from bimanual.planner_decision_suite import run_planner_decision_suite

            result = invoke_with_diagnostics(
                run_planner_decision_suite,
                protocol_path=args.protocol,
                device=args.device,
                max_tokens=args.max_tokens,
                store=store,
                project_root=root,
            )
            emit(result.model_dump(exclude={"provenance"}))
            return 0 if result.outcome == "completed" else 1
        elif args.command == "docs-check":
            from bimanual.docs import check_docs

            report = check_docs(root)
            emit(report)
            return 0 if report["outcome"] == "passed" else 1
        elif args.command == "evidence":
            if args.operation == "verify":
                if not args.run_id:
                    parser.error("evidence verify requires a run_id")
                emit(store.verify(args.run_id).model_dump(exclude={"provenance"}))
            else:
                emit(store.list_runs())
        elif args.command == "serve":
            import uvicorn

            from bimanual.api import create_app

            operator_config = None
            if args.operator_config is not None:
                from bimanual.workflow_process import WorkflowProcessConfig

                config_path = args.operator_config
                if not config_path.is_absolute():
                    config_path = root / config_path
                operator_config = WorkflowProcessConfig.model_validate_json(config_path.read_text())
            uvicorn.run(
                create_app(root, artifacts, operator_config=operator_config),
                host="127.0.0.1",
                port=args.port,
            )
        return 0
    except KeyboardInterrupt:
        emit({"outcome": "interrupted"})
        return 130
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        emit({"outcome": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
