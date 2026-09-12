from types import SimpleNamespace

import pytest

from bimanual.cli import main


@pytest.mark.parametrize(
    ("outcome", "exit_code"), [("completed", 0), ("failed", 1), ("interrupted", 1)]
)
def test_feedback_cli_preserves_outcome_and_recording(
    tmp_path, monkeypatch, capsys, outcome, exit_code
):
    seen = []

    def execute(config, **kwargs):
        seen.append(config)
        return SimpleNamespace(outcome=outcome, model_dump=lambda **kw: {"outcome": outcome})

    monkeypatch.setattr("bimanual.feedback_teacher.run_feedback_approach", execute)
    assert (
        main(["--artifacts", str(tmp_path), "feedback-approach", "--record-demonstration"])
        == exit_code
    )
    assert seen[0].record_demonstration is True
    assert outcome in capsys.readouterr().out


def test_handoff_continuity_protocol_cli_dispatch(tmp_path, monkeypatch, capsys):
    from bimanual import handoff_continuity_protocol as module

    calls = []
    result = SimpleNamespace(model_dump=lambda **kwargs: {"profile": "continuity-v1"})
    monkeypatch.setattr(
        module,
        "create_handoff_continuity_protocol",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    destination = tmp_path / "protocol.json"
    assert (
        main(
            [
                "--artifacts",
                str(tmp_path),
                "handoff-continuity-protocol-create",
                "--diagnosis-run",
                "diagnosis-a",
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    assert calls == [
        {
            "evidence_root": tmp_path.resolve(),
            "diagnosis_run_id": "diagnosis-a",
            "destination": destination,
        }
    ]
    assert "continuity-v1" in capsys.readouterr().out


def test_handoff_continuity_run_cli_preserves_failure(tmp_path, monkeypatch, capsys):
    from bimanual import handoff_continuity_teacher as module

    calls = []
    result = SimpleNamespace(outcome="failed", model_dump=lambda **kwargs: {"outcome": "failed"})
    monkeypatch.setattr(
        module,
        "run_handoff_continuity_case",
        lambda protocol, case_id, **kwargs: calls.append((protocol, case_id)) or result,
    )
    protocol = tmp_path / "protocol.json"
    assert (
        main(
            [
                "--artifacts",
                str(tmp_path),
                "handoff-continuity-run",
                str(protocol),
                "receiver-baseline",
            ]
        )
        == 1
    )
    assert calls == [(protocol, "receiver-baseline")]
    assert "failed" in capsys.readouterr().out


def test_handoff_continuity_views_cli_dispatch(tmp_path, monkeypatch, capsys):
    from bimanual import handoff_continuity_views as module

    calls = []
    result = SimpleNamespace(
        model_dump=lambda **kwargs: {"profile": "handoff_receiver_continuity_views_v1"}
    )
    monkeypatch.setattr(
        module,
        "create_handoff_continuity_views",
        lambda store, run_ids, destination: calls.append((run_ids, destination)) or result,
    )
    destination = tmp_path / "views.json"
    assert (
        main(
            [
                "--artifacts",
                str(tmp_path),
                "handoff-continuity-views-create",
                "--run-id",
                "source-a",
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    assert calls == [(["source-a"], destination)]
    assert "handoff_receiver_continuity_views_v1" in capsys.readouterr().out


@pytest.mark.parametrize(
    "command", ["handoff-continuity-export", "handoff-continuity-export-check"]
)
def test_handoff_continuity_export_cli_dispatch(tmp_path, monkeypatch, capsys, command):
    from bimanual import handoff_continuity_export as module

    calls = []
    destination = tmp_path / "dataset"
    views = tmp_path / "views.json"
    monkeypatch.setattr(
        module,
        "export_handoff_continuity_dataset",
        lambda path, store, root, repo_id: calls.append((path, root, repo_id)) or root,
    )
    monkeypatch.setattr(
        module,
        "verify_handoff_continuity_dataset",
        lambda root: calls.append(root) or {"profile": "handoff_receiver_continuity_lerobot_v1"},
    )
    if command.endswith("export"):
        args = [
            "--views",
            str(views),
            "--destination",
            str(destination),
            "--repo-id",
            "local/continuity",
        ]
        expected = [(views, destination, "local/continuity")]
    else:
        args = [str(destination)]
        expected = [destination]
    assert main(["--artifacts", str(tmp_path), command, *args]) == 0
    assert calls == expected
    assert capsys.readouterr().out


@pytest.mark.parametrize("command", ["corrective-views-create", "corrective-views-check"])
def test_corrective_cli_dispatch(tmp_path, monkeypatch, capsys, command):
    from bimanual import corrective_views

    calls = []
    result = SimpleNamespace(model_dump=lambda: {"task_scope": "approach_only"})

    def create(store, run_ids, destination):
        calls.append((run_ids, destination))
        return result

    def check(path, store):
        calls.append(path)
        return result

    monkeypatch.setattr(corrective_views, "create_corrective_views", create)
    monkeypatch.setattr(corrective_views, "load_corrective_views", check)
    destination = tmp_path / "views.json"
    args = (
        ["--run-id", "run-a", "--destination", str(destination)]
        if command.endswith("create")
        else [str(destination)]
    )
    assert main(["--artifacts", str(tmp_path), command, *args]) == 0
    assert (
        calls == [(["run-a"], destination)]
        if command.endswith("create")
        else calls == [destination]
    )
    assert "approach_only" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["corrective-export", "corrective-export-check"])
def test_corrective_export_cli_dispatch(tmp_path, monkeypatch, capsys, command):
    from bimanual import corrective_export

    destination = tmp_path / "dataset"
    views = tmp_path / "views.json"
    calls = []

    def export(path, store, root, repo_id):
        calls.append((path, root, repo_id))
        return root

    def verify(root):
        calls.append(root)
        return {"profile": "feedback_approach_corrective_lerobot_v1"}

    monkeypatch.setattr(corrective_export, "export_corrective_dataset", export)
    monkeypatch.setattr(corrective_export, "verify_corrective_dataset", verify)
    if command == "corrective-export":
        args = ["--views", str(views), "--destination", str(destination), "--repo-id", "local/test"]
        expected = [(views, destination, "local/test")]
    else:
        args = [str(destination)]
        expected = [destination]
    assert main(["--artifacts", str(tmp_path), command, *args]) == 0
    assert calls == expected
    assert capsys.readouterr().out


def test_train_cli_forwards_correction_path(tmp_path, monkeypatch, capsys):
    from bimanual import training

    seen = []

    def train(config, **kwargs):
        seen.append(config)
        return SimpleNamespace(
            outcome="completed", model_dump=lambda **kwargs: {"outcome": "completed"}
        )

    monkeypatch.setattr(training, "run_train", train)
    assert (
        main(
            [
                "train",
                "--dataset",
                str(tmp_path / "nominal"),
                "--skill-views",
                str(tmp_path / "views.json"),
                "--skill-id",
                "handoff_transfer",
                "--corrective-dataset",
                str(tmp_path / "corrections"),
            ]
        )
        == 0
    )
    assert seen[0].corrective_dataset_path == tmp_path / "corrections"
    assert "completed" in capsys.readouterr().out
