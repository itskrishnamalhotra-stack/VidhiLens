from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import Settings


@dataclass(slots=True)
class Generation:
    text: str
    seconds: float
    completion_tokens: int


class InferenceClient(Protocol):
    async def chat(
        self, messages: list[dict[str, str]], max_tokens: int,
        use_lora: bool, response_format: dict[str, Any] | None = None,
    ) -> Generation: ...

    async def health(self) -> dict[str, Any]: ...


class VLLMClient:
    """OpenAI-compatible client for the persistent local or remote vLLM server."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.vllm_api_key}"}

    async def chat(
        self, messages: list[dict[str, str]], max_tokens: int,
        use_lora: bool, response_format: dict[str, Any] | None = None,
    ) -> Generation:
        payload: dict[str, Any] = {
            "model": self.settings.lora_model_name if use_lora else self.settings.base_model_name,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.vllm_base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        return Generation(
            text=body["choices"][0]["message"]["content"].strip(),
            seconds=time.perf_counter() - started,
            completion_tokens=int(body.get("usage", {}).get("completion_tokens") or 0),
        )

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.settings.vllm_base_url}/models", headers=self.headers)
                response.raise_for_status()
                models = sorted(item.get("id") for item in response.json().get("data", []))
            required = {self.settings.base_model_name, self.settings.lora_model_name}
            return {"ready": required.issubset(models), "models": models}
        except Exception as error:
            return {"ready": False, "error": type(error).__name__}

