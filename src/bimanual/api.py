"""Read-only local project portal; it cannot start training or control a robot."""

import html
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bimanual.evidence import EvidenceStore


def create_app(project_root: Path, artifact_root: Path) -> FastAPI:
    root = project_root.resolve()
    store = EvidenceStore(artifact_root)
    app = FastAPI(title="Bimanual preparation portal", version="0.1.0", docs_url="/api/docs")
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "scope": "preparation", "control_available": False}

    @app.get("/api/project")
    def project():
        return json.loads((root / "docs/project.json").read_text())

    @app.get("/api/runs")
    def runs():
        # Source-file digests are retained on disk, but omitted from the list view.
        return [{k: v for k, v in run.items() if k != "provenance"} for run in store.list_runs()]

    @app.get("/api/runs/{run_id}/files/{filename:path}")
    def evidence_file(run_id: str, filename: str):
        try:
            manifest = store.verify(run_id)
            if filename not in manifest.files:
                raise HTTPException(404, "No such evidence file")
            return FileResponse(store.directory(run_id) / filename)
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "Evidence unavailable or integrity check failed") from exc

    @app.get("/read/{relative:path}")
    def document(relative: str):
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(404, "No such project document")
        relative = candidate.relative_to(root).as_posix()
        allowed = relative in {
            "README.md",
            "MISSION.md",
            "RESOURCES.md",
            "NOTES.md",
        } or relative.startswith(
            ("docs/", "lessons/", "reference/", "learning-records/", "assets/learning/")
        )
        if (
            not allowed
            or not candidate.is_relative_to(root)
            or not candidate.is_file()
            or candidate.suffix not in {".md", ".html", ".css", ".js", ".json", ".png", ".svg"}
        ):
            raise HTTPException(404, "No such project document")
        if candidate.suffix == ".md":
            body = (
                MarkdownIt("commonmark", {"html": False})
                .enable("table")
                .render(candidate.read_text())
            )
            return HTMLResponse(
                '<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f"<title>{html.escape(candidate.stem)} · Bimanual</title>"
                '<link rel="stylesheet" href="/read/assets/learning/lesson.css">'
                '<body><main class="lesson"><nav><a href="/">Project home</a> / '
                '<a href="/read/docs/README.md">Documentation</a></nav>'
                f"{body}</main></body></html>"
            )
        return FileResponse(candidate)

    dist = root / "web/dist"
    if (dist / "app-assets").exists():
        app.mount("/app-assets", StaticFiles(directory=dist / "app-assets"), name="app-assets")

    @app.get("/", response_class=HTMLResponse)
    def index():
        if not (dist / "index.html").is_file():
            return HTMLResponse(
                "<h1>Build the project portal</h1><p>Run npm ci and npm run build in web.</p>"
                '<p><a href="/read/docs/SETUP.md">Setup instructions</a></p>',
                status_code=503,
            )
        return FileResponse(dist / "index.html")

    return app
