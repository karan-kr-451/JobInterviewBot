"""
config/config_loader.py - Centralized configuration loader.

Merges settings.yaml with environment variables (.env overrides YAML).
Exposes a single AppConfig instance used by all modules.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ── YAML dependency ────────────────────────────────────────────────────────────
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("[config] PyYAML not installed – using defaults only")

# ── dotenv loading (optional) ──────────────────────────────────────────────────
def _load_dotenv(path: Path) -> None:
    """Parse a .env file and inject values into os.environ (non-overwriting)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


# ── Config dataclasses ─────────────────────────────────────────────────────────

@dataclass
class GroqConfig:
    api_key:          str       = ""
    models:           Dict[str, str] = field(default_factory=dict)
    fallback_model:   str       = "llama-3.1-8b-instant"
    temperature:      float     = 0.3
    enterprise_models: List[str] = field(default_factory=list)


@dataclass
class GeminiConfig:
    api_key:            str             = ""
    model:              str             = "gemini-2.0-flash"
    fallbacks:          List[str]       = field(default_factory=list)
    generation_configs: Dict[str, dict] = field(default_factory=dict)


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model:    str = "llama3.2"


@dataclass
class LLMConfig:
    backend: str        = "auto"
    groq:    GroqConfig = field(default_factory=GroqConfig)
    gemini:  GeminiConfig = field(default_factory=GeminiConfig)
    ollama:  OllamaConfig = field(default_factory=OllamaConfig)


@dataclass
class AudioConfig:
    device_index:        Optional[int] = None
    sample_rate:         int   = 16000
    chunk_duration:      float = 0.1
    queue_maxsize:       int   = 500
    vad_threshold:       float = 0.5
    rms_gate:            float = 0.005
    speech_onset_frames: int   = 3
    fast_silence_frames: int   = 18
    min_speech_duration: float = 0.4
    max_speech_duration: float = 30.0


@dataclass
class TranscriptionConfig:
    local_model:      str = "base.en"
    compute_type:     str = "int8"
    min_words:        int = 3
    final_queue_size: int = 10
    llm_queue_size:   int = 20


@dataclass
class RAGConfig:
    docs_folder: str = "interview_docs"
    top_k:       int = 2


@dataclass
class TelegramConfig:
    bot_token:    str   = ""
    chat_id:      str   = ""
    queue_size:   int   = 50
    send_timeout: float = 3.0


@dataclass
class OverlayConfig:
    width:     int   = 900
    height:    int   = 620
    x:         int   = 80
    y:         int   = 80
    alpha:     int   = 230
    font:      str   = "Consolas"
    font_size: int   = 11


@dataclass
class LoggingConfig:
    log_file:   str = "logs/interview_log.txt"
    crash_file: str = "logs/crash_debug.log"


@dataclass
class JobConfig:
    title:       str = ""
    description: str = ""


@dataclass
class AppConfig:
    llm:           LLMConfig          = field(default_factory=LLMConfig)
    audio:         AudioConfig        = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    rag:           RAGConfig          = field(default_factory=RAGConfig)
    telegram:      TelegramConfig     = field(default_factory=TelegramConfig)
    overlay:       OverlayConfig      = field(default_factory=OverlayConfig)
    logging:       LoggingConfig      = field(default_factory=LoggingConfig)
    job:           JobConfig          = field(default_factory=JobConfig)
    base_dir:      Path               = field(default_factory=lambda: Path(__file__).parent.parent)


# ── Singleton ─────────────────────────────────────────────────────────────────
_config_lock     = threading.Lock()
_config_instance: Optional[AppConfig] = None


def _resolve_base_dir() -> Path:
    """Return the antigravity/ root directory."""
    return Path(__file__).resolve().parent.parent


def load_config(reload: bool = False) -> AppConfig:
    """
    Load and return the global AppConfig singleton.
    Thread-safe. Subsequent calls return cached instance unless reload=True.
    """
    global _config_instance
    with _config_lock:
        if _config_instance is not None and not reload:
            return _config_instance

        base = _resolve_base_dir()

        # 1. Load .env first so env vars take precedence over YAML
        _load_dotenv(base / ".env")

        # 2. Load YAML
        yaml_data: dict = {}
        yaml_path = base / "config" / "settings.yaml"
        if YAML_AVAILABLE and yaml_path.exists():
            with yaml_path.open(encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}

        # 3. Build config from YAML, then override with env vars
        cfg = AppConfig(base_dir=base)
        _apply_yaml(cfg, yaml_data, base)
        _apply_env(cfg)

        # Ensure log dirs exist
        for log_path_str in [cfg.logging.log_file, cfg.logging.crash_file]:
            log_path = base / log_path_str
            log_path.parent.mkdir(parents=True, exist_ok=True)

        _config_instance = cfg
        return cfg


def _apply_yaml(cfg: AppConfig, d: dict, base: Path) -> None:
    """Populate cfg from parsed YAML dict."""
    if not d:
        return

    # LLM
    llm_d = d.get("llm", {})
    cfg.llm.backend = llm_d.get("backend", cfg.llm.backend)

    groq_d = llm_d.get("groq", {})
    cfg.llm.groq.models           = groq_d.get("models", cfg.llm.groq.models)
    cfg.llm.groq.fallback_model   = groq_d.get("fallback_model", cfg.llm.groq.fallback_model)
    cfg.llm.groq.temperature      = float(groq_d.get("temperature", cfg.llm.groq.temperature))
    cfg.llm.groq.enterprise_models = groq_d.get("enterprise_models", cfg.llm.groq.enterprise_models)

    gem_d = llm_d.get("gemini", {})
    cfg.llm.gemini.model              = gem_d.get("model", cfg.llm.gemini.model)
    cfg.llm.gemini.fallbacks          = gem_d.get("fallbacks", cfg.llm.gemini.fallbacks)
    cfg.llm.gemini.generation_configs = gem_d.get("generation_configs", cfg.llm.gemini.generation_configs)

    oll_d = llm_d.get("ollama", {})
    cfg.llm.ollama.base_url = oll_d.get("base_url", cfg.llm.ollama.base_url)
    cfg.llm.ollama.model    = oll_d.get("model", cfg.llm.ollama.model)

    # Audio
    aud_d = d.get("audio", {})
    dev = aud_d.get("device_index")
    cfg.audio.device_index        = int(dev) if dev is not None else None
    cfg.audio.sample_rate         = int(aud_d.get("sample_rate", cfg.audio.sample_rate))
    cfg.audio.chunk_duration      = float(aud_d.get("chunk_duration", cfg.audio.chunk_duration))
    cfg.audio.queue_maxsize       = int(aud_d.get("queue_maxsize", cfg.audio.queue_maxsize))
    cfg.audio.vad_threshold       = float(aud_d.get("vad_threshold", cfg.audio.vad_threshold))
    cfg.audio.rms_gate            = float(aud_d.get("rms_gate", cfg.audio.rms_gate))
    cfg.audio.speech_onset_frames = int(aud_d.get("speech_onset_frames", cfg.audio.speech_onset_frames))
    cfg.audio.fast_silence_frames = int(aud_d.get("fast_silence_frames", cfg.audio.fast_silence_frames))
    cfg.audio.min_speech_duration = float(aud_d.get("min_speech_duration", cfg.audio.min_speech_duration))
    cfg.audio.max_speech_duration = float(aud_d.get("max_speech_duration", cfg.audio.max_speech_duration))

    # Transcription
    tr_d = d.get("transcription", {})
    cfg.transcription.local_model      = tr_d.get("local_model", cfg.transcription.local_model)
    cfg.transcription.compute_type     = tr_d.get("compute_type", cfg.transcription.compute_type)
    cfg.transcription.min_words        = int(tr_d.get("min_words", cfg.transcription.min_words))
    cfg.transcription.final_queue_size = int(tr_d.get("final_queue_size", cfg.transcription.final_queue_size))
    cfg.transcription.llm_queue_size   = int(tr_d.get("llm_queue_size", cfg.transcription.llm_queue_size))

    # RAG
    rag_d = d.get("rag", {})
    cfg.rag.docs_folder = rag_d.get("docs_folder", cfg.rag.docs_folder)
    cfg.rag.top_k       = int(rag_d.get("top_k", cfg.rag.top_k))

    # Telegram
    tg_d = d.get("telegram", {})
    cfg.telegram.queue_size   = int(tg_d.get("queue_size", cfg.telegram.queue_size))
    cfg.telegram.send_timeout = float(tg_d.get("send_timeout", cfg.telegram.send_timeout))

    # Overlay
    ov_d = d.get("overlay", {})
    cfg.overlay.width     = int(ov_d.get("width", cfg.overlay.width))
    cfg.overlay.height    = int(ov_d.get("height", cfg.overlay.height))
    cfg.overlay.x         = int(ov_d.get("x", cfg.overlay.x))
    cfg.overlay.y         = int(ov_d.get("y", cfg.overlay.y))
    cfg.overlay.alpha     = int(ov_d.get("alpha", cfg.overlay.alpha))
    cfg.overlay.font      = ov_d.get("font", cfg.overlay.font)
    cfg.overlay.font_size = int(ov_d.get("font_size", cfg.overlay.font_size))

    # Logging
    log_d = d.get("logging", {})
    cfg.logging.log_file   = log_d.get("log_file",   cfg.logging.log_file)
    cfg.logging.crash_file = log_d.get("crash_file", cfg.logging.crash_file)

    # Job
    job_d = d.get("job", {})
    cfg.job.title       = job_d.get("title",       cfg.job.title)
    cfg.job.description = job_d.get("description", cfg.job.description)


def _apply_env(cfg: AppConfig) -> None:
    """Override config with environment variables."""
    # API keys
    if os.environ.get("GROQ_API_KEY"):
        cfg.llm.groq.api_key = os.environ["GROQ_API_KEY"]
    if os.environ.get("GEMINI_API_KEY"):
        cfg.llm.gemini.api_key = os.environ["GEMINI_API_KEY"]

    # Telegram
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg.telegram.bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("TELEGRAM_CHAT_ID"):
        cfg.telegram.chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # Audio device
    dev = os.environ.get("DEVICE_INDEX", "").strip()
    if dev:
        try:
            cfg.audio.device_index = int(dev)
        except ValueError:
            pass

    # LLM backend override
    backend = os.environ.get("LLM_BACKEND", "").strip()
    if backend:
        cfg.llm.backend = backend


def get_config() -> AppConfig:
    """Return the singleton config, loading it if necessary."""
    global _config_instance
    if _config_instance is None:
        return load_config()
    return _config_instance
