"""
ui/overlay_window.py - Transparent always-on-top Win32 overlay window.

Displays live transcripts and streaming AI responses as a click-through HUD.
Uses the Win32 layered-window API for true transparency without any
third-party windowing toolkit except Python's built-in ctypes.

Thread model: The overlay runs its own Win32 message loop in a daemon thread.
Methods (set_question, stream_token, etc.) are thread-safe – they post messages
to the Win32 queue via win32api.PostMessage / ctypes SendMessage.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Optional

from core.logger import get_logger

log = get_logger("ui.overlay")

# ── Platform check ────────────────────────────────────────────────────────────
_WIN32 = sys.platform == "win32"

if _WIN32:
    try:
        import ctypes
        import ctypes.wintypes as wt
        _HAS_WIN32 = True
    except ImportError:
        _HAS_WIN32 = False
else:
    _HAS_WIN32 = False


class OverlayWindow:
    """
    Transparent always-on-top overlay window with click-through support.

    Public API (all thread-safe):
        start()            – start overlay thread (non-blocking)
        shutdown()         – destroy window and stop thread
        set_status(msg)    – show status line (e.g. "Listening…")
        set_question(text) – show the detected interview question
        stream_token(tok)  – append a streaming LLM token
        finalize()         – mark response as complete
        set_alpha(value)   – adjust transparency (0-255)
    """

    def __init__(self, overlay_cfg) -> None:
        self._cfg      = overlay_cfg
        self._lock     = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running  = False
        self._hwnd     = None

        # Text state
        self._status:   str = "[LISTEN] Listening…"
        self._question: str = ""
        self._response: str = ""
        self._recording: bool = False

        # Tkinter fallback (cross-platform)
        self._tk_root  = None
        self._tk_text  = None
        self._use_tk   = not _HAS_WIN32

        # Dirty flag for Tkinter refresh
        self._dirty    = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the overlay in a background daemon thread."""
        self._running = True
        if self._use_tk:
            self._thread = threading.Thread(
                target=self._run_tk, daemon=True, name="overlay"
            )
        else:
            self._thread = threading.Thread(
                target=self._run_win32, daemon=True, name="overlay"
            )
        self._thread.start()

    def shutdown(self) -> None:
        """Destroy the overlay and stop the thread."""
        self._running = False
        if self._tk_root:
            try:
                self._tk_root.after(0, self._tk_root.destroy)
            except Exception:
                pass

    # ── Public setters (thread-safe) ──────────────────────────────────────────

    def set_status(self, message: str, recording: bool = False) -> None:
        with self._lock:
            self._status    = message
            self._recording = recording
            self._dirty     = True
        self._refresh()

    def set_question(self, text: str) -> None:
        with self._lock:
            self._question = text
            self._response = ""
            self._dirty    = True
        self._refresh()

    def stream_token(self, token: str) -> None:
        with self._lock:
            self._response += token
            self._dirty     = True
        self._refresh()

    def finalize(self) -> None:
        """Called when LLM streaming is complete."""
        self._refresh()

    def set_alpha(self, value: int) -> None:
        """Adjust window transparency. value: 0 (invisible) – 255 (opaque)."""
        with self._lock:
            self._cfg.alpha = max(0, min(255, value))
        if self._tk_root:
            try:
                self._tk_root.after(0, lambda: self._tk_root.attributes("-alpha", self._cfg.alpha / 255))
            except Exception:
                pass

    # ── Tkinter implementation (cross-platform) ───────────────────────────────

    def _run_tk(self) -> None:
        """Tkinter-based overlay (used on non-Windows or when win32 is unavailable)."""
        try:
            import tkinter as tk
            self._tk_root = tk.Tk()
            root = self._tk_root
            cfg  = self._cfg

            root.title("Interview Assistant")
            root.geometry(f"{cfg.width}x{cfg.height}+{cfg.x}+{cfg.y}")
            root.configure(bg="#0a0a14")
            root.attributes("-topmost", True)
            root.attributes("-alpha", cfg.alpha / 255)
            root.overrideredirect(True)    # No window decorations

            # Make click-through on Windows via SetWindowLong
            if _WIN32:
                try:
                    root.update()
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED     = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020
                    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ctypes.windll.user32.SetWindowLongW(
                        hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                    )
                except Exception:
                    pass

            # Text widget for display
            self._tk_text = tk.Text(
                root,
                bg="#0a0a14", fg="#00ff88",
                font=(cfg.font, cfg.font_size),
                wrap=tk.WORD,
                relief=tk.FLAT,
                padx=12, pady=8,
                state=tk.DISABLED,
                cursor="arrow",
            )
            self._tk_text.pack(fill=tk.BOTH, expand=True)

            # Configure text tags
            self._tk_text.tag_config("status",   foreground="#4a9eff", font=(cfg.font, cfg.font_size - 1))
            self._tk_text.tag_config("question", foreground="#ffcc00", font=(cfg.font, cfg.font_size, "bold"))
            self._tk_text.tag_config("response", foreground="#00ff88", font=(cfg.font, cfg.font_size))
            self._tk_text.tag_config("divider",  foreground="#2a2a4a")

            def _update():
                if not self._running:
                    return
                if self._dirty:
                    self._tk_refresh()
                root.after(150, _update)

            root.after(150, _update)
            root.mainloop()
        except Exception as exc:
            log.error("Overlay (Tk) error: %s\n%s", exc, traceback.format_exc())

    def _tk_refresh(self) -> None:
        """Rebuild the text widget content from current state."""
        with self._lock:
            status   = self._status
            question = self._question
            response = self._response
            self._dirty = False

        if not self._tk_text:
            return
        try:
            self._tk_text.config(state="normal")
            self._tk_text.delete("1.0", "end")

            self._tk_text.insert("end", f"{status}\n", "status")
            self._tk_text.insert("end", "─" * 60 + "\n", "divider")

            if question:
                self._tk_text.insert("end", f"Q: {question}\n\n", "question")
            if response:
                self._tk_text.insert("end", response, "response")

            self._tk_text.config(state="disabled")
            self._tk_text.see("end")
        except Exception:
            pass

    # ── Win32 implementation ──────────────────────────────────────────────────

    def _run_win32(self) -> None:
        """
        Full Win32 layered window overlay.
        Falls back to Tkinter if any Win32 call fails.
        """
        try:
            self._win32_main()
        except Exception as exc:
            log.warning("Win32 overlay failed (%s) – falling back to Tkinter", exc)
            self._use_tk = True
            self._run_tk()

    def _win32_main(self) -> None:
        """Create and run a Win32 layered transparent window."""
        import ctypes
        import ctypes.wintypes as wt

        user32  = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        gdi32   = ctypes.windll.gdi32

        cfg = self._cfg

        # Window class registration
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM
        )

        def wnd_proc(hwnd, msg, wparam, lparam):
            WM_DESTROY = 2
            WM_PAINT   = 15
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            if msg == WM_PAINT:
                self._win32_paint(hwnd)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wnd_proc_cb = WNDPROC(wnd_proc)
        hinstance   = kernel32.GetModuleHandleW(None)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style",         wt.UINT),
                ("lpfnWndProc",   WNDPROC),
                ("cbClsExtra",    ctypes.c_int),
                ("cbWndExtra",    ctypes.c_int),
                ("hInstance",     wt.HINSTANCE),
                ("hIcon",         wt.HICON),
                ("hCursor",       wt.HANDLE),
                ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName",  wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
            ]

        wc = WNDCLASSW()
        wc.lpfnWndProc   = wnd_proc_cb
        wc.hInstance     = hinstance
        wc.lpszClassName = "InterviewOverlay"
        wc.style         = 0x0003  # CS_HREDRAW | CS_VREDRAW
        user32.RegisterClassW(ctypes.byref(wc))

        WS_EX_LAYERED     = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOPMOST     = 0x00000008
        WS_EX_TOOLWINDOW  = 0x00000080
        WS_POPUP          = 0x80000000

        hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            "InterviewOverlay", "Interview Assistant",
            WS_POPUP,
            cfg.x, cfg.y, cfg.width, cfg.height,
            None, None, hinstance, None,
        )
        self._hwnd = hwnd

        # Set transparency (layered window attribute)
        LWA_ALPHA = 0x00000002
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, cfg.alpha, LWA_ALPHA)

        user32.ShowWindow(hwnd, 1)  # SW_NORMAL
        user32.UpdateWindow(hwnd)

        # Message loop
        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT),
                        ("wParam", wt.WPARAM), ("lParam", wt.LPARAM),
                        ("time", wt.DWORD), ("pt", wt.POINT)]
        msg = MSG()
        while self._running:
            result = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
            if result > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                if msg.message == 0x0012:  # WM_QUIT
                    break
            else:
                if self._dirty:
                    user32.InvalidateRect(hwnd, None, True)
                time.sleep(0.05)

    def _win32_paint(self, hwnd) -> None:
        """Paint text content onto the Win32 window."""
        import ctypes
        import ctypes.wintypes as wt

        with self._lock:
            status   = self._status
            question = self._question
            response = self._response
            self._dirty = False

        class PAINTSTRUCT(ctypes.Structure):
            _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL),
                        ("rcPaint", wt.RECT), ("fRestore", wt.BOOL),
                        ("fIncUpdate", wt.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

        ps  = PAINTSTRUCT()
        hdc = ctypes.windll.user32.BeginPaint(hwnd, ctypes.byref(ps))

        # Black background
        ctypes.windll.gdi32.SetBkColor(hdc, 0x00140a0a)    # RGB as COLORREF (BGR)
        ctypes.windll.gdi32.SetTextColor(hdc, 0x0088ff00)  # Green text

        rect = wt.RECT(10, 10, self._cfg.width - 10, self._cfg.height - 10)
        content = status
        if question:
            content += f"\n{'─'*40}\nQ: {question}"
        if response:
            content += f"\n\nA: {response}"

        DT_LEFT = 0; DT_WORDBREAK = 0x10
        ctypes.windll.user32.DrawTextW(hdc, content, -1, ctypes.byref(rect),
                                       DT_LEFT | DT_WORDBREAK)
        ctypes.windll.user32.EndPaint(hwnd, ctypes.byref(ps))

    def _refresh(self) -> None:
        """Schedule a visual refresh."""
        if self._tk_root:
            try:
                self._tk_root.after_idle(self._tk_refresh)
            except Exception:
                pass
        elif self._hwnd and _HAS_WIN32:
            try:
                ctypes.windll.user32.InvalidateRect(self._hwnd, None, True)
            except Exception:
                pass
