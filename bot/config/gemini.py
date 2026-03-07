"""
config.gemini - Gemini backend configuration and generation configs.
"""

import os

# =============================================================================
# GEMINI
# =============================================================================

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "AIzaSyAB6IFylj1Vwq-q5IxTP0pslWfIY4uHFso")
GEMINI_MODEL      = "gemini-2.5-flash-lite"
GEMINI_FALLBACKS  = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

# =============================================================================
# GENERATION CONFIGS (Gemini only)
# =============================================================================

GENERATION_CONFIGS = {
    "CODING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.15,
        "top_p":              0.85,
        "max_output_tokens":  400,  # Reduced for concise code + explanation
    },
    "SYSTEM_DESIGN": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  350,  # Reduced for focused design points
    },
    "CONCEPT": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for brief explanations
    },
    "PROJECT": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.55,
        "top_p":              0.90,
        "max_output_tokens":  250,  # Reduced for concise project stories
    },
    "BEHAVIORAL": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.70,
        "top_p":              0.92,
        "max_output_tokens":  250,  # Reduced for focused STAR responses
    },
    "MACHINE_LEARNING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "DEEP_LEARNING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "NLP": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "COMPUTER_VISION": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "MLOPS": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "SOFTWARE_ENGINEERING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.25,
        "top_p":              0.88,
        "max_output_tokens":  300,  # Reduced for direct answers
    },
    "DEVOPS": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "DATA_ENGINEERING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  200,  # Reduced for technical precision
    },
    "GENERAL": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.45,
        "top_p":              0.90,
        "max_output_tokens":  200,  # Reduced for brief answers
    },
    "UNKNOWN": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.45,
        "top_p":              0.90,
        "max_output_tokens":  200,  # Reduced for brief answers
    },
}
