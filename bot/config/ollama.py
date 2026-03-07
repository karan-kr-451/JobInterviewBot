"""
config.ollama - Ollama backend configuration.
"""

# =============================================================================
# OLLAMA CONFIG
# =============================================================================

OLLAMA_BASE_URL = "http://127.0.0.1:11434"

# =============================================================================
# SINGLE-MODEL STRATEGY
# =============================================================================
OLLAMA_SINGLE_MODEL = "phi3:3.8b-mini-128k-instruct-q3_K_M"

OLLAMA_MODELS = {
    "CODING":           OLLAMA_SINGLE_MODEL,
    "SYSTEM_DESIGN":    OLLAMA_SINGLE_MODEL,
    "CONCEPT":          OLLAMA_SINGLE_MODEL,
    "PROJECT":          OLLAMA_SINGLE_MODEL,
    "BEHAVIORAL":       OLLAMA_SINGLE_MODEL,
    "MACHINE_LEARNING": OLLAMA_SINGLE_MODEL,
    "GENERAL":          OLLAMA_SINGLE_MODEL,
    "UNKNOWN":          OLLAMA_SINGLE_MODEL,
}

OLLAMA_NUM_PREDICT_BY_CATEGORY = {
    "CODING":               400,
    "SYSTEM_DESIGN":        350,
    "PROJECT":              320,
    "BEHAVIORAL":           220,
    "CONCEPT":              180,
    "MACHINE_LEARNING":     180,
    "DEEP_LEARNING":        180,
    "NLP":                  180,
    "COMPUTER_VISION":      180,
    "MLOPS":                180,
    "SOFTWARE_ENGINEERING": 200,
    "DEVOPS":               180,
    "DATA_ENGINEERING":     180,
    "GENERAL":              180,
    "UNKNOWN":              180,
}
OLLAMA_NUM_PREDICT   = 180

OLLAMA_TEMPERATURE   = 0.3

# -- CPU threading --------------------------------------------------------------
OLLAMA_NUM_THREAD       = 12
OLLAMA_NUM_THREAD_BATCH = 16

# -- KV cache / context ---------------------------------------------------------
OLLAMA_NUM_CTX       = 2048
OLLAMA_NUM_CTX_LARGE = 4096

OLLAMA_KEEP_ALIVE    = -1
OLLAMA_REPEAT_PENALTY = 1.1

# -- Memory-mapped I/O ----------------------------------------------------------
OLLAMA_USE_MMAP = True


def get_ollama_num_predict(category: str) -> int:
    """Return the token budget for a given category."""
    key = category.split("|")[0].strip().upper()
    return OLLAMA_NUM_PREDICT_BY_CATEGORY.get(key, OLLAMA_NUM_PREDICT)


def get_ollama_num_ctx(category: str) -> int:
    """Return KV context size for the given domain category."""
    key = category.split("|")[0].strip().upper()
    if key in ("CODING", "SYSTEM_DESIGN", "SOFTWARE_ENGINEERING", "DATA_ENGINEERING"):
        return OLLAMA_NUM_CTX_LARGE
    return OLLAMA_NUM_CTX


def get_ollama_model(category: str) -> str:
    """Look up the Ollama model for a given category string."""
    primary = category.split("|")[0].strip().upper()
    return OLLAMA_MODELS.get(primary, OLLAMA_MODELS["UNKNOWN"])
