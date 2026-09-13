"""Immutable sampling declaration for the bar overlap corrective archive."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import canonical

PROFILE = "bar_transport_placement_sampling_v1"
ENTRY_PROFILE = "bar_entry_contact_sampling_v2"
PLACEMENT_PROGRESS_PROFILE = "bar_placement_progress_sampling_v3"
FAILURE_LOCALIZATION_MANIFEST_SHA256 = (
    "f4798d6b4412851ee747c7584d37652329f170a5f5c6588f5a2e91d2e8216633"
)
ENTRY_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "f894dc670340ef881958dddeb460e32b9b2f25dff5f8b641a601bc36a3999905"
)
PLACEMENT_PROGRESS_FAILURE_ANALYSIS_MANIFEST_SHA256 = (
    "e2c60f2e4ac0d5a7ed0887107bf06e0bb15e82891c6f34968ddf84112a887139"
)


def _profile_spec(profile: str) -> tuple[str, tuple[int, int], str]:
    specs = {
        PROFILE: (FAILURE_LOCALIZATION_MANIFEST_SHA256, (770, 1070), "transport"),
        ENTRY_PROFILE: (
            ENTRY_CONTACT_FAILURE_ANALYSIS_MANIFEST_SHA256,
            (630, 770),
            "entry_contact",
        ),
        PLACEMENT_PROGRESS_PROFILE: (
            PLACEMENT_PROGRESS_FAILURE_ANALYSIS_MANIFEST_SHA256,
            (770, 1163),
            "placement_progress",
        ),
    }
    try:
        return specs[profile]
    except KeyError as error:
        raise ValueError("Unsupported bar sampling declaration profile") from error


class BarTransportPlacementSampling(Contract):
    profile: Literal[PROFILE, ENTRY_PROFILE, PLACEMENT_PROGRESS_PROFILE] = PROFILE
    corrective_export_root: str
    corrective_export_manifest_sha256: Digest
    corrective_views_sha256: Digest
    failure_localization_manifest_sha256: Digest
    emphasis_source_interval: tuple[int, int] = (770, 1070)
    nominal_probability: float = Field(default=0.5, gt=0, lt=1)
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_profile(self):
        expected_failure, expected_interval, _ = _profile_spec(self.profile)
        if (
            Path(self.corrective_export_root).is_absolute()
            or self.failure_localization_manifest_sha256 != expected_failure
            or self.emphasis_source_interval != expected_interval
            or self.nominal_probability != 0.5
        ):
            raise ValueError("Unsupported bar transport sampling declaration")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Bar transport sampling declaration digest mismatch")
        return self


def create_bar_transport_placement_sampling(
    destination: Path,
    *,
    corrective_export_root: Path,
    failure_localization_manifest_sha256: str,
    profile: str = PROFILE,
) -> BarTransportPlacementSampling:
    """Write a one-time declaration after independently auditing the archive."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Sampling declaration already exists")
    from bimanual.bar_overlap_correction_export import verify_bar_overlap_dataset

    root = Path(corrective_export_root).resolve(strict=True)
    expected_failure, emphasis_interval, _ = _profile_spec(profile)
    if failure_localization_manifest_sha256 != expected_failure:
        raise ValueError("Bar sampling requires the profile's sealed failure analysis")
    manifest = verify_bar_overlap_dataset(root)
    body = dict(
        schema_version=1,
        profile=profile,
        corrective_export_root=os.path.relpath(root, destination.parent.resolve()),
        corrective_export_manifest_sha256=manifest["manifest_sha256"],
        corrective_views_sha256=manifest["views_sha256"],
        failure_localization_manifest_sha256=failure_localization_manifest_sha256,
        emphasis_source_interval=emphasis_interval,
        nominal_probability=0.5,
    )
    result = BarTransportPlacementSampling.model_validate(
        body | {"manifest_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical(result.model_dump(mode="json")) + b"\n")
    return result


def load_bar_transport_placement_sampling(
    path: Path, *, corrective_export_root: Path
) -> BarTransportPlacementSampling:
    path = Path(path).resolve(strict=True)
    result = BarTransportPlacementSampling.model_validate_json(path.read_text())
    root = Path(corrective_export_root).resolve(strict=True)
    if (path.parent / result.corrective_export_root).resolve() != root:
        raise ValueError("Bar transport sampling archive binding mismatch")
    from bimanual.bar_overlap_correction_export import verify_bar_overlap_dataset_binding

    manifest = verify_bar_overlap_dataset_binding(root)
    if (
        manifest["manifest_sha256"] != result.corrective_export_manifest_sha256
        or manifest["views_sha256"] != result.corrective_views_sha256
    ):
        raise ValueError("Bar transport sampling source binding changed")
    return result
