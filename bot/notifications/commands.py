"""
notifications.commands - Telegram command polling.
"""

import threading
import time
import requests

from config.telegram import TELEGRAM_BOT_TOKEN, TELEGRAM_POLL_TIMEOUT
from core.http_utils import smart_gc_protection, create_fresh_session, close_response_safely

_RETRY_BACKOFF_MIN = 5
_RETRY_BACKOFF_MAX = 60


def make_command_poller(notifier, history: list,
                        history_lock: threading.Lock):
    """Create and return a daemon thread that polls Telegram for commands."""
    def _poll():
        last_update_id = 0
        backoff        = _RETRY_BACKOFF_MIN
        last_err       = ""
        session        = None  # Keep session per thread

        while True:
            resp = None
            try:
                # Use smart GC protection for periodic collection
                with smart_gc_protection():
                    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                    params = {"offset": last_update_id + 1, "timeout": TELEGRAM_POLL_TIMEOUT}
                    
                    # Create session once per thread, reuse it
                    if session is None:
                        session = create_fresh_session()
                        session.trust_env = False  # Disable .netrc (not thread-safe)
                    
                    try:
                        resp = session.get(url, params=params, timeout=TELEGRAM_POLL_TIMEOUT + 5)
                        data = resp.json()
                    except Exception as e:
                        # If session fails, recreate it
                        close_response_safely(resp)
                        resp = None
                        if session:
                            try:
                                session.close()
                            except:
                                pass
                        session = None
                        raise
                    
                    close_response_safely(resp)
                    resp = None
                    
                    backoff  = _RETRY_BACKOFF_MIN
                    last_err = ""

                    if data.get("ok") and data.get("result"):
                        for update in data["result"]:
                            last_update_id = update["update_id"]
                            text = update.get("message", {}).get("text", "").lower().strip()
                            if text == "/start":
                                notifier.send_message("  Interview Assistant Active")
                            elif text == "/clear":
                                with history_lock:
                                    history.clear()
                                notifier.send_message("[OK] History cleared.")
                            elif text == "/status":
                                with history_lock:
                                    n = len(history) // 2
                                notifier.send_message(f"  {n} Q&A pairs in history.")

            except requests.exceptions.ReadTimeout:
                pass

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.RequestException) as e:
                err = str(e)[:60]
                if err != last_err:
                    print(f"[Telegram poll] Offline - backing off {backoff}s")
                    last_err = err
                time.sleep(backoff)
                backoff = min(backoff * 2, _RETRY_BACKOFF_MAX)

            except Exception as e:
                try:
                    error_msg = str(e)
                    print(f"[Telegram poll] {error_msg}")
                except:
                    print("[Telegram poll] Unknown error")
                time.sleep(5)
            
            finally:
                close_response_safely(resp)

    return threading.Thread(target=_poll, daemon=True, name="tg-commands")
