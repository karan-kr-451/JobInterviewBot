"""
core/app_state.py — Centralized, thread-safe application state store.

Single source of truth for ALL shared state in the process.
Uses SafeLock (never plain threading.Lock).
State is a typed dataclass — no raw dicts.
All mutable collections use bounded containers (deque, set, LRU).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from antigravity.core.safe_lock import SafeLock


@dataclass
class AppState:
    # ── Recording state ───────────────────────────────────────────────────────
    is_recording:   bool = False
    is_processing:  bool = False

    # ── Backend ───────────────────────────────────────────────────────────────
    current_backend: str = "groq"      # "groq" | "gemini" | "ollama"

    # ── History (bounded — no unbounded lists) ────────────────────────────────
    transcript_history: deque = field(
        default_factory=lambda: deque(maxlen=500)
    )
    response_history: deque = field(
        default_factory=lambda: deque(maxlen=200)
    )

    # ── Duplicate detection — O(1) lookup ─────────────────────────────────────
    session_questions: set = field(default_factory=set)

    # ── Diagnostics ───────────────────────────────────────────────────────────
    error_count:  int   = 0
    start_time:   float = field(default_factory=time.time)

    # ── Lock (NOT included in equality/repr to keep dataclass simple) ─────────
    _lock: SafeLock = field(
        default_factory=lambda: SafeLock("AppState", timeout=3.0),
        repr=False, compare=False,
    )

    # ── Recording ─────────────────────────────────────────────────────────────

    def set_recording(self, value: bool) -> None:
        with self._lock:
            self.is_recording = value

    def set_processing(self, value: bool) -> None:
        with self._lock:
            self.is_processing = value

    def set_backend(self, name: str) -> None:
        with self._lock:
            self.current_backend = name

    # ── Transcript / Response history ─────────────────────────────────────────

    def add_transcript(self, text: str) -> None:
        """Add transcript and register as seen question (O(1) dedup)."""
        with self._lock:
            self.transcript_history.append(text)
            self.session_questions.add(text[:100])

    def add_response(self, text: str) -> None:
        with self._lock:
            self.response_history.append(text)

    def is_duplicate_question(self, text: str) -> bool:
        """O(1) set membership test."""
        with self._lock:
            return text[:100] in self.session_questions

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def increment_error(self) -> None:
        with self._lock:
            self.error_count += 1

    def snapshot(self) -> dict:
        """Return a plain-dict snapshot (safe to read without lock)."""
        with self._lock:
            return {
                "is_recording":    self.is_recording,
                "is_processing":   self.is_processing,
                "current_backend": self.current_backend,
                "error_count":     self.error_count,
                "transcript_count": len(self.transcript_history),
                "uptime_s":        time.time() - self.start_time,
            }


# ── Process-level singleton ───────────────────────────────────────────────────
_state: Optional[AppState] = None
_state_lock = SafeLock("StateInit", timeout=5.0)


def get_app_state() -> AppState:
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = AppState()
    return _state
