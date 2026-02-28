from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

api_app = pytest.importorskip("api.app")
schemas = pytest.importorskip("api.schemas")
tasks_mod = pytest.importorskip("api.tasks")

ArtifactType = schemas.ArtifactType
TaskResult = schemas.TaskResult
TaskStatus = schemas.TaskStatus
TaskType = schemas.TaskType
TaskState = tasks_mod.TaskState


class _DummyManager:
    async def submit_generate(self, request):
        return "task123"

    async def submit_plot(self, request):
        return "task_plot"

    async def submit_continue(self, request):
        return "task_continue"

    async def submit_evaluate(self, payload):
        return "task_eval"

    async def get(self, task_id):
        return None

    async def stop(self):
        return None


def _client_with_token(monkeypatch):
    monkeypatch.setenv("PAPERBANANA_API_TOKEN", "test-token")
    return TestClient(api_app.app)


def test_health_is_public(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_auth_required_for_task_endpoints(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        resp = client.post(
            "/api/v1/tasks/generate",
            json={"source_context": "a", "communicative_intent": "b"},
        )
        assert resp.status_code == 401


def test_submit_generate_task(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.post(
            "/api/v1/tasks/generate",
            headers={"Authorization": "Bearer test-token"},
            json={"source_context": "method text", "communicative_intent": "caption"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["task_id"] == "task123"
        assert body["task_type"] == "generate"


def test_submit_generate_task_invalid_provider_returns_422(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.post(
            "/api/v1/tasks/generate",
            headers={"Authorization": "Bearer test-token"},
            json={
                "source_context": "method text",
                "communicative_intent": "caption",
                "providers": {"vlm_provider": "not_supported"},
            },
        )
        assert resp.status_code == 422
        detail_text = str(resp.json())
        assert "vlm_provider must be one of" in detail_text


def test_submit_generate_task_invalid_aspect_ratio_returns_422(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.post(
            "/api/v1/tasks/generate",
            headers={"Authorization": "Bearer test-token"},
            json={
                "source_context": "method text",
                "communicative_intent": "caption",
                "aspect_ratio": "10:7",
            },
        )
        assert resp.status_code == 422
        detail_text = str(resp.json())
        assert "aspect_ratio must be one of" in detail_text


def test_submit_continue_task_with_aspect_ratio(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.post(
            "/api/v1/tasks/continue",
            headers={"Authorization": "Bearer test-token"},
            json={
                "run_id": "run_20260226_120000_ab12cd",
                "additional_iterations": 1,
                "aspect_ratio": "16:9",
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["task_id"] == "task_continue"
        assert body["task_type"] == "continue"


def test_get_task_status_not_found(monkeypatch):
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.get(
            "/api/v1/tasks/task_missing",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 404


def test_submit_evaluate_task(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.post(
            "/api/v1/tasks/evaluate",
            headers={"Authorization": "Bearer test-token"},
            files={
                "generated_image": ("generated.png", b"\x89PNG\r\n\x1a\n", "image/png"),
                "reference_image": ("reference.png", b"\x89PNG\r\n\x1a\n", "image/png"),
            },
            data={
                "source_context": "context",
                "caption": "caption",
            },
        )
        assert resp.status_code == 202
        assert resp.json()["task_type"] == "evaluate"


def test_submit_evaluate_task_invalid_vlm_provider_returns_422(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _DummyManager())
        resp = client.post(
            "/api/v1/tasks/evaluate",
            headers={"Authorization": "Bearer test-token"},
            files={
                "generated_image": ("generated.png", b"\x89PNG\r\n\x1a\n", "image/png"),
                "reference_image": ("reference.png", b"\x89PNG\r\n\x1a\n", "image/png"),
            },
            data={
                "source_context": "context",
                "caption": "caption",
                "vlm_provider": "not_supported",
            },
        )
        assert resp.status_code == 422
        detail_text = str(resp.json())
        assert "vlm_provider must be one of" in detail_text


def test_download_artifact_success(monkeypatch, tmp_path: Path):
    class _ManagerWithArtifact(_DummyManager):
        async def get(self, task_id):
            image = tmp_path / "out.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n")
            return TaskState(
                task_id=task_id,
                task_type=TaskType.GENERATE,
                payload={},
                created_at=dt.datetime.now(dt.timezone.utc),
                status=TaskStatus.COMPLETED,
                artifact_path=str(image),
                artifact_type=ArtifactType.IMAGE,
                result=TaskResult(
                    artifact_url=f"/api/v1/tasks/{task_id}/artifact",
                    artifact_type=ArtifactType.IMAGE,
                ),
            )

    with _client_with_token(monkeypatch) as client:
        monkeypatch.setattr(api_app, "_task_manager", _ManagerWithArtifact())
        resp = client.get(
            "/api/v1/tasks/task_img/artifact",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")
