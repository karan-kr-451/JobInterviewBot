"""
ui/gui_dashboard.py - Tkinter-based management dashboard.

Tabs:
  Setup    – audio device selector, API keys, document paths, job info
  Logs     – live-tail of interview_log.txt
  Controls – LLM backend switch, overlay transparency, toggle transcription

The dashboard runs in a threading.Thread (not the main thread).
It stores its settings to config/settings.yaml via config_loader.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

from core.logger import get_logger

log = get_logger("ui.dashboard")


class GUIDashboard:
    """
    Full-featured management dashboard built with Tkinter.

    Usage:
        dashboard = GUIDashboard(cfg, launch_event)
        dashboard.start()       # non-blocking
        launch_event.wait()     # blocks until user clicks "Save & Launch"
    """

    def __init__(self, cfg, launch_event: threading.Event) -> None:
        self._cfg    = cfg
        self._launch = launch_event
        self._root   = None
        self._thread: Optional[threading.Thread] = None
        self._vars:  dict = {}     # StringVar / IntVar store
        self._log_queue: queue.Queue = queue.Queue(maxsize=200)

    def start(self) -> None:
        """Start dashboard in a background thread."""
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="gui-dashboard"
        )
        self._thread.start()

    def log_line(self, line: str) -> None:
        """Push a log line to the dashboard log tab (thread-safe)."""
        try:
            self._log_queue.put_nowait(line)
        except queue.Full:
            pass

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk, filedialog, messagebox

            self._root = root = tk.Tk()
            root.title("Interview Assistant – Setup")
            root.configure(bg="#0d1117")
            root.geometry("700x560")
            root.resizable(True, True)

            # Style
            style = ttk.Style()
            style.theme_use("clam")
            style.configure(".", background="#0d1117", foreground="#e6edf3",
                            font=("Segoe UI", 10))
            style.configure("TNotebook",        background="#0d1117")
            style.configure("TNotebook.Tab",    background="#161b22", foreground="#e6edf3",
                            padding=[10, 4])
            style.map("TNotebook.Tab",          background=[("selected", "#1f6feb")])
            style.configure("TFrame",           background="#0d1117")
            style.configure("TLabel",           background="#0d1117", foreground="#e6edf3")
            style.configure("TEntry",           fieldbackground="#161b22", foreground="#e6edf3",
                            insertcolor="#e6edf3")
            style.configure("Accent.TButton",   background="#1f6feb", foreground="white",
                            font=("Segoe UI", 10, "bold"), padding=6)
            style.configure("TButton",          background="#21262d", foreground="#e6edf3", padding=4)

            nb = ttk.Notebook(root)
            nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # ── Tab 1: Setup ──────────────────────────────────────────────────
            tab_setup = ttk.Frame(nb)
            nb.add(tab_setup, text=" ⚙ Setup")
            self._build_setup_tab(tab_setup, root)

            # ── Tab 2: Logs ───────────────────────────────────────────────────
            tab_logs = ttk.Frame(nb)
            nb.add(tab_logs, text=" 📋 Logs")
            self._build_logs_tab(tab_logs)

            # ── Tab 3: Controls ───────────────────────────────────────────────
            tab_ctrl = ttk.Frame(nb)
            nb.add(tab_ctrl, text=" 🎛 Controls")
            self._build_controls_tab(tab_ctrl)

            # ── Launch button ─────────────────────────────────────────────────
            btn_frame = ttk.Frame(root)
            btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

            ttk.Button(
                btn_frame, text="Save & Launch  ▶",
                style="Accent.TButton",
                command=self._on_launch,
            ).pack(side=tk.RIGHT, padx=4)

            ttk.Button(
                btn_frame, text="Quit",
                command=lambda: sys.exit(0),
            ).pack(side=tk.RIGHT)

            # Poll log queue
            def _poll_logs():
                try:
                    while True:
                        line = self._log_queue.get_nowait()
                        if hasattr(self, "_log_text") and self._log_text:
                            self._log_text.config(state="normal")
                            self._log_text.insert("end", line + "\n")
                            self._log_text.see("end")
                            self._log_text.config(state="disabled")
                except queue.Empty:
                    pass
                root.after(500, _poll_logs)

            root.after(500, _poll_logs)
            root.protocol("WM_DELETE_WINDOW", lambda: sys.exit(0))
            root.mainloop()

        except Exception as exc:
            log.error("Dashboard error: %s\n%s", exc, traceback.format_exc())

    def _build_setup_tab(self, frame, root) -> None:
        import tkinter as tk
        from tkinter import filedialog

        cfg  = self._cfg
        vars = self._vars

        def _row(parent, label, row):
            lbl = tk.Label(parent, text=label, bg="#0d1117", fg="#8b949e",
                           font=("Segoe UI", 9), anchor="w")
            lbl.grid(row=row, column=0, sticky="w", padx=(12, 4), pady=3)
            return lbl

        def _entry(parent, key, default, row, show=None):
            v = tk.StringVar(value=default)
            vars[key] = v
            e = tk.Entry(parent, textvariable=v, bg="#161b22", fg="#e6edf3",
                         insertbackground="#e6edf3", relief="flat",
                         show=show or "", font=("Consolas", 9), width=42)
            e.grid(row=row, column=1, sticky="ew", padx=(4, 12), pady=3)
            return e

        # Audio
        sec = tk.LabelFrame(frame, text=" Audio ", bg="#0d1117", fg="#8b949e",
                            font=("Segoe UI", 9, "bold"))
        sec.pack(fill=tk.X, padx=12, pady=(10, 4))
        sec.columnconfigure(1, weight=1)
        _row(sec, "Device Index", 0)
        _entry(sec, "device_index",
               str(cfg.audio.device_index) if cfg.audio.device_index is not None else "", 0)

        # API Keys
        sec2 = tk.LabelFrame(frame, text=" API Keys ", bg="#0d1117", fg="#8b949e",
                              font=("Segoe UI", 9, "bold"))
        sec2.pack(fill=tk.X, padx=12, pady=4)
        sec2.columnconfigure(1, weight=1)
        _row(sec2, "Groq API Key", 0);   _entry(sec2, "groq_key",   cfg.llm.groq.api_key,   0, show="•")
        _row(sec2, "Gemini API Key", 1); _entry(sec2, "gemini_key", cfg.llm.gemini.api_key, 1, show="•")

        # Telegram
        sec3 = tk.LabelFrame(frame, text=" Telegram (optional) ", bg="#0d1117", fg="#8b949e",
                              font=("Segoe UI", 9, "bold"))
        sec3.pack(fill=tk.X, padx=12, pady=4)
        sec3.columnconfigure(1, weight=1)
        _row(sec3, "Bot Token", 0);  _entry(sec3, "tg_token", cfg.telegram.bot_token, 0, show="•")
        _row(sec3, "Chat ID",   1);  _entry(sec3, "tg_chat",  cfg.telegram.chat_id,   1)

        # Job
        sec4 = tk.LabelFrame(frame, text=" Job Info ", bg="#0d1117", fg="#8b949e",
                              font=("Segoe UI", 9, "bold"))
        sec4.pack(fill=tk.X, padx=12, pady=4)
        sec4.columnconfigure(1, weight=1)
        _row(sec4, "Job Title", 0); _entry(sec4, "job_title", cfg.job.title, 0)

        # LLM backend
        sec5 = tk.LabelFrame(frame, text=" LLM Backend ", bg="#0d1117", fg="#8b949e",
                              font=("Segoe UI", 9, "bold"))
        sec5.pack(fill=tk.X, padx=12, pady=(4, 10))
        sec5.columnconfigure(1, weight=1)
        backend_var = tk.StringVar(value=cfg.llm.backend)
        vars["backend"] = backend_var
        _row(sec5, "Backend", 0)
        for i, opt in enumerate(["auto", "groq", "gemini", "ollama"]):
            tk.Radiobutton(sec5, text=opt, variable=backend_var, value=opt,
                           bg="#0d1117", fg="#e6edf3", selectcolor="#1f6feb",
                           activebackground="#0d1117", font=("Segoe UI", 9)
                           ).grid(row=0, column=i + 1, padx=4)

    def _build_logs_tab(self, frame) -> None:
        import tkinter as tk
        from tkinter import scrolledtext
        self._log_text = scrolledtext.ScrolledText(
            frame, state="disabled",
            bg="#0d1117", fg="#3fb950", insertbackground="#e6edf3",
            font=("Consolas", 9), relief="flat", wrap=tk.WORD,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Load existing log
        try:
            base = Path(__file__).resolve().parent.parent
            log_path = base / self._cfg.logging.log_file
            if log_path.exists():
                with log_path.open(encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-200:]
                self._log_text.config(state="normal")
                self._log_text.insert("end", "".join(lines))
                self._log_text.see("end")
                self._log_text.config(state="disabled")
        except Exception:
            pass

    def _build_controls_tab(self, frame) -> None:
        import tkinter as tk
        cfg  = self._cfg
        vars = self._vars

        tk.Label(frame, text="Overlay Transparency", bg="#0d1117", fg="#e6edf3",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=12, pady=(12, 2))
        alpha_var = tk.IntVar(value=cfg.overlay.alpha)
        vars["alpha"] = alpha_var
        tk.Scale(frame, from_=50, to=255, orient="horizontal",
                 variable=alpha_var, length=300,
                 bg="#0d1117", fg="#e6edf3", troughcolor="#161b22", highlightthickness=0,
                 ).pack(anchor="w", padx=12)

    def _on_launch(self) -> None:
        """Save settings and signal pipeline to start."""
        try:
            self._apply_settings()
        except Exception as exc:
            log.warning("Settings save failed: %s", exc)
        self._launch.set()
        log.info("User clicked Save & Launch")

    def _apply_settings(self) -> None:
        """Write GUI values back to the AppConfig in memory."""
        cfg  = self._cfg
        vars = self._vars

        # API keys
        if "groq_key"   in vars: cfg.llm.groq.api_key    = vars["groq_key"].get().strip()
        if "gemini_key" in vars: cfg.llm.gemini.api_key   = vars["gemini_key"].get().strip()
        if "tg_token"   in vars: cfg.telegram.bot_token   = vars["tg_token"].get().strip()
        if "tg_chat"    in vars: cfg.telegram.chat_id     = vars["tg_chat"].get().strip()
        if "backend"    in vars: cfg.llm.backend          = vars["backend"].get().strip()
        if "job_title"  in vars: cfg.job.title            = vars["job_title"].get().strip()
        if "alpha"      in vars: cfg.overlay.alpha        = vars["alpha"].get()

        # Audio device
        if "device_index" in vars:
            dev = vars["device_index"].get().strip()
            try:
                cfg.audio.device_index = int(dev) if dev else None
            except ValueError:
                pass

        # Persist API keys to .env
        base = Path(__file__).resolve().parent.parent
        env_path = base / ".env"
        try:
            lines = []
            if env_path.exists():
                with env_path.open(encoding="utf-8") as f:
                    lines = f.readlines()
            # Update or append each key
            updated = set()
            for i, line in enumerate(lines):
                for key, attr in [("GROQ_API_KEY", cfg.llm.groq.api_key),
                                   ("GEMINI_API_KEY", cfg.llm.gemini.api_key),
                                   ("TELEGRAM_BOT_TOKEN", cfg.telegram.bot_token),
                                   ("TELEGRAM_CHAT_ID", cfg.telegram.chat_id)]:
                    if line.startswith(key + "="):
                        lines[i] = f"{key}={attr}\n"
                        updated.add(key)
            for key, attr in [("GROQ_API_KEY", cfg.llm.groq.api_key),
                               ("GEMINI_API_KEY", cfg.llm.gemini.api_key),
                               ("TELEGRAM_BOT_TOKEN", cfg.telegram.bot_token),
                               ("TELEGRAM_CHAT_ID", cfg.telegram.chat_id)]:
                if key not in updated and attr:
                    lines.append(f"{key}={attr}\n")
            with env_path.open("w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as exc:
            log.debug("Could not write .env: %s", exc)
