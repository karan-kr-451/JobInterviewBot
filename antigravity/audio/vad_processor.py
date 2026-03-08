"""
audio/vad_processor.py - Voice Activity Detection (Silero VAD + RMS fallback).

VADProcessor runs in its own thread, consuming raw audio chunks from
audio_queue, classifying them as speech/silence, and enqueuing complete
utterances (as float32 numpy arrays) into the transcription queue.

Detection logic:
  1. RMS gate      – fast pre-filter: if RMS < rms_gate → silence, skip VAD
  2. Silero VAD    – neural model for accurate voice detection
  3. Onset counter – require N consecutive voiced frames to start recording
  4. Silence trail – end utterance after M consecutive silent frames
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

import numpy as np

from audio.audio_queue import audio_queue
from core.event_bus import get_bus
from core.logger import get_logger
from core.state_manager import get_state
from core.watchdog import Watchdog

log = get_logger("audio.vad")

# ── Silero VAD lazy globals ───────────────────────────────────────────────────
_vad_model: Optional[object] = None
_vad_loaded:  bool = False
_vad_loading: bool = False
_vad_lock     = threading.Lock()
SILERO_AVAILABLE = False


def load_vad(lazy: bool = True) -> bool:
    """
    Load Silero VAD model. Returns True on success (or RMS-only fallback).
    If lazy=True, loads in a background thread (non-blocking).
    """
    global _vad_model, _vad_loaded, _vad_loading, SILERO_AVAILABLE

    with _vad_lock:
        if _vad_loaded:
            return True
        if _vad_loading:
            return True

    def _do_load():
        global _vad_model, _vad_loaded, _vad_loading, SILERO_AVAILABLE
        with _vad_lock:
            _vad_loading = True
        try:
            import os
            import torch
            log.info("Loading Silero VAD…")
            hub_dir = os.path.join(os.path.expanduser("~"), ".cache", "torch", "hub")
            os.makedirs(hub_dir, exist_ok=True)
            torch.hub.set_dir(hub_dir)
            import socket
            socket.setdefaulttimeout(30)
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            with _vad_lock:
                _vad_model    = model
                _vad_loaded   = True
                _vad_loading  = False
                SILERO_AVAILABLE = True
            get_state().update(vad_mode="silero")
            log.info("[OK] Silero VAD loaded")
        except Exception as exc:
            with _vad_lock:
                _vad_loading = False
                _vad_loaded  = True   # Don't retry
            log.warning("Silero VAD unavailable (%s) – using RMS-only detection", exc)
            get_state().update(vad_mode="rms-only")

    if lazy:
        threading.Thread(target=_do_load, daemon=True, name="vad-loader").start()
        return True
    else:
        _do_load()
        return True


def _is_voiced(audio_float: np.ndarray, cfg) -> bool:
    """Return True if the audio chunk likely contains speech."""
    # 1. RMS gate (cheap)
    rms = float(np.sqrt(np.mean(audio_float ** 2)))
    if rms <= cfg.rms_gate:
        return False

    # 2. RMS-only mode if Silero not loaded
    if _vad_model is None:
        return True

    # 3. Silero VAD
    try:
        import torch
        peak = float(np.max(np.abs(audio_float)))
        if peak < 1e-6:
            return False
        gain       = min(0.3 / peak, 10.0)
        audio_norm = (audio_float * gain).astype(np.float32)
        win        = int(cfg.sample_rate * 0.096)   # 96 ms windows
        n          = len(audio_norm)
        for start in range(0, n - win + 1, win):
            window = torch.from_numpy(audio_norm[start:start + win].copy())
            prob   = float(_vad_model(window, cfg.sample_rate).item())
            if prob >= cfg.vad_threshold:
                return True
        return False
    except Exception as exc:
        log.debug("VAD inference error: %s", exc)
        return True   # Fail open


class VADProcessor:
    """
    Runs in its own thread. Reads from audio_queue,
    detects speech boundaries, and publishes complete utterances
    via the event bus ("transcript_audio_ready", payload={"audio": np.ndarray}).
    """

    def __init__(self, audio_cfg, transcription_queue, watchdog: Optional[Watchdog] = None):
        self._cfg        = audio_cfg
        self._tr_queue   = transcription_queue
        self._watchdog   = watchdog
        self._bus        = get_bus()

    def run(self) -> None:
        """Main VAD loop – runs until audio_queue is poisoned (None) or exception."""
        cfg = self._cfg
        log.info(
            "VAD loop started | onset=%d frames | silence=%d frames | "
            "rms_gate=%.4f | vad_thresh=%.2f",
            cfg.speech_onset_frames, cfg.fast_silence_frames,
            cfg.rms_gate, cfg.vad_threshold,
        )

        speech_buffer:      list = []
        is_speaking:        bool = False
        onset_counter:      int  = 0
        consecutive_silent: int  = 0

        while True:
            # ── Pull chunk (lock-free deque popleft) ──────────────────────
            try:
                chunk = audio_queue.popleft()
            except IndexError:
                time.sleep(0.05)
                continue

            if chunk is None:     # Shutdown sentinel
                break

            # ── Update watchdog ───────────────────────────────────────────
            if self._watchdog:
                self._watchdog.reset_audio()
            get_state().update(last_audio_time=time.perf_counter())

            try:
                audio_float = chunk.flatten().astype(np.float32)
                voiced      = _is_voiced(audio_float, cfg)

                # Peak-normalise for speech buffer
                peak = float(np.max(np.abs(audio_float)))
                audio_norm = audio_float * min(0.3 / peak, 8.0) if peak > 1e-6 else audio_float

                if not is_speaking:
                    if voiced:
                        onset_counter += 1
                        if onset_counter >= cfg.speech_onset_frames:
                            is_speaking        = True
                            consecutive_silent = 0
                            sys.stdout.write("\n[REC] Recording…")
                            sys.stdout.flush()
                            self._bus.publish("status_update", {"message": "[REC] Recording…", "recording": True})
                    else:
                        onset_counter = 0

                else:
                    speech_buffer.extend(audio_norm)
                    dur = len(speech_buffer) / cfg.sample_rate

                    if voiced:
                        consecutive_silent = 0
                        if dur > cfg.max_speech_duration:
                            log.warning("Max speech duration reached – flushing utterance")
                            self._flush(speech_buffer)
                            speech_buffer = []; is_speaking = False
                            onset_counter = 0; consecutive_silent = 0
                    else:
                        consecutive_silent += 1
                        sys.stdout.write(
                            f"\r[PAUSE] Silence {consecutive_silent}/{cfg.fast_silence_frames}f [{dur:.1f}s]  "
                        )
                        sys.stdout.flush()

                        if consecutive_silent >= cfg.fast_silence_frames:
                            if dur >= cfg.min_speech_duration:
                                log.info("Utterance done – %.1fs", dur)
                                self._flush(speech_buffer)
                            else:
                                log.debug("Utterance too short (%.1fs < %.1fs) – discarded",
                                          dur, cfg.min_speech_duration)
                            speech_buffer = []; is_speaking = False
                            onset_counter = 0; consecutive_silent = 0
                            self._bus.publish("status_update", {"message": "[LISTEN] Listening…", "recording": False})

            except Exception as exc:
                log.warning("VAD processing error (skipping chunk): %s", exc)
                continue

    def _flush(self, buffer: list) -> None:
        """Enqueue a completed utterance for transcription."""
        audio_np = np.array(buffer, dtype=np.float32)
        try:
            self._tr_queue.put(audio_np, block=True, timeout=5)
        except Exception:
            log.warning("Transcription queue full – utterance dropped")
