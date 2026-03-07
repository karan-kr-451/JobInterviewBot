"""
main.py - Interview Assistant entry point (modular).

Thread architecture:
  main          - starts all threads, then calls run_stream_with_restart()
  overlay       - Win32 message loop (daemon)
  tg-sender     - drains Telegram queue (daemon)
  tg-commands   - polls Telegram for commands (daemon)
  whisper-final - transcribes complete utterances (daemon)
  llm-worker    - LLM streaming worker (daemon)
  vad-loop      - VAD loop, started inside run_stream_with_restart (daemon)
"""

import sys

# -- NOCONSOLE SAFETY ---------------------------------------------------------
import os as _os
if sys.stdout is None:
    sys.stdout = open(_os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(_os.devnull, "w", encoding="utf-8", errors="replace")

try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# -- CRASH FIX A: disable tqdm GC monitor --------------------------------------
# ROOT CAUSE: tqdm's background monitor thread holds weak references that can
# trigger GC during C-extension calls -> access violation. Disable completely.
try:
    import tqdm
    import tqdm.std
    tqdm.tqdm.monitor_interval = 0
    tqdm.std.TRLock = None
    # Force-stop any existing monitor instance
    try:
        import tqdm._monitor as _tmon
        inst = getattr(_tmon.TMonitor, "_instance", None)
        if inst is not None:
            if hasattr(inst, "exit_event"):
                inst.exit_event.set()
            if hasattr(inst, "join"):
                try:
                    inst.join(timeout=0.5)
                except Exception:
                    pass
            _tmon.TMonitor._instance = None
    except Exception:
        pass
    # Monkey-patch to prevent re-creation
    try:
        import tqdm._monitor as _tmon
        _tmon.TMonitor.__init__ = lambda self, *args, **kwargs: None
    except Exception:
        pass
except Exception:
    pass

# -- CRASH FIX A: Initialize comprehensive crash prevention -------------------
from core.crash_prevention import initialize_crash_prevention
initialize_crash_prevention()

# -- SESSION GUARDIAN: Zero-crash guarantee for entire session -----------------
from core.session_guardian import (
    install_global_exception_handlers,
    register_component,
    print_session_summary
)
import atexit
atexit.register(print_session_summary)

# -- CRASH FIX B: pre-import urllib3 submodules (redundant but kept for safety) --
try:
    import urllib3, urllib3.response, urllib3.connection        # noqa: E401, F401
    import urllib3.connectionpool, urllib3.poolmanager          # noqa: E401, F401
    import urllib3.util.retry, urllib3.util.timeout             # noqa: E401, F401
    import requests, requests.adapters, requests.sessions      # noqa: E401, F401
except Exception:
    pass

# -- CRASH FIX C: pre-import huggingface_hub (redundant but kept for safety) --
try:
    import huggingface_hub                                     # noqa: F401
    import huggingface_hub._space_api                          # noqa: F401
    import huggingface_hub._jobs_api                           # noqa: F401
    import huggingface_hub.hf_api                              # noqa: F401
    import huggingface_hub._snapshot_download                  # noqa: F401
except Exception:
    pass

# -- Crash protection ----------------------------------------------------------
import faulthandler
import atexit
import time
import os
import threading
import traceback

_CRASH_LOG = "crash.log"

try:
    _crash_file = open(_CRASH_LOG, "a", encoding="utf-8", errors="replace")
    faulthandler.enable(file=_crash_file)
    print(f"[crash guard] faulthandler active -> {_CRASH_LOG}")
except Exception as _e:
    print(f"[crash guard] faulthandler failed: {_e}")
    _crash_file = None


def _write_crash(header: str, text: str):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line  = f"\n[{stamp}] {header}\n{text}\n{'='*60}\n"
    try:
        with open(_CRASH_LOG, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
    except Exception:
        pass
    print(line, file=sys.stderr)


def _python_excepthook(exc_type, exc_value, exc_tb):
    import traceback as _tb
    _write_crash(
        f"UNCAUGHT EXCEPTION in main thread: {exc_type.__name__}",
        "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _python_excepthook


def _thread_excepthook(args):
    import traceback as _tb
    name = getattr(args.thread, "name", "unknown")
    _write_crash(
        f"UNCAUGHT EXCEPTION in thread '{name}': {args.exc_type.__name__}",
        "".join(_tb.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    )

threading.excepthook = _thread_excepthook


def _atexit_log():
    _write_crash("PROCESS EXIT", "Python process exited normally via atexit.")

def _atexit_cleanup():
    """Clean shutdown of all threads and resources before process exit."""
    try:
        # Stop audio stream first
        from audio_pipeline import audio_queue
        try:
            # Signal stream shutdown by clearing queue
            # Drain stale audio using deque.clear()
            try:
                from audio.capture import audio_queue as _aq
                drained = len(_aq)
                _aq.clear()  # Atomic operation for deque
                if drained:
                    print(f"  [drained {drained} stale audio chunks after Gemini generation]")
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass
    
    # Give threads time to clean up
    time.sleep(0.2)

atexit.register(_atexit_cleanup)
atexit.register(_atexit_log)

_original_sys_exit = sys.exit

def _traced_sys_exit(code=0):
    import traceback as _tb
    stack = ''.join(_tb.format_stack()[:-1])
    _write_crash(
        f"sys.exit({code}) called",
        f"Exit code: {code}\n\nCall stack at exit:\n{stack}"
    )
    _original_sys_exit(code)

sys.exit = _traced_sys_exit

# -- Module imports (new modular packages) -------------------------------------

from config import DEVICE_INDEX, LLM_BACKEND                                    # noqa: E402

from ui.overlay import Win32Overlay                                              # noqa: E402
from audio import load_vad, list_audio_devices, run_stream_with_restart          # noqa: E402
from audio import VAD_AVAILABLE, SD_AVAILABLE                                    # noqa: E402
from transcription import load_whisper, start_workers, WHISPER_AVAILABLE         # noqa: E402
from transcription import check_groq_whisper                                     # noqa: E402
from llm import (                                                                # noqa: E402
    configure_backends, load_documents, make_llm_worker, check_ollama,
)


def main():
    # -- System Tray + Setup UI -------------------------------------------------
    # Setup ALWAYS opens first - user must click "Save & Launch" to proceed.
    # This ensures resume, job details, and API keys are reviewed before each run.
    force_setup    = "--setup" in sys.argv
    pipeline_event = threading.Event()

    try:
        from ui.tray import create_tray_app, run_setup

        if force_setup:
            launched = run_setup(force=True)
            if not launched:
                print("Setup closed without launching - exiting.")
                sys.exit(0)
        else:
            tray = create_tray_app(
                on_launch_pipeline=lambda: pipeline_event.set(),
                on_quit=lambda: sys.exit(0),
            )
            tray.start()

            # Always wait for user to configure and click "Save & Launch"
            print("Setup window opened - configure and click 'Save & Launch' to start...")
            if not pipeline_event.wait(timeout=1800):  # 30 min max
                print("Setup timed out - exiting.")
                sys.exit(0)

    except Exception as e:
        print(f"[Tray/Setup] {e} - continuing without tray")

    # Re-import config values that may have changed from setup
    import importlib
    import config as _cfg
    importlib.reload(_cfg)
    from config import DEVICE_INDEX as _DEVICE_INDEX

    print("\n" + "=" * 60)
    print("SYSTEM AUDIO INTERVIEW ASSISTANT")
    print("=" * 60)

    # -- Overlay ----------------------------------------------------------------
    overlay = Win32Overlay()
    overlay.start()

    try:
        tray._overlay = overlay
    except NameError:
        pass

    # -- Audio device list ------------------------------------------------------
    list_audio_devices()

    # -- Groq Whisper (cloud transcription - faster & more accurate) ---------
    groq_whisper_ok = check_groq_whisper()

    # -- Dependency checks ------------------------------------------------------
    errors = []
    if not SD_AVAILABLE:
        errors.append("sounddevice")
    if not WHISPER_AVAILABLE and not groq_whisper_ok:
        errors.append("faster-whisper (or set GROQ_API_KEY for cloud transcription)")
    if errors:
        print(f"ERROR: Missing: {', '.join(errors)}")
        print("   pip install sounddevice faster-whisper")
        sys.exit(1)

    # -- Model loading ----------------------------------------------------------
    # Smart loading: Skip local Whisper if Groq API is available
    print("Loading models...")
    
    # Always load VAD (lightweight, needed for speech detection)
    if not load_vad(lazy=True, force=False):
        print("WARNING: VAD unavailable - continuing with RMS-only detection")

    # Smart Whisper loading: SKIP if Groq is available (saves 500 MB RAM)
    if groq_whisper_ok:
        print("Transcription: Groq Whisper API (cloud)")
        print("[SKIP] Skipping local Whisper model (not needed with Groq)")
        # DON'T load local Whisper - saves memory and startup time!
    else:
        print("Transcription: local Whisper (set GROQ_API_KEY for faster cloud transcription)")
        if not load_whisper(lazy=False, force=False):  # blocking load if it's the only option
            print("ERROR: Whisper load failed and no Groq API key")
            sys.exit(1)

    if not configure_backends():
        print("WARNING: No LLM backend configured - check API keys")

    # -- LLM backend selection -------------------------------------------------
    # Only check Ollama if needed (avoid timeout)
    ollama_ok = False
    if LLM_BACKEND in ("ollama", "auto"):
        ollama_ok = check_ollama()
    
    if LLM_BACKEND == "ollama" and not ollama_ok:
        print("ERROR: LLM_BACKEND='ollama' but Ollama is not running.")
        print("   Start it with: ollama serve")
        print("   Or set LLM_BACKEND='auto' in config.py to fall back to Gemini")
        sys.exit(1)

    # Determine effective backend for display
    if LLM_BACKEND == "ollama":
        effective = "OLLAMA"
    elif LLM_BACKEND == "groq":
        effective = "GROQ"
    elif LLM_BACKEND == "gemini":
        effective = "GEMINI"
    else:  # auto mode
        backends = []
        if ollama_ok:
            backends.append("OLLAMA")
        from llm.groq_stream import GROQ_AVAILABLE
        if GROQ_AVAILABLE:
            backends.append("GROQ")
        if GEMINI_API_KEY:
            backends.append("GEMINI")
        effective = " + ".join(backends) if backends else "NONE"
    
    print(f"LLM backend: {effective}" + 
          (f" (rotating)" if LLM_BACKEND == "auto" and "+" in effective else ""))

    # -- Ollama warmup ---------------------------------------------------------
    if effective == "ollama":
        from llm.ollama_warmup import warmup_ollama
        warmup_ollama(block=False)

    # -- Documents --------------------------------------------------------------
    docs = load_documents()
    print(f"Resume: {'OK' if docs['resume'].strip() else 'Not found'} | "
          f"Projects: {'OK' if docs['projects'].strip() else 'Not found'}")
    
    # Generate reasoning-backed summary once indexed
    from llm.documents import summarize_candidate
    print("[GENERATING] Generating professional persona from documents...")
    docs["candidate_summary"] = summarize_candidate(docs)
    print(f"[OK] Persona: {docs['candidate_summary'][:80]}...")

    # -- Shared state -----------------------------------------------------------
    interview_history: list      = []
    history_lock: threading.Lock = threading.Lock()

    # -- Telegram (disabled temporarily) ----------------------------------------
    class DummyNotifier:
        def send_status(self, msg): pass
        def send_qa(self, q, r): pass
        def send_async(self, q, r): pass
        def send_message(self, msg): pass
    notifier = DummyNotifier()
    print("[SKIP] Telegram disabled (temporary)")

    # -- Pipeline workers -------------------------------------------------------
    start_workers(docs)
    llm_thread = make_llm_worker(interview_history, history_lock, docs, notifier, overlay)
    llm_thread.start()

    # -- Thread health monitor --------------------------------------------------
    _critical_threads: list = []

    def _health_monitor():
        time.sleep(5)
        while True:
            time.sleep(10)
            for t in _critical_threads:
                if not t.is_alive():
                    print(
                        f"\n{'!'*60}\n"
                        f"CRITICAL: Thread '{t.name}' has died!\n"
                        f"Check gemini_crash.log for details.\n"
                        f"{'!'*60}\n"
                    )
                    try:
                        with open("gemini_crash.log", "a", encoding="utf-8") as cf:
                            cf.write(
                                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                                f"Thread '{t.name}' found dead by health monitor\n"
                            )
                    except Exception:
                        pass

    threading.Thread(target=_health_monitor, daemon=True, name="health-monitor").start()
    _critical_threads.append(llm_thread)

    # -- Device check -----------------------------------------------------------
    from config import DEVICE_INDEX
    if DEVICE_INDEX is None:
        print("\nWARNING: DEVICE_INDEX is None - using default mic")
        time.sleep(2)
    else:
        print(f"Audio device ID: {DEVICE_INDEX}")

    print("\nAll threads running.")
    print("   Tray icon -> right-click for Settings / Show Overlay / Quit")
    print("   Pipeline: Audio -> VAD -> Whisper -> LLM -> Overlay")
    print("   Overlay hotkeys (Ctrl):  H=hide  Q=quit  F=fullscreen  M=minimize")
    print("                              =font   ->=nudge  PgUp/Dn=scroll\n")

    # -- Audio stream (with auto-restart on error) ------------------------------
    try:
        run_stream_with_restart(overlay=overlay, max_restarts=999)

    except KeyboardInterrupt:
        print("\n\n Shutting down...")
        try:
            notifier.send_status("  Stopped")
        except (KeyboardInterrupt, Exception):
            pass
        try:
            overlay.shutdown()
        except Exception:
            pass
        sys.exit(0)

    except Exception as e:
        print(f"\n Fatal stream error: {e}")
        traceback.print_exc()

    print("\n[WARN] Audio stream loop exited - workers still running. Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n Shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as _top_e:
        import traceback as _tb
        _write_crash(
            f"UNHANDLED EXCEPTION escaping main(): {type(_top_e).__name__}",
            _tb.format_exc()
        )
        raise
