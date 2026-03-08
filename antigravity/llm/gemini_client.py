"""
llm/gemini_client.py - Gemini REST SSE streaming client.

Streams responses from Google's Gemini API using raw SSE without
requiring the google-generativeai SDK (REST-only for reliability).
GC-safe HTTP prevents access-violation crashes during streaming.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import requests

from core.logger import get_logger
from core.watchdog import Watchdog
from utils.crash_guard import gc_safe_http, create_fresh_session, close_response_safely

log = get_logger("llm.gemini")

GEMINI_REST_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    """
    Streams a Gemini response via REST + SSE.
    Raises RuntimeError on connection/HTTP failure.
    Never calls os._exit().
    """

    def __init__(self, api_key: str, watchdog: Optional[Watchdog] = None) -> None:
        self._api_key  = api_key
        self._watchdog = watchdog

    def call(self, model_name: str, prompt: str,
             gen_config: dict, overlay=None) -> str:
        """
        Stream a response from Gemini.

        Args:
            model_name:  e.g. "gemini-2.0-flash"
            prompt:      Full prompt string.
            gen_config:  dict with temperature, top_p, max_output_tokens.
            overlay:     Optional overlay to stream tokens into.

        Returns:
            Full response string (may be empty on failure).
        """
        url    = f"{GEMINI_REST_BASE}/{model_name}:streamGenerateContent"
        params = {"alt": "sse", "key": self._api_key}
        body   = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature":     gen_config.get("temperature", 0.4),
                "topP":            gen_config.get("top_p", 0.9),
                "maxOutputTokens": gen_config.get("max_output_tokens", 400),
            },
        }

        resp = None
        try:
            with gc_safe_http():
                session = create_fresh_session()
                try:
                    resp = session.post(
                        url, params=params, json=body,
                        stream=True, timeout=(10, 120),
                    )
                except requests.exceptions.ConnectionError as exc:
                    raise RuntimeError(f"Gemini unreachable: {exc}")
                except requests.exceptions.Timeout:
                    raise RuntimeError("Gemini connection timed out")

        except RuntimeError:
            raise

        # HTTP error handling (outside gc_safe_http so we can raise cleanly)
        if resp.status_code == 429:
            close_response_safely(resp)
            raise RuntimeError(f"Gemini 429 quota exceeded for {model_name}")
        if resp.status_code == 404:
            close_response_safely(resp)
            raise RuntimeError(f"Gemini 404 model not found: {model_name}")
        if not resp.ok:
            body_text = resp.text[:200]
            close_response_safely(resp)
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {body_text}")

        return self._stream(resp, model_name, overlay)

    def _stream(self, resp, model_name: str, overlay) -> str:
        """Read SSE stream, push tokens to overlay, return full text."""
        full_text: list[str] = []
        first_token  = True
        token_count  = 0
        t_request    = time.perf_counter()
        t_last_wd    = t_request

        sys.stdout.write("Response: ")
        sys.stdout.flush()

        try:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if not data or data == "[DONE]":
                    continue

                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                try:
                    token = obj["candidates"][0]["content"]["parts"][0].get("text", "")
                except (KeyError, IndexError):
                    token = ""

                if token:
                    if first_token:
                        ttft = (time.perf_counter() - t_request) * 1000
                        sys.stdout.write(f"[TTFT {ttft:.0f}ms] ")
                        first_token = False
                    full_text.append(token)
                    token_count += 1
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    if overlay:
                        try:
                            overlay.stream_token(token)
                        except Exception:
                            pass

                # Reset watchdog every 2 s during streaming
                now = time.perf_counter()
                if now - t_last_wd > 2.0:
                    if self._watchdog:
                        self._watchdog.reset_llm()
                    t_last_wd = now

                try:
                    finish = obj["candidates"][0].get("finishReason", "")
                    if finish and finish not in ("", "STOP", "MAX_TOKENS"):
                        if finish == "SAFETY":
                            log.warning("Gemini: Safety filter triggered")
                        break
                except (KeyError, IndexError):
                    pass

        except Exception as exc:
            log.warning("Gemini stream interrupted: %s", exc)
        finally:
            close_response_safely(resp)

        sys.stdout.write("\n")
        sys.stdout.flush()

        elapsed = (time.perf_counter() - t_request) * 1000
        if token_count:
            tok_s = token_count / max(elapsed / 1000, 0.001)
            log.info("Gemini %s: %d tokens in %.0f ms (%.1f tok/s)",
                     model_name, token_count, elapsed, tok_s)

        return "".join(full_text).strip()
