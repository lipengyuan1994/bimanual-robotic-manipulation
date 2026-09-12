import json
from pathlib import Path
from types import SimpleNamespace

from bimanual.cli import main


def test_skill_checkpoint_cli_reports_development_scope(monkeypatch, capsys):
    from bimanual import skill_registry

    calls = []

    def load(run, **kwargs):
        calls.append((run, kwargs))
        return SimpleNamespace(
            report=lambda: {"release_available": False, "skill_id": "drawer_open"}
        )

    monkeypatch.setattr(skill_registry, "load_skill_checkpoint", load)
    assert (
        main(["skill-checkpoint", "training", "--skill-id", "drawer_open", "--dataset", "data"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["release_available"] is False
    assert calls == [(Path("training"), {"skill_id": "drawer_open", "dataset_root": Path("data")})]


def test_skill_checkpoint_cli_rejects_invalid_checkpoint(monkeypatch, capsys):
    from bimanual import skill_registry

    def reject(*args, **kwargs):
        raise ValueError("Checkpoint selection mismatch")

    monkeypatch.setattr(skill_registry, "load_skill_checkpoint", reject)
    assert (
        main(["skill-checkpoint", "training", "--skill-id", "drawer_open", "--dataset", "data"])
        == 1
    )
    assert json.loads(capsys.readouterr().out)["outcome"] == "failed"
