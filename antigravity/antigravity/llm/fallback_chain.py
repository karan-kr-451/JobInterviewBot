"""
llm/fallback_chain.py — LLM routing with Circuit Breaker pattern.

Handles automatic failover (e.g. Groq -> Gemini -> Ollama) dynamically.
If a provider fails, its circuit trips for 60 seconds to prevent
repeatedly waiting for timeouts on a completely dead backend.
"""

from __future__ import annotations

import logging
import time
from typing import Generator

from antigravity.utils.config_loader import LLMConfig
from antigravity.core.event_bus import EVT_BACKEND_SWITCHED, bus

logger = logging.getLogger(__name__)

# Legacy mapping for dynamic Groq model scaling and parameters
GROQ_MODELS = {
    "CODING":               "llama-3.3-70b-versatile",
    "SYSTEM_DESIGN":        "llama-3.3-70b-versatile",
    "SOFTWARE_ENGINEERING": "llama-3.3-70b-versatile",
    "PROJECT":              "llama-3.3-70b-versatile",
    "BEHAVIORAL":           "llama-3.3-70b-versatile",
    "CONCEPT":              "llama-3.1-8b-instant",
    "MACHINE_LEARNING":     "llama-3.1-8b-instant",
    "DEEP_LEARNING":        "llama-3.1-8b-instant",
    "NLP":                  "llama-3.1-8b-instant",
    "COMPUTER_VISION":      "llama-3.1-8b-instant",
    "MLOPS":                "llama-3.1-8b-instant",
    "DATA_ENGINEERING":     "llama-3.1-8b-instant",
    "DEVOPS":               "llama-3.1-8b-instant",
    "GENERAL":              "llama-3.1-8b-instant",
    "UNKNOWN":              "llama-3.1-8b-instant",
}

# Legacy category parameters ported from bot/config
LEGACY_PARAMS = {
    "CODING":       {"temp": 0.15, "max_tokens": 400},
    "SYSTEM_DESIGN":{"temp": 0.30, "max_tokens": 350},
    "CONCEPT":      {"temp": 0.30, "max_tokens": 200},
    "PROJECT":      {"temp": 0.55, "max_tokens": 250},
    "BEHAVIORAL":   {"temp": 0.70, "max_tokens": 250},
    "GENERAL":      {"temp": 0.45, "max_tokens": 200},
    "UNKNOWN":      {"temp": 0.45, "max_tokens": 200},
}


class CircuitBreaker:
    def __init__(self, reset_timeout: float = 60.0):
        self._fails = 0
        self._reset_timeout = reset_timeout
        self._last_fail = 0.0

    def is_open(self) -> bool:
        """Return True if circuit is tripped and cooling down."""
        if self._fails > 0:
            if time.time() - self._last_fail > self._reset_timeout:
                self.record_success()  # Half-open, reset
                return False
            return True
        return False

    def record_failure(self) -> None:
        self._fails += 1
        self._last_fail = time.time()

    def record_success(self) -> None:
        self._fails = 0
        self._last_fail = 0.0


class FallbackChain:
    """
    Manages a prioritized list of LLM clients.
    If 'auto' backend is selected, will try Groq -> Gemini -> Ollama.
    """

    def __init__(self, config: LLMConfig, groq_key: str, gemini_key: str) -> None:
        self._backends = {}
        self._main_target = config.backend

        # Initialize available clients
        if groq_key:
            from antigravity.llm.groq_client import GroqClient
            self._backends["groq"] = (
                GroqClient(api_key=groq_key, model=config.groq_model, max_tokens=config.max_tokens),
                CircuitBreaker()
            )

        if gemini_key:
            from antigravity.llm.gemini_client import GeminiClient
            self._backends["gemini"] = (
                GeminiClient(api_key=gemini_key, model=config.gemini_model),
                CircuitBreaker()
            )

        from antigravity.llm.ollama_client import OllamaClient
        self._backends["ollama"] = (
            OllamaClient(model=config.ollama_model),
            CircuitBreaker()
        )

        self._order = ["groq", "gemini", "ollama"]
        self._request_count = 0

    def _get_rotated_targets(self) -> list[tuple[str, str]]:
        """
        Builds a list of all available (backend, model) pairs to rotate through.
        Matches legacy V3 rotation logic.
        """
        all_targets = []
        
        # 1. Add Groq models
        if "groq" in self._backends:
            # We use the enterprise models list from legacy config
            groq_models = [
                "llama-3.3-70b-versatile",
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "llama-3.1-8b-instant"
            ]
            for m in groq_models:
                all_targets.append(("groq", m))
                
        # 2. Add Gemini models
        if "gemini" in self._backends:
            gemini_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
            for m in gemini_models:
                all_targets.append(("gemini", m))
                
        return all_targets

    def complete_stream(self, prompt: str, system: str = "", domain: str = "GENERAL", category: str = "UNKNOWN") -> Generator[str, None, None]:
        """Try routing to the main backend, fallback horizontally on failure."""
        
        # 1. Determine the attempt sequence
        rotation_list = self._get_rotated_targets()
        attempts: list[tuple[str, str]] = [] # (backend_name, model_override)
        
        has_cloud_keys = any(k in self._backends for k in ["groq", "gemini"])

        if self._main_target != "auto" and self._main_target in self._backends:
            # Fixed backend mode: only try the selected one
            attempts.append((self._main_target, ""))
        elif rotation_list:
            # Auto mode with rotation: pick a starting (backend, model) pair
            self._request_count += 1
            start_idx = self._request_count % len(rotation_list)
            rotated_backend, rotated_model = rotation_list[start_idx]
            
            attempts.append((rotated_backend, rotated_model))
            
            # Fallback to other backends in the global order if the rotated one fails
            for b_name in self._order:
                if b_name != rotated_backend and b_name in self._backends:
                    # USER RULE: Don't use ollama if cloud keys are available
                    if b_name == "ollama" and has_cloud_keys:
                        continue
                    attempts.append((b_name, ""))
        else:
            # Fallback for when rotation is not possible
            for b_name in self._order:
                if b_name in self._backends:
                    # USER RULE: Don't use ollama if cloud keys are available
                    if b_name == "ollama" and has_cloud_keys:
                        continue
                    attempts.append((b_name, ""))

        # 2. Execute attempts
        for name, override in attempts:
            client, breaker = self._backends.get(name, (None, None))
            if not client or breaker.is_open():
                continue

            params = LEGACY_PARAMS.get(category, LEGACY_PARAMS.get(domain, LEGACY_PARAMS["UNKNOWN"]))
            
            # Resolve model override: use provided rotation model OR backend default logic
            final_override = override
            if not final_override:
                if name == "groq":
                    final_override = GROQ_MODELS.get(category, GROQ_MODELS.get(domain, "llama-3.1-8b-instant"))
                # Gemini and Ollama defaults are handled inside their respective clients
            
            # Ensure Gemini models have the correct prefix
            if name == "gemini" and final_override:
                if "/" not in final_override and not final_override.startswith("models/"):
                    final_override = f"models/{final_override}"

            logger.info("[FALLBACK] Attempting %s with model: %s", name, final_override or "default")

            try:
                # We yield from the inner generator
                yield from client.complete_stream(
                    prompt, 
                    system=system, 
                    override_model=final_override,
                    temperature=params["temp"],
                    max_tokens=params["max_tokens"]
                )
                
                # If we get here without exception, the stream was successful
                breaker.record_success()
                return  # Success, stop trying fallbacks
                
            except Exception as e:
                logger.warning("[FALLBACK] %s (%s) failed: %s", name, final_override, e)
                breaker.record_failure()
                # Notify UI of failure/switch
                bus.publish(EVT_BACKEND_SWITCHED, {"failed": name})
                
        # If we exhausted all options
        yield "⚠️ All AI backends temporarily unavailable. Please check your API keys or connection."

