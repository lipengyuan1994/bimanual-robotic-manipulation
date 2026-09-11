"""Coordinator fixtures only; no training or model runtime."""

from types import SimpleNamespace

from bimanual import training_cohort_sequence as module
from bimanual.cli import main
from bimanual.training_cohort import COHORT_SKILLS


def result(skill, outcome="completed"):
    return SimpleNamespace(
        run_id="run-" + skill,
        manifest_sha256=(skill[0] * 64),
        outcome=outcome,
        metrics={"training_complete": outcome == "completed"},
    )


def test_sequence_runs_exact_order_and_reports_no_physical_quality(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        module,
        "load_training_cohort_protocol",
        lambda path: SimpleNamespace(manifest_sha256="a" * 64),
    )
    monkeypatch.setattr(
        module,
        "run_training_cohort_skill",
        lambda path, skill: calls.append((path, skill)) or result(skill),
    )
    protocol = tmp_path / "protocol.json"
    report = module.run_training_cohort_sequence(protocol)
    assert calls == [(protocol.resolve(), skill) for skill in COHORT_SKILLS]
    assert report["all_training_complete"] is True
    assert report["physical_success"] is None and report["quality_claim"] is False
    assert [row["skill_id"] for row in report["skills"]] == list(COHORT_SKILLS)


def test_sequence_stops_on_first_failure_without_retry(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        module,
        "load_training_cohort_protocol",
        lambda path: SimpleNamespace(manifest_sha256="a" * 64),
    )

    def run(path, skill):
        calls.append(skill)
        return result(skill, "failed" if skill == COHORT_SKILLS[2] else "completed")

    monkeypatch.setattr(module, "run_training_cohort_skill", run)
    report = module.run_training_cohort_sequence(tmp_path / "protocol.json")
    assert calls == list(COHORT_SKILLS[:3])
    assert report["all_training_complete"] is False
    assert report["skills"][-1]["outcome"] == "failed"


def test_cli_preserves_incomplete_sequence_exit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        module,
        "run_training_cohort_sequence",
        lambda path, **kwargs: {
            "all_training_complete": False,
            "physical_success": None,
            "quality_claim": False,
        },
    )
    assert (
        main(
            [
                "training-cohort-run-all",
                str(tmp_path / "protocol.json"),
                "--wait-for-active-seconds",
                "60",
            ]
        )
        == 1
    )
    assert '"all_training_complete": false' in capsys.readouterr().out


def test_sequence_can_wait_for_one_active_owner_then_resume(tmp_path, monkeypatch):
    calls = []
    clock = [0.0]
    monkeypatch.setattr(
        module,
        "load_training_cohort_protocol",
        lambda path: SimpleNamespace(manifest_sha256="a" * 64),
    )

    def run(path, skill):
        calls.append(skill)
        if len(calls) == 1:
            raise RuntimeError("A workflow worker still holds this lease")
        return result(skill)

    monkeypatch.setattr(module, "run_training_cohort_skill", run)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    report = module.run_training_cohort_sequence(
        tmp_path / "protocol.json", wait_for_active_seconds=60, poll_interval_seconds=5
    )
    assert calls == [COHORT_SKILLS[0], *COHORT_SKILLS]
    assert report["all_training_complete"] is True
    assert report["wait_for_active_seconds"] == 60.0
