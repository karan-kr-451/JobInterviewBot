"""
audio/device_manager.py - Audio device discovery and selection utilities.
"""

from __future__ import annotations

from core.logger import get_logger

log = get_logger("audio.device_manager")


def list_devices() -> None:
    """Print all available audio input/output devices to console."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print("\n" + "=" * 55)
        print("  AVAILABLE AUDIO DEVICES")
        print("=" * 55)
        print(devices)
        print("=" * 55)
        print("  Set DEVICE_INDEX in .env or config/settings.yaml")
        print("  Windows tip: use 'Stereo Mix' or 'CABLE Output'")
        print("=" * 55 + "\n")
    except ImportError:
        log.error("sounddevice not installed – run: pip install sounddevice")
    except Exception as exc:
        log.error("Failed to list audio devices: %s", exc)


def validate_device(device_index: int | None) -> bool:
    """Return True if device_index is valid (or None for system default)."""
    if device_index is None:
        return True
    try:
        import sounddevice as sd
        sd.query_devices(device_index)
        return True
    except Exception:
        return False


def get_default_input_device() -> dict | None:
    """Return info dict for the system default input device."""
    try:
        import sounddevice as sd
        return sd.query_devices(kind="input")
    except Exception:
        return None
