"""
core/compat_check.py — Stack validation at startup.

Ensures the installed environment matches the exact required technical stack.
Checks combinations like torch + torchaudio version bounds, faster-whisper bounds, etc.

Returns a list of error strings; empty if perfectly healthy.
"""

from __future__ import annotations

import importlib
import logging

from packaging.version import Version, InvalidVersion

logger = logging.getLogger(__name__)

# Essential required tech stack limits per original v4 spec requirements
REQUIRED_VERSIONS = {
    "torch":                ("2.5.0", "2.6.99"),
    "torchaudio":           ("2.5.0", "2.6.99"),
    "faster_whisper":       ("1.1.0", "1.9.99"),
    "groq":                 ("0.9.0", "1.9.99"),
    "google.generativeai":  ("0.8.3", "0.9.99"),
    "PyQt6":                ("6.7.0", "6.9.99"),
    "sounddevice":          ("0.5.1", "0.6.99"),
    "numpy":                ("1.26.0", "1.26.99"),  # DO NOT UPGRADE TO 2.x YET
}


def validate_stack() -> list[str]:
    """
    Validate all crucial pip packages against required version ranges.
    Returns a list of error strings. Empty = all good.
    """
    errors = []
    
    for pkg, (vmin_str, vmax_str) in REQUIRED_VERSIONS.items():
        try:
            # Handle tricky module names
            mod_name = pkg.replace("-", "_")
            if pkg == "PyQt6":
                # PyQt6 package name matches module name
                pass
            
            mod = importlib.import_module(mod_name)
            
            # Retrieve version
            v_str = getattr(mod, "__version__", "0.0.0")
            
            try:
                v = Version(v_str)
                vmin = Version(vmin_str)
                vmax = Version(vmax_str)
                
                if not (vmin <= v <= vmax):
                    errors.append(
                        f"{pkg}: Version {v} outside allowed range [{vmin_str}, {vmax_str}]"
                    )
            except InvalidVersion:
                logger.warning("[COMPAT] Could not parse version %s for %s", v_str, pkg)
                
        except ImportError:
            errors.append(f"{pkg}: NOT INSTALLED")
            
    # Check torch/torchaudio version match specifically
    _check_torch_match(errors)

    if errors:
        logger.warning("[COMPAT] Found %d compatibility errors.", len(errors))
    else:
        logger.info("[COMPAT] Technology stack validated successfully.")
        
    return errors


def _check_torch_match(errors: list[str]) -> None:
    try:
        import torch
        import torchaudio
        
        t_ver = getattr(torch, '__version__', '').split('+')[0]
        ta_ver = getattr(torchaudio, '__version__', '').split('+')[0]
        
        if t_ver and ta_ver and t_ver != ta_ver:
             errors.append(
                 f"torch/torchaudio mismatch: torch is {t_ver}, torchaudio is {ta_ver}"
             )
    except ImportError:
        pass
