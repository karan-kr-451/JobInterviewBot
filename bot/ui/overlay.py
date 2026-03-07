"""
ui.overlay - Re-exports Win32Overlay from the original overlay module.

The overlay implementation is a complex single-file Win32 GDI module (835 lines).
Rather than splitting it further, we re-export its public class here to provide
the clean package path ``ui.overlay.Win32Overlay``.
"""

# The original overlay.py sits at bot/overlay.py (sibling of this package).
# We import and re-export its public class.
import sys
import os

# Ensure the bot directory is on sys.path for the legacy import
_bot_dir = os.path.dirname(os.path.dirname(__file__))
if _bot_dir not in sys.path:
    sys.path.insert(0, _bot_dir)

from overlay import Win32Overlay  # noqa: F401
