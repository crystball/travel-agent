from __future__ import annotations

import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


class DeepSeekClient:
    """Minimal DeepSeek chat-completions client with JSON-mode support."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip(
            "/"
        )
        self.model = model or os.getenv("LLM_MODEL") or "deepseek-chat"
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("DeepSeek API key is not configured.")

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"].get("content") or ""
        if not content.strip():
            raise ValueError("DeepSeek returned empty JSON content.")
        return json.loads(content)

