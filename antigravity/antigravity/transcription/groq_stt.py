"""
transcription/groq_stt.py — Groq Whisper STT client.
"""

from __future__ import annotations

import io
import logging

import requests
import soundfile as sf
import numpy as np

from antigravity.core.event_bus import EVT_ERROR, bus

logger = logging.getLogger(__name__)


class GroqSTT:
    """Uses Groq's whisper-large-v3 model for fast cloud transcription."""

    URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, api_key: str, language: str = "en") -> None:
        self._api_key = api_key
        self._language = language

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if not self._api_key:
            return ""

        # Convert float32 numpy array to 16-bit PCM WAV in memory
        wav_io = io.BytesIO()
        try:
            sf.write(wav_io, audio, sample_rate, format="WAV", subtype="PCM_16")
            wav_io.seek(0)
        except Exception as e:
            logger.error("[GROQ_STT] Wav conversion failed: %s", e)
            return ""

        headers = {
            "Authorization": f"Bearer {self._api_key}"
        }
        files = {
            "file": ("audio.wav", wav_io, "audio/wav")
        }
        data = {
            "model": "whisper-large-v3",
            "language": self._language,
            "response_format": "json"
        }

        try:
            # Rule 7: Strict timeouts
            resp = requests.post(
                self.URL,
                headers=headers,
                files=files,
                data=data,
                timeout=(5, 30)
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("text", "").strip()

        except requests.exceptions.Timeout:
            logger.warning("[GROQ_STT] Request timed out")
            return ""
        except requests.exceptions.RequestException as e:
            logger.warning("[GROQ_STT] Request failed: %s", e)
            return ""
        except Exception as e:
            logger.error("[GROQ_STT] Unexpected error: %s", e)
            return ""
