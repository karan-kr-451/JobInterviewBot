"""
llm/groq_client.py - Groq cloud inference streaming client.

Groq's free tier delivers 500+ tok/s on LLaMA 3.x – faster than Gemini
streaming and faster than local Ollama on CPU.

Features:
  • Circuit-breaker friendly: raises RateLimitError on HTTP 429
  • GC-safe HTTP: protects against tqdm/GC access violations
  • Structured retry headers: parses x-ratelimit-reset-tokens
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Optional

import requests

from core.logger import get_logger
from core.watchdog import Watchdog
from utils.crash_guard import gc_safe_http, create_fresh_session, close_response_safely

log = get_logger("llm.groq")

GROQ_BASE_URL  = "https://api.groq.com/openai/v1/chat/completions"
GROQ_AVAILABLE = False


class RateLimitError(Exception):
    """Raised when Groq returns HTTP 429. Carries retry_after (seconds)."""
    def __init__(self, msg: str, retry_after: float = 35.0) -> None:
        super().__init__(msg)
        self.retry_after = retry_after


def check_groq(api_key: str) -> bool:
    """Probe Groq API. Returns True if key is set and reachable."""
    global GROQ_AVAILABLE
    if not api_key:
        log.info("GROQ_API_KEY not set – Groq disabled")
        return False
    resp = None
    try:
        with gc_safe_http():
            s = create_fresh_session({"Authorization": f"Bearer {api_key}"})
            resp = s.get("https://api.groq.com/openai/v1/models", timeout=5)
            if resp.status_code == 200:
                models = [m["id"] for m in resp.json().get("data", [])]
                close_response_safely(resp); resp = None
                GROQ_AVAILABLE = True
                log.info("[OK] Groq available – %d model(s)", len(models))
                return True
            else:
                log.warning("Groq HTTP %d – check GROQ_API_KEY", resp.status_code)
                close_response_safely(resp); resp = None
                return False
    except requests.exceptions.ConnectionError:
        log.warning("Groq unreachable (no internet?)")
        return False
    except Exception as exc:
        log.warning("Groq check failed: %s", exc)
        return False
    finally:
        close_response_safely(resp)


def _parse_retry_after(headers: dict, body_text: str) -> float:
    """Extract retry delay from Groq rate-limit headers or error body."""
    if "retry-after" in headers:
        try:
            return float(headers["retry-after"]) + 1.0
        except ValueError:
            pass
    reset_tok = headers.get("x-ratelimit-reset-tokens", "")
    if reset_tok.endswith("s"):
        try:
            return float(reset_tok[:-1]) + 1.0
        except ValueError:
            pass
    m = re.search(r"retry in\s+([\d.]+)s", body_text, re.I)
    if m:
        return float(m.group(1)) + 1.0
    return 35.0


class GroqClient:
    """
    Streams a chat completion from Groq.
    Raises RateLimitError on 429, RuntimeError on other failures.
    """

    def __init__(self, api_key: str, watchdog: Optional[Watchdog] = None) -> None:
        self._api_key  = api_key
        self._watchdog = watchdog

    def call(self, model_name: str, prompt: str, overlay=None,
             max_tokens: int = 512, temperature: float = 0.3) -> str:
        """Stream a Groq completion and return the full response string."""
        resp = None
        try:
            with gc_safe_http():
                session = create_fresh_session({
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type":  "application/json",
                })
                payload = {
                    "model":       model_name,
                    "messages":    [{"role": "user", "content": prompt}],
                    "stream":      True,
                    "max_tokens":  max_tokens,
                    "temperature": temperature,
                    "stop":        ["Interviewer:", "Human:", "\n\n\n"],
                }
                try:
                    resp = session.post(
                        GROQ_BASE_URL, json=payload,
                        stream=True, timeout=(8, 120),
                    )
                except requests.exceptions.ConnectionError as exc:
                    raise RuntimeError(f"Groq unreachable: {exc}")
                except requests.exceptions.Timeout:
                    raise RuntimeError("Groq connection timed out")

                if resp.status_code == 429:
                    wait = _parse_retry_after(resp.headers, resp.text)
                    raise RateLimitError(f"Groq 429 – retry after {wait:.0f}s",
                                         retry_after=wait)
                if resp.status_code == 401:
                    raise RuntimeError("Groq 401 – invalid API key")
                if resp.status_code == 404:
                    raise RuntimeError(f"Groq 404 – model '{model_name}' not found")
                if not resp.ok:
                    raise RuntimeError(f"Groq HTTP {resp.status_code}: {resp.text[:200]}")

                result = self._stream(resp, model_name, overlay)
                resp = None   # ownership transferred to _stream (which closes it)
                return result

        finally:
            close_response_safely(resp)

    def _stream(self, resp, model_name: str, overlay) -> str:
        """Parse SSE stream and return full text."""
        full_text:  list[str] = []
        first_token = True
        token_count = 0
        t_request   = time.perf_counter()
        t_last_wd   = t_request

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
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                delta = obj.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")

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

                now = time.perf_counter()
                if now - t_last_wd > 2.0:
                    if self._watchdog:
                        self._watchdog.reset_llm()
                    t_last_wd = now

                finish = obj.get("choices", [{}])[0].get("finish_reason")
                if finish and finish != "null":
                    break

        except Exception as exc:
            log.warning("Groq stream interrupted: %s", exc)
        finally:
            close_response_safely(resp)

        sys.stdout.write("\n")
        sys.stdout.flush()

        elapsed = (time.perf_counter() - t_request) * 1000
        if token_count:
            tok_s = token_count / max(elapsed / 1000, 0.001)
            log.info("Groq %s: %d tokens in %.0f ms (%.1f tok/s)",
                     model_name, token_count, elapsed, tok_s)

        return "".join(full_text).strip()
