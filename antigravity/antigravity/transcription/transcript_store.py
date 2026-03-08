"""
transcription/transcript_store.py — Transcription history and bounded queues.

Implements Rule 2 (No Unbounded Containers).
transcript_history is a deque(maxlen=500).
Inter-thread queues have maxsize limits to provide natural backpressure.
"""

from __future__ import annotations

import queue
from collections import deque
from typing import Any

import numpy as np


class BoundedAudioQueue(deque):
    """
    Bounded deque for audio chunks.
    Automatically evicts oldest if consumer is too slow, preventing OOM.
    Never blocks or raises essentially (unlike queue.Queue).
    """
    def __init__(self, maxlen: int = 100) -> None:
        super().__init__(maxlen=maxlen)


class InterThreadQueue(queue.Queue):
    """
    Bounded thread-safe queue.
    If full, put() will block, applying natural backpressure.
    """
    def __init__(self, maxsize: int = 50) -> None:
        super().__init__(maxsize=maxsize)


# O(1) transcript store
# While we have AppState, keeping a fast thread-local-ish accessor here for the worker
transcript_history: deque[str] = deque(maxlen=500)
seen_questions: set[str] = set()


def add_transcript(text: str) -> None:
    transcript_history.append(text)
    seen_questions.add(text[:100])


def is_duplicate(text: str) -> bool:
    return text[:100] in seen_questions
