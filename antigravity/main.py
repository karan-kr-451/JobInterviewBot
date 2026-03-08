"""
main.py - Interview Assistant entry point (console mode).

Thread architecture:
  Main Thread        – bootstraps everything, then blocks on audio stream
  gui-dashboard      – setup window (waits for "Save & Launch")
  tray               – system tray icon (daemon)
  overlay            – transparent Win32 overlay (daemon)
  vad-loop           – voice activity detection (daemon)
  whisper-final      – transcription worker (daemon)
  llm-worker         – LLM streaming worker (daemon)
  tg-sender          – Telegram queue drainer (daemon)
  watchdog           – audio/LLM hang monitor (daemon)
  health-monitor     – thread health checker (daemon)
"""

from __future__ import annotations

import atexit
import faulthandler
import os
import sys
import threading
import time
import traceback

# ── Stdout safety (when launched without console e.g. PyInstaller --noconsole) ──
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
for _s in (sys.stdout, sys.stderr):
    try:
        if _s.encoding and _s.encoding.lower() != "utf-8":
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Disable tqdm GC monitor BEFORE any other imports ─────────────────────────
from utils.crash_guard import disable_tqdm_monitor, gc_safe_http
disable_tqdm_monitor()

# ── Pre-warm urllib3 / requests (avoids lazy-import races in C callbacks) ─────
try:
    import urllib3, urllib3.response, urllib3.connection
    import urllib3.connectionpool, urllib3.poolmanager
    import urllib3.util.retry, urllib3.util.timeout
    import requests, requests.adapters, requests.sessions
except Exception:
    pass

# ── Pre-warm huggingface_hub ──────────────────────────────────────────────────
try:
    import huggingface_hub
    import huggingface_hub.hf_api
except Exception:
    pass

# ── Crash guard ───────────────────────────────────────────────────────────────
from pathlib import Path
_BASE = Path(__file__).resolve().parent
_CRASH_LOG = _BASE / "logs" / "crash_debug.log"
_CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)

try:
    _crash_fh = _CRASH_LOG.open("a", encoding="utf-8", errors="replace")
    faulthandler.enable(file=_crash_fh)
except Exception:
    pass


def _write_crash(header: str, text: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n[{stamp}] {header}\n{text}\n{'='*60}\n"
    try:
        with _CRASH_LOG.open("a", encoding="utf-8", errors="replace") as f:
            f.write(entry)
    except Exception:
        pass
    print(entry, file=sys.stderr)


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    _write_crash(f"UNCAUGHT EXCEPTION: {exc_type.__name__}",
                 "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args) -> None:
    name = getattr(args.thread, "name", "unknown")
    _write_crash(f"THREAD CRASH '{name}': {args.exc_type.__name__}",
                 "".join(traceback.format_exception(
                     args.exc_type, args.exc_value, args.exc_traceback)))


sys.excepthook          = _excepthook
threading.excepthook    = _thread_excepthook


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    from config.config_loader import load_config
    cfg = load_config()

    # Init structured logger
    from core.logger import init_logging, get_logger
    init_logging(cfg.base_dir, cfg.logging.log_file, cfg.logging.crash_file)
    log = get_logger("main")
    log.info("Interview Assistant starting up…")

    # ── GUI Setup Window (blocks until user clicks "Save & Launch") ───────────
    launch_event = threading.Event()
    from ui.gui_dashboard import GUIDashboard
    dashboard = GUIDashboard(cfg, launch_event)
    dashboard.start()

    print("\n" + "=" * 60)
    print("  INTERVIEW ASSISTANT – Setup window opened")
    print("  Configure your API keys and click 'Save & Launch'")
    print("=" * 60 + "\n")

    launched = launch_event.wait(timeout=1800)   # 30 min timeout
    if not launched:
        log.error("Setup timed out – exiting")
        sys.exit(0)

    # Reload config after GUI may have updated API keys
    from config.config_loader import load_config as _reload
    cfg = _reload(reload=True)
    log.info("Config reloaded after setup")

    # ── State + registry singletons ───────────────────────────────────────────
    from core.state_manager import get_state
    from core.thread_manager import get_registry
    registry = get_registry()
    state    = get_state()

    state.update(audio_device_idx=cfg.audio.device_index)

    # ── Watchdog ──────────────────────────────────────────────────────────────
    restart_event  = threading.Event()
    from core.watchdog import Watchdog
    watchdog = Watchdog(restart_event)
    watchdog.start()

    # ── Overlay ───────────────────────────────────────────────────────────────
    from ui.overlay_window import OverlayWindow
    overlay = OverlayWindow(cfg.overlay)
    overlay.start()

    # ── Tray icon ─────────────────────────────────────────────────────────────
    from ui.tray_manager import TrayManager
    logo_path = str(_BASE / "interview_bot_logo.png")
    tray = TrayManager(
        on_quit=lambda: sys.exit(0),
        on_show_dashboard=lambda: None,   # Dashboard already open
        on_show_overlay=lambda: None,
        icon_path=logo_path if Path(logo_path).exists() else None,
    )
    tray.start()

    # ── Hotkeys ───────────────────────────────────────────────────────────────
    from ui.hotkeys import HotkeyManager
    hkm = HotkeyManager()
    hkm.register("ctrl+h", overlay.shutdown)
    hkm.register("ctrl+q", lambda: sys.exit(0))
    hkm.start()

    # ── Documents + RAG ───────────────────────────────────────────────────────
    from rag.document_loader import load_documents, summarize_candidate
    from rag.context_builder import ContextBuilder

    log.info("Loading documents from '%s'…", cfg.rag.docs_folder)
    docs = load_documents(
        docs_folder=str(_BASE / cfg.rag.docs_folder),
        job_title=cfg.job.title,
        job_description=cfg.job.description,
    )

    ctx_builder = ContextBuilder.initialise(cfg, str(_BASE / cfg.rag.docs_folder))
    docs["candidate_summary"] = summarize_candidate(docs, ctx_builder._store if ctx_builder._store.is_ready() else None)
    log.info("Persona: %s…", docs["candidate_summary"][:80])

    # ── Audio devices ─────────────────────────────────────────────────────────
    from audio.device_manager import list_devices
    list_devices()

    # ── VAD ───────────────────────────────────────────────────────────────────
    from audio.vad_processor import load_vad
    load_vad(lazy=True)

    # ── Whisper ───────────────────────────────────────────────────────────────
    from audio.audio_capture import SD_AVAILABLE
    if not SD_AVAILABLE:
        log.error("sounddevice not installed – audio pipeline disabled")
        sys.exit(1)

    # ── Transcription queues ──────────────────────────────────────────────────
    from transcription.buffer_manager import make_transcription_queue, make_llm_queue
    tr_queue  = make_transcription_queue(cfg.transcription.final_queue_size)
    llm_queue = make_llm_queue(cfg.transcription.llm_queue_size)

    # ── LLM Router ────────────────────────────────────────────────────────────
    from llm.llm_router import LLMRouter
    router = LLMRouter(cfg.llm, watchdog=watchdog, log_file=cfg.logging.log_file)
    if not router.configure():
        log.warning("No LLM backend available – responses will fail until keys are set")

    # ── Telegram ──────────────────────────────────────────────────────────────
    from notifications.telegram_notifier import create_notifier
    notifier = create_notifier(cfg)

    # ── Shared conversation history ───────────────────────────────────────────
    interview_history: list       = []
    history_lock:   threading.Lock = threading.Lock()

    # ── Worker threads ────────────────────────────────────────────────────────

    # Transcription worker
    from transcription.transcription_worker import TranscriptionWorker
    tr_worker = TranscriptionWorker(
        cfg.transcription,
        groq_api_key=cfg.llm.groq.api_key,
        transcription_queue=tr_queue,
        llm_queue=llm_queue,
        docs=docs,
    )
    registry.start_thread("whisper-final", tr_worker.run)

    # LLM worker
    def _llm_loop():
        """Drain llm_queue; get response for each transcript."""
        import queue as _q
        while True:
            try:
                item = llm_queue.get(timeout=2)
                if item is None:
                    break
                question = item.get("text", "").strip()
                if not question:
                    continue
                router.get_response(
                    question, interview_history, history_lock,
                    docs, overlay, notifier,
                )
            except _q.Empty:
                continue
            except Exception as exc:
                log.error("LLM loop error: %s", exc, exc_info=True)

    registry.start_thread("llm-worker", _llm_loop)

    # Health monitor
    def _health_monitor():
        time.sleep(10)
        while True:
            time.sleep(15)
            dead = registry.health_check()
            for name in dead:
                _write_crash(f"Thread '{name}' found dead by health monitor", "")

    registry.start_thread("health-monitor", _health_monitor)

    # ── Status ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SYSTEM AUDIO INTERVIEW ASSISTANT")
    print(f"  LLM backend: {cfg.llm.backend}")
    print(f"  Audio device: {cfg.audio.device_index}")
    print(f"  Docs: {len(docs.get('resume_files', []))} resume(s), "
          f"{len(docs.get('project_files', []))} project(s)")
    print("  Hotkeys: Ctrl+H=hide  Ctrl+Q=quit")
    print("=" * 60 + "\n")

    overlay.set_status("[LISTEN] Listening…")

    # ── Audio stream (blocks; restarts on error) ──────────────────────────────
    from audio.audio_capture import AudioCapture
    from audio.vad_processor import VADProcessor
    from audio.audio_queue import audio_queue

    capture = AudioCapture(cfg.audio, watchdog=watchdog)

    # Start VAD thread before opening stream
    vad = VADProcessor(cfg.audio, tr_queue, watchdog=watchdog)
    registry.start_thread("vad-loop", vad.run, restart_on_crash=True)

    atexit.register(lambda: registry.stop_all(wait_secs=2))

    try:
        capture.run_with_restart(overlay=overlay, max_restarts=999)
    except KeyboardInterrupt:
        print("\n\nShutting down…")
        try: notifier.stop()
        except Exception: pass
        try: overlay.shutdown()
        except Exception: pass
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as _e:
        _write_crash(f"UNHANDLED EXCEPTION in main(): {type(_e).__name__}", traceback.format_exc())
        raise
