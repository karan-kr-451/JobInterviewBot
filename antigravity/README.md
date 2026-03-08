# Interview Assistant Antigravity

A clean-room, production-grade re-implementation of Interview Assistant v3.0.
Runs as a real-time AI assistant during technical interviews, listening to system
audio and streaming concise, persona-framed answers via an always-on-top overlay.

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure
Edit **`.env`** and fill in your API keys:
```
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
TELEGRAM_BOT_TOKEN=   # optional
TELEGRAM_CHAT_ID=     # optional
DEVICE_INDEX=         # audio capture device (see step 3)
```

### 3. Find your audio device
```python
python -c "import sounddevice as sd; print(sd.query_devices())"
```
Look for **Stereo Mix** (real-time PC audio) or **VB-Audio Cable**.
Set `DEVICE_INDEX` in `.env`.

### 4. Add your documents (optional, enables RAG)
Drop PDF/TXT files into `interview_docs/`:
- `resume_yourname.pdf`  → resume context
- `job_description.txt`  → role context  
- `projects.pdf`         → project details

### 5. Launch
```bash
python main.py          # Opens Setup GUI → launches pipeline
python crash_detector.py  # Supervisor mode with auto-restart
```

---

## Architecture

```
antigravity/
├── main.py              ← entry point
├── crash_detector.py    ← external supervisor
├── config/              ← settings.yaml + config_loader.py
├── core/                ← event_bus, state_manager, thread_manager, watchdog, logger
├── audio/               ← audio_capture, vad_processor (Silero VAD)
├── transcription/       ← whisper_engine, transcription_worker (Groq + local fallback)
├── llm/                 ← llm_router, gemini_client, groq_client, ollama_client, prompt_builder
├── rag/                 ← document_loader, embedding_store, context_builder
├── notifications/       ← telegram_notifier
├── ui/                  ← overlay_window, gui_dashboard, tray_manager, hotkeys
├── utils/               ← retry, safe_thread, crash_guard
├── build/               ← build_exe.py, build_with_venv.bat
├── interview_docs/      ← place your PDFs here
└── logs/                ← interview_log.txt, crash_debug.log
```

## LLM Backends

| Backend | Mode   | Notes |
|---------|--------|-------|
| Groq    | `groq`   | ~500 tok/s, free tier, LLaMA 3.3 70B |
| Gemini  | `gemini` | gemini-2.0-flash primary |
| Ollama  | `ollama` | Local, no API key needed |
| Auto    | `auto`   | Groq→Gemini rotation with fallback *(default)* |

## Hotkeys
| Shortcut | Action |
|----------|--------|
| `Ctrl+H` | Hide/show overlay |
| `Ctrl+Q` | Quit |

## Build as `.exe`
```bat
build\build_with_venv.bat
```
Output: `dist/InterviewAssistant.exe`
