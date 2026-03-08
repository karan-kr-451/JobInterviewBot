"""
core/state_manager.py - Centralized, thread-safe application state.

Provides a single StateManager singleton that any module can import
to read or update shared state, without direct coupling between threads.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppState:
    # ── Audio ──────────────────────────────────────────────────
    is_recording:     bool  = False
    last_audio_time:  float = field(default_factory=time.perf_counter)
    audio_device_idx: Optional[int] = None
    vad_mode:         str   = "initialising"   # "silero" | "rms-only"

    # ── Transcription ──────────────────────────────────────────
    last_transcript:  str   = ""
    transcription_backend: str = "unknown"     # "groq-cloud" | "local-whisper"

    # ── LLM ────────────────────────────────────────────────────
    active_backend:   str   = "none"           # "groq" | "gemini" | "ollama"
    active_model:     str   = ""
    is_generating:    bool  = False
    last_question:    str   = ""
    request_count:    int   = 0

    # ── System ──────────────────────────────────────────────────
    is_shutting_down: bool  = False
    startup_time:     float = field(default_factory=time.time)


class StateManager:
    """
    Thread-safe wrapper around AppState.

    Usage:
        from core.state_manager import get_state
        state = get_state()
        state.update(is_recording=True)
        val = state.get("is_recording")
    """

    def __init__(self) -> None:
        self._lock  = threading.RLock()
        self._state = AppState()

    def update(self, **kwargs) -> None:
        """Atomically update one or more state fields."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
                else:
                    raise AttributeError(
                        f"AppState has no field '{key}'. "
                        f"Available: {list(self._state.__dataclass_fields__.keys())}"
                    )

    def get(self, key: str):
        """Return the current value of a state field."""
        with self._lock:
            return getattr(self._state, key)

    def snapshot(self) -> AppState:
        """Return a shallow copy of the current state (safe to read without lock)."""
        with self._lock:
            import copy
            return copy.copy(self._state)

    def __repr__(self) -> str:
        with self._lock:
            return f"StateManager({self._state})"


# ── Module-level singleton ────────────────────────────────────────────────────
_state_mgr: Optional[StateManager] = None
_sm_lock = threading.Lock()


def get_state() -> StateManager:
    """Return the process-level singleton StateManager."""
    global _state_mgr
    if _state_mgr is None:
        with _sm_lock:
            if _state_mgr is None:
                _state_mgr = StateManager()
    return _state_mgr
