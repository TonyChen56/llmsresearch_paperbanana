"""Async task manager for PaperBanana HTTP API."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import structlog

from paperbanana.core.config import Settings
from paperbanana.core.pipeline import PaperBananaPipeline
from paperbanana.core.resume import find_latest_run, load_resume_state
from paperbanana.core.types import DiagramType, GenerationInput
from paperbanana.core.utils import ensure_dir, find_prompt_dir, save_json
from paperbanana.evaluation.judge import VLMJudge
from paperbanana.providers.registry import ProviderRegistry

from .schemas import (
    ArtifactType,
    ContinueTaskRequest,
    EvaluateTaskPayload,
    GenerateTaskRequest,
    PlotTaskRequest,
    ProviderOverrides,
    TaskResult,
    TaskStatus,
    TaskType,
)

logger = structlog.get_logger()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _format_task_error(exc: Exception) -> str:
    last_attempt = getattr(exc, "last_attempt", None)
    if last_attempt is not None:
        try:
            inner = last_attempt.exception()
        except Exception:
            inner = None
        if inner is not None:
            return f"{type(inner).__name__}: {inner}"
    text = str(exc)
    return text if text else type(exc).__name__


@dataclass
class TaskState:
    """In-memory state for one async task."""

    task_id: str
    task_type: TaskType
    payload: Any
    created_at: dt.datetime
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[dt.datetime] = None
    completed_at: Optional[dt.datetime] = None
    progress: Optional[str] = None
    result: Optional[TaskResult] = None
    error: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_type: Optional[ArtifactType] = None


class TaskManager:
    """Manage async task submission, execution, and cleanup."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._tasks: dict[str, TaskState] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max(1, settings.api_max_concurrent_tasks))
        self._task_root = ensure_dir(Path(settings.output_dir) / "api_tasks")

    async def start(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def submit_generate(self, request: GenerateTaskRequest) -> str:
        return await self._submit(TaskType.GENERATE, request)

    async def submit_plot(self, request: PlotTaskRequest) -> str:
        return await self._submit(TaskType.PLOT, request)

    async def submit_continue(self, request: ContinueTaskRequest) -> str:
        return await self._submit(TaskType.CONTINUE, request)

    async def submit_evaluate(self, payload: EvaluateTaskPayload) -> str:
        return await self._submit(TaskType.EVALUATE, payload)

    async def _submit(self, task_type: TaskType, payload: Any) -> str:
        task_id = uuid.uuid4().hex[:12]
        state = TaskState(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            created_at=_now(),
            progress="已排队",
        )
        async with self._lock:
            self._tasks[task_id] = state
        asyncio.create_task(self._execute(task_id))
        logger.info("Task submitted", task_id=task_id, task_type=task_type.value)
        return task_id

    async def get(self, task_id: str) -> Optional[TaskState]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def _execute(self, task_id: str) -> None:
        async with self._semaphore:
            state = await self.get(task_id)
            if state is None:
                return

            state.status = TaskStatus.RUNNING
            state.started_at = _now()
            state.progress = "任务执行中"

            try:
                if state.task_type == TaskType.GENERATE:
                    await self._run_generate(state)
                elif state.task_type == TaskType.PLOT:
                    await self._run_plot(state)
                elif state.task_type == TaskType.CONTINUE:
                    await self._run_continue(state)
                elif state.task_type == TaskType.EVALUATE:
                    await self._run_evaluate(state)
                else:
                    raise ValueError(f"Unsupported task type: {state.task_type}")

                state.status = TaskStatus.COMPLETED
                state.completed_at = _now()
                state.progress = None
                logger.info("Task completed", task_id=task_id, task_type=state.task_type.value)
            except Exception as exc:
                state.status = TaskStatus.FAILED
                state.completed_at = _now()
                state.progress = None
                state.error = _format_task_error(exc)
                logger.error(
                    "Task failed",
                    task_id=task_id,
                    task_type=state.task_type.value,
                    error=state.error,
                    exc_info=True,
                )

    def _build_settings(
        self,
        providers: Optional[ProviderOverrides] = None,
        output_format: Optional[str] = None,
        extra_updates: Optional[dict[str, Any]] = None,
        task_output_dir: Optional[Path] = None,
    ) -> Settings:
        updates: dict[str, Any] = {}
        if providers is not None:
            if providers.vlm_provider:
                updates["vlm_provider"] = providers.vlm_provider
            if providers.vlm_model:
                updates["vlm_model"] = providers.vlm_model
            if providers.image_provider:
                updates["image_provider"] = providers.image_provider
            if providers.image_model:
                updates["image_model"] = providers.image_model
        if output_format:
            updates["output_format"] = output_format
        if task_output_dir is not None:
            updates["output_dir"] = str(task_output_dir)
        if extra_updates:
            updates.update(extra_updates)
        return self._settings.model_copy(update=updates)

    async def _run_generate(self, state: TaskState) -> None:
        request: GenerateTaskRequest = state.payload
        task_dir = ensure_dir(self._task_root / state.task_id)

        updates: dict[str, Any] = {}
        if request.refinement_iterations is not None:
            updates["refinement_iterations"] = request.refinement_iterations
        if request.optimize_inputs:
            updates["optimize_inputs"] = True
        if request.auto_refine:
            updates["auto_refine"] = True
        if request.max_iterations is not None:
            updates["max_iterations"] = request.max_iterations

        settings = self._build_settings(
            providers=request.providers,
            output_format=request.output_format,
            extra_updates=updates,
            task_output_dir=task_dir,
        )

        state.progress = "初始化生成流水线"
        pipeline = PaperBananaPipeline(settings=settings)
        gen_input = GenerationInput(
            source_context=request.source_context,
            communicative_intent=request.communicative_intent,
            diagram_type=DiagramType.METHODOLOGY,
            aspect_ratio=request.aspect_ratio,
        )

        state.progress = "执行生成"
        output = await pipeline.generate(gen_input)

        state.artifact_path = output.image_path
        state.artifact_type = ArtifactType.IMAGE
        state.result = TaskResult(
            artifact_url=f"/api/v1/tasks/{state.task_id}/artifact",
            artifact_type=ArtifactType.IMAGE,
            run_id=output.metadata.get("run_id"),
            description=output.description,
            total_iterations=len(output.iterations),
            metadata=output.metadata,
        )

    async def _run_plot(self, state: TaskState) -> None:
        request: PlotTaskRequest = state.payload
        task_dir = ensure_dir(self._task_root / state.task_id)

        updates: dict[str, Any] = {}
        if request.refinement_iterations is not None:
            updates["refinement_iterations"] = request.refinement_iterations

        settings = self._build_settings(
            providers=request.providers,
            output_format=request.output_format,
            extra_updates=updates,
            task_output_dir=task_dir,
        )

        if request.source_context:
            source_context = request.source_context
        else:
            serialized = json.dumps(request.raw_data, ensure_ascii=False, indent=2)[:4000]
            source_context = f"JSON data:\n{serialized}"

        pipeline = PaperBananaPipeline(settings=settings)
        gen_input = GenerationInput(
            source_context=source_context,
            communicative_intent=request.intent,
            diagram_type=DiagramType.STATISTICAL_PLOT,
            raw_data={"data": request.raw_data},
            aspect_ratio=request.aspect_ratio,
        )

        state.progress = "执行统计图生成"
        output = await pipeline.generate(gen_input)

        state.artifact_path = output.image_path
        state.artifact_type = ArtifactType.IMAGE
        state.result = TaskResult(
            artifact_url=f"/api/v1/tasks/{state.task_id}/artifact",
            artifact_type=ArtifactType.IMAGE,
            run_id=output.metadata.get("run_id"),
            description=output.description,
            total_iterations=len(output.iterations),
            metadata=output.metadata,
        )

    async def _run_continue(self, state: TaskState) -> None:
        request: ContinueTaskRequest = state.payload

        updates: dict[str, Any] = {}
        if request.auto_refine:
            updates["auto_refine"] = True
        if request.max_iterations is not None:
            updates["max_iterations"] = request.max_iterations

        settings = self._build_settings(
            providers=request.providers,
            output_format=request.output_format,
            extra_updates=updates,
        )

        output_base = Path(settings.output_dir)
        run_id = request.run_id.strip() if request.run_id else find_latest_run(str(output_base))
        state.progress = f"加载续跑状态：{run_id}"
        resume_state = load_resume_state(str(output_base), run_id)
        if request.aspect_ratio:
            resume_state.aspect_ratio = request.aspect_ratio

        pipeline = PaperBananaPipeline(settings=settings)
        state.progress = "执行续跑"
        output = await pipeline.continue_run(
            resume_state=resume_state,
            additional_iterations=request.additional_iterations,
            user_feedback=request.user_feedback,
        )

        state.artifact_path = output.image_path
        state.artifact_type = ArtifactType.IMAGE
        state.result = TaskResult(
            artifact_url=f"/api/v1/tasks/{state.task_id}/artifact",
            artifact_type=ArtifactType.IMAGE,
            run_id=output.metadata.get("run_id", run_id),
            description=output.description,
            total_iterations=len(output.iterations),
            metadata=output.metadata,
        )

    async def _run_evaluate(self, state: TaskState) -> None:
        payload: EvaluateTaskPayload = state.payload
        task_dir = ensure_dir(self._task_root / state.task_id)

        providers = ProviderOverrides(
            vlm_provider=payload.vlm_provider,
            vlm_model=payload.vlm_model,
        )
        settings = self._build_settings(providers=providers)

        state.progress = "初始化评测器"
        vlm = ProviderRegistry.create_vlm(settings)
        judge = VLMJudge(vlm_provider=vlm, prompt_dir=find_prompt_dir())

        state.progress = "执行图像评测"
        scores = await judge.evaluate(
            image_path=payload.generated_image_path,
            source_context=payload.source_context,
            caption=payload.caption,
            reference_path=payload.reference_image_path,
        )

        scores_data = scores.model_dump()
        report_path = task_dir / "evaluation.json"
        save_json(scores_data, report_path)

        state.artifact_path = str(report_path)
        state.artifact_type = ArtifactType.JSON
        state.result = TaskResult(
            artifact_url=f"/api/v1/tasks/{state.task_id}/artifact",
            artifact_type=ArtifactType.JSON,
            metadata={},
            scores=scores_data,
        )

    async def _cleanup_loop(self) -> None:
        ttl = dt.timedelta(minutes=max(1, self._settings.api_task_ttl_minutes))
        while True:
            await asyncio.sleep(60)
            now = _now()
            remove_ids: list[str] = []
            async with self._lock:
                for task_id, state in self._tasks.items():
                    if state.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                        continue
                    if state.completed_at is None:
                        continue
                    if now - state.completed_at > ttl:
                        remove_ids.append(task_id)
                for task_id in remove_ids:
                    self._tasks.pop(task_id, None)
            if remove_ids:
                logger.info("Cleaned expired task states", count=len(remove_ids))
