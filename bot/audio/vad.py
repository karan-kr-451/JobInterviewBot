"""
audio.vad - Voice Activity Detection (Silero VAD + RMS fallback).
"""

import sys
import time
import queue

import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("ERROR: torch not installed. Run: pip install torch")

from config.audio import (
    SAMPLE_RATE, VAD_THRESHOLD, VAD_WIN_SAMPLES,
    MIN_SPEECH_DURATION, MAX_SPEECH_DURATION,
    RMS_GATE, SPEECH_ONSET_FRAMES, FAST_SILENCE_FRAMES,
)
from audio.filters import NoiseFilter
noise_filter = NoiseFilter()

from transcription.worker import enqueue_final
import transcription.worker as _tr

vad_model     = None
VAD_AVAILABLE = False
_vad_loading  = False  # NEW: Track if loading in progress
_vad_loaded   = False  # NEW: Track if already loaded


def load_vad(lazy: bool = False, force: bool = False) -> bool:
    """
    Load Silero VAD. Returns True always - falls back to RMS-only if Silero fails.
    
    Args:
        lazy: If True, load in background thread (non-blocking)
        force: If True, reload even if already loaded
    """
    global vad_model, VAD_AVAILABLE, _vad_loading, _vad_loaded
    
    if not TORCH_AVAILABLE:
        print("[WARN] torch not available - using RMS-only voice detection")
        VAD_AVAILABLE = True
        return True
    
    # Skip if already loaded (unless force=True)
    if _vad_loaded and not force:
        print("[OK] Silero VAD already loaded (skipping)")
        VAD_AVAILABLE = True
        return True
    
    # Skip if currently loading
    if _vad_loading:
        print("[WAIT] Silero VAD already loading (skipping)")
        VAD_AVAILABLE = True
        return True
    
    def _load():
        global vad_model, VAD_AVAILABLE, _vad_loading, _vad_loaded
        
        _vad_loading = True
        
        try:
            print("Loading Silero VAD...")
            import os as _os
            hub_dir = _os.path.join(_os.path.expanduser("~"), ".cache", "torch", "hub")
            _os.makedirs(hub_dir, exist_ok=True)
            torch.hub.set_dir(hub_dir)

            # Set timeout to prevent hanging
            import socket
            socket.setdefaulttimeout(30)
            
            vad_model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            
            VAD_AVAILABLE = True
            _vad_loaded = True
            print("[OK] Silero VAD loaded")
            return True
            
        except MemoryError as e:
            print(f"[WARN] Silero VAD: Out of memory ({e})")
            print("   System RAM may be insufficient. Using RMS-only detection.")
            vad_model = None
            VAD_AVAILABLE = True
            _vad_loaded = False
            return True
            
        except Exception as e:
            print(f"[WARN] Silero VAD unavailable ({e})")
            print("   Falling back to RMS-only voice detection - pipeline continues.")
            vad_model = None
            VAD_AVAILABLE = True
            _vad_loaded = False
            return True
        
        finally:
            _vad_loading = False
    
    if lazy:
        import threading
        thread = threading.Thread(target=_load, daemon=True, name="vad-loader")
        thread.start()
        VAD_AVAILABLE = True  # Optimistically set to True
        return True
    else:
        return _load()


def _is_voiced(audio_float: np.ndarray) -> bool:
    """Check if audio chunk contains voiced speech."""
    rms = float(np.sqrt(np.mean(audio_float ** 2)))
    if rms <= RMS_GATE:
        return False
    if vad_model is None:
        return True

    peak = float(np.max(np.abs(audio_float)))
    if peak > 1e-6:
        norm_gain = min(0.3 / peak, 10.0)
        audio_norm = audio_float * norm_gain
    else:
        return False

    n = len(audio_norm)
    for w in range(0, n - VAD_WIN_SAMPLES + 1, VAD_WIN_SAMPLES):
        window = torch.from_numpy(audio_norm[w : w + VAD_WIN_SAMPLES].copy())
        if float(vad_model(window, SAMPLE_RATE).item()) >= VAD_THRESHOLD:
            return True
    return False


def transcribe_loop(audio_queue: queue.Queue, overlay=None,
                    actual_chunk_duration: float = 0.1):
    """Main VAD loop - detects speech and enqueues utterances for transcription."""
    if not VAD_AVAILABLE:
        print("[VAD] not available")
        return

    print("\n[LISTEN] VAD loop started...")
    vad_mode = "Silero" if vad_model is not None else "RMS-only (Silero unavailable)"
    print(f"   mode: {vad_mode} | onset: {SPEECH_ONSET_FRAMES}f ({SPEECH_ONSET_FRAMES*actual_chunk_duration:.2f}s) | "
          f"silence: {FAST_SILENCE_FRAMES}f | "
          f"RMS {RMS_GATE} VAD {VAD_THRESHOLD}")

    speech_buffer:      list = []
    is_speaking:        bool = False
    onset_counter:      int  = 0
    consecutive_silent: int  = 0

    while True:
        # Use popleft() for deque (lock-free, thread-safe)
        try:
            chunk = audio_queue.popleft()
            # PING health checker every 20 chunks to avoid overhead
            try:
                from core.enterprise_crash_prevention import health_checker
                health_checker.ping("vad-loop")
            except:
                pass
        except IndexError:
            # Deque is empty - wait a bit and try again
            time.sleep(0.1)
            continue

        try:
            # Apply Noise Filter (moved from audio callback for stability)
            audio_raw   = chunk.flatten().astype(np.float32)
            audio_float = noise_filter.apply(audio_raw).astype(np.float32)
            
            voiced      = _is_voiced(audio_float)

            peak = float(np.max(np.abs(audio_float)))
            if peak > 1e-6:
                audio_norm = audio_float * min(0.3 / peak, 8.0)
            else:
                audio_norm = audio_float

            if not is_speaking:
                if voiced:
                    onset_counter += 1
                    if onset_counter >= SPEECH_ONSET_FRAMES:
                        is_speaking        = True
                        consecutive_silent = 0
                        if sys.stdout: sys.stdout.write(f"\n[REC] Recording"); sys.stdout.flush()
                        if overlay:
                            overlay.set_status("[REC] Recording...", recording=True)
                else:
                    onset_counter = 0
            else:
                speech_buffer.extend(audio_norm)

                if voiced:
                    consecutive_silent = 0
                    if len(speech_buffer) > SAMPLE_RATE * MAX_SPEECH_DURATION:
                        print("\nWARNING: Max duration - flushing")
                        _tr.t_speech_end = time.perf_counter()
                        enqueue_final(np.array(speech_buffer, dtype=np.float32))
                        speech_buffer = []; is_speaking = False
                        onset_counter = 0; consecutive_silent = 0
                else:
                    consecutive_silent += 1
                    dur = len(speech_buffer) / SAMPLE_RATE
                    if sys.stdout:
                        sys.stdout.write(f"\r[PAUSE] Silence {consecutive_silent}/{FAST_SILENCE_FRAMES}f [{dur:.1f}s]  ")
                        sys.stdout.flush()

                    if consecutive_silent >= FAST_SILENCE_FRAMES:
                        print(f"\n[OK] Utterance done - {dur:.1f}s")
                        if len(speech_buffer) >= SAMPLE_RATE * MIN_SPEECH_DURATION:
                            _tr.t_speech_end = time.perf_counter()
                            enqueue_final(np.array(speech_buffer, dtype=np.float32))
                        else:
                            print(f"[WARN] Too short ({dur:.1f}s < {MIN_SPEECH_DURATION}s) - discarded")

                        speech_buffer = []; is_speaking = False
                        onset_counter = 0; consecutive_silent = 0
                        if overlay:
                            overlay.set_status("[LISTEN] Listening...")
        
        except Exception as e:
            # Error processing chunk - skip and continue
            print(f"\n[VAD] Error processing chunk: {e}")
            continue
