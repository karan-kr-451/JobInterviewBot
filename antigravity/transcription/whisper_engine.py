"""
transcription/whisper_engine.py - Local faster-whisper transcription engine.

WhisperEngine loads the faster-whisper model lazily (on first transcription call)
to avoid blocking startup. Falls back gracefully if the library is not installed.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

from core.logger import get_logger

log = get_logger("transcription.whisper")

_load_lock  = threading.Lock()
_model      = None
_is_loaded  = False

WHISPER_AVAILABLE = False

try:
    from faster_whisper import WhisperModel as _WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    _WhisperModel = None


def load_model(model_name: str = "base.en", compute_type: str = "int8") -> bool:
    """
    Load the faster-whisper model.
    Thread-safe. Returns True on success.
    """
    global _model, _is_loaded

    with _load_lock:
        if _is_loaded:
            return True
        if not WHISPER_AVAILABLE:
            log.error("faster-whisper not installed – local transcription disabled.")
            return False
        try:
            log.info("Loading Whisper model '%s' (compute_type=%s)…", model_name, compute_type)
            _model     = _WhisperModel(model_name, device="cpu", compute_type=compute_type)
            _is_loaded = True
            log.info("[OK] Whisper model loaded")
            return True
        except Exception as exc:
            log.error("Whisper model load failed: %s", exc)
            return False


def transcribe(audio_np: np.ndarray, sample_rate: int = 16000,
               prompt: str = "") -> str:
    """
    Transcribe a float32 audio array.
    Returns the full transcript string, or "" on failure.
    """
    global _model

    if _model is None:
        # Attempt lazy load
        if not load_model():
            return ""

    try:
        t0 = time.perf_counter()

        segments, _ = _model.transcribe(
            audio_np,
            language="en",
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            vad_filter=False,   # We do our own VAD
            beam_size=1,        # Fast greedy decode
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if text:
            log.debug("Local Whisper: '%s' (%.0f ms)", text, elapsed_ms)

        return text

    except Exception as exc:
        log.warning("Local Whisper transcription failed: %s", exc)
        return ""
