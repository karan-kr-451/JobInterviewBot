"""
build_exe.py - PyInstaller build script for Interview Assistant.

Creates a professional Windows executable with all dependencies bundled.

Usage:
    python build_exe.py

Output:
    dist/InterviewAssistant.exe

Features:
    - Single executable file (--onefile)
    - No console window (--windowed)
    - System tray only (no taskbar icon)
    - All dependencies bundled
    - Optimized for size and performance
"""

import PyInstaller.__main__
import os
import sys
import shutil

# Get absolute paths
script_dir = os.path.dirname(os.path.abspath(__file__))
icon_path = os.path.join(script_dir, "interview_bot_logo.png")
docs_path = os.path.join(script_dir, "interview_docs")

# Check if icon exists
icon_exists = os.path.exists(icon_path)
docs_exists = os.path.exists(docs_path)

# PyInstaller arguments
args = [
    "main_gui.py",                          # Entry point
    
    # Output configuration
    "--name=InterviewAssistant",            # Executable name
    "--onefile",                            # Single executable
    "--windowed",                           # No console window (GUI only)
    "--noconsole",                          # Explicitly no console
    
    # Icon (if available)
    f"--icon={icon_path}" if icon_exists else "",
    
    # Add data files
    f"--add-data={docs_path};interview_docs" if docs_exists else "",
    f"--add-data={icon_path};." if icon_exists else "",
    "--add-data=config;config",
    "--add-data=ui;ui",
    "--add-data=audio;audio",
    "--add-data=transcription;transcription",
    "--add-data=llm;llm",
    "--add-data=notifications;notifications",
    "--add-data=core;core",
    "--add-data=.env;." if os.path.exists(".env") else "",
    "--add-data=config.yaml;." if os.path.exists("config.yaml") else "",
    
    # Hidden imports (modules loaded dynamically)
    "--hidden-import=sounddevice",
    "--hidden-import=faster_whisper",
    "--hidden-import=numpy",
    "--hidden-import=scipy",
    "--hidden-import=scipy.signal",
    "--hidden-import=requests",
    "--hidden-import=google.generativeai",
    "--hidden-import=groq",
    "--hidden-import=telegram",
    "--hidden-import=PIL",
    "--hidden-import=PIL.Image",
    "--hidden-import=PIL.ImageTk",
    "--hidden-import=pystray",
    "--hidden-import=tkinter",
    "--hidden-import=tqdm",
    "--hidden-import=huggingface_hub",
    "--hidden-import=torch",
    "--hidden-import=silero",
    "--hidden-import=yaml",
    "--hidden-import=dotenv",
    "--hidden-import=psutil",
    "--hidden-import=win32gui",
    "--hidden-import=win32con",
    "--hidden-import=win32api",
    "--hidden-import=pywintypes",
    
    # Collect submodules
    "--collect-submodules=torch",
    "--collect-submodules=faster_whisper",
    "--collect-submodules=google.generativeai",
    "--collect-submodules=scipy.signal",
    
    # Exclude unnecessary modules (reduce size)
    "--exclude-module=matplotlib",
    "--exclude-module=pandas",
    "--exclude-module=jupyter",
    "--exclude-module=notebook",
    "--exclude-module=IPython",
    "--exclude-module=pytest",
    
    # Build options
    "--clean",                              # Clean cache before build
    "--noconfirm",                          # Overwrite without asking
    
    # Optimization
    "--optimize=2",                         # Optimize bytecode (level 2)
    
    # Paths
    f"--workpath={os.path.join(script_dir, 'build')}",
    f"--distpath={os.path.join(script_dir, 'dist')}",
    f"--specpath={script_dir}",
]

# Remove empty strings
args = [arg for arg in args if arg]

print("=" * 70)
print("Building Interview Assistant Executable")
print("=" * 70)
print(f"Script directory: {script_dir}")
print(f"Icon: {'Found' if icon_exists else 'Not found (using default)'}")
print(f"Docs folder: {'Found' if docs_exists else 'Not found (will be created)'}")
print(f"Entry point: main_gui.py")
print(f"Output: dist/InterviewAssistant.exe")
print("=" * 70)
print("\nBuild configuration:")
print("  - Single file executable: YES")
print("  - Console window: NO (GUI only)")
print("  - Taskbar icon: NO (system tray only)")
print("  - Optimization: Level 2")
print("=" * 70)

# Run PyInstaller
try:
    print("\nStarting PyInstaller build...")
    print("This may take several minutes...\n")
    
    PyInstaller.__main__.run(args)
    
    print("\n" + "=" * 70)
    print("[OK] Build completed successfully!")
    print("=" * 70)
    
    exe_path = os.path.join(script_dir, 'dist', 'InterviewAssistant.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"Executable: {exe_path}")
        print(f"Size: {size_mb:.1f} MB")
    
    print("\nHow to use:")
    print("  1. Navigate to dist/ folder")
    print("  2. Double-click InterviewAssistant.exe")
    print("  3. Look for the icon in system tray (bottom-right)")
    print("  4. Right-click tray icon to access settings")
    print("  5. Configure API keys and audio device")
    print("  6. Click 'Start' to begin")
    
    print("\nNOTE:")
    print("  - Application runs in system tray only (no taskbar icon)")
    print("  - Window is hidden from screen capture for privacy")
    print("  - First run may take longer (downloading models)")
    print("=" * 70)
    
except Exception as e:
    print("\n" + "=" * 70)
    print("[ERROR] Build failed!")
    print("=" * 70)
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    print("\nTroubleshooting:")
    print("  1. Make sure PyInstaller is installed: pip install pyinstaller")
    print("  2. Check that all dependencies are installed")
    print("  3. Try running: pip install -r requirements.txt")
    print("  4. Close any running instances of the application")
    print("=" * 70)
    sys.exit(1)
