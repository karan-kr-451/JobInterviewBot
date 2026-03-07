"""
config.groq - Groq backend configuration.
"""

import os

# =============================================================================
# GROQ
# =============================================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Groq Whisper (cloud transcription)
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"
GROQ_WHISPER_FALLBACKS = [
    "whisper-large-v3",
]

GROQ_MODELS: dict = {
    # High-reasoning / Complex tasks
    "CODING":               "llama-3.3-70b-versatile",
    "SYSTEM_DESIGN":        "llama-3.3-70b-versatile",
    "SOFTWARE_ENGINEERING": "llama-3.3-70b-versatile",
    "PROJECT":              "llama-3.3-70b-versatile",
    "BEHAVIORAL":           "llama-3.3-70b-versatile",
    
    # Speed-critical / Technical concepts
    "CONCEPT":              "llama-3.1-8b-instant",
    "MACHINE_LEARNING":     "llama-3.1-8b-instant",
    "DEEP_LEARNING":        "llama-3.1-8b-instant",
    "NLP":                  "llama-3.1-8b-instant",
    "COMPUTER_VISION":      "llama-3.1-8b-instant",
    "MLOPS":                "llama-3.1-8b-instant",
    "DATA_ENGINEERING":     "llama-3.1-8b-instant",
    "DEVOPS":               "llama-3.1-8b-instant",
    
    # Generic entry points
    "GENERAL":              "llama-3.1-8b-instant",
    "UNKNOWN":              "llama-3.1-8b-instant",
}

# New models provided by user for rotation and specialized tasks
GROQ_ENTERPRISE_MODELS = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-3.1-8b-instant",
]

GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"

GROQ_MAX_TOKENS_BY_CATEGORY: dict = {
    "CODING":               250,  # Reduced to avoid rate limits
    "SYSTEM_DESIGN":        250,  # Reduced to avoid rate limits
    "SOFTWARE_ENGINEERING": 200,  # Reduced to avoid rate limits
    "PROJECT":              200,  # Reduced to avoid rate limits
    "BEHAVIORAL":           200,  # Reduced to avoid rate limits
    "CONCEPT":              150,  # Reduced to avoid rate limits
    "MACHINE_LEARNING":     150,  # Reduced to avoid rate limits
    "DEEP_LEARNING":        150,  # Reduced to avoid rate limits
    "NLP":                  150,  # Reduced to avoid rate limits
    "COMPUTER_VISION":      150,  # Reduced to avoid rate limits
    "MLOPS":                150,  # Reduced to avoid rate limits
    "DATA_ENGINEERING":     150,  # Reduced to avoid rate limits
    "DEVOPS":               150,  # Reduced to avoid rate limits
    "GENERAL":              150,  # Reduced to avoid rate limits
    "UNKNOWN":              150,  # Reduced to avoid rate limits
}
GROQ_MAX_TOKENS_DEFAULT = 150  # Reduced default to avoid rate limits

GROQ_TEMPERATURE = 0.3


def get_groq_max_tokens(category: str) -> int:
    """Return Groq token budget for the given category."""
    primary = category.split("|")[0].strip().upper()
    return GROQ_MAX_TOKENS_BY_CATEGORY.get(primary, GROQ_MAX_TOKENS_DEFAULT)
