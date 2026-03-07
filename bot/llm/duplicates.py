"""
llm.duplicates - Duplicate question detection.
"""

import time
import difflib
import threading

from config.llm import DUPLICATE_WINDOW_S, DUPLICATE_OVERLAP_THRESHOLD

_recent_questions: list = []
_recent_lock = threading.Lock()


def is_duplicate(question: str) -> bool:
    """Return True if the question is too similar to a recent one."""
    now = time.perf_counter()
    with _recent_lock:
        cutoff = now - DUPLICATE_WINDOW_S
        while _recent_questions and _recent_questions[0][1] < cutoff:
            _recent_questions.pop(0)
        q_words = question.lower().split()
        for prev_text, _ in _recent_questions:
            prev_words = prev_text.lower().split()
            ratio = difflib.SequenceMatcher(None, q_words, prev_words).ratio()
            if ratio >= DUPLICATE_OVERLAP_THRESHOLD:
                return True
        _recent_questions.append((question, now))
    return False
