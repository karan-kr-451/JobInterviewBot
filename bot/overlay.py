"""
overlay.py - Win32 invisible overlay window.

Controls (ALL require Ctrl held - no visible UI, no title bar):
  Ctrl+H          toggle hide / show
  Ctrl+Q          quit application
  Ctrl+  / Ctrl+  font size up / down
  Ctrl+F          toggle fullscreen
  Ctrl+M          minimize to taskbar
  Ctrl+  / Ctrl+-> nudge window left / right  (hold Shift for up / down)
  PgUp / PgDn     scroll answer
  Home / End      scroll to top / bottom
  Mouse wheel     scroll when hovering over window

The window is excluded from screen-capture via SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE).
"""

import sys
import ctypes
import threading
import textwrap
import time

from config import (
    OVERLAY_WIDTH, OVERLAY_HEIGHT, OVERLAY_X, OVERLAY_Y,
    OVERLAY_ALPHA, OVERLAY_FONT, OVERLAY_FONT_SZ, OVERLAY_WRAP,
    HOTKEY_HIDE, HOTKEY_QUIT, HOTKEY_FULLSCREEN, HOTKEY_MINIMIZE,
)

# -- Stub for non-Windows ------------------------------------------------------
if sys.platform != "win32":
    class Win32Overlay:
        """No-op stub on non-Windows platforms."""
        def start(self):                                        print("[Overlay] Windows only - skipped")
        def set_question(self, q):                              pass
        def stream_token(self, t):                              pass
        def set_status(self, msg, recording=False,
                       loading=False, error=False):             print(f"[Status] {msg}")
        def finalize(self):                                     pass
        def shutdown(self):                                     pass
else:
    # -- Win32 imports ---------------------------------------------------------
    _u32  = ctypes.windll.user32
    _gdi  = ctypes.windll.gdi32
    _kern = ctypes.windll.kernel32

    # -- Win32 constants -------------------------------------------------------
    WS_POPUP               = 0x80000000
    WS_VISIBLE             = 0x10000000
    WS_EX_TOPMOST          = 0x00000008
    WS_EX_LAYERED          = 0x00080000
    WS_EX_TOOLWINDOW       = 0x00000080
    WS_EX_NOACTIVATE       = 0x08000000
    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    LWA_ALPHA              = 0x00000002
    CS_HREDRAW             = 0x0002
    CS_VREDRAW             = 0x0001
    IDC_ARROW              = 32512
    WM_DESTROY             = 0x0002
    WM_PAINT               = 0x000F
    WM_KEYDOWN             = 0x0100
    WM_MOUSEACTIVATE       = 0x0021
    MA_NOACTIVATE          = 3
    WM_APP_REPAINT         = 0x0401
    WM_APP_QUIT            = 0x0402
    WM_APP_SCROLL          = 0x0403
    VK_CONTROL             = 0x11
    VK_SHIFT               = 0x10
    VK_UP                  = 0x26
    VK_DOWN                = 0x28
    VK_LEFT                = 0x25
    VK_RIGHT               = 0x27
    VK_PRIOR               = 0x21   # PgUp
    VK_NEXT                = 0x22   # PgDn
    VK_HOME                = 0x24
    VK_END                 = 0x23
    VK_F                   = 0x46
    VK_M                   = 0x4D
    TRANSPARENT            = 1
    DT_LEFT                = 0x00000000
    DT_NOPREFIX            = 0x00000800
    WH_MOUSE_LL            = 14
    HC_ACTION              = 0
    SW_MINIMIZE            = 6
    SW_RESTORE             = 9
    HWND_TOP               = 0

    # -- Colors (BGR in Win32 GDI) ---------------------------------------------
    def _rgb(r, g, b): return r | (g << 8) | (b << 16)

    COL_BG          = _rgb(13,  13,  13)
    COL_Q           = _rgb(0,  229, 255)
    COL_A           = _rgb(255, 204,  0)
    COL_LABEL       = _rgb(110, 110, 110)
    COL_STATUS_OK   = _rgb(68,  255,  68)
    COL_STATUS_REC  = _rgb(255,  60,  60)
    COL_STATUS_LOAD = _rgb(255, 153,   0)   # amber - loading / initialising
    COL_STATUS_ERR  = _rgb(255,  80,  80)   # bright red - error / degraded

    # -- ctypes structures -----------------------------------------------------
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_uint64, ctypes.c_int64)

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt_x",       ctypes.c_long),
                    ("pt_y",       ctypes.c_long),
                    ("mouseData",  ctypes.c_uint32),
                    ("flags",      ctypes.c_uint32),
                    ("time",       ctypes.c_uint32),
                    ("dwExtraInfo",ctypes.c_uint64)]

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_uint64, ctypes.c_int64
    )

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize",       ctypes.c_uint),
                    ("style",        ctypes.c_uint),
                    ("lpfnWndProc",  WNDPROC),          # must be WNDPROC, not c_void_p
                    ("cbClsExtra",   ctypes.c_int),
                    ("cbWndExtra",   ctypes.c_int),
                    ("hInstance",    ctypes.c_void_p),
                    ("hIcon",        ctypes.c_void_p),
                    ("hCursor",      ctypes.c_void_p),
                    ("hbrBackground",ctypes.c_void_p),
                    ("lpszMenuName", ctypes.c_wchar_p),
                    ("lpszClassName",ctypes.c_wchar_p),
                    ("hIconSm",      ctypes.c_void_p)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc",        ctypes.c_void_p),
                    ("fErase",     ctypes.c_bool),
                    ("rcPaint",    ctypes.c_int * 4),
                    ("fRestore",   ctypes.c_bool),
                    ("fIncUpdate", ctypes.c_bool),
                    ("rgbReserved",ctypes.c_byte * 32)]

    class RECT(ctypes.Structure):
        _fields_ = [("left",  ctypes.c_long), ("top",    ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd",    ctypes.c_void_p),
                    ("message", ctypes.c_uint),
                    ("wParam",  ctypes.c_uint64),
                    ("lParam",  ctypes.c_int64),
                    ("time",    ctypes.c_uint),
                    ("pt",      ctypes.c_long * 2)]

    # -- argtypes (set once at module load) ------------------------------------
    _u32.DefWindowProcW.argtypes            = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64]
    _u32.DefWindowProcW.restype             = ctypes.c_ssize_t
    _u32.PostMessageW.argtypes              = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64]
    _u32.PostMessageW.restype               = ctypes.c_bool
    _u32.GetKeyState.argtypes               = [ctypes.c_int]
    _u32.GetKeyState.restype                = ctypes.c_short
    _u32.DrawTextW.argtypes                 = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
                                               ctypes.c_void_p, ctypes.c_uint]
    _u32.DrawTextW.restype                  = ctypes.c_int
    _u32.SetWindowDisplayAffinity.argtypes  = [ctypes.c_void_p, ctypes.c_uint32]
    _u32.SetWindowDisplayAffinity.restype   = ctypes.c_bool
    _u32.SetLayeredWindowAttributes.argtypes= [ctypes.c_void_p, ctypes.c_uint32,
                                               ctypes.c_byte,   ctypes.c_uint32]
    _u32.SetLayeredWindowAttributes.restype = ctypes.c_bool
    _u32.GetMessageW.argtypes               = [ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_uint,   ctypes.c_uint]
    _u32.GetMessageW.restype                = ctypes.c_int
    _u32.TranslateMessage.argtypes          = [ctypes.c_void_p]
    _u32.TranslateMessage.restype           = ctypes.c_bool
    _u32.DispatchMessageW.argtypes          = [ctypes.c_void_p]
    _u32.DispatchMessageW.restype           = ctypes.c_ssize_t
    _u32.SetWindowsHookExW.argtypes         = [ctypes.c_int, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.c_uint32]
    _u32.SetWindowsHookExW.restype          = ctypes.c_void_p
    _u32.UnhookWindowsHookEx.argtypes       = [ctypes.c_void_p]
    _u32.UnhookWindowsHookEx.restype        = ctypes.c_bool
    _u32.CallNextHookEx.argtypes            = [ctypes.c_void_p, ctypes.c_int,
                                               ctypes.c_uint64, ctypes.c_int64]
    _u32.CallNextHookEx.restype             = ctypes.c_ssize_t
    _u32.GetWindowRect.argtypes             = [ctypes.c_void_p, ctypes.c_void_p]
    _u32.GetWindowRect.restype              = ctypes.c_bool
    _u32.MoveWindow.argtypes                = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                               ctypes.c_int,   ctypes.c_int, ctypes.c_bool]
    _u32.MoveWindow.restype                 = ctypes.c_bool
    _u32.GetSystemMetrics.argtypes          = [ctypes.c_int]
    _u32.GetSystemMetrics.restype           = ctypes.c_int
    _u32.ShowWindow.argtypes                = [ctypes.c_void_p, ctypes.c_int]
    _u32.ShowWindow.restype                 = ctypes.c_bool

    # -- argtypes for Win32 calls that lacked them (missing argtypes on 64-bit
    #    Windows causes ctypes to missize args -> corrupt stack -> access violation) -
    _u32.RegisterClassExW.argtypes          = [ctypes.c_void_p]
    _u32.RegisterClassExW.restype           = ctypes.c_uint32         # ATOM (16-bit value in 32-bit reg)

    _u32.UnregisterClassW.argtypes          = [ctypes.c_wchar_p, ctypes.c_void_p]
    _u32.UnregisterClassW.restype           = ctypes.c_bool

    _u32.CreateWindowExW.argtypes           = [
        ctypes.c_uint32,    # dwExStyle
        ctypes.c_wchar_p,   # lpClassName
        ctypes.c_wchar_p,   # lpWindowName
        ctypes.c_uint32,    # dwStyle
        ctypes.c_int,       # X
        ctypes.c_int,       # Y
        ctypes.c_int,       # nWidth
        ctypes.c_int,       # nHeight
        ctypes.c_void_p,    # hWndParent
        ctypes.c_void_p,    # hMenu
        ctypes.c_void_p,    # hInstance
        ctypes.c_void_p,    # lpParam
    ]
    _u32.CreateWindowExW.restype            = ctypes.c_void_p

    _u32.DestroyWindow.argtypes             = [ctypes.c_void_p]
    _u32.DestroyWindow.restype              = ctypes.c_bool

    _u32.UpdateWindow.argtypes              = [ctypes.c_void_p]
    _u32.UpdateWindow.restype               = ctypes.c_bool

    _u32.LoadCursorW.argtypes               = [ctypes.c_void_p, ctypes.c_void_p]
    _u32.LoadCursorW.restype                = ctypes.c_void_p

    _u32.BeginPaint.argtypes                = [ctypes.c_void_p, ctypes.c_void_p]
    _u32.BeginPaint.restype                 = ctypes.c_void_p

    _u32.EndPaint.argtypes                  = [ctypes.c_void_p, ctypes.c_void_p]
    _u32.EndPaint.restype                   = ctypes.c_bool

    _u32.GetClientRect.argtypes             = [ctypes.c_void_p, ctypes.c_void_p]
    _u32.GetClientRect.restype              = ctypes.c_bool

    _u32.FillRect.argtypes                  = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    _u32.FillRect.restype                   = ctypes.c_int

    _u32.InvalidateRect.argtypes            = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
    _u32.InvalidateRect.restype             = ctypes.c_bool

    _u32.PostQuitMessage.argtypes           = [ctypes.c_int]
    _u32.PostQuitMessage.restype            = None

    # -- argtypes for GDI32 calls (also previously missing) --------------------
    _gdi.CreateCompatibleDC.argtypes        = [ctypes.c_void_p]
    _gdi.CreateCompatibleDC.restype         = ctypes.c_void_p

    _gdi.CreateCompatibleBitmap.argtypes    = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    _gdi.CreateCompatibleBitmap.restype     = ctypes.c_void_p

    _gdi.SelectObject.argtypes              = [ctypes.c_void_p, ctypes.c_void_p]
    _gdi.SelectObject.restype               = ctypes.c_void_p

    _gdi.DeleteObject.argtypes              = [ctypes.c_void_p]
    _gdi.DeleteObject.restype               = ctypes.c_bool

    _gdi.DeleteDC.argtypes                  = [ctypes.c_void_p]
    _gdi.DeleteDC.restype                   = ctypes.c_bool

    _gdi.BitBlt.argtypes                    = [
        ctypes.c_void_p,    # hdcDest
        ctypes.c_int,       # x
        ctypes.c_int,       # y
        ctypes.c_int,       # cx
        ctypes.c_int,       # cy
        ctypes.c_void_p,    # hdcSrc
        ctypes.c_int,       # x1
        ctypes.c_int,       # y1
        ctypes.c_uint32,    # rop
    ]
    _gdi.BitBlt.restype                     = ctypes.c_bool

    _gdi.CreateSolidBrush.argtypes          = [ctypes.c_uint32]
    _gdi.CreateSolidBrush.restype           = ctypes.c_void_p

    _gdi.CreatePen.argtypes                 = [ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
    _gdi.CreatePen.restype                  = ctypes.c_void_p

    _gdi.MoveToEx.argtypes                  = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    _gdi.MoveToEx.restype                   = ctypes.c_bool

    _gdi.LineTo.argtypes                    = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    _gdi.LineTo.restype                     = ctypes.c_bool

    _gdi.SetBkMode.argtypes                 = [ctypes.c_void_p, ctypes.c_int]
    _gdi.SetBkMode.restype                  = ctypes.c_int

    _gdi.SetTextColor.argtypes              = [ctypes.c_void_p, ctypes.c_uint32]
    _gdi.SetTextColor.restype               = ctypes.c_uint32

    _gdi.CreateFontW.argtypes               = [
        ctypes.c_int,       # cHeight
        ctypes.c_int,       # cWidth
        ctypes.c_int,       # cEscapement
        ctypes.c_int,       # cOrientation
        ctypes.c_int,       # cWeight
        ctypes.c_uint32,    # bItalic
        ctypes.c_uint32,    # bUnderline
        ctypes.c_uint32,    # bStrikeOut
        ctypes.c_uint32,    # iCharSet
        ctypes.c_uint32,    # iOutPrecision
        ctypes.c_uint32,    # iClipPrecision
        ctypes.c_uint32,    # iQuality
        ctypes.c_uint32,    # iPitchAndFamily
        ctypes.c_wchar_p,   # pszFaceName
    ]
    _gdi.CreateFontW.restype                = ctypes.c_void_p

    # -- kernel32 argtypes -----------------------------------------------------
    _kern.GetModuleHandleW.argtypes         = [ctypes.c_wchar_p]
    _kern.GetModuleHandleW.restype          = ctypes.c_void_p

    _kern.GetLastError.argtypes             = []
    _kern.GetLastError.restype              = ctypes.c_uint32

    # SM_CXSCREEN / SM_CYSCREEN
    SM_CXSCREEN = 0
    SM_CYSCREEN = 1
    MOVE_STEP   = 40   # pixels per nudge

    # -------------------------------------------------------------------------
    class Win32Overlay:
        """
        Invisible Win32 overlay, excluded from screen capture.
        All interaction via Ctrl+<key> hotkeys - no visible title bar or chrome.
        Thread-safe: all public methods may be called from any thread.
        """

        def __init__(self):
            self._hwnd         = None
            self._ready        = threading.Event()
            self._loop_done    = threading.Event()   # set when GetMessage loop exits
            self._lock         = threading.Lock()
            self._question     = ""
            self._answer       = ""
            self._status       = "[WAIT]  Starting up..."
            self._status_col   = COL_STATUS_LOAD
            self._font_sz      = OVERLAY_FONT_SZ
            self._hidden       = False
            self._fullscreen   = False
            self._hfont        = None
            self._hfont_bold   = None
            self._cached_fsz   = None
            self._scroll_lines = 0
            self._max_lines    = 0
            self._header_lines = 3
            self._win_x        = OVERLAY_X
            self._win_y        = OVERLAY_Y
            self._win_w        = OVERLAY_WIDTH
            self._win_h        = OVERLAY_HEIGHT
            self._hbr_bg       = None
            # GC anchors - ctypes callbacks must stay alive as long as the window
            self._wndproc_cb   = None
            self._hook_cb      = None
            self._hook_handle  = None
            self._last_repaint = 0  # NEW: Throttle repaints to prevent UI starvation

        # -- Public thread-safe API --------------------------------------------

        def start(self):
            # NON-DAEMON: daemon threads are terminated by Python before atexit
            # handlers run. If the overlay thread is a daemon, PostMessage(WM_APP_QUIT)
            # in _atexit_cleanup is delivered to a dead thread - _loop_done never
            # fires, we time out, GC frees the thunks while the mouse hook still
            # points at them -> access violation. Non-daemon keeps the thread alive
            # through the full atexit sequence.
            t = threading.Thread(target=self._run, daemon=False, name="overlay")
            t.start()
            if not self._ready.wait(timeout=6):
                print("[Overlay] Warning: window did not become ready in 6s")
            import atexit
            atexit.register(self._atexit_cleanup)

        def set_question(self, question: str):
            with self._lock:
                self._question     = question
                self._answer       = ""
                self._status       = "   Generating answer..."
                self._status_col   = COL_STATUS_OK
                self._scroll_lines = 0
            self._repaint(force=True)

        def stream_token(self, token: str):
            """Append a streamed token and repaint. Safe to call from any thread."""
            with self._lock:
                self._answer += token
            self._repaint()

        def set_status(self, msg: str, recording: bool = False,
                       loading: bool = False, error: bool = False):
            """
            Update the status bar.
              recording=True -> red   (capturing speech)
              loading=True   -> amber (initialising / loading model)
              error=True     -> bright red (degraded / failed component)
              default        -> green (idle / listening)
            """
            with self._lock:
                self._status = msg
                if recording:
                    self._status_col = COL_STATUS_REC
                elif loading:
                    self._status_col = COL_STATUS_LOAD
                elif error:
                    self._status_col = COL_STATUS_ERR
                else:
                    self._status_col = COL_STATUS_OK
            self._repaint(force=True)

        def finalize(self):
            with self._lock:
                self._status     = f"  Done - {time.strftime('%H:%M:%S')}"
                self._status_col = COL_STATUS_OK
            self._repaint(force=True)

        def shutdown(self):
            """Shutdown the overlay window. Safe to call from any thread."""
            # GC is permanently disabled at startup - no toggle needed
            try:
                if self._hwnd:
                    _u32.PostMessageW(self._hwnd, WM_APP_QUIT, 0, 0)
            except Exception:
                pass

        def _atexit_cleanup(self):
            """
            Called at process exit via atexit - runs BEFORE Python GC frees modules.

            The overlay thread is non-daemon so Python keeps it alive through this
            handler. We must explicitly drive it to exit here or Python will wait
            forever after atexit completes.

            Sequence:
              1. Disable GC             -> prevent GC from running during cleanup
              2. Unregister mouse hook  -> no more hook callbacks
              3. Post WM_APP_QUIT       -> overlay message loop calls DestroyWindow
                                          then PostQuitMessage -> GetMessage returns 0
                                          -> thread sets _loop_done and exits
              4. Wait on _loop_done     -> guarantees loop has exited before GC runs
              5. If no window existed   -> set _loop_done directly so thread unblocks
            
            CRITICAL: GC must stay disabled after this function returns because
            Python will run GC after all atexit handlers complete. If GC runs while
            Win32 hook callbacks are still in memory, access violation occurs.
            """
            # 0. Disable GC to prevent access violations during cleanup
            import gc
            gc.disable()
            
            # 1. Unregister the low-level mouse hook first - fires on every mouse move
            try:
                if self._hook_handle:
                    _u32.UnhookWindowsHookEx(self._hook_handle)
                    self._hook_handle = None
            except Exception:
                pass

            # 2. Destroy the window
            try:
                hwnd = self._hwnd
                if hwnd:
                    self._hwnd = None   # clear so _repaint() becomes a no-op
                    _u32.PostMessageW(hwnd, WM_APP_QUIT, 0, 0)
                else:
                    # Window was never created - signal the thread directly
                    self._loop_done.set()
            except Exception:
                self._loop_done.set()

            # 3. Wait for the message loop to actually exit (up to 3s)
            self._loop_done.wait(timeout=3.0)
            
            # NOTE: GC stays disabled - do NOT re-enable it here

        # -- Internals ---------------------------------------------------------

        def _repaint(self, force: bool = False):
            if not self._hwnd:
                return
                
            now = time.time()
            # Throttle to max 50fps (20ms) unless it's a forced repaint
            if not force and (now - self._last_repaint < 0.020):
                return
                
            self._last_repaint = now
            _u32.PostMessageW(self._hwnd, WM_APP_REPAINT, 0, 0)

        def _vis_lines(self):
            lh   = self._font_sz + 5
            used = self._header_lines * lh + self._PAD * 3 + 12 + 6
            return max(1, (self._win_h - used) // lh)

        @property
        def _PAD(self): return 12

        def _run(self):
            """Main message loop - runs in its own dedicated thread."""
            try:
                self._run_inner()
            except Exception as e:
                import traceback
                print(f"[Overlay] _run error: {e}")
                traceback.print_exc()
            finally:
                # Always unblock start() - even if we crash before _ready.set()
                if not self._ready.is_set():
                    self._ready.set()

        def _run_inner(self):
            hInst      = _kern.GetModuleHandleW(None)
            class_name = "IVOverlayV5"

            def wndproc(hwnd, msg, wp, lp):
                msg = int(msg) & 0xFFFFFFFF
                wp  = int(wp)  & 0xFFFFFFFFFFFFFFFF

                # Debug output for window messages
                if msg == 0x0084:  # WM_NCHITTEST
                    # Allow dragging from anywhere in the window
                    return 2  # HTCAPTION

                if msg == WM_PAINT:
                    self._paint(hwnd)
                    return 0

                elif msg == WM_APP_REPAINT:
                    _u32.InvalidateRect(hwnd, None, True)
                    return 0

                elif msg == WM_APP_SCROLL:
                    delta = ctypes.c_int64(wp).value
                    vis   = self._vis_lines()
                    self._scroll_lines = max(0, min(
                        self._scroll_lines - delta,
                        max(0, self._max_lines - vis)
                    ))
                    _u32.InvalidateRect(hwnd, None, True)
                    return 0

                elif msg == WM_APP_QUIT:
                    self._cleanup_hook()
                    _u32.DestroyWindow(hwnd)
                    return 0

                elif msg == WM_KEYDOWN:
                    vk    = wp & 0xFF
                    ctrl  = bool(_u32.GetKeyState(VK_CONTROL) & 0x8000)
                    shift = bool(_u32.GetKeyState(VK_SHIFT)   & 0x8000)
                    self._handle_key(hwnd, vk, ctrl, shift)
                    return 0

                elif msg == WM_DESTROY:
                    self._cleanup_hook()
                    _u32.PostQuitMessage(0)
                    return 0

                return _u32.DefWindowProcW(hwnd, msg, wp, lp)

            self._wndproc_cb = WNDPROC(wndproc)
            # Keep a module-level reference so the GC doesn't collect the callback
            global _global_wndproc_ref
            _global_wndproc_ref = self._wndproc_cb

            # Register window class
            wc = WNDCLASSEXW()
            wc.cbSize        = ctypes.sizeof(WNDCLASSEXW)
            wc.style         = CS_HREDRAW | CS_VREDRAW
            wc.lpfnWndProc   = self._wndproc_cb          # assign directly - cast().value returns None in frozen builds
            wc.hInstance     = hInst
            wc.hCursor       = _u32.LoadCursorW(None, IDC_ARROW)
            self._hbr_bg     = _gdi.CreateSolidBrush(COL_BG)
            wc.hbrBackground = self._hbr_bg
            wc.lpszClassName = class_name
            _u32.UnregisterClassW(class_name, hInst)
            atom = _u32.RegisterClassExW(ctypes.byref(wc))
            if not atom:
                print(f"[Overlay] RegisterClassExW failed err={_kern.GetLastError()}")
                self._ready.set()
                return

            ex_style = WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW
            hwnd = _u32.CreateWindowExW(
                ex_style, class_name, "Interview Overlay",
                WS_POPUP | WS_VISIBLE,
                self._win_x, self._win_y, self._win_w, self._win_h,
                None, None, hInst, None
            )
            if not hwnd:
                print(f"[Overlay] CreateWindowExW failed err={_kern.GetLastError()}")
                self._ready.set()
                return

            self._hwnd = hwnd
            _u32.SetLayeredWindowAttributes(hwnd, 0, OVERLAY_ALPHA, LWA_ALPHA)
            _u32.ShowWindow(hwnd, 1)
            _u32.UpdateWindow(hwnd)

            # Must happen AFTER ShowWindow - DWM ordering requirement
            time.sleep(0.15)
            ok = _u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            print(f"[Overlay] {'Screen-capture hidden' if ok else 'SetWindowDisplayAffinity failed'}")

            # Mouse wheel hook for scroll-over-window
            def _ll_hook(nCode, wParam, lParam):
                if nCode == HC_ACTION and wParam == 0x020A and self._hwnd:
                    hs  = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    raw = (hs.mouseData >> 16) & 0xFFFF
                    if raw > 32767: raw -= 65536
                    lines = raw // 40
                    rc = RECT()
                    _u32.GetWindowRect(self._hwnd, ctypes.byref(rc))
                    if rc.left <= hs.pt_x <= rc.right and rc.top <= hs.pt_y <= rc.bottom:
                        _u32.PostMessageW(self._hwnd, WM_APP_SCROLL,
                                          ctypes.c_uint64(lines & 0xFFFFFFFFFFFFFFFF).value, 0)
                return _u32.CallNextHookEx(None, nCode, wParam, lParam)

            self._hook_cb = HOOKPROC(_ll_hook)
            global _global_hook_ref
            _global_hook_ref  = self._hook_cb
            self._hook_handle = _u32.SetWindowsHookExW(
                WH_MOUSE_LL,
                ctypes.cast(self._hook_cb, ctypes.c_void_p).value,
                None, 0
            )
            print(f"[Overlay] {'Mouse wheel hook' if self._hook_handle else 'Hook failed'}")

            self._ready.set()

            msg = MSG()
            while _u32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                _u32.TranslateMessage(ctypes.byref(msg))
                _u32.DispatchMessageW(ctypes.byref(msg))

            self._loop_done.set()   # message loop exited - thunks can now be GC'd safely

        def _cleanup_hook(self):
            if self._hook_handle:
                _u32.UnhookWindowsHookEx(self._hook_handle)
                self._hook_handle = None

        def _handle_key(self, hwnd, vk, ctrl, shift):
            """Dispatch secret hotkeys. All require Ctrl held."""
            if not ctrl:
                # Plain keys: scroll only
                vis = self._vis_lines()
                sc  = self._scroll_lines
                if   vk == VK_UP:    sc = max(0, sc - 3)
                elif vk == VK_DOWN:  sc = min(sc + 3, max(0, self._max_lines - vis))
                elif vk == VK_PRIOR: sc = max(0, sc - vis)
                elif vk == VK_NEXT:  sc = min(sc + vis, max(0, self._max_lines - vis))
                elif vk == VK_HOME:  sc = 0
                elif vk == VK_END:   sc = max(0, self._max_lines - vis)
                else:
                    # Unknown key, ignore
                    return
                self._scroll_lines = sc
                _u32.InvalidateRect(hwnd, None, True)
                return

            # Ctrl held - secret controls
            if vk == HOTKEY_HIDE:       # Ctrl+H
                self._toggle_hide()

            elif vk == HOTKEY_QUIT:     # Ctrl+Q
                _u32.PostMessageW(hwnd, WM_APP_QUIT, 0, 0)

            elif vk == HOTKEY_FULLSCREEN:  # Ctrl+F
                self._toggle_fullscreen(hwnd)

            elif vk == HOTKEY_MINIMIZE:    # Ctrl+M
                _u32.ShowWindow(hwnd, SW_MINIMIZE)

            elif vk == VK_UP:           # Ctrl+  -> font up
                with self._lock: self._font_sz = min(28, self._font_sz + 1)
                self._cached_fsz = None
                _u32.InvalidateRect(hwnd, None, True)

            elif vk == VK_DOWN:         # Ctrl+  -> font down
                with self._lock: self._font_sz = max(7,  self._font_sz - 1)
                self._cached_fsz = None
                _u32.InvalidateRect(hwnd, None, True)

            elif vk == VK_LEFT:         # Ctrl+  -> nudge left (Shift = up)
                dx, dy = (-MOVE_STEP, 0) if not shift else (0, -MOVE_STEP)
                self._nudge(hwnd, dx, dy)

            elif vk == VK_RIGHT:        # Ctrl+-> -> nudge right (Shift = down)
                dx, dy = (MOVE_STEP, 0) if not shift else (0, MOVE_STEP)
                self._nudge(hwnd, dx, dy)

            elif vk == VK_PRIOR:        # Ctrl+PgUp -> scroll up
                vis = self._vis_lines()
                self._scroll_lines = max(0, self._scroll_lines - vis)
                _u32.InvalidateRect(hwnd, None, True)

            elif vk == VK_NEXT:         # Ctrl+PgDn -> scroll down
                vis = self._vis_lines()
                self._scroll_lines = min(
                    self._scroll_lines + vis,
                    max(0, self._max_lines - vis)
                )
                _u32.InvalidateRect(hwnd, None, True)

        def _toggle_hide(self):
            self._hidden = not self._hidden
            _u32.ShowWindow(self._hwnd, 0 if self._hidden else SW_RESTORE)
            if not self._hidden:
                time.sleep(0.05)
                _u32.SetWindowDisplayAffinity(self._hwnd, WDA_EXCLUDEFROMCAPTURE)

        def _toggle_fullscreen(self, hwnd):
            self._fullscreen = not self._fullscreen
            if self._fullscreen:
                sw = _u32.GetSystemMetrics(SM_CXSCREEN)
                sh = _u32.GetSystemMetrics(SM_CYSCREEN)
                _u32.MoveWindow(hwnd, 0, 0, sw, sh, True)
                self._win_w, self._win_h = sw, sh
            else:
                _u32.MoveWindow(hwnd, OVERLAY_X, OVERLAY_Y,
                                OVERLAY_WIDTH, OVERLAY_HEIGHT, True)
                self._win_x, self._win_y = OVERLAY_X, OVERLAY_Y
                self._win_w, self._win_h = OVERLAY_WIDTH, OVERLAY_HEIGHT

        def _nudge(self, hwnd, dx, dy):
            rc = RECT()
            _u32.GetWindowRect(hwnd, ctypes.byref(rc))
            nx = rc.left + dx
            ny = rc.top  + dy
            self._win_x, self._win_y = nx, ny
            _u32.MoveWindow(hwnd, nx, ny, self._win_w, self._win_h, True)

        def _ensure_fonts(self, font_sz):
            if self._cached_fsz == font_sz:
                return
            if self._hfont:      _gdi.DeleteObject(self._hfont)
            if self._hfont_bold: _gdi.DeleteObject(self._hfont_bold)
            px = -(font_sz + 2)
            self._hfont      = _gdi.CreateFontW(px,0,0,0,400,0,0,0,0,0,0,0,0, OVERLAY_FONT)
            self._hfont_bold = _gdi.CreateFontW(px,0,0,0,700,0,0,0,0,0,0,0,0, OVERLAY_FONT)
            self._cached_fsz = font_sz

        def _paint(self, hwnd):
            try:
                ps  = PAINTSTRUCT()
                hdc = _u32.BeginPaint(hwnd, ctypes.byref(ps))
                if not hdc:
                    return

                rc = RECT()
                _u32.GetClientRect(hwnd, ctypes.byref(rc))
                W, H = rc.right, rc.bottom
                if W <= 0 or H <= 0:
                    _u32.EndPaint(hwnd, ctypes.byref(ps))
                    return

                # Double-buffer to eliminate flicker
                mdc  = _gdi.CreateCompatibleDC(hdc)
                if not mdc:
                    _u32.EndPaint(hwnd, ctypes.byref(ps))
                    return
                    
                mbmp = _gdi.CreateCompatibleBitmap(hdc, W, H)
                if not mbmp:
                    _gdi.DeleteDC(mdc)
                    _u32.EndPaint(hwnd, ctypes.byref(ps))
                    return
                    
                obmp = _gdi.SelectObject(mdc, mbmp)
                if not obmp:
                    _gdi.DeleteObject(mbmp)
                    _gdi.DeleteDC(mdc)
                    _u32.EndPaint(hwnd, ctypes.byref(ps))
                    return

                # Background fill
                br  = _gdi.CreateSolidBrush(COL_BG)
                bgr = RECT(); bgr.left=0; bgr.top=0; bgr.right=W; bgr.bottom=H
                _u32.FillRect(mdc, ctypes.byref(bgr), br)
                _gdi.DeleteObject(br)
                _gdi.SetBkMode(mdc, TRANSPARENT)

                with self._lock:
                    question = self._question
                    answer   = self._answer
                    status   = self._status
                    scol     = self._status_col
                    font_sz  = self._font_sz

                self._ensure_fonts(font_sz)
                lh  = font_sz + 5
                p   = self._PAD
                wrap = OVERLAY_WRAP

                def wl(text):
                    """Wrap text with fallback for memory corruption errors."""
                    try:
                        out = []
                        for raw in (text or "").splitlines() or [""]:
                            out.extend(textwrap.wrap(raw, wrap) or [""])
                        return out
                    except Exception:
                        # Memory corruption from SSL race - return unwrapped lines
                        return (text or "").splitlines() or [""]

                try:
                    q_lines = wl(question)
                    a_lines = wl(answer) if answer else []
                except Exception:
                    # Fallback if wl() itself fails
                    q_lines = [question] if question else []
                    a_lines = [answer] if answer else []

                hdr = 1 + (1 + len(q_lines) if question else 0)
                self._header_lines = hdr
                a_total = (1 + len(a_lines)) if answer else 0
                self._max_lines = a_total
                vis    = self._vis_lines()
                max_sc = max(0, a_total - vis)
                if self._scroll_lines > max_sc:
                    self._scroll_lines = max_sc

                y = p

                def dl(text, color, bold=False):
                    nonlocal y
                    try:
                        if y + lh > H - p: return
                        if not text: return  # Skip empty text
                        
                        # Sanitize text - remove null bytes and control characters
                        text = str(text).replace('\x00', '').replace('\r', '').replace('\n', ' ')
                        if not text.strip(): return
                        
                        _gdi.SelectObject(mdc, self._hfont_bold if bold else self._hfont)
                        _gdi.SetTextColor(mdc, color)
                        r = RECT(); r.left=p; r.top=y; r.right=W-p-8; r.bottom=H
                        _u32.DrawTextW(mdc, text, len(text), ctypes.byref(r), DT_LEFT | DT_NOPREFIX)
                        y += lh
                    except Exception:
                        # If drawing fails, skip this line silently
                        y += lh

                # Status bar
                dl(status, scol, bold=True)
                y += 4
                pen = _gdi.CreatePen(0, 1, _rgb(55, 55, 55))
                op  = _gdi.SelectObject(mdc, pen)
                _gdi.MoveToEx(mdc, p, y, None); _gdi.LineTo(mdc, W - p, y)
                _gdi.SelectObject(mdc, op); _gdi.DeleteObject(pen)
                y += 8

                # Question
                if question:
                    dl("QUESTION", COL_LABEL, bold=True)
                    for ln in q_lines:
                        dl(ln, COL_Q)
                    y += 6

                # Answer with scroll
                atop = y
                if answer:
                    all_a = [(COL_LABEL, True, "ANSWER")] + [(COL_A, False, ln) for ln in a_lines]
                    skip  = self._scroll_lines
                    for col, bold, ln in all_a:
                        if skip > 0:
                            skip -= 1
                            continue
                        if y + lh > H - p:
                            break
                        _gdi.SelectObject(mdc, self._hfont_bold if bold else self._hfont)
                        _gdi.SetTextColor(mdc, col)
                        r = RECT(); r.left=p; r.top=y; r.right=W-p-8; r.bottom=H
                        _u32.DrawTextW(mdc, ln, len(ln), ctypes.byref(r), DT_LEFT | DT_NOPREFIX)
                        y += lh

                    # Scrollbar
                    if a_total > vis and max_sc > 0:
                        ph  = H - atop - p
                        th  = max(16, ph * vis // a_total)
                        ty  = atop + (ph - th) * self._scroll_lines // max_sc
                        br1 = _gdi.CreateSolidBrush(_rgb(35, 35, 35))
                        rc1 = RECT(); rc1.left=W-7; rc1.top=atop; rc1.right=W-2; rc1.bottom=H-p
                        _u32.FillRect(mdc, ctypes.byref(rc1), br1); _gdi.DeleteObject(br1)
                        br2 = _gdi.CreateSolidBrush(_rgb(160, 160, 160))
                        rc2 = RECT(); rc2.left=W-7; rc2.top=ty; rc2.right=W-2; rc2.bottom=ty+th
                        _u32.FillRect(mdc, ctypes.byref(rc2), br2); _gdi.DeleteObject(br2)

                _gdi.BitBlt(hdc, 0, 0, W, H, mdc, 0, 0, 0x00CC0020)
                _gdi.SelectObject(mdc, obmp)
                _gdi.DeleteObject(mbmp)
                _gdi.DeleteDC(mdc)
                _u32.EndPaint(hwnd, ctypes.byref(ps))
            
            except Exception as e:
                # Catch any GDI/memory corruption errors to prevent crashes
                # This can happen when SSL operations corrupt memory
                print(f"[Overlay] Paint error (non-fatal): {e}")
                try:
                    # Try to clean up
                    _u32.EndPaint(hwnd, ctypes.byref(ps))
                except:
                    pass

# Module-level GC anchors
_global_wndproc_ref = None
_global_hook_ref    = None