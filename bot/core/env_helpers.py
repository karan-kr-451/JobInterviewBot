"""
core.env_helpers - Shared .env and settings.json read/write utilities.

Used by both config/ and setup_ui.py.
"""

import json
import os


_ENV_FILE      = ".env"
_SETTINGS_FILE = "settings.json"


def read_env() -> dict:
    """Read .env file into a dict."""
    d = {}
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip().strip("'\"")
    return d


def write_env(env: dict):
    """Overwrite .env with the given dict."""
    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def read_settings() -> dict:
    """Read settings.json if it exists."""
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def write_settings(settings: dict):
    """Overwrite settings.json with the given dict."""
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
