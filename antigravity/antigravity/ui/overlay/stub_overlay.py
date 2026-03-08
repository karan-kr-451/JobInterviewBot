"""
ui/overlay/stub_overlay.py — Fallback for non-Windows platforms.
"""

from __future__ import annotations

import logging
from PyQt6.QtCore import pyqtSignal, QObject

logger = logging.getLogger(__name__)


class StubOverlay(QObject):
    """
    A dummy overlay that responds to the same API but does nothing.
    Used on Linux/macOS or when overlay is disabled in config.
    """
    
    text_updated = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.text_updated.connect(self._on_text)

    def _on_text(self, text: str):
        pass

    def show(self):
        logger.info("[OVERLAY] StubOverlay ignoring show()")

    def hide(self):
        pass
    
    def close(self):
        pass

    def _exclude_from_capture(self):
        """Stub for interface consistency."""
        pass
