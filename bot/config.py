"""
config.py - All constants, credentials, and tuning knobs.
Edit ONLY this file to reconfigure the assistant.
"""

import os

def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip().strip("'\"")
# Load YAML config first (sets os.environ); fallback to .env
try:
    from config.yaml_loader import load_config as _load_yaml
    _load_yaml()
except Exception:
    _load_env()

# =============================================================================
# LLM BACKEND SELECTION
# =============================================================================
#
# "gemini"  - Google Gemini API (default, requires GEMINI_API_KEY)
# "ollama"  - Local Ollama models (no API key, requires Ollama running locally)
#
# To use Ollama:
#   1. Install Ollama: https://ollama.ai
#   2. Pull models:
#        ollama pull mistral          # fast, good for CONCEPT/BEHAVIORAL
#        ollama pull deepseek-coder   # best for CODING (code-tuned)
#        ollama pull llama3.1         # balanced, good for SYSTEM_DESIGN
#   3. Set LLM_BACKEND = "ollama" below
#   4. Adjust OLLAMA_MODELS per category if you pull different models
#
# Your hardware: i7-12th gen, 24GB RAM
# Recommended models that fit comfortably in RAM with Whisper running:
#   - mistral:7b-instruct-v0.3-q4_K_S      (~4.1GB) - fastest, best for real-time
#   - deepseek-coder:6.7b-instruct-q4_K_M (~3.8GB) - best code quality
#   - llama3.1:8b-instruct-q4_K_M     (~4.7GB) - best general quality
#   - phi3:3.8b-mini-128k-instruct-q3_K_M       (~2.3GB) - ultra-fast, lower quality
#
# Whisper small.en uses ~470MB RAM. Total budget with 24GB:
#   OS + Python + Whisper   4GB -> ~20GB free -> can run 8B q4 models fine.
#
LLM_BACKEND = os.environ.get("LLM_BACKEND", "gemini")  # set via config.yaml or GUI
#
# "auto" priority chain: Ollama -> Groq -> Gemini
#   - Ollama: local, zero latency, zero cost - used if running
#   - Groq:   free cloud API, 500+ tok/s, no credit card - used if GROQ_API_KEY set
#   - Gemini: fallback, generous 1M-context free tier

# =============================================================================
# OLLAMA CONFIG (only used when LLM_BACKEND = "ollama")
# =============================================================================

OLLAMA_BASE_URL = "http://127.0.0.1:11434"   # default Ollama server

# =============================================================================
# SINGLE-MODEL STRATEGY - eliminates reload penalty
# =============================================================================
#
# ROOT CAUSE OF 30-37s LATENCY:
#   Per-category model switching means Ollama unloads the previous model
#   and reloads from disk on EVERY category change. That reload alone costs
#   10-15s before a single token is generated. Then 512 tokens at ~20 tok/s
#   on CPU adds another 25s. Total: 30-40s.
#
# FIX: Use ONE model for ALL categories. phi3:3.8b-mini stays loaded in RAM
# permanently -> zero reload cost. Every request hits a warm model.
#
# With OLLAMA_KEEP_ALIVE=-1, Ollama never evicts the model from RAM.
# phi3:mini at q3_K_M uses ~2.3GB - fits easily alongside Whisper (~470MB).
#
# Token budget:
#   180 tokens   ~20 tok/s on CPU = ~9s generation (vs 25s at 512 tokens)
#   A focused 180-token answer is better for real-time use anyway.
#
OLLAMA_SINGLE_MODEL = "phi3:3.8b-mini-128k-instruct-q3_K_M"

OLLAMA_MODELS = {
    # ALL categories map to the same model - no reload penalty.
    # To use a different model per category, change OLLAMA_SINGLE_MODEL
    # and update all values below to match, OR switch to LLM_BACKEND="gemini".
    "CODING":           OLLAMA_SINGLE_MODEL,
    "SYSTEM_DESIGN":    OLLAMA_SINGLE_MODEL,
    "CONCEPT":          OLLAMA_SINGLE_MODEL,
    "PROJECT":          OLLAMA_SINGLE_MODEL,
    "BEHAVIORAL":       OLLAMA_SINGLE_MODEL,
    "MACHINE_LEARNING": OLLAMA_SINGLE_MODEL,
    "GENERAL":          OLLAMA_SINGLE_MODEL,
    "UNKNOWN":          OLLAMA_SINGLE_MODEL,
}

# Same model for all categories - no reload penalty.
#
#   CODING / SYSTEM_DESIGN / PROJECT - need room for code blocks and STAR answers.
#     400 tokens   20s.  A medium function + complexity line fits in ~300 tokens.
#
#   CONCEPT / BEHAVIORAL / ML / GENERAL - crisp answers only.
#     180 tokens   9s.  Definition + analogy + tradeoff fits in 180.
#
#   SPECULATIVE (fires mid-speech) - shortest possible.
#     120 tokens   6s.  Likely replaced by accurate result; waste less CPU.
#
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
OLLAMA_NUM_PREDICT   = 180             # fallback default if category not in dict above

OLLAMA_TEMPERATURE   = 0.3

# -- CPU threading --------------------------------------------------------------
#
# i7-12th gen topology: 4 P-cores (HT -> 8 threads) + 8 E-cores = 16 total.
#
# NUM_THREAD: threads for matrix multiply (the hot path in token generation).
#   Set to 12 - leaves 4 threads for Whisper + Python overhead.
#   Going to 16 hurts: OS scheduling contention with Whisper degrades both.
#   P-cores are ~2  faster than E-cores; llama.cpp schedules the hot layers
#   on the first N threads, so more threads = more P-core utilization.
#
# NUM_THREAD_BATCH: threads used during prompt eval (prefill phase).
#   Prompt eval is embarrassingly parallel -> use all 16 threads.
#   This is the "read the question" phase, not the "generate tokens" phase,
#   so it doesn't compete with Whisper (which runs before generation starts).
#
# NET EFFECT: ~20-30% faster token generation vs num_thread=8.
#   Rough estimate: 20 tok/s -> 26-28 tok/s on P-cores with better utilization.
#
OLLAMA_NUM_THREAD       = 12   # generation threads (was 8 - left P-cores idle)
OLLAMA_NUM_THREAD_BATCH = 16   # prefill threads - all cores, short burst

# -- KV cache / context ---------------------------------------------------------
#
# You have 24GB RAM. Current usage:
#   phi3:3.8b-mini q3_K_M model weights : ~2.3 GB  (always loaded)
#   Whisper small.en                     : ~0.5 GB
#   Whisper tiny.en                      : ~0.2 GB
#   Python + OS overhead                 : ~1.5 GB
#   ---------------------------------------------
#   Total fixed                          : ~4.5 GB
#   Free for KV cache + other            : ~19.5 GB
#
# KV cache size formula (phi3 3.8B):
#   n_layers=32, n_kv_heads=32, head_dim=96, 2 (K+V), 2 bytes (fp16)
#   per_token = 32   32   96   2   2 = 393,216 bytes = 384 KB/token
#   At 4096 ctx: 384KB   4096 = 1.5 GB    this was the OOM crash
#   At 2048 ctx: 384KB   2048 = 768 MB    safe
#   At 1024 ctx: 384KB   1024 = 384 MB    very safe but limits coding answers
#
# NEW STRATEGY: raise ctx now that we understand the budget.
#   Default 2048 - fits a full code block + prompt comfortably, uses 768MB KV.
#   CODING/SYSTEM_DESIGN: 4096 - allows long functions, uses 1.5GB KV.
#     This is safe now: 4.5GB fixed + 1.5GB KV = 6GB total, well under 24GB.
#
OLLAMA_NUM_CTX       = 2048   # default (was 1024 - too tight for project answers)
OLLAMA_NUM_CTX_LARGE = 4096   # CODING / SYSTEM_DESIGN - restored to full capacity

OLLAMA_KEEP_ALIVE    = -1     # never unload model from RAM
OLLAMA_REPEAT_PENALTY = 1.1   # reduce repetitive filler

# -- Memory-mapped I/O ----------------------------------------------------------
#
# OLLAMA_USE_MMAP: if True, model weights are memory-mapped from disk.
#   Pros: faster initial load (OS pages in on demand), lower RSS at startup.
#   Cons: on slow HDDs, page faults during generation add latency spikes.
#   With 24GB RAM the entire model fits in page cache after first load,
#   so mmap is fine. Set False only if you see random latency spikes.
#
# This is passed as the Ollama server env var OLLAMA_FLASH_ATTENTION,
# not a per-request option - see ollama_warmup.py for env setup notes.
#
OLLAMA_USE_MMAP = True


def get_ollama_num_predict(category: str) -> int:
    """
    Return the token budget for a given category.
    category should be the DOMAIN string (e.g. "MACHINE_LEARNING").
    """
    key = category.split("|")[0].strip().upper()
    return OLLAMA_NUM_PREDICT_BY_CATEGORY.get(key, OLLAMA_NUM_PREDICT)


def get_ollama_num_ctx(category: str) -> int:
    """
    Return KV context size for the given domain category.
    CODING/SYSTEM_DESIGN get the larger context window (4096) to fit code blocks.
    Everything else gets 2048 - sufficient for any conversational answer.
    """
    key = category.split("|")[0].strip().upper()
    if key in ("CODING", "SYSTEM_DESIGN", "SOFTWARE_ENGINEERING", "DATA_ENGINEERING"):
        return OLLAMA_NUM_CTX_LARGE
    return OLLAMA_NUM_CTX


def get_ollama_model(category: str) -> str:
    """
    Look up the Ollama model for a given category string.
    Handles pipe-separated labels like "MACHINE_LEARNING | CONCEPT" that
    the classifier returns - takes the first segment only, uppercases it.
    Falls back to UNKNOWN (= OLLAMA_SINGLE_MODEL) if no match.
    """
    primary = category.split("|")[0].strip().upper()
    return OLLAMA_MODELS.get(primary, OLLAMA_MODELS["UNKNOWN"])

# =============================================================================
# GROQ (free cloud inference - 500+ tok/s, no credit card required)
# =============================================================================
#
# Get your free API key at: https://console.groq.com
# Set it in your .env file:  GROQ_API_KEY=gsk_...
#
# FREE TIER LIMITS (2026):
#   llama-3.3-70b-versatile : 30 RPM, 1K RPD, 12K TPM, 100K TPD
#   llama-4-scout-17b       : 30 RPM, 1K RPD, 30K TPM, 500K TPD
#   llama-3.1-8b-instant    : 30 RPM, 14.4K RPD, 6K TPM, 500K TPD
#
# MODEL SELECTION STRATEGY:
#   CODING / SYSTEM_DESIGN  -> llama-3.3-70b (best reasoning)
#   CONCEPT / ML / NLP      -> llama-4-scout  (large context, fast)
#   SPECULATIVE path        -> llama-3.1-8b   (lowest latency, often replaced)
#   everything else         -> llama-4-scout  (balanced)
#
# On 429 (rate limit hit), the client reads the retry-after header and
# sleeps exactly that long before trying the fallback model.
# Groq rate limits reset per minute - waits are rarely > 10s in practice.
#
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

GROQ_MODELS: dict = {
    # Complex reasoning - use the best available model
    "CODING":               "llama-3.3-70b-versatile",
    "SYSTEM_DESIGN":        "llama-3.3-70b-versatile",
    "SOFTWARE_ENGINEERING": "llama-3.3-70b-versatile",
    # Fast factual answers - 4-Scout has 16K context, great for concept Qs
    "CONCEPT":              "meta-llama/llama-4-scout-17b-16e-instruct",
    "MACHINE_LEARNING":     "meta-llama/llama-4-scout-17b-16e-instruct",
    "DEEP_LEARNING":        "meta-llama/llama-4-scout-17b-16e-instruct",
    "NLP":                  "meta-llama/llama-4-scout-17b-16e-instruct",
    "COMPUTER_VISION":      "meta-llama/llama-4-scout-17b-16e-instruct",
    "MLOPS":                "meta-llama/llama-4-scout-17b-16e-instruct",
    "DATA_ENGINEERING":     "meta-llama/llama-4-scout-17b-16e-instruct",
    "DEVOPS":               "meta-llama/llama-4-scout-17b-16e-instruct",
    # Narrative answers - 70B for quality
    "PROJECT":              "llama-3.3-70b-versatile",
    "BEHAVIORAL":           "llama-3.3-70b-versatile",
    # Catch-all
    "GENERAL":              "meta-llama/llama-4-scout-17b-16e-instruct",
    "UNKNOWN":              "meta-llama/llama-4-scout-17b-16e-instruct",
}

# Fallback if a category key is missing from GROQ_MODELS
GROQ_FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Token budgets for Groq (generous - Groq is fast, so larger budgets are OK)
GROQ_MAX_TOKENS_BY_CATEGORY: dict = {
    "CODING":               900,
    "SYSTEM_DESIGN":        700,
    "SOFTWARE_ENGINEERING": 600,
    "PROJECT":              450,
    "BEHAVIORAL":           350,
    "CONCEPT":              300,
    "MACHINE_LEARNING":     300,
    "DEEP_LEARNING":        300,
    "NLP":                  300,
    "COMPUTER_VISION":      300,
    "MLOPS":                300,
    "DATA_ENGINEERING":     300,
    "DEVOPS":               300,
    "GENERAL":              350,
    "UNKNOWN":              350,
}
GROQ_MAX_TOKENS_DEFAULT     = 350   # fallback if category missing

GROQ_TEMPERATURE = 0.3


def get_groq_max_tokens(category: str) -> int:
    """Return Groq token budget for the given category."""
    primary = category.split("|")[0].strip().upper()
    return GROQ_MAX_TOKENS_BY_CATEGORY.get(primary, GROQ_MAX_TOKENS_DEFAULT)


# =============================================================================
# AUDIO
# =============================================================================

SAMPLE_RATE    = 16000
CHUNK_DURATION = 0.1     # 0.1s per callback block = 1600 samples

# -- Silero VAD -----------------------------------------------------------------
#
# TUNING FOR STEREO MIX:
#   VAD_THRESHOLD=0.5 is calibrated for close-mic speech (RMS ~0.01 0.05).
#   Stereo Mix at Windows volume 46 produces speech RMS ~0.005 0.02.
#   Lowering to 0.35 ensures Silero accepts real speech without triggering on
#   every notification sound (which has a very different spectral shape).
#
VAD_THRESHOLD   = 0.35
VAD_WIN_SAMPLES = 512    # Silero window size - do not change

# -- Noise gate -----------------------------------------------------------------
#
# Set just below typical speech floor on Stereo Mix.
# Notification pings / click sounds are shorter bursts - they'll pass this gate
# but get rejected by the ZCR check in transcriber.py and the onset frame count.
#
RMS_GATE = 0.002

# -- Speech onset --------------------------------------------------------------
#
# Require 3 consecutive voiced frames (0.3s) before starting to record.
# A notification ping is typically 1 2 frames. A Windows startup sound is ~5
# frames but fails the ZCR check. Interview speech sustains well past 3 frames.
#
SPEECH_ONSET_FRAMES = 2

# -- Silence detection ---------------------------------------------------------
#
# 20 frames   0.1s = 2.0s of silence required to end an utterance.
# Interview questions often have deliberate pauses mid-sentence ("tell me...
# about your experience with..."). 1.2s (12 frames) was cutting those off.
# 2.0s keeps full questions intact without letting the buffer grow too large.
#
FAST_SILENCE_FRAMES = 15

# -- Speech duration filters ---------------------------------------------------
#
# MIN raised to 1.5s: anything shorter is almost certainly a sound effect,
# not an interview question. This is the last line of defence before Whisper.
#
MIN_SPEECH_DURATION = 1.5
MAX_SPEECH_DURATION = 45   # was 60 - cap at 45s to prevent runaway buffers

def _resolve_device_index():
    """
    Priority: (1) DEVICE_INDEX from .env, (2) auto-detect Stereo Mix, (3) None.
    """
    raw = os.environ.get("DEVICE_INDEX", "").strip()
    if raw.lstrip("-").isdigit():
        idx = int(raw)
        if idx >= 0:
            return idx
    try:
        import sounddevice as _sd
        for i, d in enumerate(_sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                n = d.get("name", "").lower()
                if "stereo mix" in n or "what u hear" in n or "wave out mix" in n:
                    print(f"[Config] Auto-detected Stereo Mix at device index {i}: {d['name']}")
                    return i
    except Exception:
        pass
    print("[Config] DEVICE_INDEX: using OS default input device")
    return None

DEVICE_INDEX = _resolve_device_index()

# =============================================================================
# DUPLICATE DETECTION
# =============================================================================
#
# Prevents the same question from being answered twice when Stereo Mix
# re-triggers on audio feedback, echo, or Gemini TTS output.
# Questions with word-overlap > DUPLICATE_OVERLAP_THRESHOLD within
# DUPLICATE_WINDOW_S seconds are silently dropped.
#
DUPLICATE_WINDOW_S         = 30.0   # seconds - ignore repeats within this window
DUPLICATE_OVERLAP_THRESHOLD = 0.70  # was 0.85 - "Create an array" vs "Create your array" = ~0.75 overlap
                                     # 0.70 catches reworded repeats while still allowing genuinely
                                     # different questions that share common words

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
    # Exact common hallucinations
    "thank you", "thanks for watching", "thanks for listening",
    "thank you for watching", "thank you so much for watching",
    "thank you for listening", "thank you so much for listening",
    "please subscribe", "don't forget to subscribe",
    "you", ".", "..", "...", "bye", "goodbye", "subscribe",
    "you.", "you..", "you...", "i", "i.", "the", "the.",
    # Short noise words
    "um", "uh", "hmm", "ah", "oh",
}

# =============================================================================
# SPECULATIVE PIPELINE
# =============================================================================
#
# Lowered from 0.82 -> 0.70 so that near-identical transcripts like
# "What does machine learning?" and "What is machine learning?" still confirm
# the speculative result instead of firing a second Gemini call.
# The speculative LLM answer is already shown - no need to re-run.
#
# Speculative pipeline removed. One Whisper call + one LLM call per utterance.

# =============================================================================
# GEMINI (only used when LLM_BACKEND = "gemini")
# =============================================================================

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "AIzaSyAB6IFylj1Vwq-q5IxTP0pslWfIY4uHFso")
GEMINI_MODEL      = "gemini-2.5-flash-lite"   # safe default - free tier, fast
GEMINI_FALLBACKS  = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
]

RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY   = 35

# =============================================================================
# TELEGRAM
# =============================================================================

TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN",  "7726524846:AAGMbkVvHrZROVTHX4giEYVZv_z2EGQX0Dw")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID",    "1571206699")
TELEGRAM_QUEUE_SIZE = 64

# Timeout for Telegram send_message - keep short so startup status message
# doesn't block for 10s when internet is down. Async sends use the queue.
TELEGRAM_SEND_TIMEOUT  = 3    # seconds - was 10, caused blocking on network loss
TELEGRAM_POLL_TIMEOUT  = 30   # seconds - long-poll for commands

# =============================================================================
# PIPELINE QUEUE SIZES
# =============================================================================

AUDIO_QUEUE_MAXSIZE  = 0   # unbounded - zero audio drops
FINAL_QUEUE_MAXSIZE  = 4
GEMINI_QUEUE_MAXSIZE = 4

# =============================================================================
# OVERLAY / GUI
# =============================================================================

OVERLAY_WIDTH   = 640
OVERLAY_HEIGHT  = 460
OVERLAY_X       = 30
OVERLAY_Y       = 30
OVERLAY_ALPHA   = 215
OVERLAY_FONT    = "Consolas"
OVERLAY_FONT_SZ = 11
OVERLAY_WRAP    = 88

HOTKEY_HIDE         = 0x48  # H key
HOTKEY_QUIT         = 0x51  # Q key
HOTKEY_FULLSCREEN   = 0x46  # F key
HOTKEY_MINIMIZE     = 0x4D  # M key

# =============================================================================
# DOCUMENTS
# =============================================================================

DOCS_FOLDER = "./interview_docs"
LOG_FILE    = "interview_log.txt"

# =============================================================================
# GENERATION CONFIGS (Gemini only)
# =============================================================================

GENERATION_CONFIGS = {
    # gemini-2.5-flash-lite across the board:
    #   - Free tier, generous RPM
    #   - ~1-3s latency vs ~8-12s for gemini-2.5-flash on free tier
    #   - Quality difference is negligible for interview-length answers
    #   - If you want higher quality for CODING/SYSTEM_DESIGN and have a paid
    #     key, change those two back to "gemini-2.5-flash"
    "CODING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.15,
        "top_p":              0.85,
        "max_output_tokens":  1500,
    },
    "SYSTEM_DESIGN": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  1000,
    },
    "CONCEPT": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "PROJECT": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.55,
        "top_p":              0.90,
        "max_output_tokens":  500,
    },
    "BEHAVIORAL": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.70,
        "top_p":              0.92,
        "max_output_tokens":  350,
    },
    "MACHINE_LEARNING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "DEEP_LEARNING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "NLP": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "COMPUTER_VISION": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "MLOPS": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "SOFTWARE_ENGINEERING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.25,
        "top_p":              0.88,
        "max_output_tokens":  600,
    },
    "DEVOPS": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "DATA_ENGINEERING": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.30,
        "top_p":              0.88,
        "max_output_tokens":  400,
    },
    "GENERAL": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.45,
        "top_p":              0.90,
        "max_output_tokens":  400,
    },
    "UNKNOWN": {
        "model":              "gemini-2.5-flash-lite",
        "temperature":        0.45,
        "top_p":              0.90,
        "max_output_tokens":  400,
    },
}