"""
ui/hotkeys.py - Global keyboard hotkey polling thread.

Registers global hotkeys using the `keyboard` library (or falls back to
a ctypes-based approach on Windows). Runs in a daemon thread.

Default hotkeys (while Ctrl is held):
  Ctrl+H   – toggle overlay visibility
  Ctrl+Q   – quit application
  Ctrl+F   – toggle fullscreen overlay
  Ctrl+M   – minimise/restore overlay
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict

from core.logger import get_logger

log = get_logger("ui.hotkeys")


class HotkeyManager:
    """
    Polls for global hotkeys in a daemon thread.
    Uses the `keyboard` library if available, else is a no-op.

    Usage:
        hkm = HotkeyManager()
        hkm.register("ctrl+h", overlay.toggle)
        hkm.start()
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, Callable] = {}
        self._running   = False
        self._thread: threading.Thread | None = None
        self._available = False

        try:
            import keyboard  # noqa: F401
            self._available = True
        except ImportError:
            log.info("'keyboard' package not installed – global hotkeys disabled")

    def register(self, hotkey: str, callback: Callable) -> None:
        """Register a hotkey → callback mapping (e.g. 'ctrl+h')."""
        self._bindings[hotkey.lower()] = callback

    def start(self) -> None:
        """Start the hotkey listener in a daemon thread."""
        if not self._available:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._run, daemon=True, name="hotkeys"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        try:
            import keyboard
            for hotkey, cb in self._bindings.items():
                keyboard.add_hotkey(hotkey, cb, suppress=False)
            log.info("Global hotkeys active: %s", list(self._bindings.keys()))
            while self._running:
                time.sleep(0.2)
            keyboard.unhook_all_hotkeys()
        except Exception as exc:
            log.warning("Hotkey manager error: %s", exc)
