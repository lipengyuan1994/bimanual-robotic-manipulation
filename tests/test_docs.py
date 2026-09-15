from pathlib import Path

from bimanual.docs import check_docs


def test_documentation_graph_and_rubric():
    report = check_docs(Path(__file__).resolve().parents[1])
    assert report["outcome"] == "passed", report["problems"]


def test_release_runbook_covers_m3_command_stages(tmp_path):
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "project"
    import shutil

    shutil.copytree(root / "docs", copied / "docs")
    (copied / "README.md").write_text("# fixture\n")
    (copied / "lessons").mkdir()
    (copied / "reference").mkdir()
    (copied / "docs" / "RELEASE_REPRODUCTION.md").write_text("# incomplete\n")
    report = check_docs(copied)
    assert report["outcome"] == "failed"
    assert "Release reproduction runbook omits workflow-release-create" in report["problems"]
