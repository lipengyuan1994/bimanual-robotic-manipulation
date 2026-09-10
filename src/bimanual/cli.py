from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path


def emit(data: object) -> None:
    print(json.dumps(data, indent=2, allow_nan=False))


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
    commands.add_parser("status", help="Read the maintained project status")
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
        elif args.command == "status":
            emit(json.loads((root / "docs/project.json").read_text()))
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
