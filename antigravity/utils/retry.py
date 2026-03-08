"""
utils/retry.py - Retry decorators and helpers with exponential back-off.

Usage:
    from utils.retry import retry_on_exception

    @retry_on_exception(max_attempts=3, base_delay=1.0, exceptions=(RuntimeError,))
    def call_api():
        ...

    # Or as a function:
    result = retry_call(my_fn, arg1, kwarg=val, max_attempts=3)
"""

from __future__ import annotations

import functools
import time
import traceback
from typing import Callable, Tuple, Type


def retry_on_exception(
    max_attempts:  int   = 3,
    base_delay:    float = 1.0,
    max_delay:     float = 30.0,
    backoff_factor: float = 2.0,
    exceptions:    Tuple[Type[Exception], ...] = (Exception,),
    log_attempts:  bool   = True,
) -> Callable:
    """
    Decorator that retries the wrapped function on specified exceptions.

    Args:
        max_attempts:   Total number of attempts (including first try).
        base_delay:     Initial wait between retries in seconds.
        max_delay:      Maximum wait between retries in seconds.
        backoff_factor: Multiplier applied to delay after each failure.
        exceptions:     Tuple of exception types that trigger a retry.
        log_attempts:   Whether to print retry info.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= max_attempts:
                        if log_attempts:
                            print(f"[retry] {fn.__name__} failed after {max_attempts} "
                                  f"attempts: {exc}")
                        raise
                    if log_attempts:
                        print(f"[retry] {fn.__name__} attempt {attempt}/{max_attempts} "
                              f"failed ({type(exc).__name__}: {exc}). "
                              f"Retrying in {delay:.1f}s…")
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
        return wrapper
    return decorator


def retry_call(
    fn:            Callable,
    *args,
    max_attempts:  int   = 3,
    base_delay:    float = 1.0,
    max_delay:     float = 30.0,
    backoff_factor: float = 2.0,
    exceptions:    Tuple[Type[Exception], ...] = (Exception,),
    **kwargs,
):
    """
    Call fn(*args, **kwargs) with retry logic.
    Returns the result on success; re-raises the last exception on exhaustion.
    """
    delay = base_delay
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except exceptions as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            print(f"[retry] {getattr(fn, '__name__', repr(fn))} "
                  f"attempt {attempt}/{max_attempts} failed. "
                  f"Retrying in {delay:.1f}s…")
            time.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)
    raise last_exc  # type: ignore[misc]


def retry_api_call(fn: Callable, *args, name: str = "", **kwargs) -> str | None:
    """
    Convenience wrapper for LLM/API calls returning str.
    Returns None on all failures instead of raising.
    """
    try:
        return retry_call(fn, *args, max_attempts=2, base_delay=2.0, **kwargs)
    except Exception as exc:
        label = name or getattr(fn, "__name__", repr(fn))
        print(f"[retry_api] {label} ultimately failed: {exc}")
        try:
            from core.logger import get_logger
            get_logger("retry").error("%s ultimately failed: %s\n%s",
                                      label, exc, traceback.format_exc())
        except Exception:
            pass
        return None
