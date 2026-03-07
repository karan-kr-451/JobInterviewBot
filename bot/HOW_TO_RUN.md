# How to Run Interview Assistant

## 🚀 Quick Run Commands

### Option 1: GUI Mode (Recommended)
```bash
python main_gui.py
```
**Best for**: Interactive use with visual interface

### Option 2: Console Mode
```bash
python main.py
```
**Best for**: Headless/server deployment

### Option 3: Windows Batch File
```bash
launch_gui.bat
```
**Best for**: Windows users (double-click to run)

### Option 4: Built Executable
```bash
dist\InterviewAssistant.exe
```
**Best for**: Distribution without Python installed

## 📋 Prerequisites

### 1. Python Environment
```bash
# Check Python version (requires 3.12+)
python --version

# Activate virtual environment
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create `.env` file with:
```env
# Required: At least one LLM backend
GROQ_API_KEY=your_groq_key_here
# OR
GEMINI_API_KEY=your_gemini_key_here

# Optional: Telegram notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Optional: Audio device
DEVICE_INDEX=1  # Usually Stereo Mix
```

## 🎯 Step-by-Step Guide

### Step 1: First Time Setup
```bash
# 1. Clone/download the project
cd InterviewBot/bot

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
.venv\Scripts\activate  # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file (copy from .env.example if available)
# Add your API keys

# 6. Run the application
python main_gui.py
```

### Step 2: Configure in GUI
1. Click **Settings** tab
2. Add API keys (Groq recommended)
3. Select audio device (usually "Stereo Mix")
4. Upload your resume/documents
5. Click **Save Settings**

### Step 3: Start Assistant
1. Click **Start** button
2. Wait for "Listening..." status
3. Start your interview!

## 🔧 Advanced Run Options

### Run with Crash Detection
```bash
python crash_detector.py
```
This wraps the application with crash monitoring and logging.

### Run with Custom Config
```bash
# Edit config.yaml first, then:
python main_gui.py
```

### Run in Debug Mode
```bash
# Set environment variable
set DEBUG=1  # Windows
export DEBUG=1  # Linux/Mac

python main_gui.py
```

### Run Specific Components

**Check Audio Devices:**
```bash
python check_audio_devices.py
```

**Test Audio Capture:**
```bash
python test_audio_capture.py
```

**Test Stereo Mix:**
```bash
python test_stereo_mix.py
```

## 🏗️ Build Executable

### Build Single EXE File
```bash
# Option 1: Use batch file
build_with_venv.bat

# Option 2: Direct command
python build_exe.py
```

Output: `dist/InterviewAssistant.exe`

### Build Options
Edit `build_exe.py` to customize:
- Icon file
- Console window (show/hide)
- One-file vs one-folder
- Included data files

## 🐛 Troubleshooting

### Issue: "Module not found"
**Solution:**
```bash
# Make sure virtual environment is activated
.venv\Scripts\activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: "Audio device not found"
**Solution:**
```bash
# List available devices
python check_audio_devices.py

# Enable Stereo Mix in Windows:
# Right-click speaker icon → Sounds → Recording tab
# Right-click empty space → Show Disabled Devices
# Enable "Stereo Mix"
```

### Issue: "API key invalid"
**Solution:**
1. Check `.env` file has correct keys
2. Verify keys at:
   - Groq: https://console.groq.com/keys
   - Gemini: https://makersuite.google.com/app/apikey

### Issue: "Import errors"
**Solution:**
```bash
# Use Python 3.12 from virtual environment
.venv\Scripts\python.exe main_gui.py
```

## 📊 Run Modes Comparison

| Mode | Command | GUI | Console | Best For |
|------|---------|-----|---------|----------|
| GUI | `python main_gui.py` | ✅ | ✅ | Interactive use |
| Console | `python main.py` | ❌ | ✅ | Server/headless |
| Batch | `launch_gui.bat` | ✅ | ✅ | Windows users |
| EXE | `dist\InterviewAssistant.exe` | ✅ | ❌ | Distribution |

## 🎮 Keyboard Shortcuts (Overlay)

When overlay is active (Ctrl must be held):
- `Ctrl+H` - Toggle hide/show overlay
- `Ctrl+Q` - Quit application
- `Ctrl+F` - Toggle fullscreen
- `Ctrl+M` - Minimize to tray
- `Ctrl+↑/↓` - Adjust font size
- `Ctrl+←/→` - Move overlay left/right
- `PgUp/PgDn` - Scroll answer
- `Home/End` - Scroll to top/bottom

## 📱 System Tray

When running, the app appears in system tray:
- **Left-click** - Show/hide main window
- **Right-click** - Menu:
  - Start/Stop Assistant
  - Settings
  - Exit

## 🔄 Auto-Start (Optional)

### Windows Startup
1. Press `Win+R`
2. Type `shell:startup`
3. Create shortcut to `launch_gui.bat`

### Task Scheduler
```bash
# Create scheduled task to run at login
schtasks /create /tn "InterviewAssistant" /tr "C:\path\to\launch_gui.bat" /sc onlogon
```

## 📝 Configuration Files

### .env (Environment Variables)
```env
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
DEVICE_INDEX=1
LLM_BACKEND=auto
```

### config.yaml (Application Settings)
```yaml
llm_backend: auto
job_title: "Software Engineer"
job_description: "..."
device_index: 1
```

### settings.json (GUI Settings)
```json
{
  "window_size": [1200, 800],
  "theme": "light",
  "auto_start": false
}
```

## 🚦 Status Indicators

### Main Window
- 🟢 **Green** - Running normally
- 🟡 **Yellow** - Initializing
- 🔴 **Red** - Error/stopped

### Overlay
- 🎧 **Listening...** - Ready for speech
- 🔴 **Recording** - Capturing audio
- ⚡ **Generating...** - Processing response
- ✓ **Done** - Response complete

## 💡 Tips

1. **First Run**: Use GUI mode to configure everything
2. **Production**: Build EXE for best performance
3. **Development**: Use console mode for debugging
4. **Testing**: Use crash_detector.py wrapper

## 📞 Support

If you encounter issues:
1. Check `crash_debug_*.log` files
2. Review `TROUBLESHOOTING.md`
3. Check `QUICK_START.md`
4. Review error messages in console

## 🎯 Quick Commands Reference

```bash
# Run GUI
python main_gui.py

# Run console
python main.py

# Check audio
python check_audio_devices.py

# Build EXE
build_with_venv.bat

# Run with crash detection
python crash_detector.py

# Test audio
python test_audio_capture.py
```

---

**Recommended**: Start with `python main_gui.py` for the best experience!
