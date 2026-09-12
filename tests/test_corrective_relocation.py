"""Local dataset relocation preserves original sealed identities."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from bimanual.corrective_dataset import compose_sampling_plan
from bimanual.skill_registry import _resolve_corrective_root


def identities(original):
    return (
        SimpleNamespace(corrective_dataset_path=Path("corrections")),
        {"corrective_config_base": str(original.parent), "corrective_dataset_root": str(original)},
        {"root": str(original)},
    )


def test_explicit_override_does_not_require_original_folder(tmp_path):
    original = tmp_path / "absent-host" / "corrections"
    actual = tmp_path / "copied"
    actual.mkdir()
    config, metrics, recorded = identities(original)
    assert _resolve_corrective_root(config, metrics, recorded, actual) == actual
    assert not original.exists()
    with pytest.raises(FileNotFoundError):
        _resolve_corrective_root(config, metrics, recorded, None)


@pytest.mark.parametrize("field", ["corrective_config_base", "corrective_dataset_root"])
def test_override_cannot_bypass_original_config_identity(tmp_path, field):
    actual = tmp_path / "copy"
    actual.mkdir()
    config, metrics, recorded = identities(tmp_path / "original" / "corrections")
    metrics[field] = str(tmp_path / "wrong")
    with pytest.raises(ValueError, match="mismatch"):
        _resolve_corrective_root(config, metrics, recorded, actual)


def test_plan_uses_actual_bytes_with_original_root_identity(tmp_path):
    actual = tmp_path / "copy"
    actual.mkdir()
    export = actual / "export_manifest.json"
    export.write_text("original export")
    plan = {
        "profile": "uniform",
        "skill_view": {"skill_id": "handoff_transfer"},
        "frames": [{"dataset_index": 0}],
        "episodes": [{"probability": 1}],
    }
    manifest = {"profile": "feedback_approach_corrective_lerobot_v1", "episodes": []}
    original_root = str(tmp_path / "absent" / "corrections")
    result = compose_sampling_plan(plan, actual, manifest, recorded_root=original_root)
    assert result["corrective_dataset"]["root"] == original_root
    export.write_text("changed export")
    altered = compose_sampling_plan(plan, actual, manifest, recorded_root=original_root)
    assert altered != result
    with pytest.raises(ValueError, match="absolute"):
        compose_sampling_plan(plan, actual, manifest, recorded_root="relative")


def test_binding_reverify_preserves_actual_corrective_root(monkeypatch, tmp_path):
    from bimanual import skill_registry
    from bimanual.skill_registry import SkillCheckpointBinding

    binding = SkillCheckpointBinding(
        training_run=tmp_path,
        dataset_root=tmp_path / "nominal",
        capability=None,
        view=SimpleNamespace(skill_id="handoff_transfer"),
        training_manifest_sha256="a",
        checkpoint_path=tmp_path,
        policy_sha256="b",
        checkpoint_sha256="c",
        chunk_size=10,
        corrective_dataset_root=tmp_path / "copy",
    )
    calls = []

    def reload(*args, **kwargs):
        calls.append(kwargs)
        return binding

    monkeypatch.setattr(skill_registry, "load_skill_checkpoint", reload)
    assert binding.reverify() is binding
    assert calls[0]["corrective_dataset_root"] == tmp_path / "copy"


def test_nominal_checkpoint_rejects_corrective_override(monkeypatch, tmp_path):
    from bimanual import skill_registry
    from bimanual.training import ACTTrainingConfig

    manifest = SimpleNamespace(
        kind="act_training",
        outcome="completed",
        metrics={},
        config=ACTTrainingConfig(dataset_path=tmp_path).model_dump(mode="json"),
    )
    monkeypatch.setattr(skill_registry.EvidenceStore, "verify", lambda *args: manifest)
    with pytest.raises(ValueError, match="override requires"):
        skill_registry.load_skill_checkpoint(
            tmp_path,
            skill_id="handoff_transfer",
            dataset_root=tmp_path,
            corrective_dataset_root=tmp_path,
        )
