"""
transcription.filters - Hallucination and quality filters for Whisper output.
"""

from config.whisper import WHISPER_HALLUCINATION_PHRASES, WHISPER_MIN_WORDS


def is_hallucination(text: str) -> bool:
    """Return True if the text is a known Whisper hallucination."""
    t = text.strip().lower().rstrip(".")

    if t in WHISPER_HALLUCINATION_PHRASES:
        return True

    for phrase in WHISPER_HALLUCINATION_PHRASES:
        if len(phrase) > 4 and phrase in t:
            return True

    if len(text.split()) < WHISPER_MIN_WORDS:
        return True

    return False
