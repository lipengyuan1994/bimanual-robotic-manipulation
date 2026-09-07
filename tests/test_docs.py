from pathlib import Path

from bimanual.docs import check_docs


def test_documentation_graph_and_rubric():
    report = check_docs(Path(__file__).resolve().parents[1])
    assert report["outcome"] == "passed", report["problems"]
