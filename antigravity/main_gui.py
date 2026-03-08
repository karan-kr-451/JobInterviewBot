# main_gui.py — EXACT startup order (do not reorder)

# === PHASE 1: Pre-import protection ===
import gc
gc.disable()
gc.set_threshold(0, 0, 0)

import os
os.makedirs("logs", exist_ok=True)
import faulthandler
_fh_log = open("logs/crash_latest.log", "w", encoding="utf-8")
faulthandler.enable(file=_fh_log)
import sys
import time
import threading

# === PHASE 2: Install crash handlers ===
from antigravity.core.crash_handler import install as install_crash_handler
install_crash_handler()

# === PHASE 3: Load config ===
import logging
from antigravity.utils.logger import init_logging
from antigravity.utils.env_loader import load_env
from antigravity.utils.config_loader import load_config

init_logging(base_dir=".")
load_env(base_dir=".")
config = load_config(base_dir=".")
logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

# === PHASE 4: Validate tech stack ===
from antigravity.core.compat_check import validate_stack
errors = validate_stack()
if errors:
    for e in errors: 
        logging.error("[COMPAT ERROR] %s", e)

# === PHASE 5: Core initialization ===
import collections
import queue
from antigravity.core.gc_guard import start_safe_gc_thread
from antigravity.core.watchdog import Watchdog
from antigravity.core.app_state import get_app_state
from antigravity.transcription.transcript_store import BoundedAudioQueue
from PyQt6.QtWidgets import QApplication

start_safe_gc_thread(config.gc.manual_collect_interval_seconds)

app_state = get_app_state()
watchdog = Watchdog(check_interval=config.watchdog.check_interval_seconds)

audio_queue = BoundedAudioQueue(maxlen=100)
llm_queue   = queue.Queue(maxsize=50)
notif_queue = queue.Queue(maxsize=200)

# Init components
from antigravity.llm.rag.context_retriever import ContextRetriever
rag = ContextRetriever()
rag.load()

from antigravity.core.event_bus import bus, EVT_DOCUMENTS_UPDATED, EVT_TOKEN_USAGE_READY, EVT_CLASSIFICATION_READY
bus.subscribe(EVT_DOCUMENTS_UPDATED, lambda _: rag.load())
bus.subscribe(EVT_TOKEN_USAGE_READY, lambda d: bridge.token_usage.emit(d))
bus.subscribe(EVT_CLASSIFICATION_READY, lambda d: bridge.classification.emit(d))

from antigravity.llm.fallback_chain import FallbackChain
chain = FallbackChain(config.llm, os.environ.get("GROQ_API_KEY", ""), os.environ.get("GEMINI_API_KEY", ""))

from antigravity.audio.capture_worker import CaptureWorker
capture_worker = CaptureWorker(
    device_index=config.audio.device_index,
    audio_queue=audio_queue,
    sample_rate=config.audio.sample_rate,
    channels=config.audio.channels,
    chunk_seconds=config.audio.chunk_seconds,
    vad_threshold=config.audio.vad_threshold
)

from antigravity.transcription.transcription_worker import TranscriptionWorker
stt_worker = TranscriptionWorker(
    audio_queue=audio_queue,
    llm_queue=llm_queue,
    groq_api_key=os.environ.get("GROQ_API_KEY", ""),
    backend=config.transcription.backend,
    sample_rate=config.audio.sample_rate
)

from antigravity.llm.llm_worker import LLMWorker
llm_worker = LLMWorker(
    transcript_queue=llm_queue,
    fallback_chain=chain,
    rag_retriever=rag,
    system_prompt=config.llm.system_prompt
)

from antigravity.notifications.telegram_notifier import TelegramNotifier
telegram_worker = TelegramNotifier(
    notif_queue=notif_queue,
    bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
    enabled=config.notifications.telegram_enabled
)

# Register and start workers
for w in [capture_worker, stt_worker, llm_worker, telegram_worker]:
    watchdog.register(w)
    w.start()
watchdog.start()

# === PHASE 6: Start GUI application ===
from antigravity.ui.main_window import MainWindow
from antigravity.ui.overlay.overlay_manager import create_overlay
from antigravity.ui.tray.tray_manager import TrayManager
from antigravity.core.event_bus import bus, EVT_SHUTDOWN

app = QApplication([])
app.setApplicationName(config.name)

window = MainWindow(title=config.window_title)

overlay = create_overlay(config.overlay)
overlay.show()

# Pipe everything to Overlay HUD (V3 behavior)
from antigravity.core.event_bus import EVT_TRANSCRIPT_READY, EVT_RESPONSE_READY
bus.subscribe(EVT_TRANSCRIPT_READY, lambda d: overlay.text_updated.emit(f"Q: {d}"))
bus.subscribe(EVT_RESPONSE_READY,   lambda d: overlay.text_updated.emit(d))
bus.subscribe(EVT_CLASSIFICATION_READY, lambda d: overlay.classification_updated.emit(d))

def hard_exit():
    """Fallback if clean shutdown hangs."""
    time.sleep(2.0)
    # Use print instead of logging in case logging is already shut down
    print("[SHUTDOWN] Hang detected, forcing exit...")
    os._exit(0)

_is_quitting = False

def on_quit():
    global _is_quitting
    if _is_quitting:
        return
    _is_quitting = True
    
    logging.info("[SHUTDOWN] Sequence initiated...")
    
    # Start hard exit timer in case of hang
    exit_thread = threading.Thread(target=hard_exit, daemon=True)
    exit_thread.start()
    
    try:
        bus.publish(EVT_SHUTDOWN)
    except: pass
    
    watchdog.stop()
    capture_worker.stop()
    stt_worker.stop()
    llm_worker.stop()
    telegram_worker.stop()
    try:
        overlay.close()
    except: pass
    app.quit()
    
tray = TrayManager(
    app_name=config.name,
    on_show_clicked=lambda: window.show() or window.raise_(),
    on_quit_clicked=on_quit
)
tray.start()

# To exit, they use the tray. Or we can add a quit button.

window.show()

from antigravity.ui.main_window import bridge
bridge.startup_finished.emit()

logging.info("[MAIN] Application entered Qt event loop.")
try:
    app.exec()
except KeyboardInterrupt:
    on_quit()

# === PHASE 7: Cleanup ===
logging.info("[MAIN] Event loop finished.")
on_quit() # Ensure on_quit runs if exec returns normally
gc.collect(0)
gc.collect(1)
_fh_log.close()
sys.exit(0)
