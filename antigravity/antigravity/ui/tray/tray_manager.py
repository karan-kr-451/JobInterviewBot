"""
ui/tray/tray_manager.py — System tray icon and menu.

Uses pystray. Run in a separate thread.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _create_default_icon() -> Image.Image:
    """Generate a simple 64x64 icon dynamically if icon.ico is missing."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Draw a green circle
    draw.ellipse((8, 8, 56, 56), fill=(0, 200, 0), outline=(0, 100, 0))
    return image


class TrayManager:
    """
    Manages the system tray icon via pystray.
    Provides non-blocking execution in a daemon thread.
    """

    def __init__(self, app_name: str, on_show_clicked: Callable, on_quit_clicked: Callable) -> None:
        self.app_name = app_name
        self.on_show_clicked = on_show_clicked
        self.on_quit_clicked = on_quit_clicked
        self._icon: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None

    def _setup(self) -> None:
        try:
            from pystray import Icon, Menu, MenuItem
        except ImportError:
            logger.error("[TRAY] pystray not installed, omitting system tray.")
            return

        image = _create_default_icon()
        
        # Load local icon if available
        import os
        if os.path.exists("assets/icon.ico"):
            try:
                image = Image.open("assets/icon.ico")
            except Exception:
                pass

        menu = Menu(
            MenuItem("Show Dashboard", self._on_show),
            MenuItem("Quit", self._on_quit)
        )

        self._icon = Icon("Antigravity", image, self.app_name, menu)

    def _on_show(self, icon, item) -> None:
        # We must trigger callbacks safely; we might be on a pystray thread
        self.on_show_clicked()

    def _on_quit(self, icon, item) -> None:
        self.on_quit_clicked()
        if self._icon:
            self._icon.stop()

    def start(self) -> None:
        """Start the tray icon in a dedicated daemon thread."""
        self._setup()
        if not self._icon:
            return

        self._thread = threading.Thread(
            target=self._icon.run,
            daemon=True,
            name="TrayManager"
        )
        self._thread.start()
        logger.info("[TRAY] System tray started.")

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._icon:
            self._icon.stop()
