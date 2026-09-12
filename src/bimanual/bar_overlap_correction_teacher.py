"""Contact-only collection adapter for frozen bar-overlap corrective cases."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from bimanual.bar_overlap_correction_protocol import load_bar_overlap_correction_protocol
from bimanual.skill_corrective_teacher import run_skill_corrective_case


def _adapter(path: Path):
    protocol = load_bar_overlap_correction_protocol(path)
    family = SimpleNamespace(
        family_id="bar_contact_avoidance",
        skills=("bar_place_and_return",),
        case_seeds=protocol.case_seeds,
    )
    return SimpleNamespace(
        manifest_sha256=protocol.manifest_sha256,
        asset_root=protocol.asset_root,
        allocation_rule=protocol.allocation_rule,
        families=(family,),
    )


def run_bar_overlap_correction_case(
    protocol_path: Path, case_id: str, *, store, project_root: Path, cancelled=lambda: False
):
    """Record one fresh, contact-only bar case; never load a learned policy."""
    return run_skill_corrective_case(
        protocol_path,
        case_id,
        store=store,
        project_root=project_root,
        cancelled=cancelled,
        load_protocol=_adapter,
        recording_profile="bar_overlap_corrective_teacher_v1",
        recording_kind="bar_overlap_corrective_teacher_recording",
    )
