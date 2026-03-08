"""
notifications/telegram_notifier.py — Async background notifier.

Consumes a bounded queue and sends messages to Telegram.
NEVER blocks the main flow, even on network failures.
"""

from __future__ import annotations

import logging
import queue
import time
import requests

from antigravity.core.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseWorker):
    """
    Consumes a bounded queue of messages.
    If Telegram API is down, fails gracefully without crashing the app.
    """

    def __init__(
        self,
        notif_queue: queue.Queue,
        bot_token: str,
        chat_id: str,
        enabled: bool = True
    ) -> None:
        super().__init__(name="TelegramNotifier", restart_delay=60.0)
        self._queue   = notif_queue
        self._token   = bot_token
        self._chat_id = chat_id
        self._enabled = enabled and bool(bot_token) and bool(chat_id)
        
        if not self._enabled:
            logger.info("[NOTIFY] Telegram disabled or missing credentials.")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._heartbeat()

            try:
                msg = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if not self._enabled:
                self._queue.task_done()
                continue

            try:
                self._send_message(msg)
            except Exception as e:
                logger.error("[NOTIFY] Failed to send Telegram message: %s", e)
            finally:
                self._queue.task_done()

    def _send_message(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        # Strictly bounded timeouts (Rule 7)
        resp = requests.post(url, json=payload, timeout=(3.0, 10.0))
        resp.raise_for_status()
        logger.debug("[NOTIFY] Telegram message sent successfully.")
