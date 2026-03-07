"""
audio.watchdog - Stream watchdog and timer reset.
"""

import time
import threading

STREAM_WATCHDOG_TIMEOUT = 8.0

_last_audio_time = [time.perf_counter()]
_stream_alive    = [True]


def reset_watchdog_timer():
    """Reset the watchdog timer after a long blocking operation (e.g. LLM response)."""
    _last_audio_time[0] = time.perf_counter()


def watchdog(restart_event: threading.Event, stop_event: threading.Event):
    """
    Monitors audio_callback activity. If no audio arrives for
    STREAM_WATCHDOG_TIMEOUT seconds, signals a stream restart.
    """
    while not stop_event.is_set():
        time.sleep(1.0)
        gap = time.perf_counter() - _last_audio_time[0]
        if gap > STREAM_WATCHDOG_TIMEOUT:
            print(f"\nWARNING: Watchdog: no audio for {gap:.1f}s - requesting stream restart")
            restart_event.set()
