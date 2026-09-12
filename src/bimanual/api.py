"""Local project portal with explicit opt-in simulated workflow control."""

import html
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bimanual.evidence import EvidenceStore
from bimanual.operator_jobs import OperatorJobs
from bimanual.workflow_process import WorkflowProcessConfig


class OperatorInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    instruction: str = Field(min_length=1, max_length=4096)


def create_app(
    project_root: Path,
    artifact_root: Path,
    *,
    operator_config: WorkflowProcessConfig | None = None,
    _operator_runner=None,
) -> FastAPI:
    root = project_root.resolve()
    store = EvidenceStore(artifact_root)
    kwargs = {} if _operator_runner is None else {"_runner": _operator_runner}
    jobs = (
        OperatorJobs(operator_config, store=store, project_root=root, **kwargs)
        if operator_config is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if jobs is not None:
                await run_in_threadpool(jobs.close)

    app = FastAPI(
        title="Bimanual project portal", version="0.1.0", docs_url="/api/docs", lifespan=lifespan
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "scope": "operator_workflow" if jobs is not None else "read_only_evidence",
            "control_available": jobs is not None,
        }

    def operator_request(request: Request):
        if jobs is None:
            raise HTTPException(503, "Workflow control is not configured")
        # Custom headers require preflight from other origins; no CORS grant exists.
        if request.headers.get("x-bimanual-operator") != "1":
            raise HTTPException(403, "Explicit operator request header required")
        origin = request.headers.get("origin")
        if origin is not None and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Operator requests must use the portal origin")
        return jobs

    @app.get("/api/operator")
    def operator_status():
        job = jobs.snapshot() if jobs is not None else None
        return {
            "configured": jobs is not None,
            "job": job.report() if job is not None else None,
            "task_success_verified": False,
        }

    @app.post("/api/operator/jobs", status_code=202)
    def operator_start(body: OperatorInstruction, request: Request):
        controller = operator_request(request)
        try:
            return controller.start(body.instruction).report()
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/operator/jobs/{job_id}/stop")
    def operator_stop(job_id: str, request: Request):
        controller = operator_request(request)
        try:
            return controller.stop(job_id).report()
        except KeyError as exc:
            raise HTTPException(404, "No matching operator job") from exc

    @app.get("/api/project")
    def project():
        return json.loads((root / "docs/project.json").read_text())

    @app.get("/api/runs")
    def runs(
        limit: int | None = Query(default=None, ge=1, le=100),
        before: str | None = Query(default=None, max_length=128),
    ):
        # Source-file digests are retained on disk, but omitted from the list view.
        records = [
            {k: v for k, v in run.items() if k != "provenance"}
            for run in store.list_runs(limit=limit, before=before)
        ]
        if limit is not None:
            for record in records:
                metrics = record.get("metrics", {})
                if isinstance(metrics.get("steps"), list):
                    record["metrics"] = {k: v for k, v in metrics.items() if k != "steps"}
                    record["summary"] = {
                        "omitted_metric_fields": ["steps"],
                        "recorded_training_steps": len(metrics["steps"]),
                        "detail_scope": "Full metrics remain in the sealed local manifest",
                    }
        return records

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
