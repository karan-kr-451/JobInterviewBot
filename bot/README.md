# Interview Assistant

Real-time AI assistant for technical interviews with zero-crash guarantee.

## Quick Start

```bash
# Activate virtual environment
.venv\Scripts\activate

# Run the application
python main_gui.py
```

## Features

- Real-time audio capture and transcription
- AI-powered interview assistance
- Transparent overlay window
- System tray integration
- Zero-crash guarantee (enterprise-grade protection)

## Requirements

- Python 3.12+
- Virtual environment (.venv)
- API keys (Groq or Gemini)
- Audio device (Stereo Mix or Virtual Audio Cable)

## Configuration

Edit `.env` file:
```env
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional
DEVICE_INDEX=1
```

## Build Executable

```bash
build_with_venv.bat
```

Output: `dist\InterviewAssistant.exe`

## Exit

- Click Exit in GUI
- Press Ctrl+Q in overlay
- Right-click tray → Exit
- Press Ctrl+C in console

## Support

Check `HOW_TO_RUN.md` for detailed instructions.

---

**Status**: Production Ready ✅  
**Zero-Crash Guarantee**: Active  
**Version**: 3.0
