"""
llm/llm_router.py - Intelligent LLM backend selection and response orchestration.

Routes interview questions to the best available backend:
  auto mode → Groq → Gemini (rotated) → Ollama
  explicit   → uses only the configured backend

Features:
  • Model rotation across Groq + Gemini enterprise models
  • Automatic fallback on rate limits or errors
  • Duplicate question detection
  • Q&A logging to interview_log.txt
  • Telegram notification dispatch
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional

from core.logger import get_logger
from core.state_manager import get_state
from core.watchdog import Watchdog
from llm.groq_client import GroqClient, RateLimitError
from llm.gemini_client import GeminiClient
from llm.ollama_client import OllamaClient, check_ollama
from llm.prompt_builder import build_prompt, classify_question

log = get_logger("llm.router")

# ── Duplicate detection ───────────────────────────────────────────────────────
_recent_questions: list[str] = []
_dup_lock = threading.Lock()


def _is_duplicate(question: str, window: int = 5) -> bool:
    """Return True if the same question was asked in the last `window` questions."""
    q_norm = re.sub(r"\s+", " ", question.lower().strip())
    with _dup_lock:
        for prev in _recent_questions[-window:]:
            if prev == q_norm:
                return True
        _recent_questions.append(q_norm)
        if len(_recent_questions) > 50:
            del _recent_questions[:-50]
    return False


class LLMRouter:
    """
    Routes questions to the best available LLM backend.

    Usage:
        router = LLMRouter(cfg, watchdog)
        router.configure()   # checks backend availability
        response = router.get_response(question, history, docs, overlay)
    """

    def __init__(self, llm_cfg, watchdog: Optional[Watchdog] = None,
                 log_file: str = "logs/interview_log.txt") -> None:
        self._cfg      = llm_cfg
        self._watchdog = watchdog
        self._log_file = log_file

        self._groq_ok   = False
        self._gemini_ok = False
        self._ollama_ok = False

        self._groq   = GroqClient(llm_cfg.groq.api_key,   watchdog=watchdog)
        self._gemini = GeminiClient(llm_cfg.gemini.api_key, watchdog=watchdog)
        self._ollama = OllamaClient(llm_cfg.ollama.base_url, watchdog=watchdog)

        self._request_count = 0

    # ── Configuration ─────────────────────────────────────────────────────────

    def configure(self) -> bool:
        """Probe all configured backends. Returns True if at least one is ready."""
        from llm.groq_client import check_groq as _check_groq

        backend = self._cfg.backend

        if backend in ("groq", "auto"):
            self._groq_ok = _check_groq(self._cfg.groq.api_key)

        if backend in ("gemini", "auto"):
            if self._cfg.gemini.api_key:
                self._gemini_ok = True
                log.info("[OK] Gemini API key configured")
            else:
                log.warning("GEMINI_API_KEY not set – Gemini disabled")

        if backend in ("ollama", "auto"):
            self._ollama_ok = check_ollama(
                self._cfg.ollama.base_url, self._cfg.ollama.model
            )

        any_ok = self._groq_ok or self._gemini_ok or self._ollama_ok
        if not any_ok:
            log.warning("No LLM backend available – check API keys / Ollama status")
        return any_ok

    # ── Main API ──────────────────────────────────────────────────────────────

    def get_response(
        self,
        question: str,
        history: list,
        history_lock: threading.Lock,
        docs: dict,
        overlay=None,
        notifier=None,
    ) -> str:
        """
        Generate an AI response for the given interview question.

        Returns the response string (may be empty on failure).
        """
        if _is_duplicate(question):
            log.warning("Duplicate question skipped: '%s'", question[:60])
            return ""

        domain, category = classify_question(question)
        log.info("Question [%s | %s]: %s", domain, category, question[:80])

        if overlay:
            try:
                overlay.set_question(f"[{domain} | {category}]\n{question}")
            except Exception:
                pass

        with history_lock:
            history_snapshot = list(history[-10:])

        # Fetch RAG context
        rag_context = ""
        try:
            from rag.context_builder import ContextBuilder
            rag_context = ContextBuilder.instance().get_context(question)
        except Exception as exc:
            log.debug("RAG context unavailable: %s", exc)

        prompt = build_prompt(question, domain, category, history_snapshot, docs, rag_context)

        get_state().update(is_generating=True, last_question=question)
        if self._watchdog:
            self._watchdog.set_llm_active(True)

        response = self._route(prompt, domain, category, overlay)

        get_state().update(is_generating=False)
        if self._watchdog:
            self._watchdog.set_llm_active(False)

        if not response:
            return ""

        # Finalise overlay
        if overlay:
            try:
                overlay.finalize()
            except Exception:
                pass

        # Update conversation history
        with history_lock:
            history.extend([question, response])
            if len(history) > 20:
                del history[:-20]

        # Log to file
        self._log_qa(question, response, domain, category)

        # Telegram (async, non-blocking)
        if notifier:
            try:
                notifier.send_async(question, response)
            except Exception:
                pass

        log.info("Response [%s | %s]: %s…", domain, category, response[:80])
        return response

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route(self, prompt: str, domain: str, category: str, overlay) -> str:
        backend = self._cfg.backend

        # Explicit Ollama
        if backend == "ollama":
            return self._call_ollama(prompt, overlay)

        # Build ordered candidate list for rotation
        all_models: list[tuple[str, str]] = []

        if self._groq_ok and backend != "gemini":
            for m in self._cfg.groq.enterprise_models:
                all_models.append(("groq", m))

        if self._gemini_ok and backend != "groq":
            gem_list = [self._cfg.gemini.model] + self._cfg.gemini.fallbacks
            for m in gem_list:
                all_models.append(("gemini", m))

        if not all_models:
            if self._ollama_ok:
                return self._call_ollama(prompt, overlay)
            return "No LLM backend available – check API keys."

        self._request_count += 1
        idx = self._request_count % len(all_models)
        sel_backend, sel_model = all_models[idx]

        log.info("Routing to %s/%s (rotation %d/%d)",
                 sel_backend, sel_model, self._request_count, len(all_models))

        try:
            return self._call_backend(sel_backend, sel_model, prompt,
                                       domain, category, overlay)
        except RateLimitError as exc:
            log.warning("%s rate limited – trying fallback: %s", sel_model, exc)
            # Try next in list
            fallback_idx = (idx + 1) % len(all_models)
            fb_backend, fb_model = all_models[fallback_idx]
            try:
                return self._call_backend(fb_backend, fb_model, prompt,
                                           domain, category, overlay)
            except Exception as exc2:
                log.error("Fallback %s/%s also failed: %s", fb_backend, fb_model, exc2)
                return "All models temporarily unavailable – please try again."
        except Exception as exc:
            log.error("LLM call failed (%s/%s): %s", sel_backend, sel_model, exc)
            return "Technical issue – could you repeat that?"

    def _call_backend(self, backend: str, model: str, prompt: str,
                      domain: str, category: str, overlay) -> str:
        if backend == "groq":
            cfg    = self._cfg.groq
            tokens = self._get_groq_max_tokens(domain)
            return self._groq.call(
                model, prompt, overlay,
                max_tokens=tokens, temperature=cfg.temperature,
            )
        else:  # gemini
            gen_cfgs = self._cfg.gemini.generation_configs
            gen_cfg  = gen_cfgs.get(category, gen_cfgs.get("UNKNOWN", {}))
            return self._gemini.call(model, prompt, gen_cfg, overlay)

    def _call_ollama(self, prompt: str, overlay) -> str:
        try:
            return self._ollama.call(self._cfg.ollama.model, prompt, overlay)
        except RuntimeError as exc:
            return f"Local model unavailable: {exc}"

    @staticmethod
    def _get_groq_max_tokens(domain: str) -> int:
        limits = {
            "CODING":         600,
            "SYSTEM_DESIGN":  700,
            "CONCEPT":        300,
            "BEHAVIORAL":     300,
            "PROJECT":        400,
        }
        return limits.get(domain, 400)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_qa(self, question: str, response: str, domain: str, category: str) -> None:
        """Append a Q&A pair to the interview log."""
        try:
            import os
            from pathlib import Path
            # Resolve log file relative to the antigravity root
            base = Path(__file__).resolve().parent.parent
            log_path = base / self._log_file
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", errors="replace") as f:
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(
                    f"\n[{stamp}] [{domain} | {category}]\n"
                    f"Q: {question}\n"
                    f"A: {response}\n"
                    f"{'-'*60}\n"
                )
        except Exception as exc:
            log.debug("Log write failed: %s", exc)
