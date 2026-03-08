"""
ui/overlay/overlay_manager.py — Overlay factory.
"""

from __future__ import annotations

import sys
import logging
from typing import Any

from antigravity.utils.config_loader import OverlayConfig

logger = logging.getLogger(__name__)


def create_overlay(config: OverlayConfig) -> Any:
    """
    Returns the appropriate overlay instance.
    Win32Overlay for Windows, StubOverlay for others or if disabled.
    """
    if not config.enabled:
        from antigravity.ui.overlay.stub_overlay import StubOverlay
        return StubOverlay()

    if sys.platform == "win32":
        from antigravity.ui.overlay.win32_overlay import Win32Overlay
        logger.info("[OVERLAY] Initializing Win32 transparent HUD.")
        return Win32Overlay(
            opacity=config.opacity,
            position=config.position,
            font_size=config.font_size
        )
    else:
        logger.warning("[OVERLAY] Transparent overlay not supported on %s.", sys.platform)
        from antigravity.ui.overlay.stub_overlay import StubOverlay
        return StubOverlay()
