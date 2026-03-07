"""
config.whisper - Whisper transcription configuration.
"""

# =============================================================================
# WHISPER
# =============================================================================

WHISPER_BEAM_SIZE  = 5
WHISPER_THREADS    = 8
WHISPER_WORKERS    = 2

WHISPER_NO_SPEECH_THRESHOLD         = 0.8
WHISPER_LOG_PROB_THRESHOLD          = -0.5
WHISPER_COMPRESSION_RATIO_THRESHOLD = 2.0
WHISPER_MIN_WORDS                   = 3

WHISPER_HALLUCINATION_PHRASES = {
    "thank you", "thanks for watching", "thanks for listening",
    "thank you for watching", "thank you so much for watching",
    "thank you for listening", "thank you so much for listening",
    "please subscribe", "don't forget to subscribe",
    "you", ".", "..", "...", "bye", "goodbye", "subscribe",
    "you.", "you..", "you...", "i", "i.", "the", "the.",
    "um", "uh", "hmm", "ah", "oh",
}
