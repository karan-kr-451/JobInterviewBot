"""
ui/overlay/win32_overlay.py — Windows Transparent HUD (PyQt6).

Uses Qt.WindowType.WindowTransparentForInput and FRAMELESSWINDOWHINT
to create a click-through, always-on-top HUD.

Rules:
 - MUST be run on the main GUI thread.
 - Does not use BaseWorker (it's a Qt QWidget).

v3 fixes:
 - Prose line-height tightened (1.25) — no more double-spacing
 - Badge is compact pill (left-aligned), not full-width bar
 - Max width capped at 460px — less screen coverage
 - Code uses per-line <p margin:0> — no extra blank rows between lines
 - Anti-glare dim palette (brightness <= 160, no pure greens/whites)
"""

from __future__ import annotations

import logging
import ctypes
import re

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget, QFrame,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Palette — all colours dim (brightness <= 160) to reduce glasses reflection
# ---------------------------------------------------------------------------
PALETTE = {
    "bg_window":  "rgba(11, 13, 17, 215)",
    "border":     "#1c2430",
    "badge_bg":   "rgba(28, 48, 78, 230)",
    "badge_fg":   "#6a90b8",   # muted steel-blue
    "text_fg":    "#8aaa8c",   # desaturated sage (replaces bright #00FF00)
    "code_bg":    "rgba(6, 8, 12, 245)",
    "code_fg":    "#7aa09a",   # dim teal-grey
    "code_border":"#1e2d3d",
    "kw_fg":      "#5e86b0",   # muted blue — keywords
    "str_fg":     "#6e9470",   # muted green — strings
    "num_fg":     "#8e7658",   # muted amber — numbers
    "cmt_fg":     "#404840",   # very dim — comments
    "lang_fg":    "#364044",   # language label
}


# ---------------------------------------------------------------------------
# Syntax helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_BOLD_KW = {"def", "class", "return", "import", "from", "if", "else", "elif",
             "for", "while"}
_ALL_KW  = _BOLD_KW | {"in", "not", "and", "or", "True", "False", "None",
                        "try", "except", "with", "as", "lambda", "pass",
                        "break", "continue", "yield", "async", "await", "raise"}
_KW_PAT  = re.compile(r"\b(" + "|".join(re.escape(k) for k in _ALL_KW) + r")\b")


def _highlight_line(raw: str) -> str:
    """Return syntax-coloured HTML for one raw (unescaped) code line."""
    comment_sfx = ""
    m = re.match(r"^(.*?)(#.*)$", raw)
    if m:
        raw, comment_sfx = m.group(1), (
            f"<font color='{PALETTE['cmt_fg']}'>{_esc(m.group(2))}</font>"
        )

    out = _esc(raw)

    # Strings
    out = re.sub(
        r"('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")",
        lambda mo: f"<font color='{PALETTE['str_fg']}'>{mo.group(0)}</font>",
        out,
    )
    # Numbers
    out = re.sub(
        r"\b(\d+\.?\d*)\b",
        lambda mo: f"<font color='{PALETTE['num_fg']}'>{mo.group(0)}</font>",
        out,
    )
    # Keywords
    def _kw_sub(mo: re.Match) -> str:
        w = mo.group(0)
        inner = f"<b>{w}</b>" if w in _BOLD_KW else w
        return f"<font color='{PALETTE['kw_fg']}'>{inner}</font>"
    out = _KW_PAT.sub(_kw_sub, out)

    return out + comment_sfx


def _code_block_html(code: str, lang: str, fs: int) -> str:
    lang_label = lang.upper() if lang else "CODE"
    # Each line in its own zero-margin <p> — avoids empty rows between lines
    lines_html = "".join(
        f"<p style='margin:0;padding:0;white-space:pre'>{_highlight_line(ln)}</p>"
        for ln in code.split("\n")
    )
    return (
        f"<div style='"
        f"background:{PALETTE['code_bg']};"
        f"border:1px solid {PALETTE['code_border']};"
        f"border-left:3px solid {PALETTE['kw_fg']};"
        f"border-radius:4px;"
        f"padding:5px 8px;"
        f"margin:3px 0;"
        f"'>"
        f"<p style='margin:0 0 3px 0;padding:0;"
        f"font-size:{fs - 3}px;color:{PALETTE['lang_fg']}'>"
        f"── {lang_label} ──</p>"
        f"<span style='"
        f"font-family:Consolas,\"Courier New\",monospace;"
        f"font-size:{fs}px;color:{PALETTE['code_fg']}'>"
        f"{lines_html}</span>"
        f"</div>"
    )


def _prose_html(text: str, fs: int) -> str:
    escaped = _esc(text)
    # Inline `code`
    escaped = re.sub(
        r"`([^`]+)`",
        lambda m: (
            f"<code style='background:rgba(6,8,12,200);"
            f"color:{PALETTE['code_fg']};padding:0 3px;"
            f"border-radius:2px;font-size:{fs - 1}px'>"
            f"{_esc(m.group(1))}</code>"
        ),
        escaped,
    )
    # Each line in its own zero-margin paragraph → tight spacing
    lines_html = "".join(
        f"<p style='margin:0;padding:0;line-height:1.25'>{ln}</p>"
        for ln in escaped.split("\n")
    )
    return (
        f"<span style='color:{PALETTE['text_fg']};"
        f"font-family:Consolas,monospace;font-size:{fs}px'>"
        f"{lines_html}</span>"
    )


def _render_to_html(text: str, fs: int) -> str:
    """Convert markdown-ish text (with ``` fences) to HTML for QLabel."""
    CODE_FENCE = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)
    segments, last = [], 0

    for m in CODE_FENCE.finditer(text):
        prose = text[last : m.start()].strip()
        if prose:
            segments.append(("prose", prose))
        segments.append(("code", m.group(2).rstrip(), m.group(1) or ""))
        last = m.end()

    tail = text[last:].strip()
    if tail:
        segments.append(("prose", tail))
    if not segments:
        segments.append(("prose", text))

    body = "".join(
        _prose_html(s[1], fs) if s[0] == "prose" else _code_block_html(s[1], s[2], fs)
        for s in segments
    )
    return f"<html><body style='margin:0;padding:0'>{body}</body></html>"


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class Win32Overlay(QWidget):
    """
    Transparent, click-through always-on-top HUD for Windows.

    Signals (call from any thread — Qt queues them to the GUI thread):
      text_updated(str)           — replace body text
      classification_updated(str) — replace category badge
    """

    text_updated           = pyqtSignal(str)
    classification_updated = pyqtSignal(str)

    MAX_WIDTH = 460   # px — narrow enough not to cover half the screen

    def __init__(
        self,
        opacity:   float = 0.80,   # lower → less lens glare
        position:  str   = "top-right",
        font_size: int   = 13,
    ) -> None:
        super().__init__()
        self.opacity   = opacity
        self.position  = position
        self.font_size = font_size
        self._current_classification = ""
        self._current_text           = ""

        self._setup_ui()
        self.text_updated.connect(self._on_text_updated)
        self.classification_updated.connect(self._on_classification_updated)
        QTimer.singleShot(100, self._apply_positioning)
        QTimer.singleShot(500, self._apply_stealth_affinity)

    # ------------------------------------------------------------------
    # Stealth — excluded from Zoom / Teams screen capture
    # ------------------------------------------------------------------
    def _apply_stealth_affinity(self) -> None:
        try:
            hwnd = self.winId()
            if isinstance(hwnd, (int, ctypes.c_void_p)):
                ctypes.windll.user32.SetWindowDisplayAffinity(int(hwnd), 0x00000011)
                logger.info("[OVERLAY] Stealth affinity applied.")
        except Exception as exc:
            logger.warning("[OVERLAY] Stealth affinity failed: %s", exc)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self.opacity)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Dark translucent card
        self._card = QFrame()
        self._card.setStyleSheet(
            f"QFrame {{"
            f"  background:{PALETTE['bg_window']};"
            f"  border:1px solid {PALETTE['border']};"
            f"  border-radius:6px;"
            f"}}"
        )
        card = QVBoxLayout(self._card)
        card.setContentsMargins(10, 7, 10, 9)
        card.setSpacing(5)

        # Badge row — left-aligned compact pill
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(0)

        self._badge = QLabel("")
        self._badge.setVisible(False)
        self._badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._badge.setStyleSheet(
            f"QLabel {{"
            f"  color:{PALETTE['badge_fg']};"
            f"  background:{PALETTE['badge_bg']};"
            f"  font-family:Consolas,monospace;"
            f"  font-size:{self.font_size - 2}px;"
            f"  font-weight:bold;"
            f"  padding:2px 8px;"
            f"  border-radius:3px;"
            f"  border:none;"
            f"}}"
        )
        badge_row.addWidget(self._badge)
        badge_row.addStretch()
        card.addLayout(badge_row)

        # Content area — fixed width, word-wrap, rich text
        self._content = QLabel("")
        self._content.setWordWrap(True)
        self._content.setTextFormat(Qt.TextFormat.RichText)
        self._content.setFixedWidth(self.MAX_WIDTH)
        self._content.setStyleSheet(
            f"QLabel {{"
            f"  color:{PALETTE['text_fg']};"
            f"  font-family:Consolas,monospace;"
            f"  font-size:{self.font_size}px;"
            f"  background:transparent;"
            f"  border:none;"
            f"  padding:0;margin:0;"
            f"}}"
        )
        card.addWidget(self._content)

        root.addWidget(self._card)

    # ------------------------------------------------------------------
    # Signal handlers (always called on GUI thread via Qt queuing)
    # ------------------------------------------------------------------
    def _on_text_updated(self, text: str) -> None:
        self._current_text = text
        self._refresh_display()

    def _on_classification_updated(self, label: str) -> None:
        self._current_classification = label
        self._refresh_display()

    def _refresh_display(self) -> None:
        # Badge
        if self._current_classification:
            self._badge.setText(f"  {self._current_classification}  ")
            self._badge.setVisible(True)
        else:
            self._badge.setVisible(False)

        # Trim to last 25 lines to prevent uncontrolled height growth
        lines = self._current_text.split("\n")
        body  = "\n".join(lines[-25:]) if len(lines) > 25 else self._current_text

        self._content.setText(_render_to_html(body, self.font_size))
        self.adjustSize()
        self._apply_positioning()

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------
    def _apply_positioning(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom   = screen.availableGeometry()
        w, h   = self.width(), self.height()
        x      = geom.width() - w - 20
        y      = 20
        if self.position == "bottom-right":
            y = geom.height() - h - 50
        elif self.position == "top-left":
            x = 20
        elif self.position == "bottom-left":
            x, y = 20, geom.height() - h - 50
        self.move(geom.x() + x, geom.y() + y)