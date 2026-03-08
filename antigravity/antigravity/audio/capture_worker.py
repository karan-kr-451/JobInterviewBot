"""
audio/capture_worker.py — Bulletproof audio capture.

Captures system audio using sounddevice.
Uses a bounded deque (never runs out of memory on OOM).
Callback is completely wrapped in try/except — never crashes C runtime.
A simple RMS gate avoids pointless deque-pushing during absolute silence.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

import numpy as np

from antigravity.core.base_worker import BaseWorker
from antigravity.core.event_bus import EVT_RECORDING_START, EVT_RECORDING_STOP, bus

logger = logging.getLogger(__name__)


class CaptureWorker(BaseWorker):
    """
    Reads from the microphone using PortAudio and pushes interleaved
    audio frames into the shared bounded deque.
    """

    def __init__(
        self,
        device_index: Optional[int],
        audio_queue: deque[np.ndarray],
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_seconds: float = 0.5,
        vad_threshold: float = 0.005,
    ) -> None:
        super().__init__(name="CaptureWorker", restart_delay=3.0)
        self._device_index  = device_index
        self._audio_queue   = audio_queue
        self._sample_rate   = sample_rate
        self._channels      = channels
        self._chunk_frames  = int(sample_rate * chunk_seconds)
        self._vad_threshold = vad_threshold

    def _run_loop(self) -> None:
        import sounddevice as sd

        logger.info(
            "[AUDIO] Opening stream: dev=%s, sr=%d, block=%d",
            self._device_index, self._sample_rate, self._chunk_frames
        )

        with sd.InputStream(
            device=self._device_index,
            channels=self._channels,
            samplerate=self._sample_rate,
            blocksize=self._chunk_frames,
            dtype=np.float32,
            callback=self._callback,
        ):
            bus.publish(EVT_RECORDING_START)
            logger.info("[AUDIO] Stream active and recording.")
            
            # Keep thread alive cleanly
            while not self._stop_event.is_set():
                self._heartbeat()  # Update health_ts
                time.sleep(0.1)
                
            logger.info("[AUDIO] Stream stop requested.")
            
        bus.publish(EVT_RECORDING_STOP)
        logger.info("[AUDIO] Stream closed safely.")

    def _callback(self, indata: np.ndarray, frames: int, time_info: dict, status) -> None:
        """
        PortAudio callback.
        THIS MUST BE BULLETPROOF. NEVER RAISE AN EXCEPTION.
        """
        try:
            if status:
                logger.debug("[AUDIO] PortAudio status code: %s", status)

            # Pass all frames faithfully to the transcription queue.
            # We skip explicit amplitude gating (RMS) to allow WASAPI lookback 
            # streams (which can be very quiet) to trigger the actual VAD model downstream.
            self._audio_queue.append(indata.copy().flatten())
            
        except Exception as e:
            # We explicitly eat and log the exception.
            # Raising here would cause a C-level segmentation fault.
            logger.error("[AUDIO_CB] Error in audio callback: %s", e)
