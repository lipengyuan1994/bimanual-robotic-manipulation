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


def test_bar_overlap_run_cli_preserves_a_completed_teacher_recording(monkeypatch, capsys):
    from bimanual import bar_overlap_correction_teacher

    seen = {}

    def collect(protocol, case_id, **kwargs):
        seen.update(protocol=protocol, case_id=case_id, kwargs=kwargs)
        return SimpleNamespace(outcome="completed", model_dump=lambda **_: {"outcome": "completed"})

    monkeypatch.setattr(bar_overlap_correction_teacher, "run_bar_overlap_correction_case", collect)
    assert main(["bar-overlap-run", "protocol.json", "bar_contact_avoidance-54000"]) == 0
    assert seen["protocol"] == Path("protocol.json")
    assert seen["case_id"] == "bar_contact_avoidance-54000"
    assert json.loads(capsys.readouterr().out) == {"outcome": "completed"}
