"""
transcription.groq_whisper - Groq Whisper API transcription.

WHY: Local Whisper small.en takes ~2000ms and mishears questions
     ('What does React?' instead of 'What is React?').
     Groq's whisper-large-v3-turbo runs in ~300ms with much higher accuracy.

FREE TIER:  7,200 req/day, 28,800s audio/day (enough for 8h of interviews)
"""

import io
import wave
import time
import threading
import soundfile as sf
import gc

import numpy as np
import requests

from config.groq import GROQ_API_KEY, GROQ_WHISPER_MODEL, GROQ_WHISPER_FALLBACKS
from config.audio import SAMPLE_RATE
from transcription.filters import is_hallucination
from core.http_utils import (
    smart_gc_protection, create_fresh_session, 
    close_response_safely, _http_lock
)
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

GROQ_WHISPER_AVAILABLE = False

# Thread-local requests session for connection reuse
_tls = threading.local()


def _get_session() -> requests.Session:
    if not hasattr(_tls, "session"):
        _tls.session = requests.Session()
        _tls.session.trust_env = False  # CRITICAL: Disable .netrc to prevent os.environ race
        _tls.session.headers.update({
            "Authorization": f"Bearer {GROQ_API_KEY}",
        })
    return _tls.session


def check_groq_whisper() -> bool:
    """Check if Groq Whisper API is available. Returns True if key is set."""
    global GROQ_WHISPER_AVAILABLE
    if not GROQ_API_KEY:
        print("  Groq Whisper: GROQ_API_KEY not set - using local Whisper")
        return False
    GROQ_WHISPER_AVAILABLE = True
    print(f"Groq Whisper available ({GROQ_WHISPER_MODEL})")
    return True


def _audio_to_wav_bytes(audio_np: np.ndarray,
                        sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert float32 numpy array to WAV byte buffer."""
    # Normalize to prevent clipping
    peak = float(np.max(np.abs(audio_np)))
    if peak > 0.0:
        audio_np = audio_np * min(0.95 / peak, 1.0)

    audio_int16 = (audio_np * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def transcribe_groq(audio_np: np.ndarray, prompt: str = None) -> str:
    """
    Transcribe audio via Groq Whisper API.
    Optional 'prompt' help Whisper with technical terms, spelling, etc.
    
    FIX: Use gc_safe_http() to prevent access violations during HTTP operations.
    """
    if not GROQ_API_KEY:
        return ""

    if audio_np is None or len(audio_np) < SAMPLE_RATE * 0.3:
        return ""

    # Pre-filter: skip silence
    rms = float(np.sqrt(np.mean(audio_np ** 2)))
    if rms < 0.003:
        return ""

    # Convert numpy to WAV in memory
    buf = io.BytesIO()
    try:
        # Normalize to [-1, 1] if not already
        if audio_np.dtype != np.float32:
            audio_np = audio_np.astype(np.float32)

        sf.write(buf, audio_np, SAMPLE_RATE, format="WAV")
        buf.seek(0)
    except Exception as e:
        print(f"[groq_whisper] audio conversion error: {e}")
        return ""

    default_prompt = "Transcribe the following interview question precisely, including technical terms."
    final_prompt   = f"{default_prompt} {prompt}" if prompt else default_prompt

    t0 = time.perf_counter()

    # Explicitly disable GC before high-risk operation
    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
        
    try:
        # Use the global HTTP lock to prevent OpenSSL race conditions on Windows
        with _http_lock:
            # Session context manager ensures proper pool cleanup on Windows
            with create_fresh_session({"Authorization": f"Bearer {GROQ_API_KEY}"}) as session:
                models_to_try = [GROQ_WHISPER_MODEL] + GROQ_WHISPER_FALLBACKS
                files = {"file": ("audio.wav", buf, "audio/wav")}
                data = {
                    "language": "en",
                    "prompt": final_prompt,
                    "response_format": "text",
                }
                
                for attempt, current_model in enumerate(models_to_try):
                    resp = None
                    try:
                        # Reset buffer for retry (crucial for BytesIO pointer safety)
                        buf.seek(0)
                        data["model"] = current_model
                        
                        resp = session.post(
                            GROQ_WHISPER_URL,
                            files=files,
                            data=data,
                            timeout=30,
                        )
                        resp.raise_for_status()
                        
                        text = resp.text.strip() if resp.text else ""
                        close_response_safely(resp)
                        resp = None
                        
                        ms = (time.perf_counter() - t0) * 1000
                        
                        if not text:
                            print(f"[Groq Whisper {ms:.0f}ms] empty response from {current_model}")
                            return ""

                        if is_hallucination(text):
                            print(f"[Groq Whisper {ms:.0f}ms] hallucination on {current_model}: '{text}'")
                            return ""

                        fallback_info = f" ({current_model})" if attempt > 0 else ""
                        print(f"[Groq Whisper{fallback_info} {ms:.0f}ms] '{text[:100]}'")
                        return text

                    except requests.exceptions.RequestException as e:
                        close_response_safely(resp)
                        resp = None
                        if attempt < len(models_to_try) - 1:
                            print(f"[Groq Whisper] {type(e).__name__} on {current_model}, falling back...")
                            time.sleep(0.5)
                            continue
                        else:
                            raise e
                    finally:
                        close_response_safely(resp)

    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        print(f"[Groq Whisper {ms:.0f}ms] {type(e).__name__}: {e}")
        return ""
    finally:
        # Keep GC disabled (as per core/crash_prevention policy)
        pass