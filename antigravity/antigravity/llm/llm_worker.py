"""
llm/llm_worker.py — Processes transcripts into responses.

Pulls from transcript queue, filters out dupes, applies RAG context,
queries FallbackChain, and publishes the streaming response.
"""

from __future__ import annotations

import io
import logging
import queue
import time
from typing import Optional

from antigravity.core.app_state import get_app_state
from antigravity.core.base_worker import BaseWorker
from antigravity.core.event_bus import EVT_RESPONSE_READY, EVT_TOKEN_USAGE_READY, EVT_CLASSIFICATION_READY, bus
from antigravity.core.safe_lock import SafeLock
from antigravity.llm.response_cache import get_cached_response, set_cached_response
from antigravity.llm.prompt_builder import build_final_prompt

logger = logging.getLogger(__name__)


class LLMWorker(BaseWorker):
    """
    Reads from transcript_queue, calls FallbackChain, caches response,
    and publishes text fragments via EVT_RESPONSE_READY.
    """

    def __init__(
        self,
        transcript_queue: queue.Queue,
        fallback_chain,
        rag_retriever,
        system_prompt: str,
    ) -> None:
        super().__init__(name="LLMWorker", restart_delay=3.0)
        self._in_queue = transcript_queue
        self._chain = fallback_chain
        self._rag = rag_retriever
        self._system_prompt = system_prompt
        self._lock = SafeLock("LLMWorker", timeout=3.0)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._heartbeat()

            try:
                question = self._in_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Update AppState processing flag
            get_app_state().set_processing(True)
            
            try:
                self._process_question(question)
            except Exception as e:
                logger.error("[LLM] Uncaught error during generation: %s", e)
                bus.publish(EVT_RESPONSE_READY, f"⚠️ Error generating response: {e}")
            finally:
                get_app_state().set_processing(False)
                self._in_queue.task_done()

    def _process_question(self, question: str) -> None:
        # 1. Check response cache
        cached = get_cached_response(question)
        if cached:
            logger.info("[LLM] Providing cached response.")
            bus.publish(EVT_RESPONSE_READY, cached)
            # Re-update history so UI logic perfectly matches processing
            get_app_state().add_response(cached)
            return

        # 1.5 Classify the question dynamically using Groq (or fallback keywords)
        import os
        from antigravity.llm.classifier import classify_question
        domain, category = classify_question(question, groq_api_key=os.environ.get("GROQ_API_KEY", ""))
        logger.info("[LLM] Classified question as %s | %s", domain, category)
        bus.publish(EVT_CLASSIFICATION_READY, f"{domain} | {category}")

        # 2. Build Prompt (passes RAG retriever for metadata access)
        prompt = build_final_prompt(question, domain=domain, category=category, rag_retriever=self._rag)

        # 4. Stream response (holding string purely in StringIO to avoid O(n^2) copy overhead - Rule 9)
        buf = io.StringIO()
        logger.info("[LLM] Generating response...")
        
        try:
            stream = self._chain.complete_stream(
                prompt, 
                system=self._system_prompt,
                domain=domain,
                category=category
            )
            for chunk in stream:
                # Intercept exact token metrics yielded by LLM clients
                if isinstance(chunk, dict) and chunk.get("_type") == "usage":
                    bus.publish(EVT_TOKEN_USAGE_READY, chunk)
                    continue
                    
                if chunk:
                    buf.write(chunk)
                    # We broadcast full partial strings (some UIs append, some replace,
                    # here our UI logic will just expect the growing buffer)
                    bus.publish(EVT_RESPONSE_READY, buf.getvalue())
                    
                    # keep watchdog happy during long streams
                    self._heartbeat()
                    
                    if self._stop_event.is_set():
                        logger.debug("[LLM] Shutdown requested mid-stream. Aborting.")
                        return
                    
            full_response = buf.getvalue().strip()
            if full_response:
                # 5. Save and cache the final result
                get_app_state().add_response(full_response)
                set_cached_response(question, full_response)
                logger.debug("[LLM] Generation complete (%d chars)", len(full_response))
            else:
                logger.warning("[LLM] Empty response generated.")
                bus.publish(EVT_RESPONSE_READY, "⚠️ Warning: LLM returned empty response.")
                
        except Exception as e:
            raise e
        finally:
            buf.close()
