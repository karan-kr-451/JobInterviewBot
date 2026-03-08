"""
transcription/buffer_manager.py - Bounded queue management for transcription pipeline.

Provides:
  transcription_queue  - audio (np.ndarray) from VAD → TranscriptionWorker
  llm_queue            - text dicts {"text": str} from TranscriptionWorker → LLMWorker
"""

from __future__ import annotations

import queue


def make_transcription_queue(maxsize: int = 10) -> queue.Queue:
    """Create a bounded Queue for audio utterances awaiting transcription."""
    return queue.Queue(maxsize=maxsize)


def make_llm_queue(maxsize: int = 20) -> queue.Queue:
    """Create a bounded Queue for text transcripts awaiting LLM processing."""
    return queue.Queue(maxsize=maxsize)


def drain_queue(q: queue.Queue) -> int:
    """Drain all items from queue. Returns number of items removed."""
    count = 0
    while not q.empty():
        try:
            q.get_nowait()
            count += 1
        except queue.Empty:
            break
    return count
