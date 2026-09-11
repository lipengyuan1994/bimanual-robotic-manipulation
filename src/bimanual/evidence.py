"""Local provenance and file-integrity records, not claims about robot performance."""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import subprocess
import uuid
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def provenance(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    # Hash working source as well as the base commit; uncommitted work is never
    # misrepresented as the committed revision. Runtime output and caches are excluded.
    names = git("ls-files", "--cached", "--others", "--exclude-standard")
    sources = {
        name: digest_file(root / name)
        for name in sorted(set((names or "").splitlines()))
        if (root / name).is_file()
    }
    return {
        "git_revision": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "source_files": sources,
        "source_sha256": hashlib.sha256(canonical(sources)).hexdigest(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "platform": platform.platform(),
    }


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: int = 1
    run_id: str
    created_at: str
    kind: str
    outcome: str
    claims: list[str] = Field(default_factory=list)
    config: dict[str, Any]
    metrics: dict[str, Any]
    provenance: dict[str, Any]
    files: dict[str, str]
    manifest_sha256: str


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def new_run(self) -> Path:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        directory = self.root / "runs" / run_id
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def seal(
        self,
        directory: Path,
        *,
        kind: str,
        outcome: str,
        config: dict[str, Any],
        metrics: dict[str, Any],
        source: dict[str, Any],
        claims: list[str],
    ) -> Manifest:
        if directory.parent.resolve() != (self.root / "runs").resolve():
            raise ValueError("Run directory is outside this evidence store")
        files = {
            p.relative_to(directory).as_posix(): digest_file(p)
            for p in sorted(directory.rglob("*"))
            if p.is_file() and p != directory / "manifest.json"
        }
        payload = dict(
            schema_version=1,
            run_id=directory.name,
            created_at=datetime.now(UTC).isoformat(),
            kind=kind,
            outcome=outcome,
            claims=claims,
            config=config,
            metrics=metrics,
            provenance=source,
            files=files,
        )
        payload["manifest_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
        manifest = Manifest.model_validate(payload)
        # Exclusive creation: an existing sealed run is never overwritten.
        with (directory / "manifest.json").open("x") as stream:
            stream.write(manifest.model_dump_json(indent=2) + "\n")
        try:
            with sqlite3.connect(self.root / "runs.sqlite3") as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS runs "
                    "(run_id TEXT PRIMARY KEY, created_at TEXT, kind TEXT, outcome TEXT)"
                )
                db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?)",
                    (manifest.run_id, manifest.created_at, kind, outcome),
                )
        except sqlite3.Error as exc:
            warnings.warn(
                f"Evidence sealed; optional SQLite index update failed: {exc}", stacklevel=2
            )
        return manifest

    def directory(self, run_id: str) -> Path:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("Invalid run id")
        directory = (self.root / "runs" / run_id).resolve()
        if directory.parent != (self.root / "runs").resolve():
            raise ValueError("Invalid run path")
        return directory

    def read(self, run_id: str) -> Manifest:
        return Manifest.model_validate_json((self.directory(run_id) / "manifest.json").read_text())

    def verify(self, run_id: str) -> Manifest:
        directory = self.directory(run_id)
        manifest = self.read(run_id)
        if manifest.run_id != run_id or manifest.schema_version != 1:
            raise ValueError("Manifest identity or schema mismatch")
        payload = manifest.model_dump(exclude={"manifest_sha256"})
        if hashlib.sha256(canonical(payload)).hexdigest() != manifest.manifest_sha256:
            raise ValueError("Manifest digest mismatch")
        for name, expected in manifest.files.items():
            candidate = (directory / name).resolve()
            if not candidate.is_relative_to(directory) or not candidate.is_file():
                raise ValueError(f"Invalid or missing evidence file: {name}")
            if digest_file(candidate) != expected:
                raise ValueError(f"Evidence digest mismatch: {name}")
        actual = {
            p.relative_to(directory).as_posix()
            for p in directory.rglob("*")
            if p.is_file() and p != directory / "manifest.json"
        }
        if actual != set(manifest.files):
            raise ValueError("Unsealed files found in run")
        return manifest

    def list_runs(
        self, *, limit: int | None = None, before: str | None = None
    ) -> list[dict[str, Any]]:
        # Manifests are authoritative. The SQLite index is only a rebuildable cache.
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 100):
            raise ValueError("Run page limit must be between 1 and 100")
        result = []
        for file in sorted((self.root / "runs").glob("*/manifest.json"), reverse=True):
            if before is not None and file.parent.name >= before:
                continue
            if limit is not None and len(result) >= limit:
                break
            try:
                manifest = self.verify(file.parent.name)
                result.append(manifest.model_dump() | {"integrity": "verified"})
            except (ValueError, OSError) as exc:
                result.append(
                    {"run_id": file.parent.name, "integrity": "failed", "error": str(exc)}
                )
        return result
