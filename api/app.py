"""FastAPI application for PaperBanana HTTP API."""

from __future__ import annotations

import inspect
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

import structlog
import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from paperbanana.core.config import Settings
from paperbanana.core.utils import detect_image_mime_type, ensure_dir

from .docs import description, request_examples, tags_metadata
from .schemas import (
    ContinueTaskRequest,
    EvaluateTaskPayload,
    GenerateTaskRequest,
    PlotTaskRequest,
    TaskCreateResponse,
    TaskResponse,
    TaskStatus,
    TaskType,
)
from .tasks import TaskManager

logger = structlog.get_logger()

_settings: Optional[Settings] = None
_task_manager: Optional[TaskManager] = None


def _get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("API settings not initialized")
    return _settings


def _get_task_manager() -> TaskManager:
    if _task_manager is None:
        raise RuntimeError("Task manager not initialized")
    return _task_manager


def _require_auth(
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
) -> None:
    token = _get_settings().paperbanana_api_token
    if not token:
        raise HTTPException(status_code=500, detail="PAPERBANANA_API_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    provided = authorization[7:].strip()
    if not secrets.compare_digest(provided, token):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize settings and task manager."""
    global _settings, _task_manager

    _settings = Settings()
    if not _settings.paperbanana_api_token:
        raise RuntimeError(
            "PAPERBANANA_API_TOKEN is required for API mode. "
            "Set it in environment variables before starting the service."
        )

    _task_manager = TaskManager(_settings)
    await _task_manager.start()

    ensure_dir(Path(_settings.output_dir))
    logger.info(
        "API started",
        output_dir=_settings.output_dir,
        vlm_provider=_settings.vlm_provider,
        image_provider=_settings.image_provider,
    )
    yield
    manager = _task_manager
    _task_manager = None
    _settings = None
    if manager is not None:
        stop_fn = getattr(manager, "stop", None)
        if callable(stop_fn):
            maybe_awaitable = stop_fn()
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
    logger.info("API shutting down")


app = FastAPI(
    title="PaperBanana API",
    description=description,
    version="0.1.2",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

_outputs_dir = ensure_dir(Path(Settings().output_dir))
app.mount("/outputs", StaticFiles(directory=str(_outputs_dir)), name="outputs")

_static_dir = ensure_dir(Path(__file__).parent / "static")
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", tags=["Health"], include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect to static docs page."""
    return RedirectResponse(url="/static/docs.html")


@app.get(
    "/health",
    tags=["Health"],
    summary="心跳检测",
    description="用于服务存活探测的心跳接口。",
)
async def heartbeat_check():
    """Heartbeat endpoint for liveness checks."""
    return {"status": "ok", "version": "0.1.2"}


@app.post(
    "/api/v1/tasks/generate",
    response_model=TaskCreateResponse,
    status_code=202,
    tags=["Tasks"],
    dependencies=[Depends(_require_auth)],
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {"examples": {"generate": request_examples["generate"]}}
            }
        }
    },
)
async def create_generate_task(request: GenerateTaskRequest):
    """Submit a methodology-diagram generation task."""
    manager = _get_task_manager()
    task_id = await manager.submit_generate(request)
    return TaskCreateResponse(
        task_id=task_id,
        task_type=TaskType.GENERATE,
        status=TaskStatus.PENDING,
        status_url=f"/api/v1/tasks/{task_id}",
    )


@app.post(
    "/api/v1/tasks/plot",
    response_model=TaskCreateResponse,
    status_code=202,
    tags=["Tasks"],
    dependencies=[Depends(_require_auth)],
    openapi_extra={
        "requestBody": {
            "content": {"application/json": {"examples": {"plot": request_examples["plot"]}}}
        }
    },
)
async def create_plot_task(request: PlotTaskRequest):
    """Submit a statistical-plot generation task."""
    manager = _get_task_manager()
    task_id = await manager.submit_plot(request)
    return TaskCreateResponse(
        task_id=task_id,
        task_type=TaskType.PLOT,
        status=TaskStatus.PENDING,
        status_url=f"/api/v1/tasks/{task_id}",
    )


@app.post(
    "/api/v1/tasks/continue",
    response_model=TaskCreateResponse,
    status_code=202,
    tags=["Tasks"],
    dependencies=[Depends(_require_auth)],
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {"examples": {"continue": request_examples["continue"]}}
            }
        }
    },
)
async def create_continue_task(request: ContinueTaskRequest):
    """Submit a continue-run task."""
    manager = _get_task_manager()
    task_id = await manager.submit_continue(request)
    return TaskCreateResponse(
        task_id=task_id,
        task_type=TaskType.CONTINUE,
        status=TaskStatus.PENDING,
        status_url=f"/api/v1/tasks/{task_id}",
    )


@app.post(
    "/api/v1/tasks/evaluate",
    response_model=TaskCreateResponse,
    status_code=202,
    tags=["Tasks"],
    dependencies=[Depends(_require_auth)],
)
async def create_evaluate_task(
    generated_image: UploadFile = File(..., description="待评测生成图"),
    reference_image: UploadFile = File(..., description="参考图"),
    source_context: str = Form(...),
    caption: str = Form(...),
    vlm_provider: Optional[str] = Form(None),
    vlm_model: Optional[str] = Form(None),
):
    """Submit an evaluation task via multipart file upload."""
    upload_id = uuid.uuid4().hex[:12]
    upload_dir = ensure_dir(Path(_get_settings().output_dir) / "api_uploads" / upload_id)

    generated_name = Path(generated_image.filename or "generated.png").name
    reference_name = Path(reference_image.filename or "reference.png").name

    generated_path = upload_dir / f"generated_{generated_name}"
    reference_path = upload_dir / f"reference_{reference_name}"

    generated_bytes = await generated_image.read()
    reference_bytes = await reference_image.read()
    generated_path.write_bytes(generated_bytes)
    reference_path.write_bytes(reference_bytes)

    payload = EvaluateTaskPayload(
        generated_image_path=str(generated_path),
        reference_image_path=str(reference_path),
        source_context=source_context,
        caption=caption,
        vlm_provider=vlm_provider,
        vlm_model=vlm_model,
    )

    manager = _get_task_manager()
    task_id = await manager.submit_evaluate(payload)
    return TaskCreateResponse(
        task_id=task_id,
        task_type=TaskType.EVALUATE,
        status=TaskStatus.PENDING,
        status_url=f"/api/v1/tasks/{task_id}",
    )


@app.get(
    "/api/v1/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["Tasks"],
    dependencies=[Depends(_require_auth)],
)
async def get_task(task_id: str):
    """Get task status."""
    manager = _get_task_manager()
    state = await manager.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return TaskResponse(
        task_id=state.task_id,
        task_type=state.task_type,
        status=state.status,
        created_at=state.created_at,
        started_at=state.started_at,
        completed_at=state.completed_at,
        progress=state.progress,
        result=state.result,
        error=state.error,
    )


@app.get(
    "/api/v1/tasks/{task_id}/artifact",
    tags=["Tasks"],
    dependencies=[Depends(_require_auth)],
)
async def download_task_artifact(task_id: str):
    """Download task artifact (image/json)."""
    manager = _get_task_manager()
    state = await manager.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if state.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Task has not completed successfully")
    if not state.artifact_path or not state.artifact_type:
        raise HTTPException(status_code=404, detail="Task artifact not found")

    artifact_path = Path(state.artifact_path)
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Task artifact file not found")

    if state.artifact_type.value == "json":
        return FileResponse(
            path=str(artifact_path),
            media_type="application/json",
            filename=f"{task_id}.json",
        )

    mime = detect_image_mime_type(artifact_path)
    ext = artifact_path.suffix or ".png"
    return FileResponse(
        path=str(artifact_path),
        media_type=mime if mime.startswith("image/") else "image/png",
        filename=f"{task_id}{ext}",
    )


@app.get(
    "/api/v1/tasks/{task_id}/image",
    tags=["Tasks"],
    include_in_schema=False,
    dependencies=[Depends(_require_auth)],
)
async def download_task_image_alias(task_id: str):
    """Backward-compatible alias to artifact endpoint."""
    return await download_task_artifact(task_id)


def main() -> None:
    """Local entrypoint for API service."""
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, workers=1, reload=False)


if __name__ == "__main__":
    main()
