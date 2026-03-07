"""
audio.capture - Audio stream capture, device management, and stream restart loop.
"""

import sys
import time
import threading
import traceback
from collections import deque

import numpy as np

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    print("ERROR: sounddevice not installed. Run: pip install sounddevice")

from config.audio import SAMPLE_RATE, CHUNK_DURATION, DEVICE_INDEX, AUDIO_QUEUE_MAXSIZE
from audio.watchdog import watchdog, _last_audio_time

# Use deque instead of queue.Queue - it's thread-safe for append/popleft
# and doesn't use locks, making it safe to use from C-level audio callbacks
# Note: maxlen=None for unbounded deque (maxlen=0 would create empty deque)
audio_queue = deque(maxlen=None if AUDIO_QUEUE_MAXSIZE == 0 else AUDIO_QUEUE_MAXSIZE)
_actual_chunk_duration = CHUNK_DURATION


def audio_callback(indata, frames, time_info, status):
    """
    PortAudio callback - pushes audio chunks to the queue.
    
    CRITICAL: This runs in a C-level audio thread. ABSOLUTE MINIMUM.
    Only append to deque - nothing else.
    """
    try:
        audio_queue.append(indata)
    except:
        pass


def list_audio_devices():
    """Print all available audio devices."""
    if not SD_AVAILABLE:
        print("sounddevice not available")
        return
    print("\n" + "=" * 50)
    print("[LISTEN] AVAILABLE AUDIO DEVICES")
    print("=" * 50)
    print(sd.query_devices())
    print("=" * 50)
    print("  Set DEVICE_INDEX in config.py:")
    print("   Windows: 'Stereo Mix' or 'CABLE Output'")
    print("   Mac:     'BlackHole' or 'Soundflower'")
    print("=" * 50 + "\n")


def _open_stream(chunk_duration: float):
    return sd.InputStream(
        device=DEVICE_INDEX,
        callback=audio_callback,
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=int(SAMPLE_RATE * chunk_duration),
        dtype=np.float32,
        latency="low",
    ), chunk_duration


def _try_open_stream():
    """Try to open audio stream with various configurations."""
    global _actual_chunk_duration
    
    # Try different block sizes
    durations = [CHUNK_DURATION, 0.3, 0.5, 0.2, 0.15]
    
    for duration in durations:
        try:
            stream, dur = _open_stream(duration)
            _actual_chunk_duration = dur
            if dur != CHUNK_DURATION:
                print(f"  blocksize {CHUNK_DURATION}s rejected - using {dur}s")
            return stream
        except Exception as e:
            blocksize = int(SAMPLE_RATE * duration)
            print(f"  blocksize {blocksize} failed: {e}")
    
    # If all block sizes fail, provide helpful error message
    error_msg = f"Cannot open audio device {DEVICE_INDEX}"
    
    # Suggest alternatives
    print("\n" + "=" * 60)
    print("  AUDIO DEVICE ERROR")
    print("=" * 60)
    print(f"Device {DEVICE_INDEX} (Stereo Mix) cannot be opened.")
    print("\nPossible causes:")
    print("  1. Stereo Mix is disabled in Windows")
    print("  2. Another application is using the device")
    print("  3. Audio driver issue")
    print("\nSolutions:")
    print("  1. Enable Stereo Mix:")
    print("     Right-click speaker icon -> Sounds -> Recording tab")
    print("     Right-click empty space -> Show Disabled Devices")
    print("     Enable 'Stereo Mix' and set as default")
    print("\n  2. Try a different device:")
    print("     - Device 6: Stereo Mix (DirectSound)")
    print("     - Device 12: Stereo Mix (WASAPI)")
    print("     - Device 18: Stereo Mix (WDM-KS)")
    print("\n  3. Use Virtual Audio Cable:")
    print("     Download from: https://vb-audio.com/Cable/")
    print("\n  4. Close other audio applications")
    print("=" * 60 + "\n")
    
    raise RuntimeError(error_msg)


def run_stream_with_restart(overlay=None, max_restarts: int = 20):
    """
    Open stream, run until KeyboardInterrupt or fatal error.
    Restarts on ANY exception up to max_restarts times.
    """
    from audio.vad import transcribe_loop

    restarts      = 0
    vad_started   = False
    stop_watchdog = threading.Event()
    restart_event = threading.Event()

    wd = threading.Thread(target=watchdog, args=(restart_event, stop_watchdog),
                          daemon=True, name="stream-watchdog")
    wd.start()

    while restarts <= max_restarts:
        restart_event.clear()
        _last_audio_time[0] = time.perf_counter()

        try:
            stream = _try_open_stream()
        except Exception as e:
            print(f"\n  Cannot open device: {e}")
            print("   Check DEVICE_INDEX in config.py")
            stop_watchdog.set()
            return

        print(f"  Stream opened (attempt {restarts+1})")

        try:
            with stream:
                if not vad_started:
                    threading.Thread(
                        target=transcribe_loop,
                        args=(audio_queue, overlay, _actual_chunk_duration),
                        daemon=True, name="vad-loop"
                    ).start()
                    vad_started = True

                if overlay:
                    overlay.set_status("[LISTEN]  Listening...")

                while not restart_event.is_set():
                    time.sleep(0.5)

                if restart_event.is_set():
                    print("  Watchdog restart - reopening stream...")

        except KeyboardInterrupt:
            stop_watchdog.set()
            raise

        except Exception as e:
            restarts += 1
            print(f"\nWARNING: Stream error (restart {restarts}/{max_restarts}):")
            traceback.print_exc()

        time.sleep(1.0)

    stop_watchdog.set()
    print("  Too many restarts - giving up")
    print("   Try: set DEVICE_INDEX to a different device, or use VoiceMeeter")
