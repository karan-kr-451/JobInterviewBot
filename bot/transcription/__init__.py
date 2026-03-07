"""
transcription - Whisper transcription package.
"""

from transcription.whisper_model import (      # noqa: F401
    load_whisper, WHISPER_AVAILABLE,
    transcribe_accurate,
)
from transcription.worker import (             # noqa: F401
    start_workers, enqueue_final,
    final_queue, gemini_queue,
)
from transcription.filters import is_hallucination  # noqa: F401

try:
    from transcription.groq_whisper import (   # noqa: F401
        check_groq_whisper, transcribe_groq,
        GROQ_WHISPER_AVAILABLE,
    )
except ImportError:
    check_groq_whisper = lambda: False
    transcribe_groq = None
    GROQ_WHISPER_AVAILABLE = False
