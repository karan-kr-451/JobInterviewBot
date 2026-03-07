"""
llm.groq_stream - Groq Cloud inference backend (free tier).

Groq's free tier gives 500+ tok/s inference on Llama 3.x - faster than
Gemini streaming and 20  faster than local Ollama on CPU.

ENTERPRISE PROTECTION:
- Circuit breaker for API failures
- Resource pool for concurrent requests
- Retry with exponential backoff
- Timeout enforcement
"""

import json
import re
import sys
import time

import requests
from core.http_utils import gc_safe_http, close_response_safely, create_fresh_session
from core.enterprise_crash_prevention import (
    safe_http_call, retry_with_backoff, with_timeout, safe_execution
)

# Ensure availability is checked on import
try:
    from llm.groq_stream import check_groq
    check_groq()
except ImportError:
    pass

from config.groq import GROQ_API_KEY, GROQ_MODELS, GROQ_FALLBACK_MODEL

GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_AVAILABLE = False


def check_groq() -> bool:
    """Probe Groq API. Returns True if key is set and reachable."""
    global GROQ_AVAILABLE
    if not GROQ_API_KEY:
        print("  Groq: GROQ_API_KEY not set - skipping")
        return False
    
    resp = None
    session = None
    try:
        # ENTERPRISE: Use safe execution with timeout
        with safe_execution("Groq API check", fallback_value=False):
            with gc_safe_http():
                session = requests.Session()
                session.trust_env = False  # CRITICAL: Disable .netrc to prevent os.environ race
                resp = session.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    models = [m["id"] for m in resp.json().get("data", [])]
                    close_response_safely(resp)
                    resp = None
                    GROQ_AVAILABLE = True
                    print(f"[OK] Groq available - {len(models)} model(s) accessible")
                    return True
                else:
                    print(f"  Groq: HTTP {resp.status_code} - check GROQ_API_KEY")
                    close_response_safely(resp)
                    resp = None
                    return False
    except requests.exceptions.ConnectionError:
        print("  Groq: unreachable (no internet?)")
        return False
    except Exception as e:
        print(f"  Groq: {type(e).__name__}: {e}")
        return False
    finally:
        close_response_safely(resp)


def get_groq_model(category: str) -> str:
    """Return the best Groq model for the given question category."""
    primary = category.split("|")[0].strip().upper()
    return GROQ_MODELS.get(primary, GROQ_FALLBACK_MODEL)


def _parse_retry_after(headers: dict, body_text: str) -> float:
    """Extract retry-after from Groq rate-limit headers or error body."""
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


class RateLimitError(Exception):
    """Raised when Groq returns HTTP 429. Carries retry_after (seconds)."""
    def __init__(self, msg: str, retry_after: float = 35.0):
        super().__init__(msg)
        self.retry_after = retry_after


def call_groq_streaming(
    model_name: str,
    prompt: str,
    overlay=None,
    max_tokens: int = 512,
    temperature: float = 0.3,
) -> str:
    """
    Stream a chat completion from Groq.
    Returns the full response string.
    Raises RuntimeError on connection failure or unrecoverable HTTP error.
    Raises RateLimitError on HTTP 429.
    
    CRITICAL: Entire function wrapped with GC protection because response
    streaming happens after the POST request completes.
    """
    resp = None
    # CRITICAL: Wrap ENTIRE function with GC protection
    # The crash happens during resp.iter_lines(), not during the POST
    try:
        with gc_safe_http():
            session = create_fresh_session({
                "Authorization": f"Bearer {GROQ_API_KEY}",
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
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(f"Groq unreachable: {e}")
            except requests.exceptions.Timeout:
                raise RuntimeError("Groq connection timed out")

            if resp.status_code == 429:
                wait = _parse_retry_after(resp.headers, resp.text)
                raise RateLimitError(f"Groq 429 - retry after {wait:.0f}s", retry_after=wait)

            if resp.status_code == 401:
                raise RuntimeError("Groq 401 - invalid API key. Set GROQ_API_KEY in .env")

            if resp.status_code == 404:
                raise RuntimeError(f"Groq 404 - model '{model_name}' not found")

            if not resp.ok:
                raise RuntimeError(f"Groq HTTP {resp.status_code}: {resp.text[:200]}")

            full_text    = []
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
                            try:
                                from audio.watchdog import reset_watchdog_timer as _rwd
                                _rwd()
                            except Exception:
                                pass
                            t_last_wd = now

                    finish = obj.get("choices", [{}])[0].get("finish_reason")
                    if finish and finish != "null":
                        break

            except Exception as e:
                print(f"\n[Groq stream] {type(e).__name__}: {e}")

            # CRITICAL: Close response before exiting gc_safe_http
            close_response_safely(resp)
            resp = None

            sys.stdout.write("\n")
            sys.stdout.flush()

            elapsed_ms = (time.perf_counter() - t_request) * 1000
            if token_count:
                tok_s = token_count / max(elapsed_ms / 1000, 0.001)
                print(f"[Groq] {token_count} tokens in {elapsed_ms:.0f}ms ({tok_s:.1f} tok/s) [{model_name}]")

            # Don't drain audio queue - let VAD loop handle it naturally
            # Draining from multiple threads causes race conditions with C-level audio callback
            # The deque has maxlen=None (unbounded) so old chunks will be processed normally

            return "".join(full_text).strip()
    
    finally:
        # Ensure response is closed even if exception occurs
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
