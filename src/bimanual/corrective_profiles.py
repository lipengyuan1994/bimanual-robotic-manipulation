"""Fail-closed dispatch across immutable corrective dataset schema versions."""

from __future__ import annotations

import json
from pathlib import Path

from bimanual.corrective_export import PROFILE as APPROACH_PROFILE
from bimanual.handoff_continuity_export import PROFILE as CONTINUITY_PROFILE


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
    raise ValueError("Unsupported corrective dataset profile")
