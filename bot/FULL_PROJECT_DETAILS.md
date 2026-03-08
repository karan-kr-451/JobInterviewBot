# 📄 Interview Assistant: Full Project Details

## 🚀 Overview
**Interview Assistant** is a professional, enterprise-grade real-time AI assistant specifically designed for technical interviews. It features a "Zero-Crash Guarantee" through robust threading and comprehensive error handling.

- **Current Version**: 3.0  
- **Architecture**: Modular, Multi-threaded, Event-driven  
- **Primary Goal**: Provide real-time assistance during interviews by transcribing audio and generating AI-powered responses with zero latency perception.

---

## 🎨 Key Features
- **Real-time Transcription**: High-accuracy audio capture from systems using "Stereo Mix" or Virtual Audio Cable.
- **AI-Powered Assistance**: Integration with **Groq**, **Gemini**, and **Ollama** for context-aware interview answers.
- **Transparent Overlay**: Dynamic HUD (Heads-Up Display) that stays on top but is click-through and adjustable.
- **GUI Management**: Professional interface for settings, document uploads (resumes/job descriptions), and real-time monitoring.
- **System Tray Integration**: Background operation with quick-access controls.
- **Zero-Crash Guard**: Internal health monitoring and fail-safes against API latencies, library bugs, and thread deadlocks.
- **Telegram Notifications**: Optional remote logging and alerts via Telegram Bot API.

---

## 🏗️ Technical Architecture

### 🧵 Thread Model
The application operates on a sophisticated multi-threaded architecture to ensure UI responsiveness:
1. **Main Thread**: Controls the lifecycle and orchestrates worker threads.
2. **GUI Thread (PyQt6)**: Manages the professional dashboard and settings window.
3. **Overlay Thread**: High-performance Win32 transparent window for real-time display.
4. **Transcription Worker**: Drains audio buffers and processes transcription through Groq Whisper or local models.
5. **LLM Worker**: Handles streaming AI responses using chosen backends (Groq/Gemini).
6. **Telegram Notifier**: Asynchronous queue-based logging to prevent network latency from blocking the core app.
7. **Crash Monitor**: Periodic health checks on all worker threads.

### 🧩 Core Modules
| Module | Purpose |
|--------|---------|
| `core/` | Heart of the application; handles event routing and state management. |
| `llm/` | Multi-backend support (Groq, Gemini, Ollama) with prompt engineering and document context integration. |
| `transcription/` | Real-time audio processing and STT (Speech-To-Text) logic. |
| `ui/` | PyQt6-based dashboard and specialized Win32 overlay logic. |
| `audio/` | PyAudio/PortAudio low-level capture and device management. |
| `notifications/` | Telegram integration for status updates and remote logging. |

---

## 🛠️ Technology Stack
- **Language**: Python 3.12+
- **GUI Framework**: PyQt6
- **Real-time Graphics**: Win32 API (for high-performance transparency)
- **Audio Processing**: PyAudio, NumPy
- **Transcription**: Groq Whisper (Remote), Faster-Whisper (Local fallback)
- **AI Engines**:
    - **Groq**: LLaMA-3 (for speed)
    - **Gemini**: Gemini-1.5/2.0 Flash (for stability and large context)
    - **Ollama**: Local fallback support
- **Configuration**: YAML, JSON, and Dotenv
- **Distribution**: PyInstaller with optimized build scripts

---

## ⚙️ Configuration & Environment

### 🔑 API Management (`.env`)
The system requires valid API keys for top-tier performance:
- `GROQ_API_KEY`: Required for ultra-fast LLaMA response times.
- `GEMINI_API_KEY`: Used for robust fallback and deep context analysis.
- `TELEGRAM_BOT_TOKEN`: Required if remote notifications are enabled.

### 📝 Application Settings (`config.yaml`)
- **Backend Selection**: `auto` (default), `groq`, or `gemini`.
- **Personality**: Customizable job descriptions and resumes for pre-context.
- **Audio**: `device_index` for precise hardware targeting.

---

## 🛡️ "Zero-Crash Guarantee" Implementation
The project is hardened against common Python failure points:
- **GC Protection**: Disables specific garbage collection triggers that cause access violations in C-extensions (like `tqdm`).
- **Watchdog Timer**: Restarts transcription/LLM flows if a response hang is detected.
- **Thread Isolation**: Worker crashes do not propagate to the GUI or each other.
- **Pre-loading**: All heavy binary modules are imported at startup to avoid race conditions during lazy imports.
- **Fault Handling**: Uses Python's `faulthandler` and `traceback` to log exact failure points to `.crash_log` files for debugging.

---

## 💻 Execution & Deployment

### Run Modes
- **GUI Mode** (`main_gui.py`): Full-featured dashboard with settings editor.
- **Console Mode** (`main.py`): Lightweight version with text-only output.
- **Wrapped Mode** (`crash_detector.py`): External supervisor that auto-restarts the core process on failure.

### Build Process
The project includes specialized scripts to package as a standalone Windows executable:
1. `build_exe.py`: Core build logic using PyInstaller.
2. `build_with_venv.bat`: Complete automated pipeline from environment prep to final EXE.

---

## 📞 Maintenance & Logging
Logs are generated per session:
- `interview_log.txt`: Conversation and status history.
- `crash_debug_*.log`: Technical logs for debugging (if enabled).
- `settings.json`: Persisted user preferences for the GUI.

---

**Status**: Ready for Production  
**Support**: Documentation available in `HOW_TO_RUN.md`, `README.md`, and `CRASH_ISSUES_COMPLETE_HISTORY.md`.
