"""
config.audio - Audio capture and VAD configuration.
"""

import os

# =============================================================================
# AUDIO
# =============================================================================

SAMPLE_RATE    = 16000
CHUNK_DURATION = 0.1     # 0.1s per callback block = 1600 samples

# -- Silero VAD -----------------------------------------------------------------
VAD_THRESHOLD   = 0.35
VAD_WIN_SAMPLES = 512    # Silero window size - do not change

# -- Noise gate -----------------------------------------------------------------
RMS_GATE = 0.002

# -- Speech onset --------------------------------------------------------------
SPEECH_ONSET_FRAMES = 2

# -- Silence detection ---------------------------------------------------------
FAST_SILENCE_FRAMES = 10  # Reduced from 15 for faster response (1.0s instead of 1.5s)

# -- Speech duration filters ---------------------------------------------------
MIN_SPEECH_DURATION = 1.5
MAX_SPEECH_DURATION = 45

# -- Pipeline queue sizes ------------------------------------------------------
AUDIO_QUEUE_MAXSIZE  = 0   # unbounded - zero audio drops
FINAL_QUEUE_MAXSIZE  = 4
GEMINI_QUEUE_MAXSIZE = 4


def _resolve_device_index():
    """
    Priority: (1) DEVICE_INDEX from .env, (2) auto-detect Stereo Mix, (3) None.
    """
    raw = os.environ.get("DEVICE_INDEX", "").strip()
    if raw.lstrip("-").isdigit():
        idx = int(raw)
        if idx >= 0:
            return idx
    try:
        import sounddevice as _sd
        for i, d in enumerate(_sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                n = d.get("name", "").lower()
                if "stereo mix" in n or "what u hear" in n or "wave out mix" in n:
                    print(f"[Config] Auto-detected Stereo Mix at device index {i}: {d['name']}")
                    return i
    except Exception:
        pass
    print("[Config] DEVICE_INDEX: using OS default input device")
    return None


DEVICE_INDEX = _resolve_device_index()
