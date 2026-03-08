"""
audio/audio_capture.py - Audio stream capture with auto-restart on device error.

AudioCapture opens a sounddevice.InputStream with a minimal C-level callback
(appends to a deque – absolutely nothing else). The stream is managed by
run_stream() which restarts automatically on transient hardware errors.

Thread model:
  Audio callback  – C-level portaudio thread (cannot hold Python GIL safely)
  VAD thread      – reads from audio_queue (started separately in vad_processor)
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from collections import deque
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False

from core.logger import get_logger
from core.state_manager import get_state
from core.watchdog import Watchdog

log = get_logger("audio.capture")

# ── Shared audio queue (lock-free deque) ──────────────────────────────────────
# Maxlen=500 prevents unbounded growth during LLM generation pauses (~50s of audio).
audio_queue: deque = deque(maxlen=500)


class AudioCapture:
    """
    Opens a sounddevice InputStream and fills audio_queue with float32 chunks.

    Usage:
        cap = AudioCapture(cfg.audio)
        cap.run_with_restart(overlay=overlay, max_restarts=999)
    """

    def __init__(self, audio_cfg, watchdog: Optional[Watchdog] = None) -> None:
        self._cfg      = audio_cfg
        self._watchdog = watchdog
        self._chunk_duration = audio_cfg.chunk_duration

    # ── Public ────────────────────────────────────────────────────────────────

    def run_with_restart(self, overlay=None, max_restarts: int = 999) -> None:
        """
        Open the audio stream. On any exception, wait 1 s and retry.
        Runs in the calling thread (blocking).
        The VAD thread must be started separately before calling this.
        """
        if not SD_AVAILABLE:
            log.error("sounddevice not installed – audio pipeline disabled.")
            return

        restarts = 0
        while restarts <= max_restarts:
            try:
                stream = self._open_stream()
            except RuntimeError as exc:
                log.error("Cannot open audio device: %s", exc)
                return   # Fatal – device doesn't exist at all

            log.info("Audio stream opened (attempt %d)", restarts + 1)
            if overlay:
                try:
                    overlay.set_status("[LISTEN] Listening…")
                except Exception:
                    pass
            get_state().update(last_audio_time=time.perf_counter())

            try:
                with stream:
                    while True:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                restarts += 1
                log.warning(
                    "Stream error (restart %d/%d): %s",
                    restarts, max_restarts, exc,
                )
                traceback.print_exc()

            time.sleep(1.0)

        log.error("Too many audio restarts (%d) – giving up.", max_restarts)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """
        CRITICAL: Runs in C-level PortAudio thread.
        Must do ABSOLUTELY NOTHING except append to the deque.
        No Python objects, no locks, no imports.
        """
        try:
            audio_queue.append(indata.copy())
        except Exception:
            pass

    def _open_stream(self):
        """Try several block-sizes until one succeeds."""
        durations = [self._chunk_duration, 0.3, 0.2, 0.5, 0.15]
        device    = self._cfg.device_index

        for dur in durations:
            blocksize = int(self._cfg.sample_rate * dur)
            try:
                stream = sd.InputStream(
                    device=device,
                    callback=self._audio_callback,
                    channels=1,
                    samplerate=self._cfg.sample_rate,
                    blocksize=blocksize,
                    dtype=np.float32,
                    latency="low",
                )
                if dur != self._chunk_duration:
                    log.info("Using blocksize %.2fs (%.0f samples) instead of %.2fs",
                             dur, blocksize, self._chunk_duration)
                self._chunk_duration = dur
                return stream
            except Exception as exc:
                log.debug("blocksize %d failed: %s", blocksize, exc)

        dev_str = f"device {device}" if device is not None else "default device"
        self._print_device_help(device)
        raise RuntimeError(f"Cannot open {dev_str} with any blocksize")

    @staticmethod
    def _print_device_help(device) -> None:
        print("\n" + "=" * 60)
        print("  AUDIO DEVICE ERROR")
        print("=" * 60)
        print(f"  Device {device!r} cannot be opened.")
        print("\n  Possible causes:")
        print("    1. Stereo Mix / CABLE Output is disabled")
        print("    2. Another application has exclusive access")
        print("    3. Audio driver issue")
        print("\n  Solutions:")
        print("    1. Enable Stereo Mix: right-click speaker → Sounds → Recording")
        print("    2. Try a different DEVICE_INDEX in .env")
        print("    3. Install VB-Audio Cable: https://vb-audio.com/Cable/")
        print("=" * 60 + "\n")
