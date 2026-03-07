"""
ui - User interface package (overlay, setup window, tray icon).

This package re-exports from the original monolithic files which remain
in place for now. The overlay.py and setup_ui.py files are large Win32/Tkinter
modules that benefit from staying as single files.
"""

from ui.overlay import Win32Overlay        # noqa: F401
from ui.tray import create_tray_app, run_setup  # noqa: F401
