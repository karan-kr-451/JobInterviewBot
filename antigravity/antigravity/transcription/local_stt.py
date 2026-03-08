"""
transcription/local_stt.py — Local fallback using faster-whisper.

Lazy-loads the torch/ctranslate2 stack.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class LocalSTT:
    """Uses faster-whisper locally."""

    def __init__(self, model_size: str = "tiny.en") -> None:
        self.model_size = model_size
        self._model: Any = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return

        logger.info("[LOCAL_STT] Loading faster-whisper %s model...", self.model_size)
        try:
            # Rule 6: Lazy imports
            from faster_whisper import WhisperModel
            import torch
            
            # Use CPU by default to avoid CUDA issues, matched requirements
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )
            self._loaded = True
            logger.info("[LOCAL_STT] Model loaded successfully.")
        except Exception as e:
            logger.error("[LOCAL_STT] Failed to load local model: %s", e)
            raise

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        try:
            self._load()
        except Exception:
            return ""

        try:
            # Convert specifically to float32 for faster-whisper
            audio_fp32 = audio.astype(np.float32)

            segments, info = self._model.transcribe(
                audio_fp32,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
                without_timestamps=True,
            )

            # Eagerly consume the generator
            text = " ".join([seg.text for seg in segments])
            return text.strip()

        except Exception as e:
            logger.error("[LOCAL_STT] Transcription failed: %s", e)
            return ""
