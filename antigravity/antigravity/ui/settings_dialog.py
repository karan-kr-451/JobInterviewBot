"""
ui/settings_dialog.py — PyQt6 Settings Dialog for API keys and basic config.
"""

from __future__ import annotations

import logging
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QComboBox
)

logger = logging.getLogger(__name__)


def load_env_dict(path: str) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    res = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                res[k.strip()] = v.strip()
    return res


def save_env_dict(path: str, data: dict[str, str]) -> None:
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                k = line.strip().split("=", 1)[0].strip()
                if k in data:
                    f.write(f"{k}={data.pop(k)}\n")
                else:
                    f.write(line)
            else:
                f.write(line)
                
        # Write remaining new keys
        for k, v in data.items():
            f.write(f"{k}={v}\n")


class SettingsDialog(QDialog):
    """
    Dialog to configure .env variables like API keys.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Antigravity Settings")
        self.setMinimumWidth(400)
        self._env_path = ".env"
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Groq API Key
        layout.addWidget(QLabel("Groq API Key (Primary STT & LLM):"))
        self.groq_input = QLineEdit()
        self.groq_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.groq_input)

        # Gemini API Key
        layout.addWidget(QLabel("Gemini API Key (Fallback LLM):"))
        self.gemini_input = QLineEdit()
        self.gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.gemini_input)

        # Telegram
        layout.addWidget(QLabel("Telegram Bot Token (Optional):"))
        self.tg_token_input = QLineEdit()
        self.tg_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.tg_token_input)

        layout.addWidget(QLabel("Telegram Chat ID (Optional):"))
        self.tg_chat_input = QLineEdit()
        layout.addWidget(self.tg_chat_input)

        # Device index
        layout.addWidget(QLabel("Audio Device Index (Leave blank for default):"))
        self.device_input = QLineEdit()
        layout.addWidget(self.device_input)

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_data)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _load_data(self):
        env_data = load_env_dict(self._env_path)
        self.groq_input.setText(env_data.get("GROQ_API_KEY", ""))
        self.gemini_input.setText(env_data.get("GEMINI_API_KEY", ""))
        self.tg_token_input.setText(env_data.get("TELEGRAM_BOT_TOKEN", ""))
        self.tg_chat_input.setText(env_data.get("TELEGRAM_CHAT_ID", ""))
        self.device_input.setText(env_data.get("DEVICE_INDEX", ""))

    def _save_data(self):
        env_data = {
            "GROQ_API_KEY": self.groq_input.text().strip(),
            "GEMINI_API_KEY": self.gemini_input.text().strip(),
            "TELEGRAM_BOT_TOKEN": self.tg_token_input.text().strip(),
            "TELEGRAM_CHAT_ID": self.tg_chat_input.text().strip(),
        }
        
        dev_idx = self.device_input.text().strip()
        if dev_idx:
            env_data["DEVICE_INDEX"] = dev_idx
            
        save_env_dict(self._env_path, env_data)
        QMessageBox.information(self, "Settings Saved", "Settings saved to .env file. Please restart the application for changes to take effect.")
        self.accept()
