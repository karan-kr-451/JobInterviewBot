# main_console.py — Headless CLI execution

# === PHASE 1: Pre-import protection ===
import gc
gc.disable()
gc.set_threshold(0, 0, 0)

import os
os.makedirs("logs", exist_ok=True)
import faulthandler
_fh_log = open("logs/crash_latest.log", "w", encoding="utf-8")
faulthandler.enable(file=_fh_log)

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
import time
from antigravity.core.gc_guard import start_safe_gc_thread
from antigravity.core.watchdog import Watchdog
from antigravity.core.app_state import get_app_state
from antigravity.transcription.transcript_store import BoundedAudioQueue

start_safe_gc_thread(config.gc.manual_collect_interval_seconds)

app_state = get_app_state()
watchdog = Watchdog(check_interval=config.watchdog.check_interval_seconds)

audio_queue = BoundedAudioQueue(maxlen=100)
llm_queue   = queue.Queue(maxsize=50)
notif_queue = queue.Queue(maxsize=200)

from antigravity.llm.rag.context_retriever import ContextRetriever
rag = ContextRetriever()
rag.load()

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

# Register event callbacks to stdout
from antigravity.core.event_bus import bus, EVT_TRANSCRIPT_READY, EVT_RESPONSE_READY, EVT_BACKEND_SWITCHED, EVT_WORKER_DEAD

bus.subscribe(EVT_TRANSCRIPT_READY, lambda t: print(f"\n[USER] {t}"))
bus.subscribe(EVT_RESPONSE_READY, lambda r: print(f"[AI] {r}", end="\r" if "\n" not in r else "\n"))
bus.subscribe(EVT_BACKEND_SWITCHED, lambda d: print(f"\n[SYSTEM] Backend switched: {d.get('failed')} failed."))
bus.subscribe(EVT_WORKER_DEAD, lambda d: print(f"\n[CRITICAL] Worker died: {d.get('worker')}"))

# Start workers
for w in [capture_worker, stt_worker, llm_worker, telegram_worker]:
    watchdog.register(w)
    w.start()
watchdog.start()

print("\n--- Antigravity Console Mode Started ---\nPress Ctrl+C to stop.\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down...")
    capture_worker.stop()
    stt_worker.stop()
    llm_worker.stop()
    telegram_worker.stop()
finally:
    gc.collect(0)
    _fh_log.close()
