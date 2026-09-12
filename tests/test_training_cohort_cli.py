from types import SimpleNamespace

import pytest

from bimanual.cli import main


@pytest.mark.parametrize("command", ["training-cohort-create", "training-cohort-check"])
def test_training_cohort_cli_dispatch(tmp_path, monkeypatch, capsys, command):
    from bimanual import training_cohort

    calls = []
    result = SimpleNamespace(model_dump=lambda **kwargs: {"scope": "training_runtime_only"})

    def create(dataset, views, prerequisites, *, store, destination):
        calls.append((dataset, views, prerequisites, store.root, destination))
        return result

    def check(path):
        calls.append(path)
        return result

    monkeypatch.setattr(training_cohort, "create_training_cohort_protocol", create)
    monkeypatch.setattr(training_cohort, "load_training_cohort_protocol", check)
    protocol = tmp_path / "cohort.json"
    if command.endswith("create"):
        args = [
            "--dataset",
            str(tmp_path / "dataset"),
            "--skill-views",
            str(tmp_path / "views.json"),
            "--destination",
            str(protocol),
            "--experiment-protocol-run",
            "experiment",
            "--training-run",
            "training",
            "--recorded-run",
            "recorded",
            "--physical-prefix2-run",
            "prefix2",
            "--physical-prefix5-run",
            "prefix5",
        ]
    else:
        args = [str(protocol)]
    assert main(["--artifacts", str(tmp_path / "evidence"), command, *args]) == 0
    assert calls
    assert "training_runtime_only" in capsys.readouterr().out


def test_training_cohort_run_cli_preserves_failed_outcome(tmp_path, monkeypatch, capsys):
    from bimanual import training_cohort_runner

    calls = []
    result = SimpleNamespace(
        outcome="failed",
        model_dump=lambda **kwargs: {"outcome": "failed", "physical_success": None},
    )
    monkeypatch.setattr(
        training_cohort_runner,
        "run_training_cohort_skill",
        lambda protocol, skill: calls.append((protocol, skill)) or result,
    )
    protocol = tmp_path / "cohort.json"
    assert (
        main(
            [
                "training-cohort-run",
                str(protocol),
                "--skill",
                "bar_place_and_return",
            ]
        )
        == 1
    )
    assert calls == [(protocol, "bar_place_and_return")]
    assert "physical_success" in capsys.readouterr().out
