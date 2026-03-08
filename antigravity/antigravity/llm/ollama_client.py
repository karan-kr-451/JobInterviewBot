"""
llm/ollama_client.py — Local LLaMA client via Ollama.

Uses the ollama python SDK (pip install ollama==0.3.3)
"""

from __future__ import annotations

import logging
from typing import Generator

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, model: str = "llama3.2") -> None:
        self.model = model

    def complete_stream(self, prompt: str, system: str = "", override_model: str = "", temperature: float = 0.3, max_tokens: int = 512) -> Generator[str, Any, None]:
        """Stream an answer token by token via local Ollama instance."""
        try:
            import ollama
        except ImportError:
            logger.error("[OLLAMA_CLIENT] ollama library not installed")
            yield "⚠️ Local Ollama python SDK not found."
            return

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            run_model = override_model if override_model else self.model
            
            stream = ollama.chat(
                model=run_model,
                messages=messages,
                stream=True,
                options={"temperature": temperature, "num_predict": max_tokens}
            )

            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    if content:
                        yield content
        except Exception as e:
            logger.warning("[OLLAMA_CLIENT] Inference failed (is Ollama running?): %s", e)
            raise
