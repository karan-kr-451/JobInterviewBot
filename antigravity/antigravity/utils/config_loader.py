"""
utils/config_loader.py — YAML configuration loader returning typed dataclasses.

Reads config.yaml and applies environment variable overrides.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    device_index: int | None = None
    sample_rate: int = 16000
    channels: int = 1
    chunk_seconds: float = 0.5
    vad_threshold: float = 0.005


@dataclass
class TranscriptionConfig:
    backend: str = "groq"
    local_model: str = "tiny.en"
    language: str = "en"


@dataclass
class LLMConfig:
    backend: str = "auto"
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.0-flash"
    ollama_model: str = "llama3.2"
    max_tokens: int = 1024
    temperature: float = 0.3
    system_prompt: str = (
        "You are an expert technical interview assistant. "
        "Answer concisely and accurately. Focus on the most "
        "important technical points. Be direct and helpful."
    )


@dataclass
class OverlayConfig:
    enabled: bool = True
    opacity: float = 0.85
    position: str = "top-right"
    font_size: int = 14
    max_lines: int = 20


@dataclass
class NotificationsConfig:
    telegram_enabled: bool = False


@dataclass
class WatchdogConfig:
    check_interval_seconds: float = 10.0
    stale_threshold_seconds: float = 30.0


@dataclass
class GCConfig:
    manual_collect_interval_seconds: float = 60.0


@dataclass
class AppConfig:
    name: str = "Interview Assistant"
    version: str = "4.0"
    window_title: str = "Antigravity Interview Assistant"
    
    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    gc: GCConfig = field(default_factory=GCConfig)


def load_config(base_dir: str) -> AppConfig:
    """Load config.yaml if it exists, otherwise return defaults."""
    cfg = AppConfig()
    yaml_path = os.path.join(base_dir, "config.yaml")

    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            # Parse top level
            app_data = data.get("app", {})
            cfg.name = app_data.get("name", cfg.name)
            cfg.version = str(app_data.get("version", cfg.version))
            cfg.window_title = app_data.get("window_title", cfg.window_title)

            # Parse sub-sections
            _apply(cfg.audio, data.get("audio", {}))
            _apply(cfg.transcription, data.get("transcription", {}))
            _apply(cfg.llm, data.get("llm", {}))
            _apply(cfg.overlay, data.get("overlay", {}))
            _apply(cfg.notifications, data.get("notifications", {}))
            _apply(cfg.watchdog, data.get("watchdog", {}))
            _apply(cfg.gc, data.get("gc", {}))

            logger.info("[CONFIG] Loaded settings from %s", yaml_path)
        except Exception as e:
            logger.error("[CONFIG] Error reading config.yaml: %s", e)
    else:
        logger.warning("[CONFIG] config.yaml not found, creating default...")
        _write_default(yaml_path)

    # Environment variable overrides
    _apply_env_overrides(cfg)
    return cfg


def _apply(obj: Any, src: dict) -> None:
    for k, v in src.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


def _apply_env_overrides(cfg: AppConfig) -> None:
    # DEVICE_INDEX
    env_dev = os.getenv("DEVICE_INDEX")
    if env_dev is not None:
        try:
            cfg.audio.device_index = int(env_dev)
        except ValueError:
            pass
            
    # LLM_BACKEND
    env_llm = os.getenv("LLM_BACKEND")
    if env_llm:
        cfg.llm.backend = env_llm.strip().lower()


def _write_default(path: str) -> None:
    """Create a default config.yaml based on the v4 spec."""
    template = """\
app:
  name: "Interview Assistant"
  version: "4.0"
  window_title: "Antigravity Interview Assistant"

audio:
  device_index: null       # override with DEVICE_INDEX env var
  sample_rate: 16000
  channels: 1
  chunk_seconds: 0.5
  vad_threshold: 0.005     # amplitude gate before VAD model

transcription:
  backend: "groq"          # groq | local
  local_model: "tiny.en"   # faster-whisper model size
  language: "en"

llm:
  backend: "auto"          # auto | groq | gemini | ollama
  groq_model: "llama-3.3-70b-versatile"
  gemini_model: "gemini-2.0-flash"
  ollama_model: "llama3.2"
  max_tokens: 1024
  temperature: 0.3
  system_prompt: |
    You are an expert technical interview assistant.
    Answer concisely and accurately. Focus on the most
    important technical points. Be direct and helpful.

overlay:
  enabled: true
  opacity: 0.85
  position: "top-right"    # top-right | top-left | bottom-right | bottom-left
  font_size: 14
  max_lines: 20

notifications:
  telegram_enabled: false

watchdog:
  check_interval_seconds: 10
  stale_threshold_seconds: 30

gc:
  manual_collect_interval_seconds: 60
"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(template)
    except Exception as e:
        logger.error("[CONFIG] Failed to write default config.yaml: %s", e)
