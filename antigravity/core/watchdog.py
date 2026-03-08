"""
core/watchdog.py - Watchdog timer that restarts the audio stream on hangs.

The watchdog monitors two conditions:
  1. Audio silence timeout  – no audio chunks received for AUDIO_TIMEOUT seconds
                              → sets restart_event to trigger stream reopen.
  2. LLM worker timeout     – no LLM activity for LLM_TIMEOUT seconds while
                              a response is being generated → logs warning.

Call reset_audio() from the audio callback.
Call reset_llm()   from inside LLM streaming loops.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from core.logger import get_logger

log = get_logger("watchdog")

# ── Configurable timeouts (seconds) ──────────────────────────────────────────
AUDIO_TIMEOUT = 15.0    # Restart stream if no audio for this long
LLM_TIMEOUT   = 45.0    # Warn if LLM worker hangs past this


class Watchdog:
    """
    Self-contained watchdog. Start it with start(); stop with stop().
    Pass restart_event to trigger audio-stream restart.
    """

    def __init__(self, restart_event: threading.Event) -> None:
        self._restart   = restart_event
        self._stop      = threading.Event()
        self._lock      = threading.Lock()

        self._last_audio: float = time.perf_counter()
        self._last_llm:   float = time.perf_counter()
        self._llm_active: bool  = False

        self._thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def reset_audio(self) -> None:
        """Call from audio callback on every received chunk."""
        with self._lock:
            self._last_audio = time.perf_counter()

    def reset_llm(self) -> None:
        """Call periodically from inside LLM streaming loops."""
        with self._lock:
            self._last_llm = time.perf_counter()

    def set_llm_active(self, active: bool) -> None:
        """Signal that an LLM generation is in progress or finished."""
        with self._lock:
            self._llm_active = active
            if active:
                self._last_llm = time.perf_counter()

    def start(self) -> None:
        """Start the watchdog polling thread."""
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="watchdog",
        )
        self._thread.start()
        log.debug("Watchdog started (audio_timeout=%.0fs, llm_timeout=%.0fs)",
                  AUDIO_TIMEOUT, LLM_TIMEOUT)

    def stop(self) -> None:
        """Signal the watchdog thread to stop."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop.is_set():
            time.sleep(2.0)

            now = time.perf_counter()

            with self._lock:
                audio_gap  = now - self._last_audio
                llm_gap    = now - self._last_llm
                llm_active = self._llm_active

            # Audio silence check
            if audio_gap > AUDIO_TIMEOUT:
                log.warning(
                    "No audio for %.0fs – triggering stream restart", audio_gap
                )
                self._restart.set()
                # Reset timer to avoid repeated triggers while stream reopens
                with self._lock:
                    self._last_audio = time.perf_counter()

            # LLM hang check
            if llm_active and llm_gap > LLM_TIMEOUT:
                log.warning(
                    "LLM worker appears hung (%.0fs without activity)", llm_gap
                )
                # Don't restart the stream for this – just log.
                # A future enhancement could kill and restart the LLM thread.
