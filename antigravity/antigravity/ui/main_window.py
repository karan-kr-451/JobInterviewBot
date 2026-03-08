"""
ui/main_window.py — Main GUI dashboard (PyQt6).

Rule 12: NO worker references in this file — communicate via EventBus only.
ALL state updates via Qt signals via SignalBridge to guarantee thread safety.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QPushButton, QLabel, QSplitter, QFileDialog
)

from antigravity.core.event_bus import (
    bus, EVT_TRANSCRIPT_READY, EVT_RESPONSE_READY, 
    EVT_RECORDING_START, EVT_RECORDING_STOP, 
    EVT_ERROR, EVT_WORKER_DEAD, EVT_BACKEND_SWITCHED,
    EVT_TOKEN_USAGE_READY, EVT_DOCUMENTS_UPDATED,
    EVT_CLASSIFICATION_READY
)
from antigravity.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    """
    Converts EventBus callbacks (any thread) to Qt signals (GUI thread).
    Mandatory for PyQt6 thread safety.
    """
    transcript        = pyqtSignal(str)
    response          = pyqtSignal(str)
    recording_start   = pyqtSignal()
    recording_stop    = pyqtSignal()
    error             = pyqtSignal(str)
    worker_dead       = pyqtSignal(str)
    startup_finished  = pyqtSignal()
    token_usage       = pyqtSignal(dict)
    classification    = pyqtSignal(str)


# Process-level bridge
bridge = SignalBridge()

# Wire EventBus -> Qt Signals (Called from worker threads)
bus.subscribe(EVT_TRANSCRIPT_READY, lambda d: bridge.transcript.emit(d))
bus.subscribe(EVT_RESPONSE_READY,   lambda d: bridge.response.emit(d))
bus.subscribe(EVT_RECORDING_START,  lambda d: bridge.recording_start.emit())
bus.subscribe(EVT_RECORDING_STOP,   lambda d: bridge.recording_stop.emit())
bus.subscribe(EVT_ERROR,            lambda d: bridge.error.emit(str(d)))
bus.subscribe(EVT_WORKER_DEAD,      lambda d: bridge.worker_dead.emit(str(d)))
bus.subscribe(EVT_CLASSIFICATION_READY, lambda d: bridge.classification.emit(str(d)))
# Token usage wired natively in main_gui.py along with other startup wiring


class MainWindow(QMainWindow):
    def __init__(self, title: str = "Antigravity Interview Assistant"):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(800, 600)
        
        self._setup_ui()
        self._connect_signals()
        
        # We start looking for updates
        self.status_label.setText("Status: Initializing modules...")

    def _setup_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout()
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: #555;")
        
        self.lbl_tokens = QLabel("Tokens: Waiting")
        self.lbl_tokens.setStyleSheet("color: #0066cc;")
        self.lbl_tokens.setToolTip("LLM token usage per request")
        
        self.lbl_type = QLabel("Category: -")
        self.lbl_type.setStyleSheet("color: #6a0dad; font-weight: bold;")
        
        self.btn_ghost = QPushButton("Ghost: OFF")
        self.btn_ghost.setCheckable(True)
        self.btn_ghost.clicked.connect(self._on_ghost_toggled)
        self.btn_ghost.setFixedWidth(80)
        
        self.btn_upload = QPushButton("Upload Docs")
        self.btn_upload.clicked.connect(self._on_upload_clicked)
        
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.clicked.connect(self._open_settings)
        
        toolbar.addWidget(self.status_label)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.lbl_type)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.lbl_tokens)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_ghost)
        toolbar.addSpacing(5)
        toolbar.addWidget(self.btn_upload)
        toolbar.addSpacing(5)
        toolbar.addWidget(self.btn_settings)
        layout.addLayout(toolbar)

        # Split content: Transcript (top) / Response (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Transcript area
        t_widget = QWidget()
        t_layout = QVBoxLayout(t_widget)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.addWidget(QLabel("<b>Live Transcript:</b>"))
        self.txt_transcript = QTextEdit()
        self.txt_transcript.setReadOnly(True)
        self.txt_transcript.setFont(QFont("Segoe UI", 11))
        t_layout.addWidget(self.txt_transcript)
        
        # Response area
        r_widget = QWidget()
        r_layout = QVBoxLayout(r_widget)
        r_layout.setContentsMargins(0, 0, 0, 0)
        r_layout.addWidget(QLabel("<b>AI Suggested Response:</b>"))
        self.txt_response = QTextEdit()
        self.txt_response.setReadOnly(True)
        self.txt_response.setFont(QFont("Segoe UI", 12))
        self.txt_response.setStyleSheet("background-color: #f0f8ff;")
        r_layout.addWidget(self.txt_response)
        
        splitter.addWidget(t_widget)
        splitter.addWidget(r_widget)
        splitter.setSizes([200, 400])
        
        layout.addWidget(splitter)
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        bridge.transcript.connect(self._on_transcript)
        bridge.response.connect(self._on_response)
        bridge.recording_start.connect(lambda: self.status_label.setText("Status: 🔴 RECORDING"))
        bridge.recording_start.connect(lambda: self.status_label.setStyleSheet("font-weight: bold; color: red;"))
        bridge.recording_stop.connect(lambda: self.status_label.setText("Status: ⏹️ STOPPED"))
        bridge.recording_stop.connect(lambda: self.status_label.setStyleSheet("font-weight: bold; color: #555;"))
        bridge.error.connect(self._on_error)
        bridge.worker_dead.connect(self._on_worker_dead)
        bridge.startup_finished.connect(self._on_startup_finished)
        bridge.token_usage.connect(self._on_token_usage)
        bridge.classification.connect(self._on_classification)

    def _on_transcript(self, text: str) -> None:
        # Move cursor to end, insert, scroll
        self.txt_transcript.moveCursor(QTextCursor.MoveOperation.End)
        self.txt_transcript.insertPlainText(f"• {text}\n\n")
        self.txt_transcript.ensureCursorVisible()

    def _on_response(self, text: str) -> None:
        self.txt_response.setPlainText(text)
        self.txt_response.moveCursor(QTextCursor.MoveOperation.End)
        self.txt_response.ensureCursorVisible()

    def _on_error(self, text: str) -> None:
        self.txt_response.setPlainText(f"⚠️ ERROR: {text}")
        self.txt_response.setStyleSheet("background-color: #ffe6e6;")
        # Reset color after 5 seconds
        QTimer.singleShot(5000, lambda: self.txt_response.setStyleSheet("background-color: #f0f8ff;"))

    def _on_worker_dead(self, data: str) -> None:
        self.status_label.setText(f"Status: ⚠️ CRITICAL - Worker Died: {data}")
        self.status_label.setStyleSheet("font-weight: bold; color: red; background-color: yellow;")

    def _on_startup_finished(self) -> None:
        self.status_label.setText("Status: 🟢 System Ready & Listening")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")

    def _on_token_usage(self, usage: dict) -> None:
        model = usage.get("model", "unknown")
        inp = usage.get("input", 0)
        out = usage.get("output", 0)
        self.lbl_tokens.setText(f"Tokens ({model}): {inp} In | {out} Out")

    def _on_classification(self, label: str) -> None:
        self.lbl_type.setText(f"Category: {label}")

    def _on_ghost_toggled(self, checked: bool) -> None:
        """Toggles semi-transparency and Always-on-Top."""
        if checked:
            self.setWindowOpacity(0.7)
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.btn_ghost.setText("Ghost: ON")
            self.btn_ghost.setStyleSheet("background-color: #e0f0ff; font-weight: bold;")
        else:
            self.setWindowOpacity(1.0)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.btn_ghost.setText("Ghost: OFF")
            self.btn_ghost.setStyleSheet("")
        
        # After changing flags, window must be reshown on Windows
        self.show()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.exec()
        
    def _on_upload_clicked(self) -> None:
        import os
        import shutil
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Resume or Documents", "", "Documents (*.pdf *.txt *.md *.docx)"
        )
        if not files:
            return
            
        docs_dir = "interview_docs"
        os.makedirs(docs_dir, exist_ok=True)
        
        count = 0
        for src in files:
            fname = os.path.basename(src)
            dest = os.path.join(docs_dir, fname)
            try:
                shutil.copy2(src, dest)
                count += 1
            except Exception as e:
                logger.error("Failed to copy %s: %s", fname, e)
                
        if count > 0:
            self.txt_response.append(f"<i>Uploaded {count} file(s) successfully! RAG context updating...</i>")
            # Notify RAG system to reload
            bus.publish(EVT_DOCUMENTS_UPDATED)
        
    def closeEvent(self, event) -> None:
        # Hide instead of close to keep tray active
        event.ignore()
        self.hide()
