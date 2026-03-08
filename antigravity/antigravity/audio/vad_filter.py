"""
audio/vad_filter.py — Silero Voice Activity Detector.

Filters out background noise and segments utterances before they hit Whisper.
Lazy-loads the torch hub model inside the class (Rule 6).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class VADFilter:
    """
    Wrapper around Silero VAD (v4 preferred) for classifying chunks.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.model: Any = None
        self.get_speech_timestamps: Any = None

    def _load_model(self) -> None:
        if self.model is not None:
            return
            
        logger.info("[VAD] Loading Silero VAD model via torch.hub...")
        import torch
        # Reduce verbosity from torch hub
        import warnings
        warnings.filterwarnings("ignore", module="torch.hub")
        
        try:
            # v5 might be available, fallback to v4
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True
            )
            self.model = model
            self.get_speech_timestamps = utils[0]
            logger.info("[VAD] Silero model loaded successfully.")
        except Exception as e:
            logger.error("[VAD] Failed to load Silero VAD: %s", e)
            raise

    def is_speech(self, chunk: np.ndarray, threshold: float = 0.5) -> bool:
        """
        Return True if speech is detected over the probability threshold.
        If the model fails to load, falls back to a simple energy check.
        """
        try:
            self._load_model()
        except Exception:
            # Fallback: simple energy check
            return float(np.max(np.abs(chunk))) > 0.05
            
        import torch
        
        # Audio from Stereo Mix / Loopback is often heavily attenuated.
        # We must normalize it (gain up to 8.0x) so Silero can actually 'hear' it
        # matching the old V3 logic.
        audio_float = chunk.copy()
        peak = float(np.max(np.abs(audio_float)))
        if peak > 1e-6:
            audio_norm = audio_float * min(0.3 / peak, 8.0)
        else:
            audio_norm = audio_float
            
        tensor = torch.from_numpy(audio_norm)
        try:
            # Convert to float32 expected by Silero model
            if tensor.dtype != torch.float32:
                tensor = tensor.to(torch.float32)
                
            # Silero requires EXACTLY 512 samples per chunk at 16000Hz (or 256 at 8000Hz)
            window_size = 512 if self.sample_rate == 16000 else 256
            
            # If the chunk is smaller than window_size, pad it with zeros
            if len(tensor) < window_size:
                pad_size = window_size - len(tensor)
                tensor = torch.nn.functional.pad(tensor, (0, pad_size))
                
            # Evaluate speech probabilities across all window_size segments
            for i in range(0, len(tensor) - window_size + 1, window_size):
                segment = tensor[i: i + window_size]
                prob = self.model(segment, self.sample_rate).item()
                # If ANY segment within this larger chunk is speech, the whole chunk is speech
                if prob >= threshold:
                    return True
                    
            return False
            
        except Exception as e:
            logger.warning("[VAD] Model inference failed: %s", e)
            return float(np.max(np.abs(chunk))) > 0.05
        finally:
            del tensor  # Explicit delete (Rule 3)
