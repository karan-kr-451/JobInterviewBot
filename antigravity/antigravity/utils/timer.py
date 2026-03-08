"""
utils/timer.py — Lightweight timeout/timer helper.

Used to avoid blocking calls from hanging forever if the underlying
library doesn't fully respect its own timeout parameters.
"""

from __future__ import annotations

import time


class Timer:
    """Simple elapsed time tracker."""
    
    def __init__(self) -> None:
        self._start = time.time()
        
    def reset(self) -> None:
        self._start = time.time()
        
    @property
    def elapsed(self) -> float:
        return time.time() - self._start
        
    def has_exceeded(self, seconds: float) -> bool:
        return self.elapsed > seconds
