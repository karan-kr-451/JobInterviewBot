"""
llm/gemini_client.py — Gemini 2.0 Flash client.

Uses google-generativeai SDK. Strict timeouts enforced.
"""

from __future__ import annotations

import logging
from typing import Generator

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model_name = model
        self._model = None
        self._initialized = False

    def _init(self) -> None:
        if self._initialized:
            return
            
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        
        self._model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=1024,
            )
        )
        self._initialized = True

    def complete_stream(self, prompt: str, system: str = "", override_model: str = "", temperature: float = 0.45, max_tokens: int = 400) -> Generator[str, Any, None]:
        """Stream completion from Gemini."""
        if not self.api_key:
            yield "⚠️ Gemini API key missing."
            return

        try:
            self._init()
        except Exception as e:
            logger.error("[GEMINI_CLIENT] Failed to initialize: %s", e)
            raise

        combined_prompt = f"{system}\n\n{prompt}" if system else prompt

        # If a different model is requested, instantiate a temporary model object for this request
        target_model = self._model
        if override_model and override_model != self.model_name:
            import google.generativeai as genai
            target_model = genai.GenerativeModel(
                model_name=override_model,
                generation_config=genai.GenerationConfig(
                    temperature=temperature, # Use the provided temperature for override model
                    max_output_tokens=max_tokens, # Use the provided max_tokens for override model
                )
            )
        
        from google.generativeai.types import GenerationConfig
        gen_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            top_p=0.9
        )

        try:
            # We apply a strict timeout context if needed, but the SDK handles some.
            # For robust timeout against the SDK hanging, we rely on the watchdog
            response = target_model.generate_content(
                combined_prompt,
                stream=True,
                generation_config=gen_config
            )
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                u = response.usage_metadata
                yield {
                    "_type": "usage", 
                    "input": u.prompt_token_count, 
                    "output": u.candidates_token_count, 
                    "model": override_model or self.model_name
                }
                    
        except Exception as e:
            logger.warning("[GEMINI_CLIENT] Inference failed: %s", e)
            raise
