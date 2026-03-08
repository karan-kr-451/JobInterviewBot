"""
audio/device_manager.py — Enumerate and validate audio devices.

Returns information in typed dicts, avoiding lists for faster lookups.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# O(1) device cache
_audio_devices_cache: dict[int, str] | None = None


def get_input_devices() -> dict[int, str]:
    """
    Returns mapping of device_index -> device_name for all input devices.
    Results are cached on first call.
    """
    global _audio_devices_cache
    if _audio_devices_cache is not None:
        return _audio_devices_cache

    try:
        import sounddevice as sd
    except ImportError as e:
        logger.error("[AUDIO] sounddevice not installed: %s", e)
        return {}

    devices = {}
    try:
        # sd.query_devices() returns a DeviceList (dict-like)
        for i, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices[i] = dev.get("name", f"Unknown {i}")
    except Exception as e:
        logger.error("[AUDIO] Error enumerating devices: %s", e)

    _audio_devices_cache = devices
    return devices


def print_devices() -> None:
    """Helper to dump devices to log at startup."""
    devices = get_input_devices()
    logger.info("[AUDIO] Found %d input devices:", len(devices))
    for idx, name in devices.items():
        logger.info("[AUDIO]   [%2d] %s", idx, name)
