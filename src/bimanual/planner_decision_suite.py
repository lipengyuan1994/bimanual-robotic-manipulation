"""Frozen, source-bound visual-planner decisions; never robot execution evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import traceback
from pathlib import Path
from typing import Annotated, Literal

from PIL import Image
from pydantic import Field, model_validator

from bimanual.contracts import Contract, DemonstrationEpisode, Digest, SkillRequest
from bimanual.evidence import EvidenceStore, Manifest, canonical, digest_file, provenance
from bimanual.planner import (
    LocalQwenPlanner,
    PlannerContext,
    SkillName,
    camera_images,
    parse_proposal,
    planner_messages,
    verify_model,
)
from bimanual.planner_sensors import SensorBundle, load_sensor_bundle, observation_digest


class ExpectedDecision(Contract):
    skill: SkillName
    arm: Literal["left", "right", "both", "none"]
    target: Literal["drawer", "spoon", "fork", "plate", "cup", "practice_block"] | None
    destination: Literal["table", "drawer", "left_gripper", "right_gripper"] | None
    target_visibility: Literal["visible", "not_visible", "uncertain"]
    visible_state: Literal["uncertain", "incomplete", "apparently_complete"]

    @model_validator(mode="after")
    def supported_combination(self):
        SkillRequest(
            episode_id="frozen-expectation",
            instruction_revision=0,
            observation_sequence=0,
            skill=self.skill,
            arm=self.arm,
            target=self.target,
            destination=self.destination,
            explanation="Frozen expected decision shape.",
        )
        if self.skill not in ("stop", "clarify") and self.target_visibility != "visible":
            raise ValueError("Expected manipulation requires a visible target")
        if self.skill not in ("stop", "clarify") and self.visible_state == "apparently_complete":
            raise ValueError("Expected completed state cannot request manipulation")
        return self


class PlannerDecisionCaseSpec(Contract):
    case_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
    recording: Annotated[str, Field(min_length=1)]
    frame: Annotated[int, Field(strict=True, ge=0)]
    sensor_bundle: str | None = None
    instruction: Annotated[str, Field(min_length=1, max_length=4096)]
    completed_steps: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    retry_number: Annotated[int, Field(strict=True, ge=0, le=2)] = 0
    available_skills: Annotated[tuple[SkillName, ...], Field(max_length=6)]
    accepted_decisions: Annotated[tuple[ExpectedDecision, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def safe_paths(self):
        for value in (self.recording, self.sensor_bundle):
            if value is not None and (not value or Path(value).is_absolute()):
                raise ValueError("Case source paths must be relative to the case specification")
        return self


class FrozenPlannerDecisionCase(PlannerDecisionCaseSpec):
    source_run_id: str
    source_manifest_sha256: Digest
    source_observation_sha256: Digest
    sensor_run_id: str | None = None
    sensor_manifest_sha256: Digest | None = None
    camera_profile: Literal["policy480_v1", "overhead960_wrist480_v1", "overhead1920_wrist480_v1"]

    @model_validator(mode="after")
    def sensor_binding(self):
        values = (self.sensor_bundle, self.sensor_run_id, self.sensor_manifest_sha256)
        if (values[0] is None) != (values[1] is None or values[2] is None):
            raise ValueError("Sensor path and identity must be present together")
        if self.sensor_bundle is None and self.camera_profile != "policy480_v1":
            raise ValueError("Higher-resolution profiles require a frozen sensor bundle")
        if self.sensor_bundle is not None and self.camera_profile == "policy480_v1":
            raise ValueError("Sensor bundles cannot claim the policy camera profile")
        return self


class PlannerDecisionProtocol(Contract):
    profile: Literal["frozen_qwen_planner_decision_suite_v1"] = (
        "frozen_qwen_planner_decision_suite_v1"
    )
    model_root: str
    model_manifest_sha256: Digest
    model_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    cases: Annotated[tuple[FrozenPlannerDecisionCase, ...], Field(min_length=1)]
    runtime_sources: dict[str, Digest]
    selection_rule: Literal["evaluate_every_frozen_case_once"] = "evaluate_every_frozen_case_once"
    scope: Literal["visual_decisions_only_no_live_dispatch_or_manipulation_claim"] = (
        "visual_decisions_only_no_live_dispatch_or_manipulation_claim"
    )
    live_dispatch_authorized: Literal[False] = False
    manipulation_success: None = None
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_declaration(self):
        if not self.model_root or Path(self.model_root).is_absolute():
            raise ValueError("Model root must be relative to the protocol")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Planner decision case ids must be unique")
        if set(self.runtime_sources) != {"planner.py", "planner_decision_suite.py"}:
            raise ValueError("Planner protocol runtime source set changed")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Planner decision protocol body seal mismatch")
        return self


def _source_recording(path: Path) -> tuple[Manifest, DemonstrationEpisode]:
    path = path.resolve(strict=True)
    manifest = EvidenceStore(path.parent.parent).verify(path.name)
    if manifest.outcome != "completed" or "demonstration/episode.json" not in manifest.files:
        raise ValueError("Planner case requires a completed sealed demonstration")
    episode = DemonstrationEpisode.model_validate_json(
        (path / "demonstration/episode.json").read_text()
    )
    return manifest, episode


def _runtime_sources() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {
        "planner.py": digest_file(root / "planner.py"),
        "planner_decision_suite.py": digest_file(root / "planner_decision_suite.py"),
    }


def create_planner_decision_protocol(
    *, spec_path: Path, model_root: Path, destination: Path
) -> PlannerDecisionProtocol:
    """Freeze cases before inference; the specification itself makes no quality claim."""
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Planner decision protocol already exists")
    spec_path = spec_path.resolve(strict=True)
    model_root = model_root.resolve(strict=True)
    raw = json.loads(spec_path.read_text())
    if not isinstance(raw, list) or not raw:
        raise ValueError("Planner case specification must be a non-empty JSON list")
    specs = tuple(PlannerDecisionCaseSpec.model_validate(item) for item in raw)
    if len({case.case_id for case in specs}) != len(specs):
        raise ValueError("Planner decision case ids must be unique")
    model = verify_model(model_root)
    frozen = []
    for spec in specs:
        recording = (spec_path.parent / spec.recording).resolve(strict=True)
        source, episode = _source_recording(recording)
        if spec.frame >= len(episode.frames):
            raise ValueError(f"Planner case frame is outside its recording: {spec.case_id}")
        observation = episode.frames[spec.frame].observation
        camera_profile = "policy480_v1"
        sensor_run_id = None
        sensor_manifest_sha256 = None
        sensor_relative = None
        if spec.sensor_bundle is not None:
            sensor = (spec_path.parent / spec.sensor_bundle).resolve(strict=True)
            sensor_manifest = EvidenceStore(sensor.parent.parent).verify(sensor.name)
            bundle = SensorBundle.model_validate_json((sensor / "sensor-bundle.json").read_text())
            load_sensor_bundle(
                sensor,
                observation=observation,
                source_run_id=source.run_id,
                source_manifest_sha256=source.manifest_sha256,
            )
            camera_profile = bundle.profile
            sensor_run_id = sensor_manifest.run_id
            sensor_manifest_sha256 = sensor_manifest.manifest_sha256
            sensor_relative = os.path.relpath(sensor, destination.parent)
        payload = spec.model_dump(mode="json")
        payload.update(
            recording=os.path.relpath(recording, destination.parent),
            sensor_bundle=sensor_relative,
            source_run_id=source.run_id,
            source_manifest_sha256=source.manifest_sha256,
            source_observation_sha256=observation_digest(observation),
            sensor_run_id=sensor_run_id,
            sensor_manifest_sha256=sensor_manifest_sha256,
            camera_profile=camera_profile,
        )
        frozen.append(FrozenPlannerDecisionCase.model_validate(payload))
    body = {
        "schema_version": 1,
        "profile": "frozen_qwen_planner_decision_suite_v1",
        "model_root": os.path.relpath(model_root, destination.parent),
        "model_manifest_sha256": digest_file(model_root / "model-manifest.json"),
        "model_revision": model["revision"],
        "cases": [case.model_dump(mode="json") for case in frozen],
        "runtime_sources": _runtime_sources(),
        "selection_rule": "evaluate_every_frozen_case_once",
        "scope": "visual_decisions_only_no_live_dispatch_or_manipulation_claim",
        "live_dispatch_authorized": False,
        "manipulation_success": None,
    }
    body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    result = PlannerDecisionProtocol.model_validate(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_planner_decision_protocol(path: Path) -> PlannerDecisionProtocol:
    path = path.resolve(strict=True)
    protocol = PlannerDecisionProtocol.model_validate_json(path.read_bytes())
    model_root = (path.parent / protocol.model_root).resolve(strict=True)
    model = verify_model(model_root)
    if (
        digest_file(model_root / "model-manifest.json") != protocol.model_manifest_sha256
        or model["revision"] != protocol.model_revision
    ):
        raise ValueError("Frozen planner model identity changed")
    if _runtime_sources() != protocol.runtime_sources:
        raise ValueError("Planner suite runtime changed after protocol freeze")
    for case in protocol.cases:
        recording = (path.parent / case.recording).resolve(strict=True)
        source, episode = _source_recording(recording)
        if (source.run_id, source.manifest_sha256) != (
            case.source_run_id,
            case.source_manifest_sha256,
        ):
            raise ValueError(f"Planner source identity changed: {case.case_id}")
        if case.frame >= len(episode.frames):
            raise ValueError(f"Planner source frame disappeared: {case.case_id}")
        observation = episode.frames[case.frame].observation
        if observation_digest(observation) != case.source_observation_sha256:
            raise ValueError(f"Planner source observation changed: {case.case_id}")
        if case.sensor_bundle is not None:
            sensor = (path.parent / case.sensor_bundle).resolve(strict=True)
            sensor_manifest = EvidenceStore(sensor.parent.parent).verify(sensor.name)
            if (sensor_manifest.run_id, sensor_manifest.manifest_sha256) != (
                case.sensor_run_id,
                case.sensor_manifest_sha256,
            ):
                raise ValueError(f"Planner sensor identity changed: {case.case_id}")
            load_sensor_bundle(
                sensor,
                observation=observation,
                source_run_id=source.run_id,
                source_manifest_sha256=source.manifest_sha256,
            )
    return protocol


def _serializable_prompt(context, images):
    return [
        dict(
            message,
            content=[
                {key: value for key, value in item.items() if key != "image"}
                for item in message["content"]
            ],
        )
        for message in planner_messages(context, images)
    ]


def _decision_matches(proposal, accepted: tuple[ExpectedDecision, ...]) -> tuple[bool, list[str]]:
    request = proposal.request
    actual = {
        "skill": request.skill,
        "arm": request.arm,
        "target": request.target,
        "destination": request.destination,
        "target_visibility": proposal.target_visibility,
        "visible_state": proposal.visible_state,
    }
    alternatives = [
        [name for name, value in actual.items() if value != getattr(expected, name)]
        for expected in accepted
    ]
    closest = min(alternatives, key=lambda mismatches: (len(mismatches), mismatches))
    return not closest, closest


def run_planner_decision_suite(
    *,
    protocol_path: Path,
    device: str,
    store: EvidenceStore,
    project_root: Path,
    max_tokens: int = 384,
) -> Manifest:
    """Evaluate every frozen case with one model load and retain wrong decisions."""
    import importlib.metadata

    project_root = project_root.resolve()
    protocol_path = (
        protocol_path if protocol_path.is_absolute() else project_root / protocol_path
    ).resolve()
    directory = store.new_run()
    source_at_start = provenance(project_root)
    config = {
        "protocol": str(protocol_path),
        "device": device,
        "max_new_tokens": max_tokens,
        "mode": "frozen_recorded_observations_only",
    }
    metrics = {
        "process_complete": False,
        "all_cases_passed": False,
        "case_count": 0,
        "passed_case_count": 0,
        "failed_case_count": 0,
        "live_dispatch_authorized": False,
        "manipulation_success": None,
    }
    outcome = "failed"
    prepared = []
    try:
        if device not in ("cpu", "mps"):
            raise ValueError("Supported planner devices are cpu and mps")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 1024:
            raise ValueError("Planner output budget must be between 1 and 1024 tokens")
        protocol = load_planner_decision_protocol(protocol_path)
        shutil.copyfile(protocol_path, directory / "protocol.json")
        model_root = (protocol_path.parent / protocol.model_root).resolve(strict=True)
        shutil.copyfile(model_root / "model-manifest.json", directory / "model-manifest.json")
        if digest_file(directory / "model-manifest.json") != protocol.model_manifest_sha256:
            raise ValueError("Planner model manifest changed while copying")
        for case in protocol.cases:
            recording = (protocol_path.parent / case.recording).resolve(strict=True)
            source, episode = _source_recording(recording)
            observation = episode.frames[case.frame].observation
            case_root = directory / "cases" / case.case_id
            case_root.mkdir(parents=True)
            shutil.copyfile(recording / "manifest.json", case_root / "source-manifest.json")
            context = PlannerContext(
                retry_number=case.retry_number,
                observation=observation,
                camera_profile=case.camera_profile,
                instruction=case.instruction,
                completed_steps=case.completed_steps,
                available_skills=case.available_skills,
            )
            if case.sensor_bundle is None:
                images = camera_images(context, recording)
                image_artifacts = observation.frames
                image_roots = (recording,) * len(image_artifacts)
            else:
                sensor = (protocol_path.parent / case.sensor_bundle).resolve(strict=True)
                images = load_sensor_bundle(
                    sensor,
                    observation=observation,
                    source_run_id=source.run_id,
                    source_manifest_sha256=source.manifest_sha256,
                )
                bundle = SensorBundle.model_validate_json(
                    (sensor / "sensor-bundle.json").read_text()
                )
                shutil.copyfile(sensor / "manifest.json", case_root / "sensor-manifest.json")
                image_artifacts = bundle.images
                image_roots = (sensor,) * len(image_artifacts)
            input_root = case_root / "input"
            input_root.mkdir(parents=True)
            copied = []
            for index, (artifact_owner, root) in enumerate(
                zip(image_artifacts, image_roots, strict=True)
            ):
                artifact = artifact_owner.artifact
                target = input_root / f"{index}-{artifact.path.replace('/', '_')}"
                shutil.copyfile(artifact.verify(root), target)
                copied.append(target)
            if [digest_file(path) for path in copied] != [
                owner.artifact.sha256 for owner in image_artifacts
            ]:
                raise ValueError(f"Planner inputs changed while copying: {case.case_id}")
            copied_images = []
            for path, original in zip(copied, images, strict=True):
                with Image.open(path) as image:
                    if image.format != "PNG" or image.mode != "RGB" or image.size != original.size:
                        raise ValueError(f"Copied planner image is invalid: {case.case_id}")
                    image.load()
                    copied_images.append(image.copy())
            if any(
                copied.tobytes() != original.tobytes()
                for copied, original in zip(copied_images, images, strict=True)
            ):
                raise ValueError(f"Planner pixels changed while copying: {case.case_id}")
            images = tuple(copied_images)
            (case_root / "context.json").write_text(context.model_dump_json(indent=2) + "\n")
            (case_root / "prompt.json").write_bytes(
                canonical(_serializable_prompt(context, images)) + b"\n"
            )
            prepared.append((case, context, images, case_root))
        planner = LocalQwenPlanner(model_root, device=device)
        results = []
        for case, context, images, case_root in prepared:
            record = {"case_id": case.case_id, "passed": False, "mismatches": []}
            try:
                text, timing = planner.generate(context, images, max_tokens=max_tokens)
                (case_root / "response.txt").write_text(text)
                (case_root / "inference.json").write_bytes(canonical(timing) + b"\n")
                if timing.get("generation_budget_reached") is not False:
                    raise ValueError("Planner generation reached its token budget")
                proposal = parse_proposal(text, context)
                (case_root / "proposal.json").write_text(proposal.model_dump_json(indent=2) + "\n")
                record["passed"], record["mismatches"] = _decision_matches(
                    proposal, case.accepted_decisions
                )
            except (Exception, KeyboardInterrupt) as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                record["error"] = f"{type(exc).__name__}: {exc}"
                (case_root / "error.txt").write_text(traceback.format_exc())
            (case_root / "evaluation.json").write_bytes(canonical(record) + b"\n")
            results.append(record)
        metrics.update(
            process_complete=True,
            case_count=len(results),
            passed_case_count=sum(result["passed"] for result in results),
            failed_case_count=sum(not result["passed"] for result in results),
            all_cases_passed=all(result["passed"] for result in results),
            protocol_manifest_sha256=protocol.manifest_sha256,
            model_revision=protocol.model_revision,
            requested_device=device,
            actual_device=planner.device,
            precision=planner.dtype,
            model_load_seconds=planner.load_seconds,
        )
        outcome = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        (directory / "error.txt").write_text(traceback.format_exc())
    for package in ("transformers", "torch"):
        try:
            metrics[f"{package}_version"] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            metrics[f"{package}_version"] = None
    (directory / "metrics.json").write_bytes(canonical(metrics) + b"\n")
    return store.seal(
        directory,
        kind="frozen_visual_planner_decision_suite",
        outcome=outcome,
        config=config,
        metrics=metrics,
        source=source_at_start,
        claims=[],
    )
