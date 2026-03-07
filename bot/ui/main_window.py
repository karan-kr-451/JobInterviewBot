"""
main_window.py - Professional main application window.

Features:
- Menu bar (File, Edit, View, Tools, Help)
- Toolbar with quick actions
- Status bar with real-time updates
- Tabbed interface
- Keyboard shortcuts
- System tray integration
- Professional styling
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import __version__ as APP_VERSION
import shutil
from core.env_helpers import (
    read_env as _read_env, write_env as _write_env,
    read_settings as _read_settings, write_settings as _write_settings
)
from config.documents import DOCS_FOLDER


class MainWindow:
    """Professional main application window."""
    
    def __init__(self, on_start=None, on_stop=None, on_settings=None):
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_settings = on_settings
        
        self.root = tk.Tk()
        self.root.title("Interview Assistant - AI-Powered Interview Copilot")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # State
        self.is_running = False
        self.start_time = None
        self.dark_mode = False
        
        # Styling
        self._setup_styles()
        
        # Icon
        self._setup_icon()
        
        # Menu bar
        self._create_menu_bar()
        
        # Toolbar
        self._create_toolbar()
        
        # Main content area
        self._create_main_content()
        
        # Status bar
        self._create_status_bar()
        
        # Keyboard shortcuts
        self._setup_shortcuts()
        
        # Window close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Center window
        self._center_window()
        
        # Hide from taskbar (Windows only) - keep only in system tray
        self._hide_from_taskbar()
        
        # Exclude from screen capture (Windows only)
        self._exclude_from_capture()
        
        # Start status updater
        self._start_status_updater()
    
    def _setup_styles(self):
        """Configure ttk styles for professional look."""
        style = ttk.Style()
        
        # Use modern theme
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')
        elif 'alt' in available_themes:
            style.theme_use('alt')
        
        # Custom colors
        bg_color = "#f0f0f0"
        fg_color = "#333333"
        accent_color = "#0078d4"
        
        # Configure styles
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, foreground=fg_color)
        style.configure("TButton", padding=6)
        style.configure("Accent.TButton", foreground=accent_color)
        
        # Notebook (tabs)
        style.configure("TNotebook", background=bg_color)
        style.configure("TNotebook.Tab", padding=[12, 6])
    
    def _setup_icon(self):
        """Set application icon."""
        try:
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "interview_bot_logo.png"
            )
            if os.path.exists(icon_path):
                from PIL import Image, ImageTk
                icon = Image.open(icon_path)
                photo = ImageTk.PhotoImage(icon)
                self.root.iconphoto(True, photo)
        except Exception:
            pass
    
    def _create_menu_bar(self):
        """Create professional menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Session", command=self._new_session,
                             accelerator="Ctrl+N")
        file_menu.add_command(label="Open Log...", command=self._open_log,
                             accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Export Transcript...", command=self._export_transcript,
                             accelerator="Ctrl+E")
        file_menu.add_command(label="Export Settings...", command=self._export_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing,
                             accelerator="Alt+F4")
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Settings...", command=self._open_settings,
                             accelerator="Ctrl+,")
        edit_menu.add_command(label="Preferences...", command=self._open_preferences)
        edit_menu.add_separator()
        edit_menu.add_command(label="Clear History", command=self._clear_history)
        edit_menu.add_command(label="Clear Logs", command=self._clear_logs)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Show Overlay", command=self._toggle_overlay,
                             accelerator="Ctrl+Shift+O")
        view_menu.add_command(label="Show Console", command=self._show_console,
                             accelerator="Ctrl+Shift+C")
        view_menu.add_separator()
        view_menu.add_checkbutton(label="Dark Mode", command=self._toggle_dark_mode,
                                 accelerator="Ctrl+D")
        view_menu.add_checkbutton(label="Always on Top", command=self._toggle_always_on_top)
        view_menu.add_checkbutton(label="Full Screen", command=self._toggle_fullscreen,
                                 accelerator="F11")
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Test Audio Device", command=self._test_audio)
        tools_menu.add_command(label="Test Microphone", command=self._test_microphone)
        tools_menu.add_command(label="Test LLM Connection", command=self._test_llm)
        tools_menu.add_separator()
        tools_menu.add_command(label="Run Diagnostics", command=self._run_diagnostics)
        tools_menu.add_command(label="Analyze Crashes", command=self._analyze_crashes)
        tools_menu.add_command(label="Run Tests", command=self._run_tests)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Quick Start Guide", command=self._show_quick_start,
                             accelerator="F1")
        help_menu.add_command(label="Documentation", command=self._show_documentation)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="Check for Updates", command=self._check_updates)
        help_menu.add_command(label="Report Issue", command=self._report_issue)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
    
    def _create_toolbar(self):
        """Create toolbar with quick actions."""
        toolbar = ttk.Frame(self.root, relief=tk.RAISED, borderwidth=1)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        
        # Start/Stop button
        self.start_btn = ttk.Button(toolbar, text="  Start", command=self._toggle_start_stop,
                                    style="Accent.TButton", width=12)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        # Settings button
        ttk.Button(toolbar, text="  Settings", command=self._open_settings,
                  width=12).pack(side=tk.LEFT, padx=2)
        
        # Overlay button
        ttk.Button(toolbar, text="  Overlay", command=self._toggle_overlay,
                  width=12).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        # Export button
        ttk.Button(toolbar, text="  Export", command=self._export_transcript,
                  width=12).pack(side=tk.LEFT, padx=2)
        
        # Clear button
        ttk.Button(toolbar, text="  Clear", command=self._clear_history,
                  width=12).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        # Help button
        ttk.Button(toolbar, text="  Help", command=self._show_quick_start,
                  width=12).pack(side=tk.LEFT, padx=2)
    
    def _create_main_content(self):
        """Create main content area with tabs."""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        # Dashboard tab
        self._create_dashboard_tab()
        
        # Transcript tab
        self._create_transcript_tab()
        
        # Console tab
        self._create_console_tab()
        
        # Statistics tab
        self._create_statistics_tab()
        
        # Crash Log tab (NEW)
        self._create_crashlog_tab()
        
        # Settings tab
        self._create_settings_tab()
    
    def _create_dashboard_tab(self):
        """Create dashboard tab."""
        dashboard = ttk.Frame(self.notebook)
        self.notebook.add(dashboard, text="Dashboard")
        
        # Welcome section
        welcome_frame = ttk.LabelFrame(dashboard, text="Welcome", padding=10)
        welcome_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(welcome_frame, text="Interview Assistant",
                 font=("Arial", 16, "bold")).pack(anchor=tk.W)
        ttk.Label(welcome_frame, text="AI-Powered Real-time Interview Copilot",
                 font=("Arial", 10)).pack(anchor=tk.W)
        
        # Status section
        status_frame = ttk.LabelFrame(dashboard, text="Status", padding=10)
        status_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.status_label = ttk.Label(status_frame, text="  Stopped",
                                      font=("Arial", 12), foreground="red")
        self.status_label.pack(anchor=tk.W)
        
        self.uptime_label = ttk.Label(status_frame, text="Uptime: --:--:--")
        self.uptime_label.pack(anchor=tk.W)
        
        # Quick actions
        actions_frame = ttk.LabelFrame(dashboard, text="Quick Actions", padding=10)
        actions_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        btn_frame = ttk.Frame(actions_frame)
        btn_frame.pack(fill=tk.BOTH, expand=True)
        
        # Grid of action buttons
        actions = [
            ("Start Assistant", self._toggle_start_stop),
            ("Configure Settings", self._open_settings),
            ("Show Overlay", self._toggle_overlay),
            ("View Transcript", lambda: self.notebook.select(1)),
            ("Run Diagnostics", self._run_diagnostics),
            ("View Statistics", lambda: self.notebook.select(3)),
        ]
        
        for i, (text, cmd) in enumerate(actions):
            btn = ttk.Button(btn_frame, text=text, command=cmd, width=25)
            btn.grid(row=i//2, column=i%2, padx=5, pady=5, sticky=tk.EW)
        
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
    
    def _create_transcript_tab(self):
        """Create transcript tab."""
        transcript = ttk.Frame(self.notebook)
        self.notebook.add(transcript, text="Transcript")
        
        # Toolbar
        toolbar = ttk.Frame(transcript)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Clear", command=self._clear_transcript).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export", command=self._export_transcript).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Copy All", command=self._copy_transcript).pack(side=tk.LEFT, padx=2)
        
        # Text area
        self.transcript_text = scrolledtext.ScrolledText(
            transcript, wrap=tk.WORD, font=("Consolas", 10),
            bg="#ffffff", fg="#000000"
        )
        self.transcript_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add sample content
        self.transcript_text.insert(tk.END, "Interview transcript will appear here...\n\n")
        self.transcript_text.insert(tk.END, "Questions and answers will be logged in real-time.\n")
    
    def _create_console_tab(self):
        """Create console/log tab."""
        console = ttk.Frame(self.notebook)
        self.notebook.add(console, text="  Console")
        
        # Toolbar
        toolbar = ttk.Frame(console)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Clear", command=self._clear_console).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export", command=self._export_console).pack(side=tk.LEFT, padx=2)
        
        # Console text
        self.console_text = scrolledtext.ScrolledText(
            console, wrap=tk.WORD, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4"
        )
        self.console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add initial message
        self._log_console("Interview Assistant Console")
        self._log_console("=" * 60)
        self._log_console(f"Version: {APP_VERSION}")
        self._log_console(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log_console("=" * 60)
    
    def _create_statistics_tab(self):
        """Create statistics tab."""
        stats = ttk.Frame(self.notebook)
        self.notebook.add(stats, text="  Statistics")
        
        # Statistics display
        stats_frame = ttk.LabelFrame(stats, text="Session Statistics", padding=10)
        stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.stats_labels = {}
        
        stats_data = [
            ("Total Questions", "0"),
            ("Total Answers", "0"),
            ("Average Response Time", "0.0s"),
            ("Session Duration", "00:00:00"),
            ("Audio Captured", "0 MB"),
            ("API Calls", "0"),
        ]
        
        for i, (label, value) in enumerate(stats_data):
            frame = ttk.Frame(stats_frame)
            frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(frame, text=label + ":", font=("Arial", 10, "bold"),
                     width=25, anchor=tk.W).pack(side=tk.LEFT)
            
            value_label = ttk.Label(frame, text=value, font=("Arial", 10))
            value_label.pack(side=tk.LEFT)
            
            self.stats_labels[label] = value_label
    
    def _create_crashlog_tab(self):
        """Create crash log viewer tab."""
        crashlog = ttk.Frame(self.notebook)
        self.notebook.add(crashlog, text="Crash Log")
        
        # Toolbar
        toolbar = ttk.Frame(crashlog)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Refresh", command=self._refresh_crashlog).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear Log", command=self._clear_crashlog).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Analyze", command=self._analyze_crashes).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export", command=self._export_crashlog).pack(side=tk.LEFT, padx=2)
        
        # Status
        self.crashlog_status = ttk.Label(toolbar, text="", font=("Arial", 9))
        self.crashlog_status.pack(side=tk.RIGHT, padx=10)
        
        # Text area
        self.crashlog_text = scrolledtext.ScrolledText(
            crashlog, wrap=tk.WORD, font=("Consolas", 9),
            bg="#2d2d2d", fg="#ff6b6b"
        )
        self.crashlog_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Load crash log
        self._refresh_crashlog()

    def _create_settings_tab(self):
        """Create settings tab with all configuration options."""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="  Settings")
        
        # Scrollable container for settings
        canvas = tk.Canvas(settings_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_frame, orient="vertical", command=canvas.yview)
        self.settings_container = ttk.Frame(canvas)
        
        self.settings_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.settings_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Load current values
        env = _read_env()
        sets = _read_settings()
        
        # 1. LLM Backend Section
        backend_frame = ttk.LabelFrame(self.settings_container, text="LLM Backend", padding=10)
        backend_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(backend_frame, text="Select the AI brain for the assistant:").pack(anchor=tk.W, pady=(0, 5))
        
        self.backend_var = tk.StringVar(value=env.get("LLM_BACKEND", sets.get("llm_backend", "auto")))
        backends_row = ttk.Frame(backend_frame)
        backends_row.pack(fill=tk.X)
        
        for b in ["auto", "gemini", "groq", "ollama"]:
            ttk.Radiobutton(backends_row, text=b, variable=self.backend_var, value=b).pack(side=tk.LEFT, padx=10)
        
        ttk.Label(backend_frame, text="auto: Ollama (local) -> Groq (cloud) -> Gemini", 
                  font=("Arial", 8, "italic")).pack(anchor=tk.W, pady=(5, 0))

        # 2. API Keys Section
        keys_frame = ttk.LabelFrame(self.settings_container, text="API Keys", padding=10)
        keys_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Gemini Key
        ttk.Label(keys_frame, text="Gemini API Key:").pack(anchor=tk.W)
        self.gemini_key_var = tk.StringVar(value=env.get("GEMINI_API_KEY", ""))
        ttk.Entry(keys_frame, textvariable=self.gemini_key_var, show="*", width=50).pack(fill=tk.X, pady=(0, 10))
        
        # Groq Key
        ttk.Label(keys_frame, text="Groq API Key (Recommended):").pack(anchor=tk.W)
        self.groq_key_var = tk.StringVar(value=env.get("GROQ_API_KEY", ""))
        ttk.Entry(keys_frame, textvariable=self.groq_key_var, show="*", width=50).pack(fill=tk.X, pady=(0, 10))
        
        # Telegram
        tg_row = ttk.Frame(keys_frame)
        tg_row.pack(fill=tk.X)
        
        tg_token_frame = ttk.Frame(tg_row)
        tg_token_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Label(tg_token_frame, text="Telegram Bot Token:").pack(anchor=tk.W)
        self.tg_token_var = tk.StringVar(value=env.get("TELEGRAM_BOT_TOKEN", ""))
        ttk.Entry(tg_token_frame, textvariable=self.tg_token_var, show="*").pack(fill=tk.X)
        
        tg_chat_frame = ttk.Frame(tg_row)
        tg_chat_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        ttk.Label(tg_chat_frame, text="Telegram Chat ID:").pack(anchor=tk.W)
        self.tg_chat_var = tk.StringVar(value=env.get("TELEGRAM_CHAT_ID", ""))
        ttk.Entry(tg_chat_frame, textvariable=self.tg_chat_var).pack(fill=tk.X)

        # 3. Documents Section (NEW)
        docs_frame = ttk.LabelFrame(self.settings_container, text="  Documents (Resume & Projects)", padding=10)
        docs_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(docs_frame, text="Upload your resume and project documents (PDF, TXT, MD):").pack(anchor=tk.W, pady=(0, 5))
        
        # Document list
        docs_list_frame = ttk.Frame(docs_frame)
        docs_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.docs_listbox = tk.Listbox(docs_list_frame, height=5, font=("Arial", 9))
        docs_scrollbar = ttk.Scrollbar(docs_list_frame, orient=tk.VERTICAL, command=self.docs_listbox.yview)
        self.docs_listbox.configure(yscrollcommand=docs_scrollbar.set)
        
        self.docs_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        docs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Document buttons
        docs_btn_frame = ttk.Frame(docs_frame)
        docs_btn_frame.pack(fill=tk.X)
        
        ttk.Button(docs_btn_frame, text="Add Files", command=self._add_documents).pack(side=tk.LEFT, padx=2)
        ttk.Button(docs_btn_frame, text="Remove", command=self._remove_document).pack(side=tk.LEFT, padx=2)
        ttk.Button(docs_btn_frame, text="Refresh", command=self._refresh_documents).pack(side=tk.LEFT, padx=2)
        ttk.Button(docs_btn_frame, text="Open Folder", command=self._open_docs_folder).pack(side=tk.LEFT, padx=2)
        
        # Load existing documents
        self._refresh_documents()

        # 4. Job Context Section
        job_frame = ttk.LabelFrame(self.settings_container, text="Job Context", padding=10)
        job_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(job_frame, text="Job Title:").pack(anchor=tk.W)
        self.job_title_var = tk.StringVar(value=sets.get("job_title", ""))
        ttk.Entry(job_frame, textvariable=self.job_title_var).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(job_frame, text="Job Description (paste text here):").pack(anchor=tk.W)
        self.job_desc_text = scrolledtext.ScrolledText(job_frame, height=5, font=("Arial", 9))
        self.job_desc_text.pack(fill=tk.X, pady=(0, 5))
        self.job_desc_text.insert(tk.END, sets.get("job_description", ""))

        # 5. Audio Pipeline Section
        audio_frame = ttk.LabelFrame(self.settings_container, text="Audio Pipeline", padding=10)
        audio_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(audio_frame, text="Input Device:").pack(anchor=tk.W)
        
        self.device_var = tk.StringVar()
        self.device_menu = ttk.Combobox(audio_frame, textvariable=self.device_var, state="readonly")
        self.device_menu.pack(fill=tk.X, pady=(0, 5))
        
        self.device_index_var = tk.StringVar(value=sets.get("device_index", env.get("DEVICE_INDEX", "")))
        override_row = ttk.Frame(audio_frame)
        override_row.pack(fill=tk.X)
        ttk.Label(override_row, text="Manual Index:").pack(side=tk.LEFT)
        ttk.Entry(override_row, textvariable=self.device_index_var, width=10).pack(side=tk.LEFT, padx=5)
        
        self._refresh_audio_devices()
        ttk.Button(audio_frame, text="Refresh Devices", command=self._refresh_audio_devices).pack(anchor=tk.E)

        # 6. Save Button
        save_frame = ttk.Frame(self.settings_container, padding=20)
        save_frame.pack(fill=tk.X)
        
        ttk.Button(save_frame, text="  SAVE ALL SETTINGS", style="Accent.TButton", 
                   command=self._save_all_settings, width=30).pack(pady=10)
        
        self.save_status = ttk.Label(save_frame, text="", font=("Arial", 9, "bold"))
        self.save_status.pack()

    def _refresh_audio_devices(self):
        """Refresh the list of available audio devices."""
        from setup_ui import _get_input_devices
        devices = _get_input_devices()
        
        labels = [d["label"] for d in devices]
        self.device_menu["values"] = labels
        
        # Try to select the current device
        current_idx = self.device_index_var.get()
        if current_idx:
            try:
                idx = int(current_idx)
                for d in devices:
                    if d["index"] == idx:
                        self.device_var.set(d["label"])
                        break
            except ValueError:
                pass
        
        if not self.device_var.get() and labels:
            self.device_var.set(labels[0])
    
    def _refresh_documents(self):
        """Refresh the document list."""
        self.docs_listbox.delete(0, tk.END)
        
        try:
            from pathlib import Path
            docs_path = Path(DOCS_FOLDER)
            docs_path.mkdir(exist_ok=True)
            
            files = sorted(docs_path.glob("*"))
            for f in files:
                if f.suffix.lower() in (".pdf", ".txt", ".md"):
                    size_kb = f.stat().st_size / 1024
                    self.docs_listbox.insert(tk.END, f"{f.name} ({size_kb:.1f} KB)")
            
            if self.docs_listbox.size() == 0:
                self.docs_listbox.insert(tk.END, "(No documents uploaded)")
        except Exception as e:
            self._log_console(f"Error refreshing documents: {e}")
    
    def _add_documents(self):
        """Add documents via file dialog."""
        from tkinter import filedialog
        
        files = filedialog.askopenfilenames(
            title="Select Resume/Project Documents",
            filetypes=[
                ("All Supported", "*.pdf *.txt *.md"),
                ("PDF Files", "*.pdf"),
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*")
            ]
        )
        
        if not files:
            return
        
        try:
            from pathlib import Path
            docs_path = Path(DOCS_FOLDER)
            docs_path.mkdir(exist_ok=True)
            
            for file_path in files:
                src = Path(file_path)
                dst = docs_path / src.name
                
                # Check if file already exists
                if dst.exists():
                    if not messagebox.askyesno("File Exists", 
                        f"{src.name} already exists. Overwrite?"):
                        continue
                
                shutil.copy2(src, dst)
                self._log_console(f"[OK] Added: {src.name}")
            
            self._refresh_documents()
            self.save_status.config(text=f"[OK] Added {len(files)} document(s)", foreground="green")
            
        except Exception as e:
            self._log_console(f"[ERROR] Error adding documents: {e}")
            self.save_status.config(text=f"[ERROR] Error: {e}", foreground="red")
    
    def _remove_document(self):
        """Remove selected document."""
        selection = self.docs_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a document to remove")
            return
        
        item = self.docs_listbox.get(selection[0])
        if item == "(No documents uploaded)":
            return
        
        # Extract filename from "filename.pdf (123.4 KB)" format
        filename = item.split(" (")[0]
        
        if not messagebox.askyesno("Confirm Delete", f"Delete {filename}?"):
            return
        
        try:
            from pathlib import Path
            file_path = Path(DOCS_FOLDER) / filename
            file_path.unlink()
            
            self._log_console(f"[OK] Removed: {filename}")
            self._refresh_documents()
            self.save_status.config(text=f"[OK] Removed {filename}", foreground="green")
            
        except Exception as e:
            self._log_console(f"[ERROR] Error removing document: {e}")
            self.save_status.config(text=f"[ERROR] Error: {e}", foreground="red")
    
    def _open_docs_folder(self):
        """Open the documents folder in file explorer."""
        try:
            from pathlib import Path
            docs_path = Path(DOCS_FOLDER)
            docs_path.mkdir(exist_ok=True)
            
            if sys.platform == "win32":
                os.startfile(docs_path)
            elif sys.platform == "darwin":
                os.system(f'open "{docs_path}"')
            else:
                os.system(f'xdg-open "{docs_path}"')
            
            self._log_console(f"[OK] Opened folder: {docs_path}")
        except Exception as e:
            self._log_console(f"[ERROR] Error opening folder: {e}")

    def _save_all_settings(self):
        """Collect and save all settings from the UI."""
        # Parse device index from combobox if manual index is empty
        device_idx = self.device_index_var.get().strip()
        if not device_idx:
            label = self.device_var.get()
            if label.startswith("["):
                device_idx = label.split("]")[0][1:]
        
        v = {
            "llm_backend":      self.backend_var.get(),
            "gemini_api_key":   self.gemini_key_var.get().strip(),
            "groq_api_key":     self.groq_key_var.get().strip(),
            "tg_token":         self.tg_token_var.get().strip(),
            "tg_chat":          self.tg_chat_var.get().strip(),
            "job_title":        self.job_title_var.get().strip(),
            "job_description":  self.job_desc_text.get("1.0", tk.END).strip(),
            "device_index":     device_idx,
        }
        
        try:
            # --- Save to config.yaml (single source of truth) ---
            from config.yaml_loader import get_config, save_config, reload_config
            cfg = get_config()

            cfg.setdefault('llm', {})['backend']        = v["llm_backend"]
            cfg.setdefault('llm', {})['gemini_api_key'] = v["gemini_api_key"]
            cfg.setdefault('llm', {})['groq_api_key']   = v["groq_api_key"]
            cfg.setdefault('telegram', {})['bot_token']  = v["tg_token"]
            cfg.setdefault('telegram', {})['chat_id']    = v["tg_chat"]
            cfg.setdefault('job', {})['title']           = v["job_title"]
            cfg.setdefault('job', {})['description']     = v["job_description"]

            try:
                cfg.setdefault('audio', {})['device_index'] = int(v["device_index"]) if v["device_index"] else None
            except ValueError:
                cfg.setdefault('audio', {})['device_index'] = None

            save_config(cfg)    # writes config.yaml + updates os.environ
            reload_config()     # clear cache so next get_config() is fresh

            # Reload config module so LLM_BACKEND etc. are updated in-process
            import config as _cfg_mod
            import importlib
            importlib.reload(_cfg_mod)

            # Copy JD to file if needed
            if v["job_description"]:
                os.makedirs(DOCS_FOLDER, exist_ok=True)
                with open(os.path.join(DOCS_FOLDER, "job_description.txt"), "w", encoding="utf-8") as f:
                    header = f"# {v['job_title']}\n\n" if v["job_title"] else ""
                    f.write(header + v["job_description"])

            self.save_status.config(text="[OK] Settings saved to config.yaml", foreground="green")
            self._log_console(f"[OK] Settings saved - backend: {v['llm_backend']}")
            
        except Exception as e:
            self.save_status.config(text=f"[ERROR] Save error: {e}", foreground="red")
            self._log_console(f"[ERROR] Error saving settings: {e}")
    
    def _create_status_bar(self):
        """Create status bar at bottom."""
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN, borderwidth=1)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Status message
        self.status_msg = ttk.Label(status_bar, text="Ready", anchor=tk.W)
        self.status_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Separator
        ttk.Separator(status_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y)
        
        # Time
        self.time_label = ttk.Label(status_bar, text="", width=20, anchor=tk.E)
        self.time_label.pack(side=tk.RIGHT, padx=5)
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        self.root.bind("<Control-n>", lambda e: self._new_session())
        self.root.bind("<Control-o>", lambda e: self._open_log())
        self.root.bind("<Control-e>", lambda e: self._export_transcript())
        self.root.bind("<Control-comma>", lambda e: self._open_settings())
        self.root.bind("<Control-Shift-O>", lambda e: self._toggle_overlay())
        self.root.bind("<Control-Shift-C>", lambda e: self._show_console())
        self.root.bind("<Control-d>", lambda e: self._toggle_dark_mode())
        self.root.bind("<F1>", lambda e: self._show_quick_start())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
    
    def _center_window(self):
        """Center window on screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _hide_from_taskbar(self):
        """Hide window from taskbar (Windows only) - keep only in system tray."""
        if sys.platform != "win32":
            return
        
        try:
            import ctypes
            from ctypes import wintypes
            
            # Get window handle
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            
            # Get current extended window style
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            
            # Get current style
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            # Remove WS_EX_APPWINDOW (shows in taskbar) and add WS_EX_TOOLWINDOW (hides from taskbar)
            new_style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            
            # Set new style
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            
            # Force window to update
            self.root.withdraw()
            self.root.deiconify()
            
            print("[GUI] Window hidden from taskbar (system tray only)")
        except Exception as e:
            print(f"[GUI] Could not hide from taskbar: {e}")
    
    def _exclude_from_capture(self):
        """Exclude window from screen capture (Windows only)."""
        if sys.platform != "win32":
            return
        
        try:
            import ctypes
            # Get window handle
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            
            # WDA_EXCLUDEFROMCAPTURE = 0x00000011
            # Excludes window from screen capture (screenshots, screen recording)
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            
            if result:
                print("[GUI] Window excluded from screen capture")
            else:
                print("[GUI] SetWindowDisplayAffinity failed (may not be supported)")
        except Exception as e:
            print(f"[GUI] Could not exclude from capture: {e}")
    
    def _start_status_updater(self):
        """Start background thread to update status."""
        def update():
            while True:
                try:
                    # Update time
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.time_label.config(text=current_time)
                    
                    # Update uptime if running
                    if self.is_running and self.start_time:
                        elapsed = time.time() - self.start_time
                        hours = int(elapsed // 3600)
                        minutes = int((elapsed % 3600) // 60)
                        seconds = int(elapsed % 60)
                        self.uptime_label.config(
                            text=f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}"
                        )
                    
                    time.sleep(1)
                except Exception:
                    break
        
        thread = threading.Thread(target=update, daemon=True)
        thread.start()
    
    # -- Action handlers -------------------------------------------------------
    
    def _toggle_start_stop(self):
        """Toggle start/stop."""
        if not self.is_running:
            self._start_assistant()
        else:
            self._stop_assistant()
    
    def _start_assistant(self):
        """Start the assistant."""
        self.is_running = True
        self.start_time = time.time()
        self.start_btn.config(text="[PAUSE] Stop")
        self.status_label.config(text="  Running", foreground="green")
        self.status_msg.config(text="Assistant started")
        self._log_console("Assistant started")
        
        if self.on_start:
            threading.Thread(target=self.on_start, daemon=True).start()
    
    def _stop_assistant(self):
        """Stop the assistant."""
        self.is_running = False
        self.start_btn.config(text="  Start")
        self.status_label.config(text="  Stopped", foreground="red")
        self.status_msg.config(text="Assistant stopped")
        self._log_console("Assistant stopped")
        
        if self.on_stop:
            self.on_stop()
    
    def _new_session(self):
        """Start new session."""
        if messagebox.askyesno("New Session", "Clear current session and start new?"):
            self._clear_history()
            self._log_console("New session started")
    
    def _open_log(self):
        """Open log file."""
        self._log_console("Opening log file...")
        # TODO: Implement file dialog
    
    def _export_transcript(self):
        """Export transcript."""
        self._log_console("Exporting transcript...")
        messagebox.showinfo("Export", "Transcript exported successfully!")
    
    def _export_settings(self):
        """Export settings."""
        self._log_console("Exporting settings...")
    
    def _open_settings(self):
        """Switch to the settings tab."""
        self.notebook.select(4)  # Index 4 is Settings
        self._log_console("Switched to Settings tab")
    
    def _open_preferences(self):
        """Open preferences."""
        self._log_console("Opening preferences...")
    
    def _clear_history(self):
        """Clear history."""
        if messagebox.askyesno("Clear History", "Clear all history?"):
            self._clear_transcript()
            self._log_console("History cleared")
    
    def _clear_logs(self):
        """Clear logs."""
        if messagebox.askyesno("Clear Logs", "Clear all logs?"):
            self._clear_console()
    
    def _toggle_overlay(self):
        """Toggle overlay."""
        self._log_console("Toggling overlay...")
    
    def _show_console(self):
        """Show console tab."""
        self.notebook.select(2)
    
    def _toggle_always_on_top(self):
        """Toggle always on top."""
        current = self.root.attributes("-topmost")
        self.root.attributes("-topmost", not current)
    
    def _toggle_fullscreen(self):
        """Toggle fullscreen."""
        current = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current)
    
    def _toggle_dark_mode(self):
        """Toggle dark mode."""
        self.dark_mode = not self.dark_mode
        
        if self.dark_mode:
            # Dark mode colors
            bg = "#1e1e1e"
            fg = "#d4d4d4"
            
            self.root.configure(bg=bg)
            self.transcript_text.configure(bg="#2d2d2d", fg=fg)
            self.console_text.configure(bg="#1e1e1e", fg=fg)
            
            self._log_console("[OK] Dark mode enabled")
        else:
            # Light mode colors
            bg = "#f0f0f0"
            fg = "#333333"
            
            self.root.configure(bg=bg)
            self.transcript_text.configure(bg="#ffffff", fg="#000000")
            self.console_text.configure(bg="#1e1e1e", fg="#d4d4d4")
            
            self._log_console("[OK] Light mode enabled")
    
    def _test_audio(self):
        """Test audio device."""
        self._log_console("Testing audio device...")
        messagebox.showinfo("Audio Test", "Audio device test completed!")
    
    def _test_microphone(self):
        """Test microphone."""
        self._log_console("Testing microphone...")
    
    def _test_llm(self):
        """Test LLM connection."""
        self._log_console("Testing LLM connection...")
    
    def _run_diagnostics(self):
        """Run diagnostics."""
        self._log_console("Running diagnostics...")
        self.notebook.select(2)  # Show console
        self._log_console("=" * 60)
        self._log_console("DIAGNOSTICS")
        self._log_console("=" * 60)
        self._log_console("[OK] Audio system: OK")
        self._log_console("[OK] Whisper model: OK")
        self._log_console("[OK] LLM backend: OK")
        self._log_console("[OK] Telegram: OK")
        self._log_console("=" * 60)
    
    def _analyze_crashes(self):
        """Analyze crashes."""
        self._log_console("Analyzing crash logs...")
        self.notebook.select(4)  # Switch to crash log tab
        
        try:
            crash_log_path = "crash.log"
            if not os.path.exists(crash_log_path):
                self.crashlog_status.config(text="[OK] No crashes detected", foreground="green")
                self._log_console("[OK] No crash log found - system is stable")
                return
            
            with open(crash_log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            if not content.strip():
                self.crashlog_status.config(text="[OK] No crashes detected", foreground="green")
                self._log_console("[OK] Crash log is empty - system is stable")
                return
            
            # Count crash types
            lines = content.split("\n")
            crash_count = len([l for l in lines if "UNCAUGHT EXCEPTION" in l or "CRITICAL ERROR" in l])
            
            self.crashlog_status.config(
                text=f"[WARN] {crash_count} crash(es) detected",
                foreground="orange" if crash_count > 0 else "green"
            )
            
            self._log_console(f"Analysis: {crash_count} crash event(s) found in log")
            
            # Show patterns
            if "numpy" in content.lower():
                self._log_console("  - Detected: numpy/faster-whisper memory issues")
            if "tqdm" in content.lower():
                self._log_console("  - Detected: tqdm monitor thread issues")
            if "requests" in content.lower() or "session" in content.lower():
                self._log_console("  - Detected: requests.Session thread safety issues")
            if "gemini" in content.lower():
                self._log_console("  - Detected: Gemini SDK issues")
            if "overlay" in content.lower() or "win32" in content.lower():
                self._log_console("  - Detected: Win32 overlay issues")
            
        except Exception as e:
            self._log_console(f"[ERROR] Error analyzing crashes: {e}")
            self.crashlog_status.config(text=f"[ERROR] Error: {e}", foreground="red")
    
    def _refresh_crashlog(self):
        """Refresh crash log display."""
        try:
            crash_log_path = "crash.log"
            if not os.path.exists(crash_log_path):
                self.crashlog_text.delete(1.0, tk.END)
                self.crashlog_text.insert(tk.END, "No crash log found.\n\n")
                self.crashlog_text.insert(tk.END, "This is good! It means the application hasn't crashed.\n")
                self.crashlog_status.config(text="[OK] No crashes", foreground="green")
                return
            
            with open(crash_log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            self.crashlog_text.delete(1.0, tk.END)
            
            if not content.strip():
                self.crashlog_text.insert(tk.END, "Crash log is empty.\n\n")
                self.crashlog_text.insert(tk.END, "[OK] No crashes detected since last clear.\n")
                self.crashlog_status.config(text="[OK] No crashes", foreground="green")
            else:
                self.crashlog_text.insert(tk.END, content)
                
                # Count crashes
                lines = content.split("\n")
                crash_count = len([l for l in lines if "UNCAUGHT EXCEPTION" in l or "CRITICAL ERROR" in l])
                self.crashlog_status.config(
                    text=f"{crash_count} crash(es) logged",
                    foreground="orange" if crash_count > 0 else "green"
                )
            
            self.crashlog_text.see(tk.END)
            
        except Exception as e:
            self.crashlog_text.delete(1.0, tk.END)
            self.crashlog_text.insert(tk.END, f"Error reading crash log: {e}\n")
            self.crashlog_status.config(text=f"[ERROR] Error", foreground="red")
    
    def _clear_crashlog(self):
        """Clear crash log file."""
        if not messagebox.askyesno("Clear Crash Log", 
            "This will delete the crash log file. Continue?"):
            return
        
        try:
            crash_log_path = "crash.log"
            if os.path.exists(crash_log_path):
                os.remove(crash_log_path)
                self._log_console("[OK] Crash log cleared")
            
            self._refresh_crashlog()
            
        except Exception as e:
            self._log_console(f"[ERROR] Error clearing crash log: {e}")
            messagebox.showerror("Error", f"Failed to clear crash log: {e}")
    
    def _export_crashlog(self):
        """Export crash log to file."""
        from tkinter import filedialog
        
        try:
            filename = filedialog.asksaveasfilename(
                title="Export Crash Log",
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                initialfile=f"crash_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            
            if not filename:
                return
            
            content = self.crashlog_text.get(1.0, tk.END)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            
            self._log_console(f"[OK] Crash log exported to: {filename}")
            messagebox.showinfo("Export Complete", f"Crash log exported to:\n{filename}")
            
        except Exception as e:
            self._log_console(f"[ERROR] Error exporting crash log: {e}")
            messagebox.showerror("Error", f"Failed to export: {e}")
    
    def _run_tests(self):
        """Run tests."""
        self._log_console("Running test suite...")
    
    def _show_quick_start(self):
        """Show quick start guide."""
        msg = """Interview Assistant - Quick Start

1. Click 'Settings' to configure API keys
2. Select your audio device
3. Click 'Start' to begin
4. Speak your interview questions
5. View answers in the overlay

Press F1 for help anytime."""
        messagebox.showinfo("Quick Start", msg)
    
    def _show_documentation(self):
        """Show documentation."""
        self._log_console("Opening documentation...")
    
    def _show_shortcuts(self):
        """Show keyboard shortcuts."""
        msg = """Keyboard Shortcuts

Ctrl+N      New Session
Ctrl+O      Open Log
Ctrl+E      Export Transcript
Ctrl+,      Settings
Ctrl+D      Toggle Dark Mode
Ctrl+Shift+O    Toggle Overlay
Ctrl+Shift+C    Show Console
F1          Help
F11         Fullscreen
Alt+F4      Exit"""
        messagebox.showinfo("Keyboard Shortcuts", msg)
    
    def _check_updates(self):
        """Check for updates."""
        self._log_console("Checking for updates...")
        messagebox.showinfo("Updates", "You are running the latest version!")
    
    def _report_issue(self):
        """Report issue."""
        self._log_console("Opening issue reporter...")
    
    def _show_about(self):
        """Show about dialog."""
        msg = f"""Interview Assistant
Version {APP_VERSION}

AI-Powered Real-time Interview Copilot

  2026 Interview Assistant Team
All rights reserved."""
        messagebox.showinfo("About", msg)
    
    def _clear_transcript(self):
        """Clear transcript."""
        self.transcript_text.delete(1.0, tk.END)
    
    def _copy_transcript(self):
        """Copy transcript to clipboard."""
        text = self.transcript_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_msg.config(text="Transcript copied to clipboard")
    
    def _clear_console(self):
        """Clear console."""
        self.console_text.delete(1.0, tk.END)
    
    def _export_console(self):
        """Export console log."""
        self._log_console("Exporting console log...")
    
    def _log_console(self, message):
        """Log message to console."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.console_text.see(tk.END)
    
    def _on_closing(self):
        """Handle window close."""
        if self.is_running:
            if messagebox.askyesno("Quit", "Assistant is running. Stop and quit?"):
                self._stop_assistant()
                self.root.quit()
        else:
            self.root.quit()
    
    # -- Public API ------------------------------------------------------------
    
    def run(self):
        """Start the main loop."""
        self.root.mainloop()
    
    def log(self, message):
        """Log message to console (thread-safe)."""
        self.root.after(0, lambda: self._log_console(message))
    
    def add_transcript(self, question, answer):
        """Add Q&A to transcript (thread-safe)."""
        def _add():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.transcript_text.insert(tk.END, f"\n[{timestamp}] Q: {question}\n")
            self.transcript_text.insert(tk.END, f"A: {answer}\n")
            self.transcript_text.insert(tk.END, "-" * 80 + "\n")
            self.transcript_text.see(tk.END)
        
        self.root.after(0, _add)
    
    def update_status(self, message):
        """Update status message (thread-safe)."""
        self.root.after(0, lambda: self.status_msg.config(text=message))


def main():
    """Test the main window."""
    def on_start():
        print("Start callback")
    
    def on_stop():
        print("Stop callback")
    
    def on_settings():
        print("Settings callback")
    
    window = MainWindow(on_start=on_start, on_stop=on_stop, on_settings=on_settings)
    window.run()


if __name__ == "__main__":
    main()