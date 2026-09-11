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
    corrective_create = commands.add_parser(
        "corrective-views-create", help="Pin verified approach correction intervals"
    )
    corrective_create.add_argument("--run-id", action="append", required=True)
    corrective_create.add_argument("--destination", type=Path, required=True)
    corrective_check = commands.add_parser(
        "corrective-views-check", help="Verify corrective source recordings and boundaries"
    )
    corrective_check.add_argument("manifest", type=Path)
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
    workflow_run = commands.add_parser(
        "workflow-run", help="Execute a verified local seven-skill workflow; not a quality approval"
    )
    workflow_run.add_argument("manifest", type=Path)
    workflow_run.add_argument("--planner-model", type=Path, required=True)
    workflow_run.add_argument("--instruction", required=True)
    workflow_run.add_argument("--policy-device", choices=["cpu", "mps"], default="cpu")
    workflow_run.add_argument("--planner-device", choices=["cpu", "mps"], default="cpu")
    workflow_run.add_argument(
        "--camera-profile",
        choices=["policy480_v1", "overhead1920_wrist480_v1"],
        default="policy480_v1",
    )
    workflow_run.add_argument("--wall-timeout-seconds", type=float, default=1800)
    workflow_run.add_argument("--max-actions-per-skill", type=int, default=2000)
    workflow_run.add_argument("--max-tokens", type=int, default=384)
    workflow_run.add_argument("--step-timeout-seconds", type=float, default=300)
    workflow_run.add_argument(
        "--in-process",
        action="store_true",
        help="Diagnostic mode: cooperative stops only; default uses an isolated process",
    )

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
        elif args.command == "corrective-views-create":
            from bimanual.corrective_views import create_corrective_views

            result = create_corrective_views(store, args.run_id, args.destination)
            emit(result.model_dump())
        elif args.command == "corrective-views-check":
            from bimanual.corrective_views import load_corrective_views

            result = load_corrective_views(args.manifest, store)
            emit(result.model_dump())
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
        elif args.command == "workflow-run":
            from bimanual.workflow_execution import WorkflowExecutionConfig, run_workflow_execution

            execution = WorkflowExecutionConfig(
                workflow_manifest=args.manifest,
                planner_model_directory=args.planner_model,
                instruction=args.instruction,
                policy_device=args.policy_device,
                planner_device=args.planner_device,
                camera_profile=args.camera_profile,
                wall_timeout_seconds=args.wall_timeout_seconds,
                max_actions_per_skill=args.max_actions_per_skill,
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
