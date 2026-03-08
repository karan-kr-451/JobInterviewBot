"""
llm/response_cache.py — LRUCache for LLM responses.

Prevents the LLM from generating identical responses for questions
it has already answered in this session.
Uses cachetools.LRUCache(maxsize=128) to enforce eviction (Rule 2).
"""

from __future__ import annotations

import logging
from cachetools import LRUCache
from antigravity.core.safe_lock import SafeLock

logger = logging.getLogger(__name__)

# O(1) bounded LRU cache for responses
_response_cache: LRUCache = LRUCache(maxsize=128)
_cache_lock = SafeLock("ResponseCache", timeout=2.0)


def get_cached_response(question: str) -> str | None:
    """Return cached response for a question, or None."""
    # Use first 100 chars as robust dedup key
    key = question[:100].strip().lower()
    with _cache_lock:
        response = _response_cache.get(key)
        if response:
            logger.debug("[CACHE] Cache hit for: %s...", key[:20])
        return response


def set_cached_response(question: str, response: str) -> None:
    """Cache an LLM response."""
    if not question or not response:
        return
        
    key = question[:100].strip().lower()
    with _cache_lock:
        _response_cache[key] = response
