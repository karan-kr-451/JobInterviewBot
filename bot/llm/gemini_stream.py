"""
llm.gemini_stream - Gemini REST SSE streaming.
"""

import sys
import time
import json as _json

import requests as _req
from core.http_utils import gc_safe_http, close_response_safely, create_fresh_session

from config.gemini import GEMINI_API_KEY
from config.llm import RETRY_BASE_DELAY

try:
    from audio.watchdog import reset_watchdog_timer as _reset_watchdog
except ImportError:
    def _reset_watchdog(): pass

GEMINI_REST_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def call_gemini_streaming(model_name: str, prompt: str, gen_config: dict,
                          overlay=None) -> str:
    """
    Stream Gemini response via raw REST + SSE.
    Raises on HTTP error or connection failure - never calls os._exit().
    
    CRITICAL: Entire function wrapped with GC protection because response
    streaming happens after the POST request completes.
    """
    with gc_safe_http():
        # Create fresh session to avoid thread-safety issues
        session = create_fresh_session()
        
        url = f"{GEMINI_REST_BASE}/{model_name}:streamGenerateContent"
        params = {"alt": "sse", "key": GEMINI_API_KEY}
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature":     gen_config.get("temperature", 0.4),
                "topP":            gen_config.get("top_p", 0.9),
                "maxOutputTokens": gen_config.get("max_output_tokens", 400),
            },
        }

        resp = None
        try:
            resp = session.post(url, params=params, json=body, stream=True, timeout=(10, 120))
        except _req.exceptions.ConnectionError as e:
            raise RuntimeError(f"Gemini unreachable: {e}")
        except _req.exceptions.Timeout:
            raise RuntimeError("Gemini connection timed out")

    if resp.status_code == 429:
        raise Exception(f"429 quota exceeded for {model_name}")
    if resp.status_code == 404:
        raise Exception(f"404 model not found: {model_name}")
    if not resp.ok:
        raise Exception(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")

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
            if not data or data == "[DONE]":
                continue

            try:
                obj = _json.loads(data)
            except _json.JSONDecodeError:
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
                now = time.perf_counter()
                if now - t_last_wd > 2.0:
                    _reset_watchdog()
                    t_last_wd = now

            try:
                finish = obj["candidates"][0].get("finishReason", "")
                if finish and finish not in ("", "STOP", "MAX_TOKENS"):
                    if finish == "SAFETY":
                        print(f"\n[Gemini] Safety filter triggered")
                    break
            except (KeyError, IndexError):
                pass

    except Exception as e:
        print(f"\n[Gemini stream] {type(e).__name__}: {e}")
    finally:
        close_response_safely(resp)

    sys.stdout.write("\n")
    sys.stdout.flush()

    elapsed_ms = (time.perf_counter() - t_request) * 1000
    if token_count:
        tok_s = token_count / max(elapsed_ms / 1000, 0.001)
        print(f"[Gemini] {token_count} tokens in {elapsed_ms:.0f}ms ({tok_s:.1f} tok/s) [{model_name}]")

    # Don't drain audio queue - let VAD loop handle it naturally
    # Draining from multiple threads causes race conditions with C-level audio callback

    return "".join(full_text).strip()
