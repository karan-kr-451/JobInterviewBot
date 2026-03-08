"""
llm/groq_client.py — Fast LLaMA-based client via Groq.

Uses the groq Python SDK (pip install groq==0.9.0) with strict timeouts.
Streaming responses using generators.
"""

from __future__ import annotations

import logging
from typing import Generator

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile", max_tokens: int = 1024) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if not self._client:
            from groq import Groq
            # HTTP timeout configuration: 5s connect, 30s read
            self._client = Groq(api_key=self.api_key, timeout=30.0, max_retries=1)
        return self._client

    def complete_stream(self, prompt: str, system: str = "", override_model: str = "", temperature: float = 0.3, max_tokens: int = 0) -> Generator[str, Any, None]:
        """Stream an answer token by token."""
        if not self.api_key:
            yield "⚠️ Groq API key missing."
            return

        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        run_model = override_model if override_model else self.model
        run_max   = max_tokens if max_tokens > 0 else self.max_tokens

        try:
            # We remove stream_options as it may cause 'unexpected keyword argument' 
            # on some versions of the groq SDK.
            stream = client.chat.completions.create(
                messages=messages,
                model=run_model,
                temperature=temperature,
                max_tokens=run_max,
                stream=True
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                if hasattr(chunk, 'x_groq') and chunk.x_groq and hasattr(chunk.x_groq, 'usage') and chunk.x_groq.usage:
                    u = chunk.x_groq.usage
                    yield {"_type": "usage", "input": u.prompt_tokens, "output": u.completion_tokens, "model": run_model}
                    
        except Exception as e:
            logger.warning("[GROQ_CLIENT] Inference failed: %s", e)
            raise  # Allow FallbackChain to trigger
