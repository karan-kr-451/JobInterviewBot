"""
transcription.worker - Final transcription worker and queues.

Transcription strategy:
  1. If GROQ_API_KEY is set -> use Groq Whisper API (faster, more accurate)
  2. If Groq fails or unavailable -> fall back to local Whisper small.en
"""

import queue
import threading
import time

import numpy as np

from config.whisper import WHISPER_MIN_WORDS
from config.audio import FINAL_QUEUE_MAXSIZE, GEMINI_QUEUE_MAXSIZE

final_queue  = queue.Queue(maxsize=FINAL_QUEUE_MAXSIZE)
gemini_queue = queue.Queue(maxsize=GEMINI_QUEUE_MAXSIZE)

t_speech_end: float = 0.0
t_transcript: float = 0.0


def _get_transcription_hint(docs: dict) -> str:
    """Extract technical keywords from docs to help Whisper with spelling."""
    if not docs: return ""
    
    # Extract Skills and Projects names as hints
    skills = docs.get("resume_sections", {}).get("Skills", "")[:300]
    title  = docs.get("job_title", "")
    
    # Clean up and combine
    hint = f"Terms: {title}. {skills}"
    return hint[:500]


def _final_worker(docs: dict = None):
    """Worker thread: takes audio from final_queue, transcribes, pushes to gemini_queue."""
    global t_transcript
    from transcription.whisper_model import transcribe_accurate
    
    hint = _get_transcription_hint(docs) if docs else ""

    try:
        from transcription.groq_whisper import GROQ_WHISPER_AVAILABLE, transcribe_groq
        use_groq = GROQ_WHISPER_AVAILABLE
    except ImportError:
        use_groq = False
        transcribe_groq = None

    backend = "Groq Whisper API" if use_groq else "local Whisper"
    print(f"[OK] Final worker ready ({backend})")

    while True:
        try:
            item = final_queue.get(timeout=2)
            if item is None: break

            # PING health checker
            try:
                from core.enterprise_crash_prevention import health_checker
                health_checker.ping("transcription")
            except:
                pass

            audio_np = item
            text = ""

            # Transcription - HTTP protection is handled internally by groq_whisper.py
            # Do NOT wrap with gc_safe_http() here to avoid holding the global lock
            # for the entire transcription duration (causes deadlocks with LLM/Telegram)
            if use_groq and transcribe_groq is not None:
                text = transcribe_groq(audio_np, prompt=hint)

            if not text:
                text = transcribe_accurate(audio_np, prompt=hint)

            t_transcript = time.perf_counter()

            if not text or len(text.split()) < WHISPER_MIN_WORDS:
                print(f"  Skipped (<{WHISPER_MIN_WORDS} words): '{text}'")
                continue

            print(f"[OK] Transcript: {text}")
            gemini_queue.put({"text": text})

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[final_worker] {e}")


def enqueue_final(audio_np: np.ndarray):
    """Called by VAD loop when an utterance ends."""
    # Allow enqueue even when local whisper isn't loaded (Groq Whisper may handle it)
    try:
        from transcription.groq_whisper import GROQ_WHISPER_AVAILABLE
        if GROQ_WHISPER_AVAILABLE:
            try:
                final_queue.put(audio_np, block=True, timeout=5)
            except queue.Full:
                print("Final queue full - utterance dropped")
            return
    except ImportError:
        pass

    # Require local whisper to be loaded
    from transcription.whisper_model import whisper_accurate
    if whisper_accurate is None:
        return
    try:
        final_queue.put(audio_np, block=True, timeout=5)
    except queue.Full:
        print("Final queue full - utterance dropped")


def start_workers(docs: dict = None) -> list:
    """Start the transcription worker thread."""
    t = threading.Thread(target=_final_worker, args=(docs,),
                         daemon=True, name="whisper-final")
    t.start()
    return [t]
