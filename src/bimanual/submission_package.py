"""Build and verify a local, evidence-bound hackathon submission package."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from PIL import Image
from pydantic import Field, field_validator, model_validator

from bimanual.contracts import Contract, Digest
from bimanual.evidence import EvidenceStore, canonical, digest_file
from bimanual.workflow_release_protocol import load_workflow_release_protocol
from bimanual.workflow_release_suite import KIND as RELEASE_SUITE_KIND

MANIFEST_NAME = "submission-manifest-v1.json"


@dataclass(frozen=True)
class SubmissionInputs:
    project_root: Path
    repository_revision: str | None = None
    release_protocol: Path | None = None
    release_suite: Path | None = None
    interactive_url: str | None = None
    video: Path | None = None
    slides: Path | None = None
    cover: Path | None = None


class SubmissionRequirementReport(Contract):
    complete: bool
    missing: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()


class RepositoryBinding(Contract):
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dirty_at_packaging: bool


class SourceBinding(Contract):
    path: str
    file_sha256: Digest
    manifest_sha256: Digest

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
            raise ValueError("Source path must be project relative")
        return value


class PackagedAsset(Contract):
    path: str
    sha256: Digest
    media_type: Literal["video/mp4", "application/pdf", "image/png", "image/jpeg"]

    @field_validator("path")
    @classmethod
    def packaged_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
            raise ValueError("Package asset path must be relative")
        return value


class SubmissionPackageManifest(Contract):
    profile: Literal["hackathon_submission_package_v1"] = "hackathon_submission_package_v1"
    created_at: str
    repository: RepositoryBinding
    release_protocol: SourceBinding
    release_suite: SourceBinding
    interactive_url: str
    video: PackagedAsset
    slides: PackagedAsset
    cover: PackagedAsset
    package_files: dict[str, Digest]
    local_prequalification_passed: bool
    intel_validated: bool
    release_success: bool | None
    package_complete: Literal[True] = True
    submission_status: Literal["package_complete_not_submitted"] = "package_complete_not_submitted"
    manifest_sha256: Digest

    @model_validator(mode="after")
    def exact_manifest(self):
        expected = {
            self.video.path,
            self.slides.path,
            self.cover.path,
            "evidence/release.json",
            "evidence/release-suite/manifest.json",
        }
        if not expected.issubset(self.package_files):
            raise ValueError("Submission package file inventory is incomplete")
        if (
            self.package_files["evidence/release.json"] != self.release_protocol.file_sha256
            or self.package_files["evidence/release-suite/manifest.json"]
            != self.release_suite.file_sha256
        ):
            raise ValueError("Packaged release evidence differs from its verified source")
        if (
            self.video.media_type != "video/mp4"
            or self.slides.media_type != "application/pdf"
            or self.cover.media_type not in {"image/png", "image/jpeg"}
        ):
            raise ValueError("Submission asset media types are inconsistent")
        body = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(body)).hexdigest() != self.manifest_sha256:
            raise ValueError("Submission package manifest seal mismatch")
        return self


class SubmissionRequirementsError(ValueError):
    def __init__(self, report: SubmissionRequirementReport):
        self.report = report
        details = list(report.missing) + list(report.invalid)
        super().__init__("Submission package requirements not met: " + "; ".join(details))


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ValueError("project_root is not a readable Git checkout")
    return result.stdout.strip()


def _project_relative(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("evidence must be inside project_root")
    return resolved.relative_to(root).as_posix()


def _validate_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("interactive_url must be a credential-free HTTPS URL")


def _validate_video(path: Path) -> None:
    if path.suffix.lower() != ".mp4" or path.stat().st_size < 12:
        raise ValueError("video must be a non-empty MP4 file")
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[4:8] != b"ftyp":
        raise ValueError("video does not have an MP4 file signature")


def _validate_slides(path: Path) -> None:
    if path.suffix.lower() != ".pdf" or path.stat().st_size < 8:
        raise ValueError("slides must be a non-empty PDF file")
    if not path.read_bytes().startswith(b"%PDF-"):
        raise ValueError("slides do not have a PDF file signature")


def _validate_cover(path: Path) -> None:
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("cover must be PNG or JPG")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format
    except (OSError, ValueError) as error:
        raise ValueError("cover is not a readable image") from error
    if image_format not in {"PNG", "JPEG"}:
        raise ValueError("cover must be PNG or JPG")
    if width <= 0 or height <= 0 or width * 9 != height * 16:
        raise ValueError("cover must have an exact 16:9 aspect ratio")


def _load_suite(path: Path):
    directory = path.resolve(strict=True)
    if not directory.is_dir() or directory.parent.name != "runs":
        raise ValueError("release_suite must be an EvidenceStore run directory")
    manifest = EvidenceStore(directory.parent.parent).verify(directory.name)
    if manifest.kind != RELEASE_SUITE_KIND:
        raise ValueError("release_suite has the wrong evidence kind")
    return manifest


def inspect_submission_requirements(inputs: SubmissionInputs) -> SubmissionRequirementReport:
    """Report every currently missing or invalid input without creating files."""
    required = {
        "repository_revision": inputs.repository_revision,
        "release_protocol": inputs.release_protocol,
        "release_suite": inputs.release_suite,
        "interactive_url": inputs.interactive_url,
        "video": inputs.video,
        "slides": inputs.slides,
        "cover": inputs.cover,
    }
    missing = tuple(name for name, value in required.items() if value is None or value == "")
    invalid: list[str] = []
    try:
        root = inputs.project_root.resolve(strict=True)
        current_revision = _git(root, "rev-parse", "HEAD")
    except (OSError, ValueError) as error:
        root = inputs.project_root.resolve()
        current_revision = None
        invalid.append(f"project_root: {error}")
    if inputs.repository_revision is not None and inputs.repository_revision != "":
        if current_revision is None or inputs.repository_revision != current_revision:
            invalid.append("repository_revision: does not match current HEAD")
        elif _git(root, "status", "--porcelain"):
            invalid.append("repository_revision: working tree is not clean")
    protocol = None
    if inputs.release_protocol is not None:
        try:
            _project_relative(inputs.release_protocol, root)
            protocol = load_workflow_release_protocol(inputs.release_protocol)
        except (OSError, ValueError) as error:
            invalid.append(f"release_protocol: {error}")
    if inputs.release_suite is not None:
        try:
            _project_relative(inputs.release_suite, root)
            suite = _load_suite(inputs.release_suite)
            if protocol is not None and suite.config.get("protocol_manifest_sha256") != (
                protocol.manifest_sha256
            ):
                raise ValueError("does not bind the declared release protocol")
            if not isinstance(suite.metrics.get("local_prequalification_passed"), bool):
                raise ValueError("does not declare local_prequalification_passed")
            if not isinstance(suite.metrics.get("intel_validated"), bool):
                raise ValueError("does not declare intel_validated")
            release_success = suite.metrics.get("release_success")
            if release_success is not None and type(release_success) is not bool:
                raise ValueError("has an invalid release_success value")
        except (OSError, ValueError) as error:
            invalid.append(f"release_suite: {error}")
    validators = (
        ("interactive_url", inputs.interactive_url, _validate_url),
        ("video", inputs.video, _validate_video),
        ("slides", inputs.slides, _validate_slides),
        ("cover", inputs.cover, _validate_cover),
    )
    for name, value, validator in validators:
        if value is None or value == "":
            continue
        try:
            validator(value if isinstance(value, str) else value.resolve(strict=True))
        except (OSError, ValueError) as error:
            invalid.append(f"{name}: {error}")
    return SubmissionRequirementReport(
        complete=not missing and not invalid, missing=missing, invalid=tuple(invalid)
    )


def _inventory(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): digest_file(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != MANIFEST_NAME
    }


def create_submission_package(
    inputs: SubmissionInputs, destination: Path
) -> SubmissionPackageManifest:
    """Create a new package only after all declarations and evidence verify."""
    report = inspect_submission_requirements(inputs)
    if not report.complete:
        raise SubmissionRequirementsError(report)
    root = inputs.project_root.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("submission package destination already exists")
    assert inputs.release_protocol is not None
    assert inputs.release_suite is not None
    assert inputs.video is not None and inputs.slides is not None and inputs.cover is not None
    assert inputs.interactive_url is not None and inputs.repository_revision is not None
    protocol = load_workflow_release_protocol(inputs.release_protocol)
    suite = _load_suite(inputs.release_suite)
    temporary = destination.with_name(f".{destination.name}.building")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError("submission package staging destination already exists")
    try:
        (temporary / "assets").mkdir(parents=True)
        (temporary / "evidence" / "release-suite").mkdir(parents=True)
        targets = {
            "video": temporary / "assets" / "demo.mp4",
            "slides": temporary / "assets" / "slides.pdf",
            "cover": temporary / "assets" / f"cover{inputs.cover.suffix.lower()}",
        }
        shutil.copyfile(inputs.video, targets["video"])
        shutil.copyfile(inputs.slides, targets["slides"])
        shutil.copyfile(inputs.cover, targets["cover"])
        shutil.copyfile(inputs.release_protocol, temporary / "evidence" / "release.json")
        for source in sorted(inputs.release_suite.rglob("*")):
            if source.is_file():
                relative = source.relative_to(inputs.release_suite)
                target = temporary / "evidence" / "release-suite" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        files = _inventory(temporary)

        def asset(
            key: str,
            media: Literal["video/mp4", "application/pdf", "image/png", "image/jpeg"],
        ) -> PackagedAsset:
            relative = targets[key].relative_to(temporary).as_posix()
            return PackagedAsset(path=relative, sha256=files[relative], media_type=media)

        body = {
            "schema_version": 1,
            "profile": "hackathon_submission_package_v1",
            "created_at": datetime.now(UTC).isoformat(),
            "repository": {
                "schema_version": 1,
                "revision": inputs.repository_revision,
                "dirty_at_packaging": False,
            },
            "release_protocol": {
                "schema_version": 1,
                "path": _project_relative(inputs.release_protocol, root),
                "file_sha256": digest_file(inputs.release_protocol),
                "manifest_sha256": protocol.manifest_sha256,
            },
            "release_suite": {
                "schema_version": 1,
                "path": _project_relative(inputs.release_suite / "manifest.json", root),
                "file_sha256": digest_file(inputs.release_suite / "manifest.json"),
                "manifest_sha256": suite.manifest_sha256,
            },
            "interactive_url": inputs.interactive_url,
            "video": asset("video", "video/mp4").model_dump(mode="json"),
            "slides": asset("slides", "application/pdf").model_dump(mode="json"),
            "cover": asset(
                "cover", "image/png" if inputs.cover.suffix.lower() == ".png" else "image/jpeg"
            ).model_dump(mode="json"),
            "package_files": files,
            "local_prequalification_passed": suite.metrics["local_prequalification_passed"],
            "intel_validated": suite.metrics["intel_validated"],
            "release_success": suite.metrics["release_success"],
            "package_complete": True,
            "submission_status": "package_complete_not_submitted",
        }
        body["manifest_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
        manifest = SubmissionPackageManifest.model_validate(body)
        (temporary / MANIFEST_NAME).write_bytes(canonical(manifest.model_dump(mode="json")) + b"\n")
        temporary.rename(destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return verify_submission_package(destination, project_root=root)


def verify_submission_package(directory: Path, *, project_root: Path) -> SubmissionPackageManifest:
    """Reverify the package inventory, repository revision, and source evidence."""
    directory = directory.resolve(strict=True)
    root = project_root.resolve(strict=True)
    manifest = SubmissionPackageManifest.model_validate_json(
        (directory / MANIFEST_NAME).read_bytes()
    )
    if _inventory(directory) != manifest.package_files:
        raise ValueError("Submission package file inventory changed")
    if _git(root, "rev-parse", "HEAD") != manifest.repository.revision:
        raise ValueError("Submission package repository revision is no longer checked out")
    protocol_path = (root / manifest.release_protocol.path).resolve(strict=True)
    if _project_relative(protocol_path, root) != manifest.release_protocol.path:
        raise ValueError("Submission release protocol path changed")
    if digest_file(protocol_path) != manifest.release_protocol.file_sha256:
        raise ValueError("Submission release protocol file changed")
    protocol = load_workflow_release_protocol(protocol_path)
    if protocol.manifest_sha256 != manifest.release_protocol.manifest_sha256:
        raise ValueError("Submission release protocol identity changed")
    suite_manifest_path = (root / manifest.release_suite.path).resolve(strict=True)
    if _project_relative(suite_manifest_path, root) != manifest.release_suite.path:
        raise ValueError("Submission release suite path changed")
    if digest_file(suite_manifest_path) != manifest.release_suite.file_sha256:
        raise ValueError("Submission release suite file changed")
    suite = _load_suite(suite_manifest_path.parent)
    if (
        suite.manifest_sha256 != manifest.release_suite.manifest_sha256
        or suite.config.get("protocol_manifest_sha256") != protocol.manifest_sha256
        or suite.metrics.get("local_prequalification_passed")
        != manifest.local_prequalification_passed
        or suite.metrics.get("intel_validated") != manifest.intel_validated
        or suite.metrics.get("release_success") != manifest.release_success
    ):
        raise ValueError("Submission release suite identity or outcomes changed")
    if _git(root, "status", "--porcelain"):
        raise ValueError("Submission package repository working tree is no longer clean")
    _validate_url(manifest.interactive_url)
    _validate_video(directory / manifest.video.path)
    _validate_slides(directory / manifest.slides.path)
    _validate_cover(directory / manifest.cover.path)
    return manifest
