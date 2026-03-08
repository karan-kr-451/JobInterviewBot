"""
audio/audio_queue.py - Shared audio deque used between capture and VAD.

Centralised here so both audio_capture.py and vad_processor.py can import
the same object without circular dependencies.
"""

from __future__ import annotations

from collections import deque

# Lock-free deque for audio chunks.
# maxlen=500 ≈ 50 seconds of audio at 100 ms chunks – prevents unbounded growth.
audio_queue: deque = deque(maxlen=500)
