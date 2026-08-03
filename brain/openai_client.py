"""
OpenAI-compatible chat client.

Works with any provider that exposes an OpenAI-style ``/chat/completions``
endpoint: OpenAI, Groq, Together, DeepSeek, Moonshot, OpenRouter, local
servers (vLLM, Ollama's OpenAI endpoint), etc. Only the base URL, model name,
and API key need to be configured.
"""

import json
import os
from pathlib import Path
from typing import Generator, Optional, Union

import httpx


class OpenAIClient:
    """Client for any OpenAI-compatible chat completions API."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        soul_path: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("CLOUD_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI-compatible API key required (set CLOUD_API_KEY or pass api_key)"
            )

        self.model = model or os.getenv("CLOUD_MODEL")
        if not self.model:
            raise ValueError(
                "OpenAI-compatible model name required (set CLOUD_MODEL or pass model)"
            )

        self.base_url = (
            base_url or os.getenv("CLOUD_BASE_URL") or self.DEFAULT_BASE_URL
        ).rstrip("/")

        self.client = httpx.Client(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        # Load cloud soul/personality prompt, if present.
        self.soul_prompt = ""
        if soul_path and Path(soul_path).exists():
            self.soul_prompt = Path(soul_path).read_text()

    def chat(
        self,
        query: str,
        stream: bool = True,
    ) -> Union[Generator[str, None, None], str]:
        """Send a query to the configured model via /chat/completions."""
        messages = []
        if self.soul_prompt:
            messages.append({"role": "system", "content": self.soul_prompt})
        messages.append({"role": "user", "content": query})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": stream,
        }

        if stream:
            return self._stream_chat(payload)

        response = self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _stream_chat(self, payload: dict) -> Generator[str, None, None]:
        """Stream a chat response (OpenAI SSE ``data:`` lines)."""
        with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
        ) as response:
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if "content" in delta and delta["content"] is not None:
                        yield delta["content"]
                except json.JSONDecodeError:
                    continue