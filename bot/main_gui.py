"""
main_gui.py - Main entry point with professional GUI.

Launches the professional UI instead of console-only mode.
Integrates with existing pipeline architecture.
"""

import sys
import os
import threading
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize crash prevention FIRST
from core.crash_prevention import initialize_crash_prevention
initialize_crash_prevention()

# Initialize session guardian for zero-crash guarantee
from core.session_guardian import (
    install_global_exception_handlers,
    register_component,
    print_session_summary
)
import atexit
atexit.register(print_session_summary)

# CRITICAL: Pre-import all heavy modules in main thread BEFORE starting workers
# This prevents threading issues during module initialization when GC is disabled
def _preload_modules():
    """Pre-import all heavy modules to avoid threading issues during lazy imports."""
    try:
        # Import all modules that might be lazily loaded by workers
        import numpy
        import requests
        import sounddevice
        
        # Import all our modules
        import audio.capture
        import audio.vad
        import audio.filters
        import transcription.worker
        import transcription.groq_whisper
        import llm.router
        import llm.worker
        import llm.classifier
        import llm.prompt_builder
        import llm.documents
        import llm.groq_stream
        import llm.gemini_stream
        import llm.ollama_stream
        
        # Import config modules
        import config.audio
        import config.groq
        import config.gemini
        import config.ollama
        
        print("[PRELOAD] All modules pre-imported successfully")
    except Exception as e:
        print(f"[PRELOAD] Warning during module preload: {e}")

# Pre-load modules immediately
_preload_modules()

from ui.main_window import MainWindow


class InterviewAssistantGUI:
    """Main application controller with GUI."""
    
    def __init__(self):
        self.window = None
        self.tray = None
        self.overlay = None
        self.pipeline_thread = None
        self.pipeline_stop_event = threading.Event()
        self.is_running = False
    
    def start(self):
        """Start the application."""
        # Create main window
        self.window = MainWindow(
            on_start=self._start_pipeline,
            on_stop=self._stop_pipeline
            # on_settings integrated into tabs
        )
        
        # Create system tray (optional - graceful fallback)
        try:
            from ui.tray import TrayApp
            
            # Create tray with callback to switch dashboard tab
            self.tray = TrayApp(
                on_launch_pipeline=self._start_pipeline,
                on_quit=self._quit,
                on_settings=self.window._open_settings,
                overlay_ref=None  # Will be set when pipeline starts
            )
            
            # Monkey-patch to disable auto-open in GUI mode
            self.tray._auto_open_settings = False
            
            self.tray.start()
            self.window.log("[OK] System tray icon created")
        except Exception as e:
            self.window.log(f"[WARN] System tray unavailable: {e}")
        
        # Log startup
        self.window.log("=" * 60)
        self.window.log("Interview Assistant - Professional GUI")
        self.window.log("=" * 60)
        self.window.log("Ready to start interview assistant")
        self.window.log("Click 'Start' or configure settings in the Settings tab")
        
        # Run main loop
        self.window.run()
    
    def _start_pipeline(self):
        """Start the interview assistant pipeline."""
        if self.is_running:
            self.window.log("[WARN] Pipeline already running")
            return
        
        self.window.log("=" * 60)
        self.window.log("Starting Interview Assistant Pipeline")
        self.window.log("=" * 60)
        self.window.update_status("Starting pipeline...")
        
        def run_pipeline():
            try:
                self.is_running = True
                self.pipeline_stop_event.clear()
                
                # Reload configuration to pick up changes from settings UI
                self.window.log("Reloading configuration...")
                import importlib
                import sys
                
                # Reload all config modules
                config_modules = [m for m in sys.modules.keys() if m.startswith('config')]
                for module_name in config_modules:
                    try:
                        importlib.reload(sys.modules[module_name])
                    except Exception:
                        pass
                
                # Import configuration (now reloaded)
                from config import DEVICE_INDEX, LLM_BACKEND
                from config.groq import GROQ_API_KEY
                from config.gemini import GEMINI_API_KEY
                
                self.window.log("[OK] Configuration reloaded")
                self.window.log(f"  - Audio device: {DEVICE_INDEX if DEVICE_INDEX is not None else 'default'}")
                self.window.log(f"  - LLM backend: {LLM_BACKEND}")
                self.window.log(f"  - Groq API: {'[OK] Set' if GROQ_API_KEY else '[ERROR] Not set'}")
                self.window.log(f"  - Gemini API: {'[OK] Set' if GEMINI_API_KEY else '[ERROR] Not set'}")
                
                # Initialize overlay
                from ui.overlay import Win32Overlay
                self.overlay = Win32Overlay()
                self.overlay.start()
                self.window.log("[OK] Overlay window started")
                
                # Update tray with overlay reference
                if self.tray:
                    try:
                        self.tray._overlay = self.overlay
                    except Exception:
                        pass
                
                # Check dependencies
                from audio import VAD_AVAILABLE, SD_AVAILABLE, list_audio_devices
                from transcription import WHISPER_AVAILABLE, check_groq_whisper
                
                self.window.log("Checking dependencies...")
                list_audio_devices()
                
                groq_whisper_ok = check_groq_whisper()
                
                errors = []
                if not SD_AVAILABLE:
                    errors.append("sounddevice")
                if not WHISPER_AVAILABLE and not groq_whisper_ok:
                    errors.append("faster-whisper or GROQ_API_KEY")
                
                if errors:
                    error_msg = f"Missing dependencies: {', '.join(errors)}"
                    self.window.log(f"[ERROR] {error_msg}")
                    self.window.update_status(f"Error: {error_msg}")
                    return
                
                self.window.log("[OK] All dependencies available")
                
                # Initialize enterprise crash prevention (monitoring, etc.)
                from core.enterprise_crash_prevention import (
                    initialize_enterprise_crash_prevention, health_checker
                )
                initialize_enterprise_crash_prevention()
                
                # Register components for health monitoring (pings)
                health_checker.register("vad-loop", interval=5.0)  # Check every 5s
                health_checker.register("transcription", interval=30.0)
                health_checker.register("llm", interval=60.0)
                
                # Load models (smart loading based on availability)
                self.window.log("Loading models...")
                from audio import load_vad
                from transcription import load_whisper
                from llm import configure_backends, load_documents, check_ollama
                
                # Always load VAD (lightweight, needed for speech detection)
                if not load_vad(lazy=True, force=False):
                    self.window.log("[WARN] VAD unavailable - using RMS-only detection")
                else:
                    self.window.log("[OK] VAD loading in background")
                
                # Smart Whisper loading: SKIP if Groq is available
                if groq_whisper_ok:
                    self.window.log("[OK] Groq Whisper API available (primary)")
                    self.window.log("[SKIP] Skipping local Whisper (not needed with Groq)")
                    # DON'T load local Whisper - saves 500 MB RAM!
                else:
                    self.window.log("Loading local Whisper (no Groq API)...")
                    if not load_whisper(lazy=False, force=False):  # blocking if only option
                        self.window.log("[ERROR] Whisper load failed")
                        self.window.update_status("Error: Whisper load failed")
                        return
                    self.window.log("[OK] Local Whisper loaded")
                
                if not configure_backends():
                    self.window.log("[WARN] No LLM backend configured - check API keys")
                else:
                    self.window.log("[OK] LLM backend configured")
                
                # Check Ollama only if needed
                ollama_ok = False
                if LLM_BACKEND in ("ollama", "auto"):
                    ollama_ok = check_ollama()
                
                # Check Groq availability
                groq_ok = False
                if LLM_BACKEND in ("groq", "auto"):
                    from llm.groq_stream import GROQ_AVAILABLE
                    groq_ok = GROQ_AVAILABLE
                
                if LLM_BACKEND == "ollama" and not ollama_ok:
                    self.window.log("[ERROR] Ollama not running (required for LLM_BACKEND='ollama')")
                    self.window.update_status("Error: Ollama not running")
                    return
                
                # Determine effective backend for display
                if LLM_BACKEND == "ollama":
                    effective = "OLLAMA"
                elif LLM_BACKEND == "groq":
                    effective = "GROQ"
                elif LLM_BACKEND == "gemini":
                    effective = "GEMINI"
                else:  # auto mode
                    backends = []
                    if groq_ok:
                        backends.append("GROQ")
                    if GEMINI_API_KEY:
                        backends.append("GEMINI")
                    if ollama_ok:
                        backends.append("OLLAMA")
                    effective = " + ".join(backends) if backends else "NONE"
                
                self.window.log(f"[OK] LLM backend: {effective}" + 
                               (f" (rotating)" if LLM_BACKEND == "auto" and len(backends) > 1 else ""))
                
                # Ollama warmup
                if effective == "ollama":
                    self.window.log("Warming up Ollama...")
                    from llm.ollama_warmup import warmup_ollama
                    warmup_ollama(block=False)
                    self.window.log("[OK] Ollama warmup started")
                
                # Load documents
                self.window.log("Loading documents...")
                docs = load_documents()
                self.window.log(f"[OK] Resume: {'OK' if docs['resume'].strip() else 'Not found'}")
                self.window.log(f"[OK] Projects: {'OK' if docs['projects'].strip() else 'Not found'}")
                
                # Generate candidate summary
                from llm.documents import summarize_candidate
                self.window.log("Generating professional persona...")
                docs["candidate_summary"] = summarize_candidate(docs)
                self.window.log(f"[OK] Persona: {docs['candidate_summary'][:60]}...")
                
                # Initialize shared state
                interview_history = []
                history_lock = threading.Lock()
                
                # Telegram disabled temporarily
                class DummyNotifier:
                    def send_status(self, msg): pass
                    def send_qa(self, q, r): pass
                    def send_async(self, q, r): pass
                    def send_message(self, msg): pass
                notifier = DummyNotifier()
                self.window.log("[SKIP] Telegram disabled (temporary)")
                
                # Start workers
                from transcription import start_workers
                from llm import make_llm_worker
                
                start_workers(docs)
                self.window.log("[OK] Transcription workers started")
                
                llm_thread = make_llm_worker(interview_history, history_lock, docs, notifier, self.overlay)
                llm_thread.start()
                self.window.log("[OK] LLM worker started")
                
                self.window.log("=" * 60)
                self.window.log("[OK] Pipeline started successfully")
                self.window.log("=" * 60)
                self.window.update_status("Pipeline running")
                
                # Start audio stream
                from audio import run_stream_with_restart
                self.window.log("Starting audio stream...")
                
                # Run stream (blocks until stopped)
                run_stream_with_restart(overlay=self.overlay, max_restarts=999)
                
            except KeyboardInterrupt:
                self.window.log("Pipeline interrupted by user")
            except Exception as e:
                self.window.log(f"[ERROR] Pipeline error: {e}")
                self.window.update_status(f"Error: {e}")
                import traceback
                self.window.log(traceback.format_exc())
            finally:
                self.is_running = False
                self.window.update_status("Pipeline stopped")
                self.window.log("Pipeline stopped")
                
                # Cleanup
                if self.overlay:
                    try:
                        self.overlay.shutdown()
                    except Exception:
                        pass
        
        self.pipeline_thread = threading.Thread(target=run_pipeline, daemon=True, name="pipeline")
        self.pipeline_thread.start()
    
    def _stop_pipeline(self):
        """Stop the interview assistant pipeline."""
        if not self.is_running:
            self.window.log("[WARN] Pipeline not running")
            return
        
        self.window.log("Stopping pipeline...")
        self.window.update_status("Stopping...")
        
        # Signal stop
        self.pipeline_stop_event.set()
        self.is_running = False
        
        # Shutdown overlay
        if self.overlay:
            try:
                self.overlay.shutdown()
            except Exception:
                pass
        
        self.window.log("[OK] Pipeline stopped")
        self.window.update_status("Stopped")
    
    def _quit(self):
        """Quit the application."""
        self.window.log("Quitting application...")
        
        if self.is_running:
            self._stop_pipeline()
            time.sleep(0.5)
        
        sys.exit(0)


def main():
    """Main entry point."""
    print("=" * 60)
    print("Interview Assistant - Professional GUI")
    print("=" * 60)
    print("Starting...")
    
    try:
        app = InterviewAssistantGUI()
        app.start()
    except KeyboardInterrupt:
        print("\nShutdown requested")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
