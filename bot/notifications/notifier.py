"""
notifications.notifier - Telegram notification sender.
"""

import queue
import threading
import time
import requests

from config.telegram import (
    TELEGRAM_QUEUE_SIZE, TELEGRAM_SEND_TIMEOUT,
)
from core.http_utils import smart_gc_protection, create_fresh_session, close_response_safely

_RETRY_BACKOFF_MIN = 5
_RETRY_BACKOFF_MAX = 60

# -- Thread-local session pool -------------------------------------------------
_tls = threading.local()


def _get_session() -> requests.Session:
    """Return this thread's private requests.Session, creating it if needed."""
    if not hasattr(_tls, "session"):
        _tls.session = requests.Session()
        _tls.session.trust_env = False  # CRITICAL: Disable .netrc to prevent os.environ race
    return _tls.session


class TelegramNotifier:
    """
    Thread-safe Telegram sender. send_async() never blocks the caller.
    send_message() blocks up to TELEGRAM_SEND_TIMEOUT (3s by default).
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id   = chat_id
        self.base_url  = f"https://api.telegram.org/bot{bot_token}"
        self._online   = True

        self._queue  = queue.Queue(maxsize=TELEGRAM_QUEUE_SIZE)
        self._worker = threading.Thread(
            target=self._run_worker, daemon=True, name="tg-sender"
        )
        self._worker.start()

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        resp = None
        try:
            # Use smart GC protection for this request (already acquires _http_lock)
            with smart_gc_protection():
                url = f"{self.base_url}/sendMessage"
                # Create fresh session to avoid thread-safety issues
                session = create_fresh_session()
                session.trust_env = False  # Disable .netrc (not thread-safe)
                chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                for chunk in chunks:
                    resp = session.post(url, json={
                        "chat_id": self.chat_id, "text": chunk,
                        "parse_mode": parse_mode,
                    }, timeout=TELEGRAM_SEND_TIMEOUT)
                    resp.raise_for_status()
                    close_response_safely(resp)
                    resp = None
            if not self._online:
                print("[Telegram] Connection restored")
                self._online = True
            return True
        except (requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError):
            if self._online:
                print(f"[Telegram] Offline - notifications paused (retrying in background)")
                self._online = False
            return False
        except Exception as e:
            print(f"[Telegram] send error: {e}")
            return False
        finally:
            close_response_safely(resp)

    def send_status(self, msg: str) -> bool:
        return self.send_message(f"   {msg}")

    def send_qa(self, question: str, response: str) -> bool:
        def _esc(s: str) -> str:
            for ch in r"_*[`":
                s = s.replace(ch, f"\\{ch}")
            return s
        msg = (
            f"  *INTERVIEW QUESTION DETECTED*\n\n"
            f"  *Question:*\n{_esc(question)}\n\n"
            f"  *Suggested Response:*\n{_esc(response)}\n\n"
            f"  _{time.strftime('%H:%M:%S')}_"
        )
        return self.send_message(msg)

    def send_async(self, question: str, response: str):
        try:
            self._queue.put_nowait(("qa", question, response))
        except queue.Full:
            print("[Telegram] Queue full - dropping message")

    def _run_worker(self):
        backoff = _RETRY_BACKOFF_MIN
        while True:
            try:
                item = self._queue.get(timeout=5)
                if item is None:
                    break
                kind = item[0]
                success = False
                if kind == "qa":
                    _, q, r = item
                    success = self.send_qa(q, r)
                elif kind == "msg":
                    _, text = item
                    success = self.send_message(text)
                else:
                    success = True

                if success:
                    backoff = _RETRY_BACKOFF_MIN
                else:
                    time.sleep(min(backoff, _RETRY_BACKOFF_MAX))
                    backoff = min(backoff * 2, _RETRY_BACKOFF_MAX)
                    try:
                        self._queue.put_nowait(item)
                    except queue.Full:
                        pass
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Telegram worker] {e}")

    def stop(self):
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
