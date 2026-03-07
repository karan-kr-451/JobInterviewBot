"""
setup_ui.py - System tray icon + configuration window.

SYSTEM TRAY
           
The app lives in the notification area (bottom-right clock area), NOT the
taskbar. Uses pystray for the tray icon. The icon image is generated
programmatically with Pillow so no icon.ico file is required.

Tray right-click menu:
     Settings          -> opens config window
     Show / Hide Overlay
  ---------------------
     Quit

AUDIO AUTO-DETECT
                 
sounddevice.query_devices() lists all audio inputs. The UI shows a dropdown
of every input device, with auto-scoring to pre-select the best loopback
device (Stereo Mix -> CABLE Output -> VoiceMeeter -> Bluetooth/headset).
A background thread polls every 8 seconds for newly connected devices
(Bluetooth headphones, USB headsets, etc.) and updates the dropdown.

SAVES TO
        
  .env             -> LLM_BACKEND, API keys, DEVICE_INDEX
  interview_docs/  -> resume, job description
  settings.json    -> job title, job desc text, last backend
"""

import os
import sys
import json
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog

# -- Base path (works both as script and frozen .exe) -------------------------

def _base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR      = _base()
ENV_PATH      = os.path.join(BASE_DIR, ".env")
DOCS_FOLDER   = os.path.join(BASE_DIR, "interview_docs")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

# -- Colors --------------------------------------------------------------------
BG         = "#0d0d0d"
BG2        = "#111111"
BG3        = "#181818"
BG4        = "#1e1e1e"
BORDER     = "#252525"
ACCENT     = "#00e5ff"
ACCENT2    = "#ffcc00"
TEXT       = "#d8d8d8"
TEXT_DIM   = "#505050"
TEXT_MID   = "#888888"
SUCCESS    = "#3ddc84"
DANGER     = "#ff453a"
WARN       = "#ff9f0a"
MONO       = "Consolas"

# -- .env helpers --------------------------------------------------------------

from core.env_helpers import (
    read_env as _read_env_legacy,
    read_settings as _read_settings, write_settings as _write_settings
)

# New YAML-based config
from config.yaml_loader import get_config, save_config


def _read_env():
    """Read environment/config (YAML or .env fallback)."""
    config = get_config()
    
    # Convert to flat dict for backward compatibility
    return {
        'LLM_BACKEND': config.get('llm', {}).get('backend', 'auto'),
        'GEMINI_API_KEY': config.get('llm', {}).get('gemini_api_key', ''),
        'GROQ_API_KEY': config.get('llm', {}).get('groq_api_key', ''),
        'TELEGRAM_BOT_TOKEN': config.get('telegram', {}).get('bot_token', ''),
        'TELEGRAM_CHAT_ID': config.get('telegram', {}).get('chat_id', ''),
        'DEVICE_INDEX': config.get('audio', {}).get('device_index'),
    }


def _write_env(updates):
    """Write to config.yaml."""
    config = get_config()
    
    # Update config structure
    if 'LLM_BACKEND' in updates:
        config.setdefault('llm', {})['backend'] = updates['LLM_BACKEND']
    if 'GEMINI_API_KEY' in updates:
        config.setdefault('llm', {})['gemini_api_key'] = updates['GEMINI_API_KEY']
    if 'GROQ_API_KEY' in updates:
        config.setdefault('llm', {})['groq_api_key'] = updates['GROQ_API_KEY']
    if 'TELEGRAM_BOT_TOKEN' in updates:
        config.setdefault('telegram', {})['bot_token'] = updates['TELEGRAM_BOT_TOKEN']
    if 'TELEGRAM_CHAT_ID' in updates:
        config.setdefault('telegram', {})['chat_id'] = updates['TELEGRAM_CHAT_ID']
    if 'DEVICE_INDEX' in updates:
        config.setdefault('audio', {})['device_index'] = int(updates['DEVICE_INDEX']) if updates['DEVICE_INDEX'] else None
    
    # Save to YAML
    save_config(config)


def _list_docs() -> dict:
    result = {"resume": None, "job_desc": None}
    if not os.path.exists(DOCS_FOLDER):
        return result
    for fp in os.listdir(DOCS_FOLDER):
        if not os.path.isfile(os.path.join(DOCS_FOLDER, fp)):
            continue
        low = fp.lower()
        if "resume" in low:
            result["resume"] = os.path.join(DOCS_FOLDER, fp)
        elif any(x in low for x in ("job", "jd", "description")):
            result["job_desc"] = os.path.join(DOCS_FOLDER, fp)
    return result


# -- Audio device helpers ------------------------------------------------------

def _get_input_devices() -> list[dict]:
    """
    Return list of input audio devices sorted by score (best first).
    Each dict: {index, name, score, label}

    Scoring (higher = better loopback/capture source):
      Stereo Mix / What U Hear  : 100    best: captures all system audio
      CABLE Output / VB-Audio   :  90
      VoiceMeeter               :  80
      Bluetooth / AirPods etc.  :  70    good for headphone+mic use
      Headset / Headphone       :  60
      Microphone (not headset)  :  30
      Everything else           :  10
    """
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        result = []
        for i, d in enumerate(devs):
            if d.get("max_input_channels", 0) < 1:
                continue
            name  = d.get("name", "")
            low   = name.lower()
            score = 10
            if any(x in low for x in ("stereo mix", "what u hear", "wave out mix")):
                score = 100
            elif any(x in low for x in ("cable output", "vb-audio", "vb cable",
                                          "voicemeeter output")):
                score = 90
            elif "voicemeeter" in low:
                score = 80
            elif any(x in low for x in ("bluetooth", "airpods", "galaxy buds",
                                          "jabra", "bose", "sennheiser", "sony wh",
                                          "beats", "anker")):
                score = 70
            elif any(x in low for x in ("headset", "headphone", "earphone")):
                score = 60
            elif "microphone" in low or "mic" in low:
                score = 30

            label = f"[{i}] {name}"
            result.append({"index": i, "name": name, "score": score, "label": label})

        result.sort(key=lambda x: (-x["score"], x["index"]))
        return result
    except Exception:
        return []


def _auto_select_device(devices: list[dict]) -> int | None:
    """Return the index of the best device, or None if list empty."""
    if not devices:
        return None
    return devices[0]["index"]


# -- Tray icon image (generated with Pillow - no icon.ico needed) --------------

def _make_tray_image(size=64, active=False):
    """
    Draw a minimal mic/headphone icon on a dark background.
    active=True draws it in cyan (recording), False in dim grey.
    Returns a PIL Image.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        # Fallback: solid colored square
        try:
            from PIL import Image
            img = Image.new("RGBA", (size, size), (0, 229, 255, 200) if active else (60, 60, 60, 200))
            return img
        except Exception:
            return None

    img  = Image.new("RGBA", (size, size), (13, 13, 13, 240))
    draw = ImageDraw.Draw(img)
    col  = (0, 229, 255, 255) if active else (120, 120, 120, 220)
    dim  = (30, 30, 30, 180)
    s    = size

    # Background circle
    draw.ellipse([2, 2, s-2, s-2], fill=(22, 22, 22, 255), outline=col, width=2)

    # Microphone body
    mx = s * 0.5
    bw = s * 0.18    # body half-width
    bh = s * 0.28    # body half-height
    by = s * 0.25    # body center y

    draw.rounded_rectangle(
        [mx - bw, by - bh, mx + bw, by + bh],
        radius=bw, fill=col
    )

    # Stand arc
    aw = s * 0.30
    ah = s * 0.20
    ay = by + bh * 0.3
    draw.arc(
        [mx - aw, ay - ah, mx + aw, ay + ah],
        start=0, end=180, fill=col, width=max(2, int(s*0.045))
    )

    # Stand vertical + base
    lw = max(2, int(s * 0.045))
    draw.line([mx, ay, mx, ay + ah * 0.9], fill=col, width=lw)
    draw.line([mx - aw*0.45, ay + ah*0.9, mx + aw*0.45, ay + ah*0.9],
              fill=col, width=lw)

    return img


# -- Custom Tkinter widgets ----------------------------------------------------

class _Separator(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BORDER, height=1, **kw)


class _SectionHeader(tk.Frame):
    def __init__(self, parent, title: str, **kw):
        super().__init__(parent, bg=BG, **kw)
        tk.Label(self, text=title, font=(MONO, 8, "bold"),
                 fg=ACCENT2, bg=BG).pack(side="left")
        tk.Frame(self, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=6)


class _Field(tk.Frame):
    def __init__(self, parent, label: str, value="", show="", width=30, hint="", **kw):
        super().__init__(parent, bg=BG, **kw)
        lbl = tk.Label(self, text=label, font=(MONO, 8), fg=TEXT_MID,
                       bg=BG, width=16, anchor="w")
        lbl.pack(side="left")
        self.var = tk.StringVar(value=value)
        self._entry = tk.Entry(
            self, textvariable=self.var, font=(MONO, 9),
            bg=BG3, fg=TEXT, insertbackground=ACCENT,
            relief="flat", bd=0, show=show, width=width,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT
        )
        self._entry.pack(side="left", ipady=5, padx=(0, 4))
        if hint:
            tk.Label(self, text=hint, font=(MONO, 7), fg=TEXT_DIM, bg=BG
                     ).pack(side="left")

    def get(self) -> str:
        return self.var.get().strip()


class _HoverButton(tk.Button):
    def __init__(self, parent, **kw):
        super().__init__(parent, relief="flat", bd=0, cursor="hand2", **kw)
        self.default_bg = kw.get("bg", BG4)
        self.hover_bg   = kw.get("activebackground", BORDER)
        self.bind("<Enter>", lambda e: self.config(bg=self.hover_bg))
        self.bind("<Leave>", lambda e: self.config(bg=self.default_bg))


class _FileRow(tk.Frame):
    def __init__(self, parent, label: str, path=None, filetypes=None, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._path = path
        self._ft   = filetypes or [("Text / Markdown", "*.txt *.md"), ("All files", "*.*")]

        tk.Label(self, text=label, font=(MONO, 8), fg=TEXT_MID,
                 bg=BG, width=16, anchor="w").pack(side="left")

        self._lbl = tk.Label(self, font=(MONO, 8), bg=BG, width=26, anchor="w")
        self._lbl.pack(side="left")

        _HoverButton(self, text="Browse", font=(MONO, 8),
                   bg=BG4, fg=ACCENT, activebackground=BORDER,
                   activeforeground=ACCENT, padx=8, pady=3,
                   command=self._browse).pack(side="left", padx=(0, 4))

        self._clear_btn = _HoverButton(
            self, text=" ", font=(MONO, 9), bg=BG4, fg=DANGER,
            activebackground=BORDER, activeforeground=DANGER,
            padx=6, pady=2, command=self._clear)
        self._clear_btn.pack(side="left")
        self._refresh()

    def _browse(self):
        p = filedialog.askopenfilename(title="Select file", filetypes=self._ft)
        if p:
            self._path = p
            self._refresh()

    def _clear(self):
        self._path = None
        self._refresh()

    def _refresh(self):
        if self._path:
            n = os.path.basename(self._path)
            n = n[:24] + " " if len(n) > 25 else n
            self._lbl.config(text=n, fg=SUCCESS)
            self._clear_btn.config(state="normal")
        else:
            self._lbl.config(text="not uploaded", fg=TEXT_DIM)
            self._clear_btn.config(state="disabled")

    def get(self):
        return self._path


# -- Config window -------------------------------------------------------------

class ConfigWindow:
    """
    Borderless config window that appears above the taskbar (bottom-right).
    Excluded from taskbar AND screen capture.
    Stays on top of other windows.
    """

    W, H = 580, 720

    def __init__(self, on_launch=None, on_close=None):
        self._on_launch = on_launch
        self._on_close  = on_close
        self._root      = None
        self._open      = False
        self._lock      = threading.Lock()
        self._devices   = []          # cached device list
        self._device_poll_stop = threading.Event()

    # -- Public ----------------------------------------------------------------

    def show(self):
        """Open or bring to front (thread-safe, must be called from main thread or after(0))."""
        with self._lock:
            if self._open and self._root:
                try:
                    self._root.lift()
                    self._root.focus_force()
                except Exception:
                    pass
                return
            self._open = True

        self._build()

    def hide(self):
        with self._lock:
            if self._root and self._open:
                self._root.destroy()
                self._root = None
                self._open = False

    # -- Build UI --------------------------------------------------------------

    def _build(self):
        env  = _read_env()
        sets = _read_settings()
        docs = _list_docs()

        self._root = tk.Tk()
        root       = self._root
        root.withdraw()
        root.configure(bg=BG)
        root.resizable(True, True)
        root.minsize(450, 600)
        root.overrideredirect(True)
        root.title("Interview Assistant - Settings")

        # Position bottom-right above taskbar
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x  = sw - self.W - 12
        y  = sh - self.H - 52    # 52 = taskbar height approx
        root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        # Win32: tool window (no taskbar button) + topmost + no screen-capture
        if sys.platform == "win32":
            import ctypes
            GWL_EXSTYLE      = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            WS_EX_TOPMOST    = 0x00000008
            hwnd  = ctypes.windll.user32.GetParent(root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style | WS_EX_TOOLWINDOW | WS_EX_TOPMOST) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            try:
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            except Exception:
                pass

        root.wm_attributes("-topmost", True)

        # -- Drag -------------------------------------------------------------
        self._dx = self._dy = 0
        def _ds(e): self._dx = e.x_root - root.winfo_x(); self._dy = e.y_root - root.winfo_y()
        def _dm(e): root.geometry(f"+{e.x_root-self._dx}+{e.y_root-self._dy}")

        # -- Title bar ---------------------------------------------------------
        # -- Title bar with Glow -----------------------------------------------
        tbar = tk.Frame(root, bg=BG2, height=60)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        tbar.bind("<ButtonPress-1>", _ds)
        tbar.bind("<B1-Motion>",     _dm)

        # Logo handling
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interview_bot_logo.png")
        if os.path.exists(logo_path):
            try:
                from PIL import Image, ImageTk
                limg = Image.open(logo_path).resize((40, 40), Image.Resampling.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(limg)
                tk.Label(tbar, image=self._logo_img, bg=BG2).pack(side="left", padx=(12, 10))
            except Exception:
                tk.Label(tbar, text=" ", font=(MONO, 16), fg=ACCENT, bg=BG2).pack(side="left", padx=(12, 6))
        else:
            tk.Label(tbar, text=" ", font=(MONO, 16), fg=ACCENT, bg=BG2).pack(side="left", padx=(12, 6))

        title_frame = tk.Frame(tbar, bg=BG2)
        title_frame.pack(side="left", pady=8)
        tk.Label(title_frame, text="INTERVIEW ASSISTANT", font=(MONO, 11, "bold"),
                 fg=TEXT, bg=BG2).pack(anchor="w")
        tk.Label(title_frame, text="Ultimate Real-time Copilot", font=(MONO, 8),
                 fg=ACCENT2, bg=BG2).pack(anchor="w")

        _HoverButton(tbar, text=" ", font=(MONO, 12), bg=BG2, fg=TEXT_DIM,
                   activebackground=DANGER, activeforeground="#fff",
                   padx=15, pady=10, command=self._close).pack(side="right")

        # Bind drag to all title elements so the whole bar is draggable
        def _bind_drag(widget):
            widget.bind("<ButtonPress-1>", _ds)
            widget.bind("<B1-Motion>",     _dm)
            for child in widget.winfo_children():
                if not isinstance(child, tk.Button): # Don't drag when clicking 'X'
                    _bind_drag(child)

        _bind_drag(tbar)

        tk.Frame(root, bg=ACCENT, height=2).pack(fill="x")

        # -- Scrollable body ---------------------------------------------------
        cv = tk.Canvas(root, bg=BG, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(root, orient="vertical", command=cv.yview, bg=BG,
                          troughcolor=BG, width=8)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        body = tk.Frame(cv, bg=BG)
        win  = cv.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",   lambda e: cv.itemconfig(win, width=e.width))
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta/120), "units"))

        pad = {"padx": 18, "pady": 4}

        # --   Backend ---------------------------------------------------------
        _SectionHeader(body, "LLM BACKEND").pack(fill="x", padx=18, pady=(14, 4))
        backend_row = tk.Frame(body, bg=BG)
        backend_row.pack(fill="x", padx=18, pady=(0, 2))
        tk.Label(backend_row, text="Mode", font=(MONO, 8), fg=TEXT_MID,
                 bg=BG, width=16, anchor="w").pack(side="left")

        cur_back = env.get("LLM_BACKEND", sets.get("llm_backend", "auto"))
        self._backend = tk.StringVar(value=cur_back)
        for b in ["auto", "gemini", "groq", "ollama"]:
            rb = tk.Radiobutton(
                backend_row, text=b, variable=self._backend, value=b,
                font=(MONO, 9), fg=TEXT, bg=BG, selectcolor=BG4,
                activebackground=BG, activeforeground=ACCENT,
                cursor="hand2", indicatoron=True
            )
            rb.pack(side="left", padx=(0, 14))

        tk.Label(body, text="   auto: Ollama (local) -> Groq (cloud) -> Gemini",
                 font=(MONO, 7), fg=TEXT_DIM, bg=BG).pack(anchor="w", padx=18)

        # --   API Keys --------------------------------------------------------
        _SectionHeader(body, "API KEYS").pack(fill="x", padx=18, pady=(14, 6))

        self._f_gemini = _Field(body, "Gemini Key",
                                value=env.get("GEMINI_API_KEY", ""),
                                show=" ", width=32,
                                hint="console.cloud.google.com")
        self._f_gemini.pack(fill="x", **pad)

        self._f_groq = _Field(body, "Groq Key",
                              value=env.get("GROQ_API_KEY", ""),
                              show=" ", width=32,
                              hint="console.groq.com (Highly Recommended)")
        self._f_groq.pack(fill="x", **pad)

        self._f_tg_token = _Field(body, "Telegram Bot",
                                  value=env.get("TELEGRAM_BOT_TOKEN", ""),
                                  show=" ", width=32)
        self._f_tg_token.pack(fill="x", **pad)

        self._f_tg_chat = _Field(body, "Chat ID",
                                 value=env.get("TELEGRAM_CHAT_ID", ""),
                                 width=18)
        self._f_tg_chat.pack(fill="x", **pad)

        # --   Job Context ------------------------------------------------------
        _SectionHeader(body, "JOB CONTEXT").pack(fill="x", padx=18, pady=(14, 6))

        self._f_title = _Field(body, "Job Title",
                               value=sets.get("job_title", ""), width=32)
        self._f_title.pack(fill="x", **pad)

        tk.Label(body, text="   Job Description / JD Text", font=(MONO, 8),
                 fg=TEXT_MID, bg=BG).pack(anchor="w", padx=18, pady=(4, 2))

        jd_wrap = tk.Frame(body, bg=BG3, highlightthickness=1,
                           highlightbackground=BORDER)
        jd_wrap.pack(fill="x", padx=18, pady=(0, 2))
        self._f_jd = tk.Text(jd_wrap, font=(MONO, 8), bg=BG3, fg=TEXT,
                              insertbackground=ACCENT, relief="flat", bd=0,
                              height=5, wrap="word")
        self._f_jd.pack(fill="x", padx=4, pady=4)

        existing_jd = sets.get("job_description", "")
        if not existing_jd and docs["job_desc"]:
            try:
                with open(docs["job_desc"], "r", encoding="utf-8") as f:
                    existing_jd = f.read()
            except Exception: pass
        if existing_jd:
            self._f_jd.insert("1.0", existing_jd)

        # --   Documents --------------------------------------------------------
        _SectionHeader(body, "EXPERIENCE & PROJECTS").pack(fill="x", padx=18, pady=(14, 6))

        self._f_resume = _FileRow(
            body, "Resume", path=docs["resume"],
            filetypes=[("Text / PDF", "*.txt *.md *.pdf"), ("All", "*.*")])
        self._f_resume.pack(fill="x", **pad)

        self._f_jd_file = _FileRow(
            body, "JD File", path=docs["job_desc"])
        self._f_jd_file.pack(fill="x", **pad)

        tk.Label(body, text="   Tip: Responses are tailored to your resume + job title.",
                 font=(MONO, 7), fg=TEXT_DIM, bg=BG).pack(anchor="w", padx=18)

        # --   Audio Device -----------------------------------------------------
        _SectionHeader(body, "AUDIO PIPELINE").pack(fill="x", padx=18, pady=(14, 6))

        dev_row = tk.Frame(body, bg=BG)
        dev_row.pack(fill="x", padx=18, pady=(0, 2))
        tk.Label(dev_row, text="Input Source", font=(MONO, 8), fg=TEXT_MID,
                 bg=BG, width=16, anchor="w").pack(side="left")

        self._dev_var = tk.StringVar()
        self._dev_menu = tk.OptionMenu(dev_row, self._dev_var, "Scanning...")
        self._dev_menu.config(
            font=(MONO, 8), bg=BG4, fg=TEXT, activebackground=BORDER,
            activeforeground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT, width=34, anchor="w"
        )
        self._dev_menu["menu"].config(bg=BG4, fg=TEXT, font=(MONO, 8))
        self._dev_menu.pack(side="left")

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x", padx=18, pady=(2, 0))

        self._dev_status = tk.Label(btn_row, text="", font=(MONO, 7),
                                    fg=TEXT_DIM, bg=BG)
        self._dev_status.pack(side="left")

        _HoverButton(btn_row, text="  Refresh", font=(MONO, 7),
                   bg=BG4, fg=ACCENT, activebackground=BORDER, activeforeground=ACCENT,
                   padx=8, pady=3, command=self._refresh_devices).pack(side="right")

        # Override Index row
        idx_row = tk.Frame(body, bg=BG)
        idx_row.pack(fill="x", padx=18, pady=(4, 2))
        tk.Label(idx_row, text="Override Index", font=(MONO, 8), fg=TEXT_DIM,
                 bg=BG, width=16, anchor="w").pack(side="left")
        self._dev_idx = tk.StringVar(value=sets.get("device_index", env.get("DEVICE_INDEX", "")))
        tk.Entry(idx_row, textvariable=self._dev_idx, font=(MONO, 8),
                 bg=BG3, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=0, width=8,
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left", ipady=3, padx=(0, 8))
        tk.Label(idx_row, text="(optional index override)",
                 font=(MONO, 7), fg=TEXT_DIM, bg=BG).pack(side="left")

        # --   Save / Launch ----------------------------------------------------
        _Separator(body).pack(fill="x", padx=18, pady=(20, 0))

        self._msg = tk.Label(body, text="", font=(MONO, 8), fg=SUCCESS, bg=BG)
        self._msg.pack(pady=(8, 4))

        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.pack(fill="x", padx=18, pady=(0, 10))

        _HoverButton(btn_frame, text="[START]  SAVE & START ASSISTANT",
                   font=(MONO, 11, "bold"), bg=ACCENT, fg=BG,
                   activebackground="#00b8cc", activeforeground=BG,
                   padx=20, pady=12, command=self._do_launch).pack(fill="x", pady=(0, 6))

        _HoverButton(btn_frame, text="Save Settings Only",
                   font=(MONO, 8), bg=BG3, fg=TEXT_MID,
                   activebackground=BG4, activeforeground=TEXT,
                   padx=10, pady=6, command=self._do_save_only).pack(fill="x")

        tk.Label(body, text="", bg=BG, height=1).pack()

        # -- Resize Grip ------------------------------------------------------
        grip = tk.Label(root, text=" ", font=(MONO, 10), fg=TEXT_DIM, bg=BG, cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")

        def _resize_start(e):
            self._sw = root.winfo_width()
            self._sh = root.winfo_height()
            self._sx = e.x_root
            self._sy = e.y_root

        def _resize_move(e):
            dw = e.x_root - self._sx
            dh = e.y_root - self._sy
            nw = max(450, self._sw + dw)
            nh = max(600, self._sh + dh)
            root.geometry(f"{nw}x{nh}")

        grip.bind("<ButtonPress-1>", _resize_start)
        grip.bind("<B1-Motion>",     _resize_move)

        # Load devices now (and start background poll)
        self._refresh_devices()
        self._start_device_poll()

        root.deiconify()
        root.lift()
        root.focus_force()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.mainloop()

    # -- Device management -----------------------------------------------------

    def _refresh_devices(self):
        """Rescan devices and rebuild dropdown."""
        try:
            devs = _get_input_devices()
            self._devices = devs

            # Saved override index
            saved_idx_str = self._dev_idx.get().strip() if hasattr(self, "_dev_idx") else ""
            try:
                saved_idx = int(saved_idx_str)
            except (ValueError, AttributeError):
                saved_idx = None

            if not devs:
                self._dev_var.set("No input devices found")
                if hasattr(self, "_dev_menu"):
                    menu = self._dev_menu["menu"]
                    menu.delete(0, "end")
                    menu.add_command(label="No devices found",
                                     command=lambda: self._dev_var.set("No input devices found"))
                return

            labels = [d["label"] for d in devs]

            # Determine which to pre-select
            if saved_idx is not None:
                match = next((d["label"] for d in devs if d["index"] == saved_idx), None)
                selected = match or labels[0]
            else:
                selected = labels[0]   # best-scored device

            if hasattr(self, "_dev_menu"):
                menu = self._dev_menu["menu"]
                menu.delete(0, "end")
                for lbl in labels:
                    menu.add_command(label=lbl, command=lambda v=lbl: self._dev_var.set(v))
                self._dev_var.set(selected)

            # Show score hint
            top = devs[0]
            tag = "best loopback" if top["score"] >= 90 else \
                  "bluetooth/headset" if top["score"] >= 60 else "microphone"
            if hasattr(self, "_dev_status"):
                self._dev_status.config(
                    text=f"  [OK] auto-selected: {tag}  ({len(devs)} input devices found)",
                    fg=SUCCESS
                )
        except Exception as e:
            if hasattr(self, "_dev_status"):
                self._dev_status.config(text=f"    scan failed: {e}", fg=WARN)

    def _start_device_poll(self):
        """Poll for newly connected devices every 8 seconds."""
        self._device_poll_stop.clear()
        self._last_dev_count = len(self._devices)

        def _poll():
            while not self._device_poll_stop.is_set():
                time.sleep(8)
                if self._device_poll_stop.is_set():
                    break
                try:
                    devs = _get_input_devices()
                    if len(devs) != self._last_dev_count:
                        self._last_dev_count = len(devs)
                        # Schedule UI update on main thread
                        if self._root and self._open:
                            self._root.after(0, self._refresh_devices)
                except Exception:
                    pass

        t = threading.Thread(target=_poll, daemon=True, name="device-poll")
        t.start()

    def _get_selected_device_index(self) -> str:
        """Return numeric device index string from dropdown selection."""
        # Override field takes priority
        if hasattr(self, "_dev_idx"):
            override = self._dev_idx.get().strip()
            if override.isdigit():
                return override

        # Parse from dropdown label "[N] Name"
        label = self._dev_var.get()
        if label.startswith("["):
            try:
                return label.split("]")[0][1:]
            except Exception:
                pass

        # Fallback to best scored
        if self._devices:
            return str(self._devices[0]["index"])
        return "1"

    # -- Save / Launch ---------------------------------------------------------

    def _collect(self) -> dict:
        return {
            "llm_backend":      self._backend.get(),
            "gemini_api_key":   self._f_gemini.get(),
            "groq_api_key":     self._f_groq.get(),
            "tg_token":         self._f_tg_token.get(),
            "tg_chat":          self._f_tg_chat.get(),
            "job_title":        self._f_title.get(),
            "job_description":  self._f_jd.get("1.0", "end").strip(),
            "resume_path":      self._f_resume.get(),
            "jd_file_path":     self._f_jd_file.get(),
            "device_index":     self._get_selected_device_index(),
        }

    def _validate(self, v: dict) -> str | None:
        b = v["llm_backend"]
        if b == "gemini" and not v["gemini_api_key"]:
            return "Gemini API key required when backend = gemini"
        if b == "groq" and not v["groq_api_key"]:
            return "Groq API key required when backend = groq"
        if b == "auto" and not v["gemini_api_key"] and not v["groq_api_key"]:
            return "At least one API key required for auto mode\n(unless Ollama is running locally)"
        return None

    def _save(self, v: dict):
        os.makedirs(DOCS_FOLDER, exist_ok=True)

        env_updates = {}
        if v["llm_backend"]:        env_updates["LLM_BACKEND"]        = v["llm_backend"]
        if v["gemini_api_key"]:     env_updates["GEMINI_API_KEY"]     = v["gemini_api_key"]
        if v["groq_api_key"]:       env_updates["GROQ_API_KEY"]       = v["groq_api_key"]
        if v["tg_token"]:           env_updates["TELEGRAM_BOT_TOKEN"] = v["tg_token"]
        if v["tg_chat"]:            env_updates["TELEGRAM_CHAT_ID"]   = v["tg_chat"]
        if v["device_index"]:       env_updates["DEVICE_INDEX"]       = v["device_index"]
        _write_env(env_updates)

        def _copy_doc(src, dest_name):
            if src and os.path.exists(src):
                ext  = os.path.splitext(src)[1]
                dest = os.path.join(DOCS_FOLDER, f"{dest_name}{ext}")
                try:
                    if not os.path.exists(dest) or \
                       not os.path.samefile(src, dest):
                        shutil.copy2(src, dest)
                except Exception:
                    shutil.copy2(src, dest)

        _copy_doc(v["resume_path"],  "resume")
        _copy_doc(v["jd_file_path"], "job_description")

        if v["job_description"] and not v["jd_file_path"]:
            with open(os.path.join(DOCS_FOLDER, "job_description.txt"),
                      "w", encoding="utf-8") as f:
                header = f"# {v['job_title']}\n\n" if v["job_title"] else ""
                f.write(header + v["job_description"])

        _write_settings({
            "llm_backend":     v["llm_backend"],
            "job_title":       v["job_title"],
            "job_description": v["job_description"],
            "device_index":    v["device_index"],
        })

    def _do_launch(self):
        v   = self._collect()
        err = self._validate(v)
        if err:
            self._msg.config(text=f"   {err}", fg=DANGER)
            return
        self._save(v)
        self._msg.config(text="[OK] Saved - launching...", fg=SUCCESS)
        self._root.after(350, self._finish_launch)

    def _finish_launch(self):
        self._device_poll_stop.set()
        self._open = False
        self._root.destroy()
        self._root = None
        if self._on_launch:
            self._on_launch()

    def _do_save_only(self):
        v = self._collect()
        self._save(v)
        self._msg.config(text="[OK] Saved.", fg=SUCCESS)

    def _close(self):
        self._device_poll_stop.set()
        self._open = False
        if self._root:
            self._root.destroy()
            self._root = None
        if self._on_close:
            self._on_close()


# -- System Tray ---------------------------------------------------------------

class TrayApp:
    """
    Manages the system tray icon (lives in notification area, not taskbar).

    Requires `pystray` and `Pillow`.

    Usage:
        app = TrayApp(on_launch_pipeline=start_fn, on_quit=quit_fn)
        app.start()     # non-blocking, runs tray in background thread
    """

    def __init__(self, on_launch_pipeline=None, on_quit=None, on_settings=None,
                 overlay_ref=None):
        self._on_launch_pipeline = on_launch_pipeline
        self._on_quit            = on_quit
        self._on_settings        = on_settings
        self._overlay            = overlay_ref
        self._icon               = None
        self._config_win         = None
        self._pipeline_running   = False
        self._config_lock        = threading.Lock()  # prevents duplicate windows
        self._auto_open_settings = True  # Can be disabled by GUI mode

    def start(self):
        """Start tray icon in background thread. Returns immediately."""
        t = threading.Thread(target=self._run_tray, daemon=True, name="tray")
        t.start()

    def set_active(self, active: bool):
        """Update tray icon to show recording state."""
        if self._icon:
            try:
                img = _make_tray_image(active=active)
                if img:
                    self._icon.icon = img
            except Exception:
                pass

    def _open_settings(self, icon=None, item=None):
        """Called from tray menu - open config window or trigger callback."""
        if self._on_settings:
            # If we're in GUI mode, just trigger the tab switch
            self._on_settings()
            return
            
        threading.Thread(
            target=self._show_config_window,
            daemon=True,
            name="config-window",
        ).start()

    def _show_config_window(self):
        # Prevent two config windows opening at the same time
        if not self._config_lock.acquire(blocking=False):
            return
        try:
            if self._config_win and self._config_win._open:
                return

            def _on_launch():
                self._pipeline_running = True
                if self._on_launch_pipeline:
                    threading.Thread(target=self._on_launch_pipeline,
                                     daemon=True, name="pipeline-start").start()

            def _on_close():
                pass

            self._config_win = ConfigWindow(on_launch=_on_launch, on_close=_on_close)
            self._config_win.show()   # blocks until window closed
        finally:
            self._config_lock.release()

    def _toggle_overlay(self, icon=None, item=None):
        if self._overlay:
            try:
                self._overlay.toggle_hide()
            except Exception:
                pass

    def _quit(self, icon=None, item=None):
        if self._icon:
            self._icon.stop()
        if self._on_quit:
            self._on_quit()

    def _run_tray(self):
        try:
            import pystray
        except ImportError:
            print("WARNING: pystray not installed - tray icon disabled")
            print("  pip install pystray pillow")
            # Fall back to just opening config directly (already in a background thread)
            self._show_config_window()
            return

        img = _make_tray_image(active=False)
        if img is None:
            try:
                from PIL import Image
                img = Image.new("RGBA", (64, 64), (0, 229, 255, 200))
            except Exception:
                print("WARNING: Pillow not installed - tray icon may be blank")

        menu = pystray.Menu(
            pystray.MenuItem("   Settings",     self._open_settings, default=True),
            pystray.MenuItem("   Show Overlay",  self._toggle_overlay),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("   Quit",          self._quit),
        )

        self._icon = pystray.Icon(
            name="InterviewBot",
            icon=img,
            title="Interview Assistant",
            menu=menu,
        )

        # Open settings immediately on launch (only if auto-open enabled)
        if self._auto_open_settings:
            def _deferred_open():
                time.sleep(0.8)
                self._show_config_window()
            threading.Thread(target=_deferred_open, daemon=True,
                             name="deferred-config").start()

        self._icon.run()


# -- Public entry points -------------------------------------------------------

def run_setup(force: bool = False) -> bool:
    """
    Legacy entry point used by main.py.
    force=False: skip if already configured.
    Returns True if user launched, False if closed.
    """
    if not force:
        env = _read_env()
        if (env.get("GEMINI_API_KEY") or
                env.get("GROQ_API_KEY") or
                env.get("LLM_BACKEND") == "ollama"):
            return True   # already configured

    launched = [False]

    def _on_launch():
        launched[0] = True

    win = ConfigWindow(on_launch=_on_launch)
    win.show()
    return launched[0]


def create_tray_app(**kwargs) -> TrayApp:
    """Create and return a TrayApp instance (not yet started)."""
    return TrayApp(**kwargs)


if __name__ == "__main__":
    # Standalone test
    app = TrayApp(
        on_launch_pipeline=lambda: print("Pipeline start!"),
        on_quit=lambda: os._exit(0),
    )
    app.start()
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass