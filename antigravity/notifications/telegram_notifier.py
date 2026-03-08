"""
notifications/telegram_notifier.py - Thread-safe async Telegram sender.

TelegramNotifier queues messages and sends them from a background worker thread.
The worker uses exponential back-off on failure and retries silently.

All blocking network calls are wrapped with smart_gc_protection() to prevent
GC-triggered crashes during HTTP streaming.
"""

from __future__ import annotations

import queue
import threading
import time

import requests

from core.logger import get_logger
from utils.crash_guard import smart_gc_protection, create_fresh_session, close_response_safely

log = get_logger("notifications.telegram")

_RETRY_MIN = 5
_RETRY_MAX = 60


class TelegramNotifier:
    """
    Thread-safe Telegram bot notification sender.

    send_async()   – enqueue a Q&A pair (never blocks the caller)
    send_status()  – enqueue a status message
    send_message() – send immediately (blocks up to send_timeout seconds)
    """

    def __init__(self, bot_token: str, chat_id: str,
                 queue_size: int = 50, send_timeout: float = 3.0) -> None:
        if not bot_token or not chat_id:
            raise ValueError("bot_token and chat_id are required for TelegramNotifier")
        self._token   = bot_token
        self._chat_id = chat_id
        self._timeout = send_timeout
        self._base    = f"https://api.telegram.org/bot{bot_token}"
        self._online  = True

        self._queue  = queue.Queue(maxsize=queue_size)
        self._worker = threading.Thread(
            target=self._run_worker, daemon=True, name="tg-sender"
        )
        self._worker.start()

    # ── Public API ────────────────────────────────────────────────────────────

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message immediately. Returns True on success."""
        resp = None
        try:
            with smart_gc_protection():
                session = create_fresh_session()
                session.trust_env = False
                chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                for chunk in chunks:
                    resp = session.post(
                        f"{self._base}/sendMessage",
                        json={"chat_id": self._chat_id, "text": chunk,
                              "parse_mode": parse_mode},
                        timeout=self._timeout,
                    )
                    resp.raise_for_status()
                    close_response_safely(resp)
                    resp = None
            if not self._online:
                log.info("Telegram connection restored")
                self._online = True
            return True
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            if self._online:
                log.warning("Telegram offline – notifications paused")
                self._online = False
            return False
        except Exception as exc:
            log.debug("Telegram send error: %s", exc)
            return False
        finally:
            close_response_safely(resp)

    def send_status(self, msg: str) -> bool:
        """Send a plain status message immediately."""
        return self.send_message(f"ℹ️ {msg}")

    def send_qa(self, question: str, response: str) -> bool:
        """Send a formatted Q&A pair immediately."""
        def _esc(s: str) -> str:
            for ch in r"_*[`":
                s = s.replace(ch, f"\\{ch}")
            return s
        msg = (
            f"🎯 *INTERVIEW Q&A*\n\n"
            f"*Question:*\n{_esc(question)}\n\n"
            f"*Answer:*\n{_esc(response)}\n\n"
            f"_{time.strftime('%H:%M:%S')}_"
        )
        return self.send_message(msg)

    def send_async(self, question: str, response: str) -> None:
        """Enqueue a Q&A pair for background sending (never blocks)."""
        try:
            self._queue.put_nowait(("qa", question, response))
        except queue.Full:
            log.debug("Telegram queue full – message dropped")

    def stop(self) -> None:
        """Signal the worker to stop after draining the queue."""
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    # ── Worker ────────────────────────────────────────────────────────────────

    def _run_worker(self) -> None:
        backoff = _RETRY_MIN
        while True:
            try:
                item = self._queue.get(timeout=5)
            except queue.Empty:
                continue

            if item is None:
                break

            kind    = item[0]
            success = False

            try:
                if kind == "qa":
                    _, q, r = item
                    success = self.send_qa(q, r)
                elif kind == "msg":
                    _, text = item
                    success = self.send_message(text)
                else:
                    success = True
            except Exception as exc:
                log.debug("Telegram worker error: %s", exc)

            if success:
                backoff = _RETRY_MIN
            else:
                wait = min(backoff, _RETRY_MAX)
                time.sleep(wait)
                backoff = min(backoff * 2, _RETRY_MAX)
                # Re-queue for retry
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    pass


class DummyNotifier:
    """No-op notifier used when Telegram credentials are not configured."""

    def send_status(self, msg: str) -> None: pass
    def send_qa(self, question: str, response: str) -> None: pass
    def send_async(self, question: str, response: str) -> None: pass
    def send_message(self, text: str) -> None: pass
    def stop(self) -> None: pass


def create_notifier(cfg) -> TelegramNotifier | DummyNotifier:
    """Return a real TelegramNotifier if credentials are configured, else DummyNotifier."""
    token   = cfg.telegram.bot_token
    chat_id = cfg.telegram.chat_id
    if token and chat_id:
        try:
            n = TelegramNotifier(
                token, chat_id,
                queue_size=cfg.telegram.queue_size,
                send_timeout=cfg.telegram.send_timeout,
            )
            log.info("[OK] Telegram notifier configured")
            return n
        except Exception as exc:
            log.warning("Telegram init failed: %s – using dummy notifier", exc)
    else:
        log.info("Telegram credentials not set – notifications disabled")
    return DummyNotifier()
