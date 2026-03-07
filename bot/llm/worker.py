"""
llm.worker - LLM worker thread that drains the transcription queue.
"""

import time
import queue
import threading

from llm.router import get_interview_response

try:
    from audio.watchdog import reset_watchdog_timer as _reset_watchdog
except ImportError:
    def _reset_watchdog(): pass


def make_llm_worker(history: list, history_lock: threading.Lock,
                    docs: dict, notifier, overlay=None):
    """
    Create and return (but don't start) the LLM worker thread.
    Drains gemini_queue. Each payload is {"text": "..."}.
    """
    from transcription.worker import gemini_queue

    def _worker_body():
        while True:
            try:
                payload = gemini_queue.get(timeout=2)
            except queue.Empty:
                continue

            try:
                if payload is None:
                    return   # shutdown signal

                if isinstance(payload, str):
                    payload = {"text": payload}

                question = payload["text"]

                # PING health checker
                try:
                    from core.enterprise_crash_prevention import health_checker
                    health_checker.ping("llm")
                except:
                    pass

                # LLM call - HTTP protection is handled internally by groq_stream.py
                # Do NOT wrap with gc_safe_http() here to avoid holding the global lock
                # for the entire LLM response streaming duration (causes deadlocks)
                t0       = time.perf_counter()
                response = get_interview_response(
                    question, history, history_lock, docs, overlay,
                )
                elapsed  = (time.perf_counter() - t0) * 1000
                print(f"  LLM {elapsed:.0f}ms")

                if response:
                    notifier.send_async(question, response)

                # Periodic Safe GC (every 2nd question)
                try:
                    from core.crash_prevention import check_and_gc
                    check_and_gc(threshold=2)
                except Exception:
                    pass

                _reset_watchdog()

            except KeyboardInterrupt:
                raise

            except BaseException as e:
                import traceback as _tb
                msg = (
                    f"\n{'!'*60}\n"
                    f"[LLM worker] CRASH at {time.strftime('%H:%M:%S')}\n"
                    f"Payload: {payload}\n"
                    f"{_tb.format_exc()}"
                    f"{'!'*60}\n"
                )
                print(msg)
                try:
                    with open("gemini_crash.log", "a", encoding="utf-8") as cf:
                        cf.write(msg)
                except Exception:
                    pass
                time.sleep(2.0)

    def _worker():
        print("LLM worker ready")
        while True:
            try:
                _worker_body()
                print("[LLM worker] Shutdown signal received - exiting")
                break
            except KeyboardInterrupt:
                print("[LLM worker] KeyboardInterrupt - exiting")
                break
            except BaseException as e:
                import traceback as _tb
                msg = (
                    f"\n{'!'*60}\n"
                    f"[LLM worker] OUTER CRASH at {time.strftime('%H:%M:%S')}: {e}\n"
                    f"{_tb.format_exc()}"
                    f"{'!'*60}\n"
                )
                print(msg)
                try:
                    with open("gemini_crash.log", "a", encoding="utf-8") as cf:
                        cf.write(msg)
                except Exception:
                    pass
                print("[LLM worker] Restarting in 3s...")
                time.sleep(3.0)

    t = threading.Thread(target=_worker, daemon=True, name="llm-worker")
    return t
