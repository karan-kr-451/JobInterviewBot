"""
llm.ollama_warmup - Pre-loads the Ollama model into RAM before the first question.
"""

import threading
import time

import requests
from core.http_utils import gc_safe_http, close_response_safely

from config.ollama import (
    OLLAMA_BASE_URL, OLLAMA_SINGLE_MODEL, OLLAMA_NUM_CTX,
    OLLAMA_NUM_THREAD, OLLAMA_NUM_THREAD_BATCH, OLLAMA_KEEP_ALIVE,
)


def _do_warmup():
    """Send a minimal generation request to force Ollama to load the model into RAM."""
    resp = None
    session = None
    try:
        print(f"[Ollama warmup] Loading {OLLAMA_SINGLE_MODEL} into RAM...")
        t0 = time.perf_counter()
        with gc_safe_http():
            from core.http_utils import create_fresh_session
            session = create_fresh_session()
            resp = session.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_SINGLE_MODEL,
                    "prompt": "Hello",
                    "stream": False,
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": {
                        "num_predict": 1,
                        "num_thread": OLLAMA_NUM_THREAD,
                        "num_thread_batch": OLLAMA_NUM_THREAD_BATCH,
                        "num_ctx": OLLAMA_NUM_CTX,
                    },
                },
                timeout=120,
            )
            resp.raise_for_status()
            # CRITICAL: Close response before exiting gc_safe_http
            close_response_safely(resp)
            resp = None
        ms = (time.perf_counter() - t0) * 1000
        print(f"[Ollama warmup] [OK] Model warm in {ms:.0f}ms")
    except Exception as e:
        print(f"[Ollama warmup]   Failed: {e}")
    finally:
        close_response_safely(resp)


def warmup_ollama(block: bool = False):
    """
    Warm up the Ollama model. Non-blocking by default.
    """
    if block:
        _do_warmup()
    else:
        threading.Thread(
            target=_do_warmup, daemon=True, name="ollama-warmup"
        ).start()


def ping_ollama() -> bool:
    """Quick health check - returns True if Ollama is running and the model is loaded."""
    resp = None
    session = None
    try:
        with gc_safe_http():
            from core.http_utils import create_fresh_session
            session = create_fresh_session()
            resp = session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            models = [m["name"] for m in resp.json().get("models", [])]
            # CRITICAL: Close response before exiting gc_safe_http
            close_response_safely(resp)
            resp = None
        model_base = OLLAMA_SINGLE_MODEL.split(":")[0]
        return any(model_base in m for m in models)
    except Exception:
        return False
    finally:
        close_response_safely(resp)


def build_ollama_options() -> dict:
    """Returns the standard Ollama options dict to use in every API call."""
    return {
        "num_thread":       OLLAMA_NUM_THREAD,
        "num_thread_batch": OLLAMA_NUM_THREAD_BATCH,
        "num_ctx":          OLLAMA_NUM_CTX,
    }


def print_setup_guide():
    """Remind the user if Ollama vars aren't set."""
    print("\n" + "=" * 60)
    print("OLLAMA SETUP GUIDE")
    print("=" * 60)
    print(f"  1. Install Ollama: https://ollama.ai")
    print(f"  2. Pull model:     ollama pull {OLLAMA_SINGLE_MODEL}")
    print(f"  3. Start server:   ollama serve")
    print(f"  4. Set LLM_BACKEND=ollama in config or .env")
    print("=" * 60 + "\n")
