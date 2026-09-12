import json

import pytest

from bimanual.corrective_profiles import verify_supported_corrective_dataset


@pytest.mark.parametrize(
    ("profile", "module_name", "function_name"),
    [
        (
            "feedback_approach_corrective_lerobot_v1",
            "bimanual.corrective_export",
            "verify_corrective_dataset",
        ),
        (
            "handoff_receiver_continuity_lerobot_v1",
            "bimanual.handoff_continuity_export",
            "verify_handoff_continuity_dataset",
        ),
    ],
)
def test_dispatches_only_declared_corrective_profile(
    tmp_path, monkeypatch, profile, module_name, function_name
):
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "export_manifest.json").write_text(json.dumps({"profile": profile}))
    calls = []
    monkeypatch.setattr(
        f"{module_name}.{function_name}", lambda path: calls.append(path) or {"profile": profile}
    )
    assert verify_supported_corrective_dataset(root) == {"profile": profile}
    assert calls == [root.resolve()]


def test_unknown_corrective_profile_fails_closed(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "export_manifest.json").write_text('{"profile":"unknown"}')
    with pytest.raises(ValueError, match="Unsupported"):
        verify_supported_corrective_dataset(root)
