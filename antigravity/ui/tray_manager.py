"""
ui/tray_manager.py - System tray icon using pystray.

Creates a tray icon with a context menu.
Menu items: Show Dashboard | Show Overlay | Quit
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from core.logger import get_logger

log = get_logger("ui.tray")


class TrayManager:
    """
    Wraps pystray to provide a system tray icon with callbacks.

    Usage:
        tray = TrayManager(on_quit=sys.exit, on_show_dashboard=dashboard.show)
        tray.start()   # non-blocking daemon thread
    """

    def __init__(
        self,
        on_quit:           Callable = lambda: None,
        on_show_dashboard: Callable = lambda: None,
        on_show_overlay:   Callable = lambda: None,
        icon_path:         Optional[str] = None,
    ) -> None:
        self._on_quit   = on_quit
        self._on_dash   = on_show_dashboard
        self._on_overlay = on_show_overlay
        self._icon_path  = icon_path
        self._tray      = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the tray icon in a daemon thread."""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="tray"
        )
        self._thread.start()

    def stop(self) -> None:
        """Remove the tray icon."""
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass

    def _run(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Load or generate icon
            if self._icon_path:
                try:
                    icon_img = Image.open(self._icon_path).resize((64, 64))
                except Exception:
                    icon_img = self._make_default_icon()
            else:
                icon_img = self._make_default_icon()

            menu = pystray.Menu(
                pystray.MenuItem("Show Dashboard", lambda: self._on_dash()),
                pystray.MenuItem("Show Overlay",   lambda: self._on_overlay()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit",           lambda: self._quit()),
            )

            self._tray = pystray.Icon(
                "InterviewAssistant",
                icon_img,
                "Interview Assistant",
                menu,
            )
            self._tray.run()

        except ImportError:
            log.warning("pystray/Pillow not installed – tray icon disabled")
        except Exception as exc:
            log.error("Tray manager error: %s", exc)

    def _quit(self) -> None:
        self.stop()
        self._on_quit()

    @staticmethod
    def _make_default_icon():
        """Generate a simple green circle as the default tray icon."""
        from PIL import Image, ImageDraw
        img  = Image.new("RGB", (64, 64), color=(10, 10, 20))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill=(0, 200, 100))
        draw.text((20, 20), "IA", fill="white")
        return img
