"""
ui.tray - Re-exports tray and setup functions from the original setup_ui module.

The setup_ui.py is a 1000+ line Tkinter/pystray module. Rather than splitting it,
we re-export its public API here.
"""

import sys
import os

_bot_dir = os.path.dirname(os.path.dirname(__file__))
if _bot_dir not in sys.path:
    sys.path.insert(0, _bot_dir)

from setup_ui import create_tray_app, run_setup, TrayApp, ConfigWindow  # noqa: F401
