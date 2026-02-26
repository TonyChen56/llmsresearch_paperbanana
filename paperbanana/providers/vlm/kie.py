"""KIE VLM provider — OpenAI-compatible chat API for Gemini 2.5 Flash."""

from __future__ import annotations

from typing import Optional

import structlog
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential

from paperbanana.core.utils import image_to_base64
from paperbanana.providers.base import VLMProvider

logger = structlog.get_logger()


class KieVLM(VLMProvider):
    """VLM provider using KIE's OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://api.kie.ai",
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = None

    @property
    def name(self) -> str:
        return "kie"

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
                timeout=120.0,
            )
        return self._client

    def is_available(self) -> bool:
        return self._api_key is not None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def generate(
        self,
        prompt: str,
        images: Optional[list[Image.Image]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> str:
        client = self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        content = []
        if images:
            for img in images:
                b64 = image_to_base64(img)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
        content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": content})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        response = await client.post(f"/{self._model}/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        content_value = data["choices"][0]["message"]["content"]
        if isinstance(content_value, list):
            text_parts: list[str] = []
            for part in content_value:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                else:
                    text_parts.append(str(part))
            text = "".join(text_parts)
        else:
            text = str(content_value)

        logger.debug("KIE response", model=self._model, usage=data.get("usage"))
        return text
