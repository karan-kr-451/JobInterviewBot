"""
llm/ollama_client.py - Local Ollama streaming client.

Streams responses from a locally-running Ollama instance.
No API key required. Useful as a local fallback or privacy-first mode.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import requests

from core.logger import get_logger
from core.watchdog import Watchdog
from utils.crash_guard import create_fresh_session, close_response_safely

log = get_logger("llm.ollama")


def check_ollama(base_url: str, model: str) -> bool:
    """Return True if Ollama is running and has at least one model loaded."""
    try:
        s = create_fresh_session()
        r = s.get(f"{base_url}/api/tags", timeout=2)
        close_response_safely(r)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        if models:
            log.info("[OK] Ollama available – models: %s", ", ".join(models[:5]))
            if not any(model.split(":")[0] in m for m in models):
                log.warning("Required model '%s' not found. Run: ollama pull %s", model, model)
            return True
        log.info("Ollama running but no models. Run: ollama pull %s", model)
        return False
    except Exception as exc:
        log.info("Ollama not available: %s", type(exc).__name__)
        return False


class OllamaClient:
    """
    Streams a completion from Ollama's /api/generate endpoint.
    """

    def __init__(self, base_url: str, watchdog: Optional[Watchdog] = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._watchdog = watchdog

    def call(self, model_name: str, prompt: str, overlay=None) -> str:
        """Stream an Ollama response. Returns full text or raises RuntimeError."""
        url  = f"{self._base_url}/api/generate"
        body = {
            "model":  model_name,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0.3, "num_predict": 512},
        }

        resp = None
        try:
            s    = create_fresh_session()
            resp = s.post(url, json=body, stream=True, timeout=(5, 120))
            if not resp.ok:
                raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")

            return self._stream(resp, model_name, overlay)

        except requests.exceptions.ConnectionError:
            raise RuntimeError("Ollama unreachable – is 'ollama serve' running?")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Ollama error: {exc}") from exc
        finally:
            close_response_safely(resp)

    def _stream(self, resp, model_name: str, overlay) -> str:
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
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                token = obj.get("response", "")
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

                if obj.get("done"):
                    break

        except Exception as exc:
            log.warning("Ollama stream interrupted: %s", exc)
        finally:
            close_response_safely(resp)

        sys.stdout.write("\n")
        sys.stdout.flush()
        elapsed = (time.perf_counter() - t_request) * 1000
        if token_count:
            tok_s = token_count / max(elapsed / 1000, 0.001)
            log.info("Ollama %s: %d tokens in %.0f ms (%.1f tok/s)",
                     model_name, token_count, elapsed, tok_s)
        return "".join(full_text).strip()
