"""
transcription.whisper_model - Whisper model loading and transcription.
"""

import time
import threading

import numpy as np

from config.whisper import (
    WHISPER_THREADS, WHISPER_WORKERS,
    WHISPER_NO_SPEECH_THRESHOLD, WHISPER_LOG_PROB_THRESHOLD,
    WHISPER_COMPRESSION_RATIO_THRESHOLD,
)
from config.audio import SAMPLE_RATE
from transcription.filters import is_hallucination

WHISPER_ACCURATE_SIZE = "small.en"
WHISPER_ACCURATE_BEAM = 5

WHISPER_AVAILABLE = False
whisper_accurate  = None
_whisper_loading  = False  # NEW: Track if loading in progress
_whisper_loaded   = False  # NEW: Track if already loaded

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    print("ERROR: faster-whisper not installed. Run: pip install faster-whisper>=1.0.0")

_accurate_lock = threading.Lock()


def load_whisper(lazy: bool = False, force: bool = False) -> bool:
    """
    Load the Whisper model. Returns True on success.
    
    Args:
        lazy: If True, load in background thread (non-blocking)
        force: If True, reload even if already loaded
    """
    global whisper_accurate, _whisper_loading, _whisper_loaded
    
    if not WHISPER_AVAILABLE:
        return False
    
    # Skip if already loaded (unless force=True)
    if _whisper_loaded and not force:
        print(f"[OK] {WHISPER_ACCURATE_SIZE} already loaded (skipping)")
        return True
    
    # Skip if currently loading
    if _whisper_loading:
        print(f"[LOADING] {WHISPER_ACCURATE_SIZE} already loading (skipping)")
        return True
    
    def _load():
        global whisper_accurate, _whisper_loading, _whisper_loaded
        
        _whisper_loading = True
        
        try:
            print(f"Loading {WHISPER_ACCURATE_SIZE}...")
            
            # Check available memory before loading
            try:
                import psutil
                mem = psutil.virtual_memory()
                available_gb = mem.available / (1024**3)
                if available_gb < 1.0:
                    print(f"[WARN] Low memory: {available_gb:.1f} GB available")
                    print("   Whisper may fail to load. Consider closing other applications.")
            except ImportError:
                pass  # psutil not available, continue anyway
            
            whisper_accurate = WhisperModel(
                WHISPER_ACCURATE_SIZE,
                device="cpu",
                compute_type="int8",
                cpu_threads=WHISPER_THREADS,
                num_workers=WHISPER_WORKERS,
            )
            
            _whisper_loaded = True
            print(f"[OK] {WHISPER_ACCURATE_SIZE} loaded")
            return True
            
        except MemoryError as e:
            print(f"  {WHISPER_ACCURATE_SIZE}: Out of memory")
            print(f"   Error: {e}")
            print("   Try closing other applications or use Groq Whisper API instead.")
            whisper_accurate = None
            _whisper_loaded = False
            return False
            
        except Exception as e:
            print(f"  {WHISPER_ACCURATE_SIZE}: {e}")
            print("   Whisper model failed to load. Use Groq Whisper API as alternative.")
            whisper_accurate = None
            _whisper_loaded = False
            return False
        
        finally:
            _whisper_loading = False
    
    if lazy:
        thread = threading.Thread(target=_load, daemon=True, name="whisper-loader")
        thread.start()
        return True  # Optimistically return True
    else:
        return _load()


def transcribe_accurate(audio_np: np.ndarray, prompt: str = None) -> str:
    """
    Transcribe audio with small.en. Returns empty string on failure or hallucination.
    Optional 'prompt' help Whisper with technical terms, spelling, etc.
    """
    if audio_np is None or len(audio_np) < SAMPLE_RATE * 0.2:
        return ""
    if whisper_accurate is None:
        return ""

    audio_safe: np.ndarray = np.ascontiguousarray(audio_np, dtype=np.float32)

    rms = float(np.sqrt(np.mean(audio_safe ** 2)))
    if rms < 0.003:
        return ""

    signs = np.sign(audio_safe)
    signs[signs == 0] = 1
    zcr = float(np.sum(np.abs(np.diff(signs))) / (2 * len(audio_safe)))
    if zcr < 0.015:
        return ""

    default_prompt = (
        "Technical, HR and Behavioral interview question. "
        "Programming, coding, software engineering, machine learning, "
        "system design, HR, Behavioral, Technical, Interview, Question."
    )
    final_prompt = f"{default_prompt} {prompt}" if prompt else default_prompt

    with _accurate_lock:
        # GC is permanently disabled at startup - no toggle needed
        try:
            t0 = time.perf_counter()
            segs_iter, _ = whisper_accurate.transcribe(
                audio_safe,
                beam_size=WHISPER_ACCURATE_BEAM,
                language="en",
                initial_prompt=final_prompt,
                condition_on_previous_text=False,
                vad_filter=False,
                temperature=0.0,
                word_timestamps=False,
                no_speech_threshold=WHISPER_NO_SPEECH_THRESHOLD,
                log_prob_threshold=WHISPER_LOG_PROB_THRESHOLD,
                compression_ratio_threshold=WHISPER_COMPRESSION_RATIO_THRESHOLD,
            )
            segments = list(segs_iter)
            text = " ".join(s.text.strip() for s in segments).strip()
            ms   = (time.perf_counter() - t0) * 1000
        except Exception as e:
            print(f"[accurate] error: {e}")
            return ""
        del audio_safe

    if not text:
        return ""

    if is_hallucination(text):
        print(f"[accurate {ms:.0f}ms] hallucination rejected: '{text}'")
        return ""

    print(f"[accurate {ms:.0f}ms] '{text[:80]}'")
    return text
