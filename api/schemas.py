"""Request/response schemas for PaperBanana HTTP API."""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

OutputFormat = Literal["png", "jpeg", "webp"]


class TaskStatus(str, Enum):
    """Asynchronous task status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(str, Enum):
    """Task kind for routing execution logic."""

    GENERATE = "generate"
    PLOT = "plot"
    CONTINUE = "continue"
    EVALUATE = "evaluate"


class ArtifactType(str, Enum):
    """Final artifact type produced by a task."""

    IMAGE = "image"
    JSON = "json"


class ProviderOverrides(BaseModel):
    """Optional per-task provider/model overrides."""

    vlm_provider: Optional[str] = None
    vlm_model: Optional[str] = None
    image_provider: Optional[str] = None
    image_model: Optional[str] = None


class GenerateTaskRequest(BaseModel):
    """Submit a methodology-diagram generation task."""

    source_context: str = Field(min_length=1, description="方法论文本或论文摘录")
    communicative_intent: str = Field(min_length=1, description="图表标题 / 要传达内容")
    refinement_iterations: Optional[int] = Field(default=None, ge=1, le=30)
    optimize_inputs: bool = Field(default=False, description="是否启用输入优化")
    auto_refine: bool = Field(default=False, description="是否自动迭代到满意")
    max_iterations: Optional[int] = Field(default=None, ge=1, le=100)
    output_format: Optional[OutputFormat] = None
    providers: Optional[ProviderOverrides] = None


class PlotTaskRequest(BaseModel):
    """Submit a statistical-plot generation task."""

    intent: str = Field(min_length=1, description="图表意图")
    raw_data: Any = Field(description="统计图原始数据（JSON）")
    source_context: Optional[str] = Field(
        default=None,
        description="可选：自定义上下文；为空时将从 raw_data 自动构造",
    )
    refinement_iterations: Optional[int] = Field(default=None, ge=1, le=30)
    output_format: Optional[OutputFormat] = None
    providers: Optional[ProviderOverrides] = None


class ContinueTaskRequest(BaseModel):
    """Continue a previous run with additional iterations."""

    run_id: Optional[str] = Field(default=None, description="已有 run_id")
    continue_latest: bool = Field(default=False, description="是否续跑最新 run")
    additional_iterations: Optional[int] = Field(default=None, ge=1, le=100)
    user_feedback: Optional[str] = Field(default=None, max_length=5000)
    auto_refine: bool = Field(default=False)
    max_iterations: Optional[int] = Field(default=None, ge=1, le=100)
    output_format: Optional[OutputFormat] = None
    providers: Optional[ProviderOverrides] = None

    @model_validator(mode="after")
    def validate_run_selector(self) -> ContinueTaskRequest:
        has_run_id = bool(self.run_id and self.run_id.strip())
        if has_run_id == self.continue_latest:
            raise ValueError("run_id 与 continue_latest 必须且只能二选一")
        return self


class EvaluateTaskPayload(BaseModel):
    """Internal payload for evaluate task execution."""

    generated_image_path: str
    reference_image_path: str
    source_context: str = Field(min_length=1)
    caption: str = Field(min_length=1)
    vlm_provider: Optional[str] = None
    vlm_model: Optional[str] = None


class TaskResult(BaseModel):
    """Result model returned when task succeeds."""

    artifact_url: str
    artifact_type: ArtifactType
    run_id: Optional[str] = None
    description: Optional[str] = None
    total_iterations: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    scores: Optional[dict[str, Any]] = None


class TaskCreateResponse(BaseModel):
    """Response for accepted async task submission."""

    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    status_url: str


class TaskResponse(BaseModel):
    """Task status response."""

    task_id: str
    task_type: TaskType
    status: TaskStatus
    created_at: dt.datetime
    started_at: Optional[dt.datetime] = None
    completed_at: Optional[dt.datetime] = None
    progress: Optional[str] = None
    result: Optional[TaskResult] = None
    error: Optional[str] = None
