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
    dinner.add_argument(
        "--record-demonstration",
        action="store_true",
        help="Capture full-rate training cameras and actions independently of replay",
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
                    render=not args.no_render, record_demonstration=args.record_demonstration
                ),
                store=store,
                project_root=root,
            )
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

            uvicorn.run(create_app(root, artifacts), host="127.0.0.1", port=args.port)
        return 0
    except KeyboardInterrupt:
        emit({"outcome": "interrupted"})
        return 130
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        emit({"outcome": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
