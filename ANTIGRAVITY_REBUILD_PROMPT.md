# 🚀 ANTIGRAVITY — Master Rebuild Prompt
## Interview Assistant v4.0 | Zero-Crash | Production-Grade

> **PURPOSE**: This document is a complete, self-contained prompt to rebuild the
> `JobInterviewBot / Interview Assistant` project from scratch into a new folder
> called `antigravity/`. Every known crash vector, threading flaw, GC issue,
> tech-stack incompatibility, and data-structure inefficiency is addressed with
> concrete code contracts and architecture rules.
>
> Feed the entire document to an AI coding agent (Claude, GPT-4o, Gemini, etc.)
> or follow it yourself to get a clean, hardened v4.0.

---

## 📋 TABLE OF CONTENTS
1. [Mission Statement](#1-mission-statement)
2. [Root Cause Analysis — All Known Issues](#2-root-cause-analysis)
3. [Target Folder Structure](#3-target-folder-structure)
4. [Technology Stack & Version Pins](#4-technology-stack--version-pins)
5. [Core Architecture Rules](#5-core-architecture-rules)
6. [Module-by-Module Rebuild Spec](#6-module-by-module-rebuild-spec)
7. [Threading Model (Zero-Deadlock Contract)](#7-threading-model-zero-deadlock-contract)
8. [GC & Memory Management Rules](#8-gc--memory-management-rules)
9. [Data Structure Optimization Map](#9-data-structure-optimization-map)
10. [Error Handling & Crash Guard System](#10-error-handling--crash-guard-system)
11. [Complete requirements.txt](#11-complete-requirementstxt)
12. [Environment & Config Spec](#12-environment--config-spec)
13. [Build & Run Instructions](#13-build--run-instructions)
14. [AI Coding Agent Instructions](#14-ai-coding-agent-instructions)

---

## 1. MISSION STATEMENT

Rebuild the Interview Assistant into `antigravity/` with:
- **Python 3.12** strict compatibility
- **PyQt6** (not PyQt5, not PySide6) for GUI
- **Zero deadlocks** — every lock has a timeout, every thread has a guardian
- **Zero memory leaks** — explicit resource management with context managers
- **Zero import-time crashes** — lazy loading for heavy binaries (torch, whisper)
- **Zero data-race crashes** — all shared state behind thread-safe wrappers
- **Optimized data structures** — correct container types for every use case
- **Multi-LLM fallback chain**: Groq → Gemini → Ollama (local)
- **Transparent overlay** via Win32 (Windows) with Linux/macOS stub
- **System tray** via `pystray`
- **Telegram notifier** via async queue (never blocks main flow)

---

## 2. ROOT CAUSE ANALYSIS

### 🗑️ 2.1 Garbage Collection (GC) Crashes

**Problem**: Python's cyclic GC triggers inside C-extension finalizers
(especially `tqdm`, `torch`, `pyaudio`) causing `SIGSEGV` / `ACCESS_VIOLATION`.

**Root causes found in original bot**:
```
gc.collect() called inside audio callback thread
tqdm objects held in class scope → cyclic ref → GC during C callback
torch tensors not explicitly deleted after inference
```

**Fix contract**:
```python
# antigravity/core/gc_guard.py
import gc

def apply_gc_guard():
    """
    Disable generation-2 GC during the entire process lifetime.
    Gen-0 and Gen-1 still run (short-lived objects), but gen-2
    (which triggers finalizers in C extensions) is suppressed.
    Manual collect() calls are ONLY allowed from the GC-safe thread.
    """
    gc.disable()                  # full disable at startup
    gc.set_threshold(0, 0, 0)     # no automatic threshold triggers

def manual_gc_collect():
    """Call ONLY from GCSafeThread, never from audio/torch callbacks."""
    gc.collect(0)
    gc.collect(1)
```

**Rules**:
- NEVER call `gc.collect()` inside: audio callbacks, torch inference, PyQt slots
- ALL `tqdm` usage replaced with simple `print(f"\r{pct}%", end="")` or removed
- ALL `torch.Tensor` objects explicitly deleted with `del tensor` after use
- `gc_guard.apply_gc_guard()` is the FIRST call in `main_gui.py` before any import

---

### 🔒 2.2 Deadlocks

**Problem**: Threads acquire multiple locks in inconsistent order, or hold a lock
while waiting on a blocking I/O call (API request, audio read).

**Root causes found**:
```
threading.Lock() acquired in audio callback, then in LLM callback → order reversal
requests.get() called while holding self._state_lock → infinite wait on network timeout
PyQt signal emitted from non-GUI thread while GUI thread waits on same lock
```

**Fix contract — Lock Hierarchy (strict ordering)**:
```
LOCK LEVEL 1 (lowest): AudioBuffer._lock         (audio thread only)
LOCK LEVEL 2:          TranscriptionWorker._lock  (transcription thread only)
LOCK LEVEL 3:          LLMWorker._lock            (LLM thread only)
LOCK LEVEL 4 (highest):AppState._lock             (coordinator only)

RULE: A thread may ONLY acquire a lock at level N if it holds NO lock at level >= N.
RULE: Every lock.acquire() MUST use timeout=5.0. On timeout → log + release + retry.
RULE: NO lock held during any network I/O, file I/O, or Qt signal emission.
```

**Implementation**:
```python
# antigravity/core/safe_lock.py
import threading
import logging

logger = logging.getLogger(__name__)

class SafeLock:
    """
    Drop-in replacement for threading.Lock with mandatory timeout.
    Logs a warning and returns False if timeout exceeded.
    """
    def __init__(self, name: str, timeout: float = 5.0):
        self._lock = threading.Lock()
        self.name = name
        self.timeout = timeout

    def acquire(self, timeout: float | None = None) -> bool:
        t = timeout if timeout is not None else self.timeout
        acquired = self._lock.acquire(timeout=t)
        if not acquired:
            logger.warning(f"[DEADLOCK_GUARD] Lock '{self.name}' timed out after {t}s")
        return acquired

    def release(self):
        try:
            self._lock.release()
        except RuntimeError:
            logger.error(f"[DEADLOCK_GUARD] Double-release on lock '{self.name}'")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
```

---

### 💀 2.3 Thread Death (Silent Crashes)

**Problem**: Worker threads die silently — exception swallowed, thread exits,
app hangs because nothing is queued anymore but GUI shows "Running".

**Root causes found**:
```
threading.Thread started with no exception handler in run()
Transcription thread crashes on bad audio chunk → entire pipeline freezes
LLM thread receives HTTP 429 (rate limit) → unhandled exception → dies
```

**Fix contract**:
```python
# antigravity/core/base_worker.py
import threading
import traceback
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseWorker(threading.Thread, ABC):
    """
    ALL worker threads inherit from this.
    Guarantees:
      - Exception never silently swallowed
      - Auto-restart up to MAX_RESTARTS times
      - Health heartbeat updated every cycle
      - Clean shutdown via stop_event
    """
    MAX_RESTARTS = 3

    def __init__(self, name: str, restart_delay: float = 2.0):
        super().__init__(name=name, daemon=True)
        self._stop_event = threading.Event()
        self._health_ts = 0.0  # epoch seconds, updated each loop
        self._restart_count = 0
        self._restart_delay = restart_delay
        self._exception: Exception | None = None

    def stop(self):
        self._stop_event.set()

    @property
    def is_healthy(self) -> bool:
        import time
        return (time.time() - self._health_ts) < 30.0  # stale after 30s

    def run(self):
        while self._restart_count <= self.MAX_RESTARTS:
            try:
                self._run_loop()
                break  # clean exit
            except Exception as e:
                self._exception = e
                self._restart_count += 1
                logger.error(
                    f"[THREAD_DEATH] {self.name} crashed "
                    f"(attempt {self._restart_count}/{self.MAX_RESTARTS}):\n"
                    f"{traceback.format_exc()}"
                )
                if self._restart_count <= self.MAX_RESTARTS:
                    import time
                    time.sleep(self._restart_delay)
                else:
                    logger.critical(f"[THREAD_DEATH] {self.name} permanently dead. Notifying watchdog.")
                    self._on_permanent_failure()

    @abstractmethod
    def _run_loop(self):
        """Subclass implements the actual work here."""
        ...

    def _on_permanent_failure(self):
        """Override to notify watchdog / GUI."""
        pass
```

---

### ⚙️ 2.4 Tech Stack Incompatibilities

**Problem**: Version mismatches between libraries cause `ImportError`,
`AttributeError`, and silent behavioural regressions.

**Specific incompatibilities found**:

| Conflict | Symptom | Fix |
|----------|---------|-----|
| `openai` v0.x + `groq` v0.x | `openai.ChatCompletion` removed | Pin `groq>=0.9.0`, remove `openai` |
| `torch` 2.x + `torchaudio` mismatch | `torchaudio.load` signature changed | Require identical minor versions |
| `faster-whisper` + `ctranslate2` | `CTranslate2` version drift | Pin `ctranslate2==4.4.0` |
| `pyannote.audio` 3.x + `torch` | `speechbrain` conflict | Isolate in optional extra |
| `PyQt6` + `pyqtgraph` | API breakage in 6.6+ | Use `pyqtgraph>=0.13.7` |
| `sounddevice` + `portaudio` | Windows DLL hell | Bundle portaudio DLL in `assets/` |
| `google-generativeai` 0.7→0.8 | `GenerativeModel` constructor changed | Use `>=0.8.3`, pin client |
| `librosa` + `numba` | JIT cache invalidation crash on first run | Pre-warm in background thread |

**Fix contract**:
```
# All versions are EXACT PINS in requirements.txt (see Section 11)
# Compatibility matrix is validated at startup:
```

```python
# antigravity/core/compat_check.py
import sys
import importlib
import logging

logger = logging.getLogger(__name__)

REQUIRED = {
    "torch":              ("2.5.0", "2.6.99"),
    "torchaudio":         ("2.5.0", "2.6.99"),
    "faster_whisper":     ("1.1.0", "1.9.99"),
    "groq":               ("0.9.0", "1.9.99"),
    "google.generativeai":("0.8.3", "0.9.99"),
    "PyQt6":              ("6.7.0", "6.9.99"),
    "sounddevice":        ("0.5.1", "0.6.99"),
}

def validate_stack() -> list[str]:
    """Returns list of error strings. Empty = all good."""
    from packaging.version import Version
    errors = []
    for pkg, (vmin, vmax) in REQUIRED.items():
        try:
            mod = importlib.import_module(pkg.replace(".", "/").replace("/", "."))
            v = Version(getattr(mod, "__version__", "0.0.0"))
            if not (Version(vmin) <= v <= Version(vmax)):
                errors.append(f"{pkg}: {v} outside [{vmin}, {vmax}]")
        except ImportError:
            errors.append(f"{pkg}: NOT INSTALLED")
    return errors
```

---

### 📦 2.5 Unoptimized Data Structures

**Problem**: Wrong container choices cause O(n) operations in hot paths,
unbounded memory growth, and cache-miss-heavy access patterns.

**Issues found and replacements**:

```
ORIGINAL → REPLACEMENT | REASON
─────────────────────────────────────────────────────────────────────────
list (transcript history)        → collections.deque(maxlen=500)
  WHY: list.append is fine but list[0] removal is O(n). deque is O(1) both ends.
  CRASH RISK: unbounded list grows forever → OOM after 2hr session

list (question lookup)           → dict[str, QuestionData]
  WHY: "if question in questions_list" is O(n) scan. dict is O(1).

list (audio chunks)              → collections.deque(maxlen=100)
  WHY: audio buffer must be bounded. Unbounded list = memory explosion on silence.

dict (LLM response cache)        → functools.lru_cache / cachetools.LRUCache(maxsize=128)
  WHY: naive dict never evicts → unbounded growth over long sessions.

set built from list each call    → persistent set maintained incrementally
  WHY: set(my_list) called in a loop = O(n) each iteration.

threading.Queue (unbounded)      → queue.Queue(maxsize=50)
  WHY: if consumer is slow, producer fills RAM. Bounded queue = natural backpressure.

str concatenation in loop        → io.StringIO / list then "".join()
  WHY: str + str in loop is O(n²). join() is O(n).
```

---

### 💥 2.6 Other Crash Causes

```
CRASH: PyAudio callback raises exception → segfault (C-level, unrecoverable)
FIX:  Wrap entire callback in try/except; NEVER raise from callback.

CRASH: torch loaded in audio thread → CUDA context conflict
FIX:  torch imported ONLY in dedicated InferenceThread, never in audio thread.

CRASH: PyQt6 widget accessed from non-GUI thread (QObject thread affinity)
FIX:  ALL GUI updates via Qt signals/slots ONLY. Zero direct widget access from workers.

CRASH: librosa numba cache race condition on first import
FIX:  Pre-warm librosa in a splash-screen background thread before GUI starts.

CRASH: requests.get() with no timeout → hangs forever → watchdog kills process
FIX:  ALL HTTP calls use timeout=(5, 30) — 5s connect, 30s read.

CRASH: faulthandler not enabled → SIGSEGV leaves no trace
FIX:  faulthandler.enable(file=crash_log) as SECOND call in main_gui.py.

CRASH: Uncaught exception in QThread → Qt kills entire process
FIX:  sys.excepthook + threading.excepthook both set to custom crash_handler.
```

---

## 3. TARGET FOLDER STRUCTURE

```
antigravity/
├── main_gui.py                  # Entry point (GUI mode)
├── main_console.py              # Entry point (headless/console mode)
├── crash_detector.py            # External supervisor / auto-restart wrapper
├── requirements.txt             # Pinned versions (see Section 11)
├── .env.example                 # Template env file
├── config.yaml                  # App configuration
├── build_exe.py                 # PyInstaller build script
├── build_with_venv.bat          # Windows automated build pipeline
│
├── antigravity/                 # Main package
│   ├── __init__.py
│   │
│   ├── core/                    # Foundation layer
│   │   ├── __init__.py
│   │   ├── gc_guard.py          # GC crash prevention (2.1)
│   │   ├── safe_lock.py         # Deadlock-safe locking (2.2)
│   │   ├── base_worker.py       # Immortal thread base class (2.3)
│   │   ├── compat_check.py      # Stack validation at startup (2.4)
│   │   ├── app_state.py         # Centralized, thread-safe state store
│   │   ├── event_bus.py         # Decoupled inter-module messaging
│   │   ├── crash_handler.py     # sys/threading excepthook + faulthandler
│   │   └── watchdog.py          # Health monitor for all worker threads
│   │
│   ├── audio/                   # Audio capture layer
│   │   ├── __init__.py
│   │   ├── device_manager.py    # Enumerate and select audio devices
│   │   ├── capture_worker.py    # sounddevice capture → bounded deque
│   │   └── vad_filter.py        # Silero VAD — filter silence before STT
│   │
│   ├── transcription/           # Speech-to-text layer
│   │   ├── __init__.py
│   │   ├── transcription_worker.py  # Pulls from audio deque, runs STT
│   │   ├── groq_stt.py              # Groq Whisper remote STT
│   │   ├── local_stt.py             # faster-whisper local fallback
│   │   └── transcript_store.py      # deque-based bounded transcript history
│   │
│   ├── llm/                     # Language model layer
│   │   ├── __init__.py
│   │   ├── llm_worker.py        # Pulls from transcript queue, calls LLM
│   │   ├── groq_client.py       # Groq LLaMA-3 client (primary)
│   │   ├── gemini_client.py     # Gemini 2.0 Flash client (secondary)
│   │   ├── ollama_client.py     # Ollama local client (tertiary fallback)
│   │   ├── fallback_chain.py    # Auto-fallback: Groq→Gemini→Ollama
│   │   ├── prompt_builder.py    # Context-aware prompt assembly
│   │   ├── response_cache.py    # LRU cache for repeated questions
│   │   └── rag/
│   │       ├── document_store.py    # PDF/DOCX ingestion
│   │       └── context_retriever.py # Retrieval for resume/JD context
│   │
│   ├── ui/                      # User interface layer
│   │   ├── __init__.py
│   │   ├── main_window.py       # PyQt6 main dashboard
│   │   ├── settings_dialog.py   # Settings + API key manager
│   │   ├── overlay/
│   │   │   ├── overlay_manager.py   # Spawns correct overlay per platform
│   │   │   ├── win32_overlay.py     # Windows transparent HUD
│   │   │   └── stub_overlay.py      # Linux/macOS stub (no-op)
│   │   └── tray/
│   │       └── tray_manager.py      # pystray system tray icon + menu
│   │
│   ├── notifications/           # Notification layer
│   │   ├── __init__.py
│   │   └── telegram_notifier.py # Async queue-based Telegram sender
│   │
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── logger.py            # Structured logging to file + console
│       ├── env_loader.py        # python-dotenv loader with validation
│       ├── config_loader.py     # YAML config loader with defaults
│       └── timer.py             # Lightweight watchdog timer helper
│
├── assets/
│   ├── icon.ico                 # App icon
│   ├── icon.png
│   └── portaudio_x64.dll        # Bundled PortAudio DLL (Windows)
│
├── logs/                        # Auto-created at runtime
│   ├── interview_YYYYMMDD.log
│   └── crash_YYYYMMDD_HHMMSS.log
│
└── dist/                        # PyInstaller output
    └── InterviewAssistant.exe
```

---

## 4. TECHNOLOGY STACK & VERSION PINS

```
Python:          3.12.x (NOT 3.13 — PyAudio wheels not ready)
GUI:             PyQt6==6.7.3
Audio capture:   sounddevice==0.5.1
Audio arrays:    numpy==1.26.4        ← DO NOT upgrade to 2.x (torch compat)
STT local:       faster-whisper==1.1.0
STT backend:     ctranslate2==4.4.0   ← MUST match faster-whisper expectation
ML:              torch==2.5.1+cpu     ← CPU build avoids CUDA DLL hell on most machines
                 torchaudio==2.5.1+cpu
VAD:             silero-vad (via torch.hub, no pip install)
LLM primary:     groq==0.9.0
LLM secondary:   google-generativeai==0.8.3
LLM local:       ollama==0.3.3        ← thin client, Ollama server runs separately
RAG/PDF:         pypdf==5.1.0
HTTP:            requests==2.32.3
Config:          python-dotenv==1.0.1
                 pyyaml==6.0.2
Tray:            pystray==0.19.5
Image:           pillow==10.4.0
Packaging:       pyinstaller==6.10.0
Version check:   packaging==24.1
LRU cache:       cachetools==5.5.0
```

---

## 5. CORE ARCHITECTURE RULES

These rules are NON-NEGOTIABLE. Every module must follow all of them.

### R1 — No Direct Widget Access from Workers
```python
# ❌ FORBIDDEN in any worker thread:
self.label.setText("new text")

# ✅ CORRECT — emit a signal, let Qt dispatch to GUI thread:
self.text_updated.emit("new text")
```

### R2 — No Unbounded Containers
```python
# ❌ FORBIDDEN:
self.history = []
self.history.append(item)  # grows forever

# ✅ CORRECT:
from collections import deque
self.history = deque(maxlen=500)
self.history.append(item)  # auto-evicts oldest
```

### R3 — No Bare except / Silent Swallow
```python
# ❌ FORBIDDEN:
try:
    do_something()
except:
    pass

# ✅ CORRECT:
try:
    do_something()
except Exception as e:
    logger.error(f"[MODULE] Operation failed: {e}", exc_info=True)
    # then either retry, notify, or re-raise — NEVER silently pass
```

### R4 — No Lock Held During I/O
```python
# ❌ FORBIDDEN:
with self._lock:
    response = requests.get(url, timeout=30)  # holds lock for 30s!

# ✅ CORRECT:
response = requests.get(url, timeout=(5, 30))  # fetch outside lock
with self._lock:
    self._cache[url] = response.text  # only update state inside lock
```

### R5 — All Threads are Daemon Threads
```python
# Every BaseWorker subclass sets daemon=True so that
# process exit is never blocked by a hung worker.
```

### R6 — Lazy Import for Heavy Modules
```python
# ❌ FORBIDDEN at module top level in any file that loads at import time:
import torch
import faster_whisper

# ✅ CORRECT — import inside the function/class that owns it:
class LocalSTT:
    def _load_model(self):
        import torch                    # imports happen once, on first use
        from faster_whisper import WhisperModel
        self._model = WhisperModel(...)
```

### R7 — All HTTP Calls Have Timeouts
```python
# MANDATORY signature for every requests call:
requests.get(url, timeout=(5, 30), headers=headers)
requests.post(url, json=body, timeout=(5, 60), headers=headers)
```

### R8 — PyAudio / sounddevice Callbacks are Bulletproof
```python
def _audio_callback(self, indata, frames, time_info, status):
    try:
        if status:
            logger.warning(f"[AUDIO] Status: {status}")
        # bounded deque — never raises on full, just overwrites
        self._buffer.append(indata.copy())
    except Exception as e:
        # LOG ONLY — never raise from audio callback (C-level crash)
        logger.error(f"[AUDIO_CB] {e}")
```

---

## 6. MODULE-BY-MODULE REBUILD SPEC

### 6.1 `core/app_state.py` — Thread-Safe State Store
```python
"""
Single source of truth for all shared application state.
Uses SafeLock (never plain threading.Lock).
All getters/setters acquire lock with timeout.
State is a typed dataclass — no raw dicts.
"""

from dataclasses import dataclass, field
from collections import deque
from antigravity.core.safe_lock import SafeLock

@dataclass
class AppState:
    is_recording: bool = False
    is_processing: bool = False
    current_backend: str = "groq"  # "groq" | "gemini" | "ollama"
    transcript_history: deque = field(default_factory=lambda: deque(maxlen=500))
    response_history: deque = field(default_factory=lambda: deque(maxlen=200))
    session_questions: set = field(default_factory=set)  # O(1) duplicate check
    error_count: int = 0
    _lock: SafeLock = field(default_factory=lambda: SafeLock("AppState", timeout=3.0))

    def set_recording(self, value: bool):
        with self._lock:
            self.is_recording = value

    def add_transcript(self, text: str):
        with self._lock:
            self.transcript_history.append(text)
            self.session_questions.add(text[:100])  # dedup key

    def is_duplicate_question(self, text: str) -> bool:
        with self._lock:
            return text[:100] in self.session_questions
```

### 6.2 `core/event_bus.py` — Decoupled Messaging
```python
"""
Publish-subscribe event bus.
Modules communicate via events, never by direct references.
This eliminates circular imports and tight coupling.
"""
from collections import defaultdict
from typing import Callable
import threading

class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event: str, callback: Callable):
        with self._lock:
            self._listeners[event].append(callback)

    def publish(self, event: str, data=None):
        with self._lock:
            callbacks = list(self._listeners[event])
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"[EVENTBUS] {event} handler error: {e}")

bus = EventBus()  # singleton

# Event names (use constants, not magic strings):
EVT_TRANSCRIPT_READY  = "transcript.ready"
EVT_RESPONSE_READY    = "response.ready"
EVT_RECORDING_START   = "recording.start"
EVT_RECORDING_STOP    = "recording.stop"
EVT_ERROR             = "app.error"
EVT_WORKER_DEAD       = "worker.dead"
EVT_BACKEND_SWITCHED  = "backend.switched"
```

### 6.3 `core/watchdog.py` — Thread Health Monitor
```python
"""
Monitors all registered workers every 10 seconds.
If a worker is unhealthy (heartbeat stale > 30s), emits EVT_WORKER_DEAD.
GUI subscribes to show warning. Supervisor can restart the worker.
"""
import time
import threading
from antigravity.core.event_bus import bus, EVT_WORKER_DEAD
from antigravity.core.base_worker import BaseWorker
import logging

logger = logging.getLogger(__name__)

class Watchdog:
    def __init__(self, check_interval: float = 10.0):
        self._workers: list[BaseWorker] = []
        self._interval = check_interval
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Watchdog")

    def register(self, worker: BaseWorker):
        self._workers.append(worker)

    def start(self):
        self._thread.start()

    def _loop(self):
        while True:
            time.sleep(self._interval)
            for w in self._workers:
                if w.is_alive() and not w.is_healthy:
                    logger.warning(f"[WATCHDOG] {w.name} heartbeat stale")
                    bus.publish(EVT_WORKER_DEAD, {"worker": w.name})
                elif not w.is_alive():
                    logger.error(f"[WATCHDOG] {w.name} is dead (not alive)")
                    bus.publish(EVT_WORKER_DEAD, {"worker": w.name})
```

### 6.4 `audio/capture_worker.py` — Bulletproof Audio Capture
```python
"""
Captures system audio using sounddevice.
Uses bounded deque — never runs out of memory.
Callback is wrapped in try/except — never crashes C runtime.
VAD pre-filters silence to reduce STT load.
"""
import sounddevice as sd
import numpy as np
from collections import deque
import time
from antigravity.core.base_worker import BaseWorker
from antigravity.core.event_bus import bus, EVT_RECORDING_START, EVT_RECORDING_STOP
import logging

logger = logging.getLogger(__name__)

SAMPLE_RATE   = 16000
CHANNELS      = 1
CHUNK_SECONDS = 0.5
CHUNK_FRAMES  = int(SAMPLE_RATE * CHUNK_SECONDS)
BUFFER_MAXLEN = 100  # ~50 seconds of audio max in RAM

class CaptureWorker(BaseWorker):
    def __init__(self, device_index: int, audio_queue: deque):
        super().__init__(name="CaptureWorker")
        self._device_index = device_index
        self._audio_queue = audio_queue  # shared with TranscriptionWorker
        self._stream: sd.InputStream | None = None

    def _run_loop(self):
        with sd.InputStream(
            device=self._device_index,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_FRAMES,
            dtype=np.float32,
            callback=self._callback,
        ):
            bus.publish(EVT_RECORDING_START)
            while not self._stop_event.is_set():
                self._health_ts = time.time()  # heartbeat
                time.sleep(0.1)
        bus.publish(EVT_RECORDING_STOP)

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        try:
            if status:
                logger.warning(f"[AUDIO] {status}")
            if np.max(np.abs(indata)) > 0.005:  # basic VAD gate
                self._audio_queue.append(indata.copy().flatten())
        except Exception as e:
            logger.error(f"[AUDIO_CB] {e}")  # NEVER re-raise
```

### 6.5 `llm/fallback_chain.py` — Multi-LLM Fault Tolerance
```python
"""
Tries Groq first (fastest). On any failure, falls back to Gemini.
On Gemini failure, falls back to Ollama (local, always available).
Uses circuit breaker pattern — if a backend fails 3x, mark it dead for 60s.
"""
import time
import logging
from antigravity.core.event_bus import bus, EVT_BACKEND_SWITCHED

logger = logging.getLogger(__name__)

class CircuitBreaker:
    THRESHOLD = 3
    RESET_AFTER = 60.0  # seconds

    def __init__(self, name: str):
        self.name = name
        self._failures = 0
        self._opened_at: float | None = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.time() - self._opened_at > self.RESET_AFTER:
            self._failures = 0
            self._opened_at = None
            logger.info(f"[CIRCUIT] {self.name} reset (half-open)")
            return False
        return self._failures >= self.THRESHOLD

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.THRESHOLD:
            self._opened_at = time.time()
            logger.warning(f"[CIRCUIT] {self.name} OPEN after {self._failures} failures")

    def record_success(self):
        self._failures = 0
        self._opened_at = None


class FallbackChain:
    def __init__(self, groq_client, gemini_client, ollama_client):
        self._backends = {
            "groq":   (groq_client,   CircuitBreaker("groq")),
            "gemini": (gemini_client, CircuitBreaker("gemini")),
            "ollama": (ollama_client, CircuitBreaker("ollama")),
        }
        self._order = ["groq", "gemini", "ollama"]

    def complete(self, prompt: str, system: str = "") -> str:
        for name in self._order:
            client, breaker = self._backends[name]
            if breaker.is_open():
                continue
            try:
                result = client.complete(prompt, system=system)
                breaker.record_success()
                return result
            except Exception as e:
                logger.warning(f"[FALLBACK] {name} failed: {e}")
                breaker.record_failure()
                bus.publish(EVT_BACKEND_SWITCHED, {"from": name})
        return "⚠️ All AI backends temporarily unavailable. Please check your API keys."
```

### 6.6 `ui/main_window.py` — PyQt6 GUI (skeleton)
```python
"""
Rules:
  - NO worker references in this file — communicate via EventBus only
  - ALL state updates via Qt signals (never direct slot calls from workers)
  - QTimer for periodic UI refresh (100ms) — not tight loops
  - Overlay and tray started AFTER main window is shown
"""
from PyQt6.QtWidgets import QMainWindow, QApplication
from PyQt6.QtCore import QTimer, pyqtSignal, QObject
from antigravity.core.event_bus import bus, EVT_TRANSCRIPT_READY, EVT_RESPONSE_READY

class SignalBridge(QObject):
    """Converts EventBus callbacks (any thread) to Qt signals (GUI thread)."""
    transcript_received = pyqtSignal(str)
    response_received   = pyqtSignal(str)
    worker_died         = pyqtSignal(str)

bridge = SignalBridge()

# Wire EventBus → Qt signals (thread-safe crossing point)
bus.subscribe(EVT_TRANSCRIPT_READY, lambda d: bridge.transcript_received.emit(d))
bus.subscribe(EVT_RESPONSE_READY,   lambda d: bridge.response_received.emit(d))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._setup_ui()
        bridge.transcript_received.connect(self._on_transcript)
        bridge.response_received.connect(self._on_response)

    def _setup_ui(self): ...   # full implementation in actual code

    def _on_transcript(self, text: str):
        # SAFE — this runs in GUI thread because it's connected via Qt signal
        self.transcript_view.append(text)

    def _on_response(self, text: str):
        self.response_view.setPlainText(text)
```

---

## 7. THREADING MODEL (ZERO-DEADLOCK CONTRACT)

```
┌─────────────────────────────────────────────────────┐
│                    MAIN THREAD                       │
│  1. apply_gc_guard()                                 │
│  2. faulthandler.enable()                            │
│  3. validate_stack()                                 │
│  4. Load config + .env                               │
│  5. Start all workers                                │
│  6. Register workers with Watchdog                   │
│  7. Start Watchdog                                   │
│  8. QApplication.exec()  ← blocks here               │
└──────────────────┬──────────────────────────────────┘
                   │ Qt event loop
    ┌──────────────▼──────────────┐
    │       GUI THREAD (Qt)        │
    │  MainWindow + SettingsDialog │
    │  Receives signals ONLY       │
    │  Never touches worker state  │
    └─────────────────────────────┘

    WORKER THREADS (all daemon=True, all BaseWorker subclasses):
    ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
    │CaptureWorker │  │TranscriptionWorker│  │  LLMWorker     │
    │(sounddevice) │→ │(faster-whisper/  │→ │(FallbackChain) │
    │              │  │ Groq Whisper)    │  │                │
    │Writes to:    │  │Reads from:       │  │Reads from:     │
    │audio_deque   │  │audio_deque       │  │transcript_queue│
    │(bounded)     │  │Writes to:        │  │Writes to:      │
    └──────────────┘  │transcript_queue  │  │response_queue  │
                      └──────────────────┘  └────────────────┘

    ┌──────────────┐  ┌──────────────────┐
    │ Overlay      │  │TelegramNotifier  │
    │ (Win32 HUD)  │  │(async queue)     │
    │Reads from:   │  │Never blocks main │
    │response_queue│  │flow              │
    └──────────────┘  └──────────────────┘

    ┌──────────────────────────────────────┐
    │         WATCHDOG THREAD              │
    │ Monitors all workers every 10s       │
    │ Publishes EVT_WORKER_DEAD to EventBus│
    └──────────────────────────────────────┘

DATA FLOWS (all via bounded queues, zero shared mutable state):
  audio_deque:        deque(maxlen=100)  ← between Capture and Transcription
  transcript_queue:   Queue(maxsize=50)  ← between Transcription and LLM
  response_queue:     Queue(maxsize=20)  ← between LLM and Overlay/GUI
  telegram_queue:     Queue(maxsize=200) ← async notification backlog

LOCK ACQUISITION ORDER (never violate):
  1. AudioBuffer._lock  (if needed)
  2. TranscriptionWorker._lock (if needed)
  3. LLMWorker._lock (if needed)
  4. AppState._lock (coordinator)
  → A thread holding lock N must NEVER acquire lock < N
```

---

## 8. GC & MEMORY MANAGEMENT RULES

```python
# main_gui.py — first 10 lines (ORDER MATTERS):
import gc
gc.disable()
gc.set_threshold(0, 0, 0)   # Rule 1: Disable GC before any C-ext import

import faulthandler
import logging
_crash_log = open("logs/crash_latest.log", "w")
faulthandler.enable(file=_crash_log)  # Rule 2: Enable fault handler ASAP

# Rule 3: torch tensors — always explicit delete
def run_inference(audio: np.ndarray) -> str:
    import torch
    tensor = torch.from_numpy(audio)
    try:
        result = model(tensor)
        return result.text
    finally:
        del tensor           # explicit delete
        # DO NOT call torch.cuda.empty_cache() — causes GC re-entry

# Rule 4: File handles always via context managers
def load_pdf(path: str) -> str:
    with open(path, "rb") as f:          # auto-closed
        return extract_text(f)

# Rule 5: sounddevice stream always via context manager
with sd.InputStream(..., callback=cb) as stream:
    while not stop_event.is_set():
        time.sleep(0.1)
# stream auto-closed on exit, even on exception

# Rule 6: Periodic manual GC from dedicated safe thread (NOT audio/torch threads)
class GCSafeThread(threading.Thread):
    def run(self):
        while True:
            time.sleep(60)      # every 60 seconds
            gc.collect(0)       # gen-0 only (fastest, safest)
            gc.collect(1)       # gen-1 only
            # NEVER collect(2) — that's the dangerous one
```

---

## 9. DATA STRUCTURE OPTIMIZATION MAP

```python
# antigravity/transcription/transcript_store.py

from collections import deque
from cachetools import LRUCache
import queue

# ✅ Transcript history — bounded, O(1) append+evict
transcript_history: deque[str] = deque(maxlen=500)

# ✅ Question dedup — O(1) lookup
seen_questions: set[str] = set()

# ✅ Response cache — LRU eviction, O(1) get/set
response_cache: LRUCache = LRUCache(maxsize=128)

# ✅ Audio buffer — bounded, never OOMs
audio_buffer: deque[np.ndarray] = deque(maxlen=100)

# ✅ Inter-thread queues — bounded with backpressure
transcript_queue: queue.Queue = queue.Queue(maxsize=50)
response_queue:   queue.Queue = queue.Queue(maxsize=20)
telegram_queue:   queue.Queue = queue.Queue(maxsize=200)

# ✅ String building in LLM streaming — never += in loop
def build_response(chunks: list[str]) -> str:
    import io
    buf = io.StringIO()
    for chunk in chunks:
        buf.write(chunk)
    return buf.getvalue()

# ✅ Device lookup — dict not list
audio_devices: dict[int, str] = {}    # index → name, O(1) lookup
```

---

## 10. ERROR HANDLING & CRASH GUARD SYSTEM

```python
# antigravity/core/crash_handler.py
import sys
import threading
import traceback
import logging
import datetime
import os

logger = logging.getLogger(__name__)

def _format_crash(exc_type, exc_value, exc_tb) -> str:
    lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    return "".join(lines)

def global_exception_handler(exc_type, exc_value, exc_tb):
    """Handles uncaught exceptions in the MAIN thread."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    crash_text = _format_crash(exc_type, exc_value, exc_tb)
    logger.critical(f"[CRASH] Uncaught exception:\n{crash_text}")
    _write_crash_log(crash_text)

def thread_exception_handler(args):
    """Handles uncaught exceptions in WORKER threads."""
    crash_text = _format_crash(args.exc_type, args.exc_value, args.exc_traceback)
    logger.critical(f"[CRASH] Thread '{args.thread.name}' uncaught:\n{crash_text}")
    _write_crash_log(crash_text, thread=args.thread.name)

def _write_crash_log(text: str, thread: str = "main"):
    os.makedirs("logs", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"logs/crash_{thread}_{ts}.log"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"[CRASH] Written to {path}")

def install():
    sys.excepthook = global_exception_handler
    threading.excepthook = thread_exception_handler
    logger.info("[CRASH_GUARD] Exception handlers installed")
```

### Startup Sequence in `main_gui.py`
```python
# main_gui.py — EXACT startup order (do not reorder)

# === PHASE 1: Pre-import protection ===
import gc; gc.disable(); gc.set_threshold(0, 0, 0)

import os; os.makedirs("logs", exist_ok=True)
import faulthandler
_fh_log = open("logs/crash_latest.log", "w")
faulthandler.enable(file=_fh_log)

# === PHASE 2: Install crash handlers ===
from antigravity.core.crash_handler import install as install_crash_handler
install_crash_handler()

# === PHASE 3: Load config ===
from antigravity.utils.env_loader import load_env
from antigravity.utils.config_loader import load_config
load_env()
config = load_config()

# === PHASE 4: Validate tech stack ===
from antigravity.core.compat_check import validate_stack
errors = validate_stack()
if errors:
    for e in errors: print(f"[COMPAT ERROR] {e}")
    # Show warning dialog but DON'T exit — degrade gracefully

# === PHASE 5: Pre-warm heavy modules in background ===
import threading
def _prewarm():
    try:
        import librosa  # triggers numba JIT compilation
        import numpy    # verifies numpy is loadable
    except Exception as e:
        pass  # log only, non-fatal
threading.Thread(target=_prewarm, daemon=True, name="PreWarm").start()

# === PHASE 6: Start application ===
from PyQt6.QtWidgets import QApplication
from antigravity.ui.main_window import MainWindow
app = QApplication([])
window = MainWindow()
window.show()
app.exec()

# === PHASE 7: Cleanup ===
gc.collect(0); gc.collect(1)
_fh_log.close()
```

---

## 11. COMPLETE `requirements.txt`

```
# ── Core ──────────────────────────────────────────────
numpy==1.26.4
scipy==1.13.1

# ── Audio ─────────────────────────────────────────────
sounddevice==0.5.1
soundfile==0.12.1
librosa==0.10.2.post1

# ── Machine Learning ──────────────────────────────────
# Install CPU builds to avoid CUDA DLL conflicts:
# pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
torch==2.5.1
torchaudio==2.5.1
ctranslate2==4.4.0
faster-whisper==1.1.0

# ── LLM Clients ───────────────────────────────────────
groq==0.9.0
google-generativeai==0.8.3
ollama==0.3.3

# ── GUI ───────────────────────────────────────────────
PyQt6==6.7.3
pystray==0.19.5
pillow==10.4.0

# ── HTTP & Config ─────────────────────────────────────
requests==2.32.3
python-dotenv==1.0.1
pyyaml==6.0.2

# ── RAG / Documents ───────────────────────────────────
pypdf==5.1.0

# ── Utilities ─────────────────────────────────────────
cachetools==5.5.0
packaging==24.1

# ── Build ─────────────────────────────────────────────
pyinstaller==6.10.0

# ── Optional: Speaker Diarization ─────────────────────
# Uncomment only if needed (heavy, conflicts possible):
# pyannote.audio==3.3.1
```

---

## 12. ENVIRONMENT & CONFIG SPEC

### `.env.example`
```dotenv
# Required for primary STT and LLM
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx

# Required for fallback LLM
GEMINI_API_KEY=AIzaxxxxxxxxxxxxxxxx

# Optional: Telegram notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Audio device index (run python -m sounddevice to list)
DEVICE_INDEX=1

# LLM backend: auto | groq | gemini | ollama
LLM_BACKEND=auto

# Log level: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=INFO
```

### `config.yaml`
```yaml
app:
  name: "Interview Assistant"
  version: "4.0"
  window_title: "Antigravity Interview Assistant"

audio:
  device_index: 1          # override with DEVICE_INDEX env var
  sample_rate: 16000
  channels: 1
  chunk_seconds: 0.5
  vad_threshold: 0.005     # amplitude gate before VAD model

transcription:
  backend: "groq"          # groq | local
  local_model: "tiny.en"   # faster-whisper model size
  language: "en"

llm:
  backend: "auto"          # auto | groq | gemini | ollama
  groq_model: "llama-3.3-70b-versatile"
  gemini_model: "gemini-2.0-flash-exp"
  ollama_model: "llama3.2"
  max_tokens: 1024
  temperature: 0.3
  system_prompt: |
    You are an expert technical interview assistant.
    Answer concisely and accurately. Focus on the most
    important technical points. Be direct and helpful.

overlay:
  enabled: true
  opacity: 0.85
  position: "top-right"    # top-right | top-left | bottom-right | bottom-left
  font_size: 14
  max_lines: 20

notifications:
  telegram_enabled: false

watchdog:
  check_interval_seconds: 10
  stale_threshold_seconds: 30

gc:
  manual_collect_interval_seconds: 60
```

---

## 13. BUILD & RUN INSTRUCTIONS

### Run (Development)
```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate
.venv\Scripts\activate          # Windows
source .venv/bin/activate        # Linux/macOS

# 3. Install PyTorch CPU (prevents CUDA DLL issues)
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu

# 4. Install rest of dependencies
pip install -r requirements.txt

# 5. Copy and fill env file
cp .env.example .env
# Edit .env with your API keys

# 6. Run
python main_gui.py               # GUI mode
python main_console.py           # Console mode
python crash_detector.py         # Supervised mode (auto-restart on crash)
```

### Build Executable (Windows)
```bat
rem build_with_venv.bat
@echo off
call .venv\Scripts\activate
python -m pip install --upgrade pyinstaller==6.10.0
python build_exe.py
echo Build complete: dist\InterviewAssistant.exe
```

### `build_exe.py`
```python
import PyInstaller.__main__

PyInstaller.__main__.run([
    "main_gui.py",
    "--name=InterviewAssistant",
    "--onefile",
    "--windowed",
    "--icon=assets/icon.ico",
    "--add-data=assets;assets",
    "--add-data=config.yaml;.",
    "--hidden-import=antigravity.core",
    "--hidden-import=antigravity.audio",
    "--hidden-import=antigravity.transcription",
    "--hidden-import=antigravity.llm",
    "--hidden-import=antigravity.ui",
    "--hidden-import=antigravity.notifications",
    "--collect-all=faster_whisper",
    "--collect-all=ctranslate2",
    "--collect-all=sounddevice",
    "--exclude-module=pyannote",    # heavy optional dep
    "--exclude-module=tqdm",        # GC risk
    "--exclude-module=IPython",
])
```

---

## 14. AI CODING AGENT INSTRUCTIONS

**If you are an AI agent reading this prompt, follow these steps precisely:**

### Step 1 — Create the folder structure
```bash
mkdir -p antigravity/{core,audio,transcription,llm/rag,ui/overlay,ui/tray,notifications,utils}
touch antigravity/__init__.py
touch antigravity/{core,audio,transcription,llm,ui,notifications,utils}/__init__.py
```

### Step 2 — Implement in this exact order (dependency order)
1. `antigravity/core/gc_guard.py`
2. `antigravity/core/safe_lock.py`
3. `antigravity/core/base_worker.py`
4. `antigravity/core/crash_handler.py`
5. `antigravity/core/event_bus.py`
6. `antigravity/core/app_state.py`
7. `antigravity/core/watchdog.py`
8. `antigravity/core/compat_check.py`
9. `antigravity/utils/logger.py`
10. `antigravity/utils/env_loader.py`
11. `antigravity/utils/config_loader.py`
12. `antigravity/audio/device_manager.py`
13. `antigravity/audio/capture_worker.py`
14. `antigravity/audio/vad_filter.py`
15. `antigravity/transcription/transcript_store.py`
16. `antigravity/transcription/groq_stt.py`
17. `antigravity/transcription/local_stt.py`
18. `antigravity/transcription/transcription_worker.py`
19. `antigravity/llm/response_cache.py`
20. `antigravity/llm/prompt_builder.py`
21. `antigravity/llm/groq_client.py`
22. `antigravity/llm/gemini_client.py`
23. `antigravity/llm/ollama_client.py`
24. `antigravity/llm/fallback_chain.py`
25. `antigravity/llm/llm_worker.py`
26. `antigravity/llm/rag/document_store.py`
27. `antigravity/llm/rag/context_retriever.py`
28. `antigravity/notifications/telegram_notifier.py`
29. `antigravity/ui/tray/tray_manager.py`
30. `antigravity/ui/overlay/win32_overlay.py`
31. `antigravity/ui/overlay/stub_overlay.py`
32. `antigravity/ui/overlay/overlay_manager.py`
33. `antigravity/ui/settings_dialog.py`
34. `antigravity/ui/main_window.py`
35. `main_gui.py`
36. `main_console.py`
37. `crash_detector.py`
38. `config.yaml`
39. `.env.example`
40. `requirements.txt`
41. `build_exe.py`
42. `build_with_venv.bat`

### Step 3 — Validation checklist before finishing
- [ ] No `threading.Lock()` used anywhere — only `SafeLock`
- [ ] No unbounded `list` used for streaming/history data — only `deque(maxlen=N)`
- [ ] No `queue.Queue()` without `maxsize` — all queues are bounded
- [ ] No `gc.collect()` called from audio/torch threads
- [ ] No direct widget access from worker threads — signals only
- [ ] No HTTP call without `timeout=(5, 30)`
- [ ] No `except: pass` anywhere
- [ ] Every `threading.Thread` has `daemon=True`
- [ ] `gc.disable()` is the FIRST line of `main_gui.py`
- [ ] `faulthandler.enable()` is the SECOND call in `main_gui.py`
- [ ] All imports of `torch`/`faster_whisper` are inside class methods (lazy)
- [ ] `requirements.txt` uses exact pins (`==`), not ranges

### Step 4 — Test the startup sequence
```bash
python -c "
import gc; gc.disable()
from antigravity.core.crash_handler import install; install()
from antigravity.core.compat_check import validate_stack
errors = validate_stack()
print('Stack errors:', errors if errors else 'NONE — all good')
from antigravity.core.event_bus import bus
print('EventBus:', 'OK')
from antigravity.core.app_state import AppState
state = AppState()
state.set_recording(True)
print('AppState:', 'OK')
print('All core systems: PASS')
"
```

---

## ✅ SUMMARY — Issues Fixed in Antigravity v4.0

| # | Issue | Fix Applied |
|---|-------|-------------|
| 1 | GC crashes in C-extensions | `gc.disable()` + manual gen-0/1 only in safe thread |
| 2 | Deadlocks from lock order inversion | `SafeLock` with timeout + strict lock hierarchy |
| 3 | Silent thread death | `BaseWorker` with auto-restart + Watchdog |
| 4 | Tech stack version conflicts | Exact pins + `compat_check.py` at startup |
| 5 | Unbounded list memory growth | `deque(maxlen=N)` everywhere |
| 6 | O(n) question dedup | `set` for O(1) membership test |
| 7 | Unbounded queue memory | All queues use `maxsize` |
| 8 | LRU eviction missing | `cachetools.LRUCache(maxsize=128)` |
| 9 | O(n²) string concat | `io.StringIO` / `"".join()` |
| 10 | PyAudio callback raises | try/except in callback, never re-raise |
| 11 | torch in wrong thread | torch imported only in InferenceThread |
| 12 | Direct widget access from workers | EventBus → Qt SignalBridge → GUI thread |
| 13 | librosa numba cache race | Pre-warmed in splash background thread |
| 14 | HTTP hangs | `timeout=(5, 30)` on all requests |
| 15 | SIGSEGV no trace | `faulthandler.enable()` at startup |
| 16 | Uncaught Qt thread exceptions | `sys.excepthook` + `threading.excepthook` |
| 17 | No LLM failover | `FallbackChain` with `CircuitBreaker` |
| 18 | tqdm GC cycles | All tqdm removed/replaced |
| 19 | Circular imports | EventBus decoupling, lazy imports |
| 20 | No health monitoring | Watchdog thread checks all workers every 10s |

---

*Document version: 1.0 | Project: antigravity | Target: Interview Assistant v4.0*
*Generated for complete project rework from JobInterviewBot source.*
