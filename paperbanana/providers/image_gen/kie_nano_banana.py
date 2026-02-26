"""KIE Nano Banana image generation provider."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from typing import Optional

import structlog
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential

from paperbanana.providers.base import ImageGenProvider

logger = structlog.get_logger()


class KieNanoBananaImageGen(ImageGenProvider):
    """Image generation via KIE async task API (Nano Banana)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "google/nano-banana",
        base_url: str = "https://api.kie.ai",
        poll_interval_seconds: float = 2.0,
        max_poll_attempts: int = 120,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._poll_interval_seconds = poll_interval_seconds
        self._max_poll_attempts = max_poll_attempts
        self._client = None

    @property
    def name(self) -> str:
        return "kie_nano_banana"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=180.0,
            )
        return self._client

    def is_available(self) -> bool:
        return self._api_key is not None

    def _aspect_ratio_hint(self, width: int, height: int) -> str:
        ratio = width / height
        if ratio > 1.5:
            return "wide landscape format (16:9)"
        if ratio > 1.2:
            return "landscape format (3:2)"
        if ratio < 0.67:
            return "tall portrait format (9:16)"
        if ratio < 0.83:
            return "portrait format (2:3)"
        return "square format (1:1)"

    def _kie_image_size(self, width: int, height: int) -> str:
        ratio = width / height
        if ratio > 1.5:
            return "16:9"
        if ratio > 1.2:
            return "3:2"
        if ratio < 0.67:
            return "9:16"
        if ratio < 0.83:
            return "2:3"
        return "1:1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
    ) -> Image.Image:
        client = self._get_client()

        aspect_hint = self._aspect_ratio_hint(width, height)
        full_prompt = f"{prompt}\n\nGenerate this as a {aspect_hint} image."
        if negative_prompt:
            full_prompt += f"\n\nAvoid: {negative_prompt}"

        payload = {
            "model": self._model,
            "input": {
                "prompt": full_prompt[:5000],
                "output_format": "png",
                "image_size": self._kie_image_size(width, height),
            },
        }
        if seed is not None:
            payload["input"]["seed"] = seed

        create_response = await client.post("/api/v1/jobs/createTask", json=payload)
        create_response.raise_for_status()
        task_payload = create_response.json()
        if task_payload.get("code") not in {None, 200}:
            raise ValueError(f"KIE createTask failed: {task_payload}")

        task_data = self._unwrap_data(task_payload)
        task_id = (
            task_data.get("taskId")
            or task_data.get("task_id")
            or task_data.get("id")
            or task_payload.get("taskId")
        )
        if not task_id:
            raise ValueError(f"KIE createTask response missing taskId: {task_payload}")

        logger.debug("KIE task created", model=self._model, task_id=task_id)

        record = await self._poll_until_done(task_id)
        urls = self._extract_result_urls(record)
        if not urls:
            raise ValueError(f"KIE task {task_id} finished without image URLs: {record}")

        image_response = await client.get(urls[0], timeout=180.0)
        image_response.raise_for_status()
        return Image.open(BytesIO(image_response.content))

    async def _poll_until_done(self, task_id: str) -> dict:
        client = self._get_client()

        for _ in range(self._max_poll_attempts):
            response = await client.get("/api/v1/jobs/recordInfo", params={"taskId": task_id})
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in {None, 200}:
                raise ValueError(f"KIE recordInfo failed: {payload}")
            data = self._unwrap_data(payload)

            urls = self._extract_result_urls(data)
            if urls:
                return data

            status = str(data.get("status", "")).lower()
            if any(token in status for token in ("fail", "error", "cancel")):
                raise ValueError(f"KIE task {task_id} failed with status: {status}")

            await asyncio.sleep(self._poll_interval_seconds)

        raise TimeoutError(
            f"KIE task {task_id} did not finish after "
            f"{self._max_poll_attempts * self._poll_interval_seconds:.0f}s"
        )

    def _unwrap_data(self, payload: dict) -> dict:
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    def _extract_result_urls(self, payload: dict) -> list[str]:
        result_json = payload.get("resultJson") or payload.get("result_json") or payload.get("result")
        parsed: dict = {}

        if isinstance(result_json, str):
            try:
                parsed = json.loads(result_json)
            except json.JSONDecodeError:
                parsed = {}
        elif isinstance(result_json, dict):
            parsed = result_json

        urls: list[str] = []
        for source in (parsed, payload):
            for key in ("resultUrls", "result_urls", "urls", "image_urls", "images"):
                value = source.get(key) if isinstance(source, dict) else None
                if not isinstance(value, list):
                    continue
                for item in value:
                    if isinstance(item, str) and item.startswith("http"):
                        urls.append(item)
                    elif isinstance(item, dict):
                        maybe_url = item.get("url") or item.get("image_url") or item.get("imageUrl")
                        if isinstance(maybe_url, str) and maybe_url.startswith("http"):
                            urls.append(maybe_url)
        return urls
