"""One-time physical evaluation declaration for the bar corrective checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.skill_physical_process import PROCESS_KIND, SkillPhysicalProcessConfig
from bimanual.skill_physical_protocol import _source_paths
from bimanual.training import ACTTrainingConfig
from bimanual.worker_lease import WorkerLease

PROFILE = "bar_transport_physical_margin_evaluation_protocol_v2"
COMPLETION_PROFILE = "bar_transport_physical_completion_evaluation_protocol_v3"
LATE_CONTACT_PROFILE = "bar_transport_physical_late_contact_evaluation_protocol_v4"
LATE_WORKBENCH_OVERLAP_PROFILE = (
    "bar_transport_physical_late_workbench_overlap_evaluation_protocol_v5"
)
CPU_LATE_WORKBENCH_OVERLAP_PROFILE = (
    "bar_transport_physical_cpu_late_workbench_overlap_evaluation_protocol_v1"
)
SKILL = "bar_place_and_return"
KIND = "learned_skill_teacher_prepared_physical_evaluation"
MARGIN_RAD = 0.001
COMPLETION_PREDECESSOR_RUN_ID = "20260913T231721-0f277ff9c89a"
COMPLETION_PREDECESSOR_MANIFEST_SHA256 = (
    "bedfd660f07018408543c9ff754f1ffcade9ac6ce0e4dc2307c212f8b0f04b2a"
)


def _evaluation_source_paths(root: Path) -> tuple[str, ...]:
    """Include this declaration runner as well as the evaluator runtime."""

    return tuple(sorted(set(_source_paths(root)) | {Path(__file__).name}))


def _clean_process_child(process, child) -> bool:
    """Accept a child only when its guardian certifies clean termination."""

    return (
        process.kind == PROCESS_KIND
        and process.metrics.get("process_complete") is True
        and process.metrics.get("child_manifest_verified") is True
        and process.metrics.get("child_run_id") == child.run_id
        and process.metrics.get("child_manifest_sha256") == child.manifest_sha256
        and process.metrics.get("child_outcome") == child.outcome
        and process.metrics.get("child_reaped") is True
        and process.metrics.get("child_exitcode") == 0
        and process.metrics.get("guardian_terminal_verified") is True
        and process.metrics.get("guardian_reaped") is True
        and process.metrics.get("guardian_exitcode") == 0
        and process.metrics.get("forced_interruption") is False
        and process.metrics.get("component_passed")
        == (child.metrics.get("component_passed") is True)
        and process.outcome == child.outcome
    )


def _verify_prior_failure(store: EvidenceStore, run_id: str, training_run: Path, *, profile: str):
    """Validate the exact failed predecessor appropriate to a declaration profile."""

    prior = store.verify(run_id)
    common = (
        prior.kind != KIND
        or prior.outcome != "failed"
        or prior.config.get("skill_id") != SKILL
        or prior.config.get("device") != "mps"
        or prior.metrics.get("actual_policy_devices") not in (["mps"], ["mps:0"])
    )
    if profile == PROFILE:
        valid = (
            prior.config.get("training_run") == str(training_run)
            and prior.metrics.get("error")
            == "ValueError: Measured dinner joints exceeded model limits"
        )
        error = "Prior evaluation is not the sealed MPS near-limit bar failure"
    elif profile == COMPLETION_PROFILE:
        valid = (
            prior.run_id == COMPLETION_PREDECESSOR_RUN_ID
            and prior.manifest_sha256 == COMPLETION_PREDECESSOR_MANIFEST_SHA256
            and prior.metrics.get("failure_code") == "physical_milestone_incomplete"
            and "readiness not reached" in str(prior.metrics.get("reason", ""))
            and prior.metrics.get("policy_target_margin_rad") == MARGIN_RAD
            and prior.metrics.get("autonomous_skill_actions") == 1900
        )
        error = "Prior evaluation is not the sealed MPS margin completion failure"
    elif profile == LATE_CONTACT_PROFILE:
        valid = (
            prior.run_id == "20260914T013733-48d18dd52514"
            and prior.manifest_sha256
            == "535415a0885eeac772da179d8a764ef1b4086e986693cac60389effc6e4cfb7a"
            and prior.metrics.get("component_passed") is False
            and prior.metrics.get("autonomous_skill_actions") == 24
        )
        error = "Prior evaluation is not the sealed MPS late left-contact failure"
    elif profile in (LATE_WORKBENCH_OVERLAP_PROFILE, CPU_LATE_WORKBENCH_OVERLAP_PROFILE):
        valid = (
            prior.run_id == "20260915T125916-a7977c78bed6"
            and prior.manifest_sha256
            == "2cfe4f44685c85dd69b9a85d79f8c065f42022e6335c9fca10c6341246a0b90b"
            and prior.metrics.get("component_passed") is False
            and prior.metrics.get("autonomous_skill_actions") == 255
            and "overlap_m=" in str(prior.metrics.get("error", ""))
            and "bad_contacts=[]" in str(prior.metrics.get("error", ""))
        )
        error = "Prior evaluation is not the sealed MPS late workbench-overlap failure"
    else:
        raise ValueError("Unsupported bar physical evaluation profile")
    if common or not valid:
        raise ValueError(error)
    return prior


class BarTransportPhysicalProtocol(Contract):
    profile: Literal[
        PROFILE,
        COMPLETION_PROFILE,
        LATE_CONTACT_PROFILE,
        LATE_WORKBENCH_OVERLAP_PROFILE,
        CPU_LATE_WORKBENCH_OVERLAP_PROFILE,
    ] = PROFILE
    training_run: str
    training_manifest_sha256: Digest
    dataset_root: str
    dataset_manifest_sha256: Digest
    skill_views_path: str
    skill_views_sha256: Digest
    sampling_declaration_sha256: Digest
    prior_evaluation_run_id: str
    prior_evaluation_manifest_sha256: Digest
    policy_target_margin_rad: Literal[MARGIN_RAD] = MARGIN_RAD
    evaluation_sources: dict[str, Digest]
    device: Literal["cpu", "mps"] = "mps"
    execute_chunk_steps: Literal[2] = 2
    max_actions: Literal[1900] = 1900
    wall_timeout_seconds: Literal[1200.0] = 1200.0
    execution_authorized_by_this_artifact: Literal[False] = False
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact(self):
        if any(
            not value or Path(value).is_absolute()
            for value in (self.training_run, self.dataset_root, self.skill_views_path)
        ) or set(self.evaluation_sources) != set(
            _evaluation_source_paths(Path(__file__).resolve().parent)
        ):
            raise ValueError("Bar physical evaluation declaration has invalid source bindings")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Bar physical evaluation declaration digest mismatch")
        expected_device = (
            "cpu" if self.profile == CPU_LATE_WORKBENCH_OVERLAP_PROFILE else "mps"
        )
        if self.device != expected_device:
            raise ValueError("Bar physical evaluation declaration device does not match profile")
        return self


def create_bar_transport_physical_protocol(
    training_run: Path, destination: Path, prior_evaluation_run: str
) -> BarTransportPhysicalProtocol:
    """Freeze one evaluation only after a matching corrective run completed."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Bar physical evaluation declaration already exists")
    training_run = Path(training_run).resolve(strict=True)
    store = EvidenceStore(training_run.parents[1])
    manifest = store.verify(training_run.name)
    config = ACTTrainingConfig.model_validate(manifest.config)
    actual_device = manifest.metrics.get("actual_device")
    profile = (
        CPU_LATE_WORKBENCH_OVERLAP_PROFILE
        if (
            config.sampling_profile == "bar_late_workbench_overlap_sampling_v7"
            and actual_device == "cpu"
        )
        else LATE_WORKBENCH_OVERLAP_PROFILE
        if config.sampling_profile == "bar_late_workbench_overlap_sampling_v7"
        else LATE_CONTACT_PROFILE
        if config.sampling_profile == "bar_late_left_contact_sampling_v6"
        else COMPLETION_PROFILE
        if config.sampling_profile == "bar_margin_completion_sampling_v5"
        else PROFILE
    )
    prior = _verify_prior_failure(store, prior_evaluation_run, training_run, profile=profile)
    if (
        manifest.kind != "act_training"
        or manifest.outcome != "completed"
        or manifest.metrics.get("training_completed") is not True
        or actual_device not in {"cpu", "mps"}
        or (actual_device == "cpu" and profile != CPU_LATE_WORKBENCH_OVERLAP_PROFILE)
        or (actual_device == "mps" and profile == CPU_LATE_WORKBENCH_OVERLAP_PROFILE)
        or config.skill_id != SKILL
        or config.sampling_profile
        not in {
            "bar_transport_placement_v1",
            "bar_entry_contact_sampling_v2",
            "bar_placement_progress_sampling_v3",
            "bar_placement_contact_sampling_v4",
            "bar_margin_completion_sampling_v5",
            "bar_late_left_contact_sampling_v6",
            "bar_late_workbench_overlap_sampling_v7",
        }
        or config.corrective_dataset_path is None
        or config.sampling_protocol_run is None
    ):
        raise ValueError("Training run is not a completed bar transport corrective candidate")
    from bimanual.skill_registry import load_skill_checkpoint

    binding = load_skill_checkpoint(training_run, skill_id=SKILL, dataset_root=config.dataset_path)
    binding.reverify()
    root = Path(__file__).resolve().parent
    body = dict(
        schema_version=1,
        profile=profile,
        training_run=os.path.relpath(training_run, destination.parent),
        training_manifest_sha256=manifest.manifest_sha256,
        dataset_root=os.path.relpath(config.dataset_path, destination.parent),
        dataset_manifest_sha256=digest_file(config.dataset_path / "export_manifest.json"),
        skill_views_path=os.path.relpath(config.skill_views_path, destination.parent),
        skill_views_sha256=digest_file(config.skill_views_path),
        sampling_declaration_sha256=digest_file(config.sampling_protocol_run),
        prior_evaluation_run_id=prior.run_id,
        prior_evaluation_manifest_sha256=prior.manifest_sha256,
        policy_target_margin_rad=MARGIN_RAD,
        evaluation_sources={
            name: digest_file(root / name) for name in _evaluation_source_paths(root)
        },
        device="cpu" if profile == CPU_LATE_WORKBENCH_OVERLAP_PROFILE else "mps",
        execute_chunk_steps=2,
        max_actions=1900,
        wall_timeout_seconds=1200.0,
        execution_authorized_by_this_artifact=False,
    )
    result = BarTransportPhysicalProtocol.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_bar_transport_physical_protocol(path: Path) -> BarTransportPhysicalProtocol:
    path = Path(path).resolve(strict=True)
    result = BarTransportPhysicalProtocol.model_validate_json(path.read_bytes())
    root = Path(__file__).resolve().parent
    for name, digest in result.evaluation_sources.items():
        if digest_file(root / name) != digest:
            raise ValueError("Bar physical evaluator source changed after protocol freeze")
    return result


def _reverify_protocol(path: Path, file_sha256: str, manifest_sha256: str) -> None:
    if digest_file(path) != file_sha256:
        raise ValueError("Bar physical evaluation declaration changed during execution")
    if load_bar_transport_physical_protocol(path).manifest_sha256 != manifest_sha256:
        raise ValueError("Bar physical evaluation source changed during execution")


def run_bar_transport_physical_protocol(path: Path):
    """Run exactly one guarded physical evaluation; preserve interruptions for review."""
    path = Path(path).resolve(strict=True)
    file_sha256 = digest_file(path)
    protocol = load_bar_transport_physical_protocol(path)
    training_run = (path.parent / protocol.training_run).resolve(strict=True)
    store = EvidenceStore(training_run.parents[1])
    prior = _verify_prior_failure(
        store, protocol.prior_evaluation_run_id, training_run, profile=protocol.profile
    )
    if prior.manifest_sha256 != protocol.prior_evaluation_manifest_sha256:
        raise ValueError("Prior bar failure changed after protocol freeze")
    from bimanual.skill_physical_evaluation import (
        SkillPhysicalEvaluationConfig,
    )
    from bimanual.skill_physical_process import run_skill_physical_process

    config = SkillPhysicalEvaluationConfig(
        training_run=training_run,
        dataset_root=(path.parent / protocol.dataset_root).resolve(strict=True),
        skill_views_path=(path.parent / protocol.skill_views_path).resolve(strict=True),
        skill_id=SKILL,
        device=protocol.device,
        max_actions=protocol.max_actions,
        execute_chunk_steps=protocol.execute_chunk_steps,
        policy_target_margin_rad=protocol.policy_target_margin_rad,
        wall_timeout_seconds=protocol.wall_timeout_seconds,
        evaluation_protocol_sha256=protocol.manifest_sha256,
        evaluation_protocol_file_sha256=file_sha256,
    )
    expected = config.model_dump(mode="json")
    process_expected = SkillPhysicalProcessConfig(evaluation=config).model_dump(mode="json")
    with WorkerLease.acquire(store.root / ".bar-transport-physical-coordinator.lock"):
        interrupted = []
        children = []
        processes = []
        for config_path in (store.root / "runs").glob("*/config.json"):
            if (config_path.parent / "manifest.json").exists():
                continue
            try:
                recorded = json.loads(config_path.read_text())
            except (OSError, ValueError):
                continue
            if recorded == process_expected:
                interrupted.append(config_path.parent.name)
        if interrupted:
            raise RuntimeError(
                "Interrupted bar physical process requires manual adjudication; no automatic retry"
            )
        for manifest_path in (store.root / "runs").glob("*/manifest.json"):
            manifest = store.verify(manifest_path.parent.name)
            if manifest.kind == KIND and manifest.config == expected:
                children.append(manifest)
            if manifest.kind == PROCESS_KIND and manifest.config == process_expected:
                processes.append(manifest)
        if len(children) > 1 or len(processes) > 1:
            raise RuntimeError("Ambiguous repeated bar physical evaluation evidence")
        if processes:
            process = processes[0]
            child_id = process.metrics.get("child_run_id")
            if not isinstance(child_id, str):
                _reverify_protocol(path, file_sha256, protocol.manifest_sha256)
                return process
            child = store.verify(child_id)
            if len(children) != 1 or children[0] != child:
                raise ValueError(
                    "Bar physical process child binding is incomplete or contradictory"
                )
            _reverify_protocol(path, file_sha256, protocol.manifest_sha256)
            return child if _clean_process_child(process, child) else process
        if children:
            raise RuntimeError(
                "Bar physical evaluation child has no sealed process wrapper; "
                "manual adjudication required"
            )
        process = run_skill_physical_process(
            SkillPhysicalProcessConfig(evaluation=config),
            store=store,
            project_root=Path.cwd(),
        )
        _reverify_protocol(path, file_sha256, protocol.manifest_sha256)
        child_id = process.metrics.get("child_run_id")
        if not isinstance(child_id, str):
            return process
        child = store.verify(child_id)
        if process.metrics.get("child_manifest_sha256") != child.manifest_sha256:
            raise ValueError("Bar physical process child binding changed after execution")
        if child.config != expected:
            raise ValueError("Bar physical child changed its frozen configuration")
        return child if _clean_process_child(process, child) else process
