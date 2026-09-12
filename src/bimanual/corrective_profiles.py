"""Fail-closed dispatch across immutable corrective dataset schema versions."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.bar_overlap_correction_export import PROFILE as BAR_OVERLAP_PROFILE
from bimanual.corrective_export import PROFILE as APPROACH_PROFILE
from bimanual.handoff_continuity_export import PROFILE as CONTINUITY_PROFILE
from bimanual.skill_corrective_export import PROFILE as SKILL_PROFILE


def verify_supported_corrective_dataset(root: Path) -> dict:
    root = Path(root).resolve(strict=True)
    try:
        profile = json.loads((root / "export_manifest.json").read_bytes()).get("profile")
    except (OSError, ValueError, AttributeError) as error:
        raise ValueError("Corrective dataset manifest is missing or malformed") from error
    if profile == APPROACH_PROFILE:
        from bimanual.corrective_export import verify_corrective_dataset

        return verify_corrective_dataset(root)
    if profile == CONTINUITY_PROFILE:
        from bimanual.handoff_continuity_export import verify_handoff_continuity_dataset

        return verify_handoff_continuity_dataset(root)
    if profile == BAR_OVERLAP_PROFILE:
        from bimanual.bar_overlap_correction_export import verify_bar_overlap_dataset

        return verify_bar_overlap_dataset(root)
    if profile == SKILL_PROFILE:
        from bimanual.skill_corrective_export import verify_skill_corrective_dataset

        return verify_skill_corrective_dataset(root)
    raise ValueError("Unsupported corrective dataset profile")


def verify_supported_corrective_dataset_binding(root: Path) -> dict:
    """Use an already independently-audited corrective archive at runtime."""
    root = Path(root).resolve(strict=True)
    try:
        profile = json.loads((root / "export_manifest.json").read_bytes()).get("profile")
    except (OSError, ValueError, AttributeError) as error:
        raise ValueError("Corrective dataset manifest is missing or malformed") from error
    if profile == SKILL_PROFILE:
        from bimanual.skill_corrective_export import verify_skill_corrective_dataset_binding

        return verify_skill_corrective_dataset_binding(root)
    if profile == BAR_OVERLAP_PROFILE:
        from bimanual.bar_overlap_correction_export import verify_bar_overlap_dataset_binding

        return verify_bar_overlap_dataset_binding(root)
    return verify_supported_corrective_dataset(root)
