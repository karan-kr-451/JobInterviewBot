"""
utils/env_loader.py — Loads variables from .env using python-dotenv.

Provides validation of required keys (e.g. GROQ_API_KEY).
Called during startup Phase 3.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_env(base_dir: str) -> None:
    """Load .env file from base_dir into os.environ."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("[ENV] python-dotenv not installed; relying on system env vars")
        return

    env_path = os.path.join(base_dir, ".env")
    if not os.path.exists(env_path):
        logger.info("[ENV] No .env file found at %s. Creating template...", env_path)
        _create_template(env_path)

    loaded = load_dotenv(env_path)
    if loaded:
        logger.info("[ENV] Loaded variables from .env")
    else:
        logger.warning("[ENV] .env file was empty or failed to load")


def _create_template(path: str) -> None:
    template = (
        "GROQ_API_KEY=\n"
        "GEMINI_API_KEY=\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "TELEGRAM_CHAT_ID=\n"
        "DEVICE_INDEX=1\n"
        "LLM_BACKEND=auto\n"
        "LOG_LEVEL=INFO\n"
    )
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(template)
    except Exception as e:
        logger.error("[ENV] Failed to create .env template: %s", e)
