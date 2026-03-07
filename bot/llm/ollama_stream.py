"""
llm.ollama_stream - Local Ollama streaming backend.
"""

import sys
import time
import json as _json

import requests as _req
from core.http_utils import gc_safe_http, close_response_safely, create_fresh_session

from config.ollama import (
    OLLAMA_BASE_URL, OLLAMA_TEMPERATURE, OLLAMA_NUM_THREAD,
    OLLAMA_NUM_THREAD_BATCH, OLLAMA_KEEP_ALIVE, OLLAMA_REPEAT_PENALTY,
    get_ollama_num_predict, get_ollama_num_ctx,
)

try:
    from audio.watchdog import reset_watchdog_timer as _reset_watchdog
except ImportError:
    def _reset_watchdog(): pass


def call_ollama_streaming(model_name: str, prompt: str,
                          overlay=None,
                          category: str = "UNKNOWN") -> str:
    """
    Stream from local Ollama. Returns full response text.
    
    CRITICAL: Entire function wrapped with GC protection because response
    streaming happens after the POST request completes.
    """
    with gc_safe_http():
        # Create fresh session to avoid thread-safety issues
        session = create_fresh_session()
        
        _num_predict = get_ollama_num_predict(category)
        _num_ctx     = get_ollama_num_ctx(category)
        print(f"   tokens: {_num_predict}  ctx: {_num_ctx}")

        url     = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model":      model_name,
            "prompt":     prompt,
            "stream":     True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature":      OLLAMA_TEMPERATURE,
                "num_predict":      _num_predict,
                "num_thread":       OLLAMA_NUM_THREAD,
                "num_thread_batch": OLLAMA_NUM_THREAD_BATCH,
                "num_ctx":          _num_ctx,
                "repeat_penalty":   OLLAMA_REPEAT_PENALTY,
                "stop": [
                    "Interviewer:", "Human:", "\n\n\n", "\n\n",
                ],
            },
        }

        resp = None
        try:
            resp = session.post(url, json=payload, stream=True, timeout=(5, 120))
            resp.raise_for_status()
        except _req.exceptions.ConnectionError:
            raise RuntimeError(f"Ollama not running at {OLLAMA_BASE_URL}. Start with: ollama serve")
        except _req.exceptions.HTTPError:
            if resp and resp.status_code == 404:
                raise RuntimeError(f"Model '{model_name}' not found. Pull it: ollama pull {model_name}")
            raise

        full_text        = []
        _t_request       = time.perf_counter()
        _t_last_watchdog = time.perf_counter()
        _first_token     = True
        _token_count     = 0
        sys.stdout.write("Response: ")
        sys.stdout.flush()

        try:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    chunk = _json.loads(raw_line)
                except _json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    if _first_token:
                        _ttft = (time.perf_counter() - _t_request) * 1000
                        sys.stdout.write(f"[TTFT {_ttft:.0f}ms] ")
                        _first_token = False
                    full_text.append(token)
                    _token_count += 1
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    if overlay:
                        try: overlay.stream_token(token)
                        except Exception: pass
                    now = time.perf_counter()
                    if now - _t_last_watchdog > 2.0:
                        _reset_watchdog()
                        _t_last_watchdog = now
                if chunk.get("done"):
                    elapsed_ms = (time.perf_counter() - _t_request) * 1000
                    tok_s = _token_count / max(elapsed_ms / 1000, 0.001)
                    print(f"\n[Ollama] {_token_count} tokens in {elapsed_ms:.0f}ms ({tok_s:.1f} tok/s)")
                    break
        except Exception as e:
            print(f"\n[Ollama stream] {type(e).__name__}: {e}")
        finally:
            close_response_safely(resp)

        sys.stdout.write("\n")
        sys.stdout.flush()

        # Don't drain audio queue - let VAD loop handle it naturally
        # Draining from multiple threads causes race conditions with C-level audio callback

        return "".join(full_text).strip()
