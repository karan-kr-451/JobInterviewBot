"""
config - All constants, credentials, and tuning knobs.

This package re-exports every symbol from its submodules so that existing
``from config import X`` statements continue to work without modification.

Configuration is now loaded from config.yaml (with .env fallback for compatibility).
"""

# Version
__version__ = "1.0.0"

# Load configuration from YAML (or .env fallback)
from config.yaml_loader import load_config as _load_config
_load_config()

# Ensure sub-modules are re-read on reload (required for UI settings to take effect)
import importlib as _il
import config.audio, config.llm, config.ollama, config.groq, config.gemini, config.whisper, config.telegram, config.overlay, config.documents
for _m in [config.audio, config.llm, config.ollama, config.groq, config.gemini, config.whisper, config.telegram, config.overlay, config.documents]:
    _il.reload(_m)

# -- Audio ----------------------------------------------------------------------
from config.audio import (                                           # noqa: E402, F401
    SAMPLE_RATE, CHUNK_DURATION, VAD_THRESHOLD, VAD_WIN_SAMPLES,
    RMS_GATE, SPEECH_ONSET_FRAMES, FAST_SILENCE_FRAMES,
    MIN_SPEECH_DURATION, MAX_SPEECH_DURATION,
    AUDIO_QUEUE_MAXSIZE, FINAL_QUEUE_MAXSIZE, GEMINI_QUEUE_MAXSIZE,
    DEVICE_INDEX,
)

# Smart default device selection
# Priority: Stereo Mix (1) > Microphone Array (2) > Default (None)
# User can override in Settings
if DEVICE_INDEX is None:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        
        # Look for Stereo Mix first (best for system audio capture)
        for i, d in enumerate(devices):
            if d.get('max_input_channels', 0) > 0:
                name_lower = d.get('name', '').lower()
                if 'stereo mix' in name_lower or 'what u hear' in name_lower:
                    DEVICE_INDEX = i
                    break
        
        # Fallback to first available input device
        if DEVICE_INDEX is None:
            for i, d in enumerate(devices):
                if d.get('max_input_channels', 0) > 0:
                    DEVICE_INDEX = i
                    break
    except Exception:
        pass  # Will use system default

# -- LLM backend ---------------------------------------------------------------
from config.llm import (                                             # noqa: E402, F401
    LLM_BACKEND, RETRY_MAX_ATTEMPTS, RETRY_BASE_DELAY,
    DUPLICATE_WINDOW_S, DUPLICATE_OVERLAP_THRESHOLD,
)

# -- Ollama ---------------------------------------------------------------------
from config.ollama import (                                          # noqa: E402, F401
    OLLAMA_BASE_URL, OLLAMA_SINGLE_MODEL, OLLAMA_MODELS,
    OLLAMA_NUM_PREDICT_BY_CATEGORY, OLLAMA_NUM_PREDICT,
    OLLAMA_TEMPERATURE, OLLAMA_NUM_THREAD, OLLAMA_NUM_THREAD_BATCH,
    OLLAMA_NUM_CTX, OLLAMA_NUM_CTX_LARGE,
    OLLAMA_KEEP_ALIVE, OLLAMA_REPEAT_PENALTY, OLLAMA_USE_MMAP,
    get_ollama_num_predict, get_ollama_num_ctx, get_ollama_model,
)

# -- Groq -----------------------------------------------------------------------
from config.groq import (                                            # noqa: E402, F401
    GROQ_API_KEY, GROQ_MODELS, GROQ_FALLBACK_MODEL,
    GROQ_WHISPER_MODEL,
    GROQ_MAX_TOKENS_BY_CATEGORY, GROQ_MAX_TOKENS_DEFAULT,
    GROQ_TEMPERATURE, get_groq_max_tokens,
)

# -- Gemini ---------------------------------------------------------------------
from config.gemini import (                                          # noqa: E402, F401
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACKS,
    GENERATION_CONFIGS,
)

# -- Whisper --------------------------------------------------------------------
from config.whisper import (                                         # noqa: E402, F401
    WHISPER_BEAM_SIZE, WHISPER_THREADS, WHISPER_WORKERS,
    WHISPER_NO_SPEECH_THRESHOLD, WHISPER_LOG_PROB_THRESHOLD,
    WHISPER_COMPRESSION_RATIO_THRESHOLD, WHISPER_MIN_WORDS,
    WHISPER_HALLUCINATION_PHRASES,
)

# -- Telegram -------------------------------------------------------------------
from config.telegram import (                                        # noqa: E402, F401
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_QUEUE_SIZE,
    TELEGRAM_SEND_TIMEOUT, TELEGRAM_POLL_TIMEOUT,
)

# -- Overlay --------------------------------------------------------------------
from config.overlay import (                                         # noqa: E402, F401
    OVERLAY_WIDTH, OVERLAY_HEIGHT, OVERLAY_X, OVERLAY_Y,
    OVERLAY_ALPHA, OVERLAY_FONT, OVERLAY_FONT_SZ, OVERLAY_WRAP,
    HOTKEY_HIDE, HOTKEY_QUIT, HOTKEY_FULLSCREEN, HOTKEY_MINIMIZE,
)

# -- Documents ------------------------------------------------------------------
from config.documents import DOCS_FOLDER, LOG_FILE                   # noqa: E402, F401

# -- Backward-compat alias expected by groq_client.py ---------------------------
# The old config.py never defined GROQ_SPECULATIVE_MODEL but groq_client.py
# imported it.  Define a safe fallback so the import doesn't break.
GROQ_SPECULATIVE_MODEL = GROQ_FALLBACK_MODEL
