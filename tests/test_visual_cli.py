import json
from pathlib import Path

from bimanual.cli import main


def test_frozen_protocol_cli_reports_scope(capsys):
    path = Path(__file__).parents[1] / "docs/experiments/visual-training-protocol-v1.json"
    assert main(["visual-protocol-check", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["validated_recordings"] is False
    assert report["physical_layout_count"] == 1
    assert not set(report["training_seeds"]) & set(report["test_seeds"])


def test_visual_source_cli_missing_source_fails_without_success_claim(tmp_path, capsys):
    path = Path(__file__).parents[1] / "docs/experiments/visual-training-protocol-v1.json"
    assert main(["visual-source-check", str(tmp_path / "missing"), "--protocol", str(path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["outcome"] == "failed"
    assert "episode_sha256" not in report
