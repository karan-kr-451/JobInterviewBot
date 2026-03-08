"""
transcription/transcription_worker.py - STT worker thread.

Strategy:
  1. Try Groq Whisper API (cloud, fast) if GROQ_API_KEY is set.
  2. Fall back to local faster-whisper if Groq fails or key is missing.

Reads audio from transcription_queue; pushes {"text": str} to llm_queue.
"""

from __future__ import annotations

import queue
import sys
import time

import numpy as np
import requests

from core.logger import get_logger
from core.state_manager import get_state
from utils.crash_guard import gc_safe_http, create_fresh_session, close_response_safely

log = get_logger("transcription.worker")

# ── Groq Whisper ──────────────────────────────────────────────────────────────
GROQ_WHISPER_AVAILABLE = False


def _check_groq_whisper(api_key: str) -> bool:
    """Return True if Groq whisper-large-v3 is accessible."""
    if not api_key:
        return False
    try:
        s = create_fresh_session({"Authorization": f"Bearer {api_key}"})
        r = s.get("https://api.groq.com/openai/v1/models", timeout=5)
        close_response_safely(r)
        return r.status_code == 200
    except Exception:
        return False


def _transcribe_groq(audio_np: np.ndarray, api_key: str, prompt: str = "") -> str:
    """Send audio to Groq Whisper API. Returns transcript string or ''."""
    import io
    import soundfile as sf

    try:
        # Convert numpy array to in-memory WAV
        buf = io.BytesIO()
        sf.write(buf, audio_np, 16000, format="WAV", subtype="PCM_16")
        buf.seek(0)

        with gc_safe_http():
            s = create_fresh_session({"Authorization": f"Bearer {api_key}"})
            files   = {"file": ("audio.wav", buf, "audio/wav")}
            data    = {"model": "whisper-large-v3", "language": "en",
                       "response_format": "text"}
            if prompt:
                data["prompt"] = prompt[:224]   # Groq max prompt length
            r = s.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                files=files, data=data, timeout=(10, 60),
            )
            text = r.text.strip() if r.ok else ""
            close_response_safely(r)
            return text
    except Exception as exc:
        log.debug("Groq Whisper failed: %s", exc)
        return ""


class TranscriptionWorker:
    """
    Pulls audio arrays from transcription_queue, transcribes them,
    pushes text items to llm_queue.
    """

    def __init__(self, tr_cfg, groq_api_key: str,
                 transcription_queue: queue.Queue,
                 llm_queue: queue.Queue,
                 docs: dict | None = None) -> None:
        self._cfg     = tr_cfg
        self._api_key = groq_api_key
        self._tr_q    = transcription_queue
        self._llm_q   = llm_queue
        self._docs    = docs or {}
        self._use_groq = False

        # Check Groq availability at construction time
        self._use_groq = _check_groq_whisper(self._api_key)
        if self._use_groq:
            log.info("[OK] Transcription: Groq Whisper API")
            get_state().update(transcription_backend="groq-cloud")
        else:
            log.info("Transcription: local faster-whisper ('%s')", tr_cfg.local_model)
            get_state().update(transcription_backend="local-whisper")
            # Pre-load local model
            from transcription.whisper_engine import load_model
            load_model(tr_cfg.local_model, tr_cfg.compute_type)

    def _get_hint(self) -> str:
        """Build a Whisper context prompt from job title + skills."""
        doc = self._docs
        if not doc:
            return ""
        title  = doc.get("job_title", "")
        skills = doc.get("resume_sections", {}).get("Skills", "")[:200]
        return f"{title}. {skills}"[:500]

    def run(self) -> None:
        """Worker loop – runs until None sentinel or exception."""
        hint = self._get_hint()
        log.info("TranscriptionWorker started")

        while True:
            try:
                item = self._tr_q.get(timeout=2)
            except queue.Empty:
                continue

            if item is None:
                log.info("TranscriptionWorker stopping (None sentinel)")
                break

            audio_np: np.ndarray = item
            text = ""

            # 1. Try Groq Whisper
            if self._use_groq:
                text = _transcribe_groq(audio_np, self._api_key, prompt=hint)

            # 2. Fall back to local Whisper
            if not text:
                from transcription.whisper_engine import transcribe as local_transcribe
                text = local_transcribe(audio_np, prompt=hint)

            if not text or len(text.split()) < self._cfg.min_words:
                log.debug("Transcript too short (%r) – discarded", text)
                continue

            log.info("Transcript: %s", text)
            sys.stdout.write(f"\n[TRANSCRIPT] {text}\n")
            sys.stdout.flush()

            try:
                self._llm_q.put({"text": text}, block=True, timeout=5)
            except queue.Full:
                log.warning("LLM queue full – transcript dropped: %r", text)
