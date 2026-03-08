"""
transcription/transcription_worker.py — VAD chunking and STT dispatch.

Pulls from the bounded audio deque, runs VAD to find solid speech chunks,
dispatches to Groq/Local STT, updates the transcript store, and pushes
to the LLM queue.
"""

from __future__ import annotations

import logging
import queue
import time
from collections import deque

import numpy as np

from antigravity.core.base_worker import BaseWorker
from antigravity.core.event_bus import EVT_TRANSCRIPT_READY, bus
from antigravity.core.safe_lock import SafeLock
from antigravity.transcription.transcript_store import add_transcript, is_duplicate

logger = logging.getLogger(__name__)


class TranscriptionWorker(BaseWorker):
    """
    Consumes audio_queue, buffers into chunks using VAD, transcribes,
    and publishes to LLM queue.
    """

    def __init__(
        self,
        audio_queue: deque[np.ndarray],
        llm_queue: queue.Queue,
        groq_api_key: str,
        backend: str = "groq",
        sample_rate: int = 16000,
    ) -> None:
        super().__init__(name="TranscriptionWorker", restart_delay=3.0)
        self._audio_queue = audio_queue
        self._llm_queue   = llm_queue
        self._sample_rate = sample_rate
        
        # Lock level 2
        self._lock = SafeLock("TranscriptionWorker", timeout=3.0)

        # STT Backends
        self.backend_choice = backend
        if backend == "groq" and groq_api_key:
            from antigravity.transcription.groq_stt import GroqSTT
            self._stt = GroqSTT(api_key=groq_api_key)
        else:
            from antigravity.transcription.local_stt import LocalSTT
            self._stt = LocalSTT(model_size="tiny.en")
            
        # VAD
        from antigravity.audio.vad_filter import VADFilter
        self._vad = VADFilter(sample_rate=sample_rate)
        
        # Chunking state
        self._chunk_buffer: list[np.ndarray] = []
        self._silence_chunks = 0
        self._max_silence_chunks = 3  # roughly 1.5 seconds if chunk=0.5s

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._heartbeat()
            
            # Read from audio deque (non-blocking)
            try:
                # deque is bounded, we popleft to consume oldest
                chunk = self._audio_queue.popleft()
            except IndexError:
                # Queue empty: If we have a buffer waiting and we hit silence timeout, process it now
                if self._chunk_buffer and self._silence_chunks >= self._max_silence_chunks:
                    self._process_buffer()
                time.sleep(0.05)
                continue

            if chunk is None:
                continue

            # Check if chunk contains speech (VAD)
            # A chunk of all zeros is our explicit silence marker from the capture worker
            if np.max(np.abs(chunk)) > 0:
                is_speech = self._vad.is_speech(chunk)
            else:
                is_speech = False

            if is_speech:
                # Provide visual feedback to user that loopback audio is being heard
                if self._silence_chunks > 0:
                    print("[VAD] Voice detected from loopback audio! Listening...")
                self._chunk_buffer.append(chunk)
                self._silence_chunks = 0
            else:
                # Only increment silence if we actually started tracking an utterance
                if self._chunk_buffer:
                    self._silence_chunks += 1
                    self._chunk_buffer.append(chunk)

            # If we hit max silence while reading, process the buffer immediately
            if self._chunk_buffer and self._silence_chunks >= self._max_silence_chunks:
                self._process_buffer()

    def _process_buffer(self) -> None:
        """Concatenates buffered chunks, transcribes, and clears buffer."""
        if not self._chunk_buffer:
            return

        with self._lock:
            audio_data = np.concatenate(self._chunk_buffer)
            self._chunk_buffer.clear()
            self._silence_chunks = 0
            
        # Transcribe (DO NOT HOLD LOCK DURING I/O - Rule 4)
        if self._stop_event.is_set():
            return

        logger.debug("[STT] Processing %.1fs of audio...", len(audio_data) / self._sample_rate)
        text = self._stt.transcribe(audio_data, self._sample_rate)
        
        if self._stop_event.is_set():
            return
            
        if text and len(text) > 4:
            if not is_duplicate(text):
                logger.info("[STT] Transcript: %s", text)
                add_transcript(text)
                bus.publish(EVT_TRANSCRIPT_READY, text)
                
                # Push to bounded LLM queue (Rule 2)
                try:
                    self._llm_queue.put(text, block=False)
                except queue.Full:
                    logger.warning("[STT] LLM queue full, dropping transcript!")
