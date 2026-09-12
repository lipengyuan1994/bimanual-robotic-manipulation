from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from bimanual.cli import main
from bimanual.evidence import EvidenceStore
from bimanual.submission_package import (
    MANIFEST_NAME,
    SubmissionInputs,
    SubmissionRequirementsError,
    create_submission_package,
    inspect_submission_requirements,
    verify_submission_package,
)


def _git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return result.stdout.decode().strip()


@pytest.fixture
def complete_inputs(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "fixture@example.invalid")
    _git(project, "config", "user.name", "Fixture")
    (project / "tracked.txt").write_text("submission fixture\n")
    _git(project, "add", "tracked.txt")
    _git(project, "commit", "-qm", "fixture")
    revision = _git(project, "rev-parse", "HEAD")

    protocol_path = project / "release.json"
    protocol_path.write_text('{"fixture":"release"}\n')
    (project / ".gitignore").write_text("release-evidence/\n")
    _git(project, "add", "release.json", ".gitignore")
    _git(project, "commit", "-qm", "release declaration")
    revision = _git(project, "rev-parse", "HEAD")
    protocol = SimpleNamespace(manifest_sha256="a" * 64)
    monkeypatch.setattr(
        "bimanual.submission_package.load_workflow_release_protocol", lambda path: protocol
    )
    store = EvidenceStore(project / "release-evidence")
    run = store.new_run()
    suite = store.seal(
        run,
        kind="local_workflow_release_suite",
        outcome="failed",
        config={"protocol_manifest_sha256": protocol.manifest_sha256},
        metrics={
            "local_prequalification_passed": False,
            "intel_validated": False,
            "release_success": None,
        },
        source={},
        claims=[],
    )
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42fixture")
    slides = tmp_path / "slides.pdf"
    slides.write_bytes(b"%PDF-1.7\nfixture\n%%EOF\n")
    cover = tmp_path / "cover.png"
    Image.new("RGB", (160, 90), color=(12, 34, 56)).save(cover)
    return SubmissionInputs(
        project_root=project,
        repository_revision=revision,
        release_protocol=protocol_path,
        release_suite=store.directory(suite.run_id),
        interactive_url="https://demo.example.invalid/app",
        video=video,
        slides=slides,
        cover=cover,
    )


def test_incomplete_inputs_report_every_missing_requirement_without_output(tmp_path):
    inputs = SubmissionInputs(project_root=tmp_path)
    report = inspect_submission_requirements(inputs)
    assert report.complete is False
    assert report.missing == (
        "repository_revision",
        "release_protocol",
        "release_suite",
        "interactive_url",
        "video",
        "slides",
        "cover",
    )
    destination = tmp_path / "submission"
    with pytest.raises(SubmissionRequirementsError) as raised:
        create_submission_package(inputs, destination)
    assert raised.value.report == report
    assert not destination.exists()


def test_package_binds_verified_evidence_assets_and_honest_outcomes(complete_inputs, tmp_path):
    destination = tmp_path / "submission"
    created = create_submission_package(complete_inputs, destination)
    loaded = verify_submission_package(destination, project_root=complete_inputs.project_root)
    assert loaded == created
    assert (destination / MANIFEST_NAME).is_file()
    assert loaded.package_complete is True
    assert loaded.submission_status == "package_complete_not_submitted"
    assert loaded.local_prequalification_passed is False
    assert loaded.intel_validated is False
    assert loaded.release_success is None
    assert loaded.repository.revision == complete_inputs.repository_revision
    assert loaded.video.media_type == "video/mp4"
    assert loaded.slides.media_type == "application/pdf"
    assert loaded.cover.media_type == "image/png"
    assert "evidence/release-suite/manifest.json" in loaded.package_files


def test_package_verifier_rejects_changed_asset(complete_inputs, tmp_path):
    destination = tmp_path / "submission"
    create_submission_package(complete_inputs, destination)
    (destination / "assets" / "slides.pdf").write_bytes(b"%PDF-1.7\nchanged\n%%EOF\n")
    with pytest.raises(ValueError, match="inventory changed"):
        verify_submission_package(destination, project_root=complete_inputs.project_root)


def test_package_verifier_rejects_changed_source_evidence(complete_inputs, tmp_path):
    destination = tmp_path / "submission"
    create_submission_package(complete_inputs, destination)
    complete_inputs.release_protocol.write_text('{"fixture":"changed"}\n')
    with pytest.raises(ValueError, match="protocol file changed"):
        verify_submission_package(destination, project_root=complete_inputs.project_root)


def test_invalid_declarations_are_reported_together(complete_inputs, tmp_path):
    bad_cover = tmp_path / "bad-cover.png"
    Image.new("RGB", (100, 100)).save(bad_cover)
    inputs = SubmissionInputs(
        **{
            **complete_inputs.__dict__,
            "interactive_url": "http://localhost:8000",
            "cover": bad_cover,
        }
    )
    report = inspect_submission_requirements(inputs)
    assert report.complete is False
    assert report.missing == ()
    assert any(item.startswith("interactive_url:") for item in report.invalid)
    assert any(item.startswith("cover:") for item in report.invalid)


def test_dirty_repository_cannot_be_packaged(complete_inputs):
    (complete_inputs.project_root / "tracked.txt").write_text("changed\n")
    report = inspect_submission_requirements(complete_inputs)
    assert report.complete is False
    assert "repository_revision: working tree is not clean" in report.invalid


def test_submission_check_cli_reports_incomplete_without_output(tmp_path, capsys):
    result = main(
        [
            "--project-root",
            str(tmp_path),
            "submission-check",
            "--revision",
            "0" * 40,
            "--release-protocol",
            str(tmp_path / "missing-release.json"),
            "--release-suite",
            str(tmp_path / "missing-suite"),
            "--interactive-url",
            "http://localhost",
            "--video",
            str(tmp_path / "missing.mp4"),
            "--slides",
            str(tmp_path / "missing.pdf"),
            "--cover",
            str(tmp_path / "missing.png"),
        ]
    )
    assert result == 1
    assert '"complete": false' in capsys.readouterr().out
