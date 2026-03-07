"""
crash_detector.py - Enhanced crash detection and logging

Run this INSTEAD of main_gui.py to get detailed crash information.
"""

import sys
import os
import time
import traceback
import threading
import signal
import atexit
from datetime import datetime

# Setup logging FIRST
log_file = f"crash_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_handle = open(log_file, 'a', encoding='utf-8', errors='replace')

# Redirect stdout/stderr to file AND console
class TeeOutput:
    def __init__(self, terminal, log_file):
        self.terminal = terminal
        self.log = log_file
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    
    def fileno(self):
        """Return file descriptor for faulthandler."""
        return self.log.fileno()

original_stdout = sys.stdout
original_stderr = sys.stderr

sys.stdout = TeeOutput(original_stdout, log_handle)
sys.stderr = TeeOutput(original_stderr, log_handle)

print("=" * 80)
print(f"CRASH DETECTOR ACTIVE - Logging to {log_file}")
print("=" * 80)

# Enable faulthandler for segfaults
import faulthandler
try:
    faulthandler.enable(file=log_handle)
    print("[OK] Faulthandler enabled (will catch segfaults)")
except Exception as e:
    print(f"[WARN] Faulthandler failed: {e}")

# Track all threads
def log_all_threads():
    """Log all active threads."""
    print("\n" + "=" * 80)
    print("ACTIVE THREADS:")
    print("=" * 80)
    try:
        for thread in threading.enumerate():
            try:
                # Handle both thread objects and potential tuples
                if hasattr(thread, 'name'):
                    print(f"  - {thread.name} (daemon={thread.daemon}, alive={thread.is_alive()})")
                else:
                    print(f"  - {thread} (unknown type)")
            except Exception as e:
                print(f"  - <error reading thread: {e}>")
    except Exception as e:
        print(f"Error enumerating threads: {e}")
    print("=" * 80 + "\n")

# Monitor thread health
def thread_monitor():
    """Monitor thread health every 5 seconds."""
    while True:
        time.sleep(5)
        log_all_threads()

monitor_thread = threading.Thread(target=thread_monitor, daemon=True, name="crash-monitor")
monitor_thread.start()
print("[OK] Thread monitor started")

# Catch ALL exceptions
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Catch all uncaught exceptions."""
    print("\n" + "!" * 80)
    print("UNCAUGHT EXCEPTION IN MAIN THREAD")
    print("!" * 80)
    print(f"Type: {exc_type.__name__}")
    print(f"Value: {exc_value}")
    print("\nTraceback:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print("!" * 80 + "\n")
    
    # Keep process alive for inspection
    print("Process will stay alive for 10 seconds for inspection...")
    time.sleep(10)

sys.excepthook = global_exception_handler
print("[OK] Global exception handler installed")

# Catch thread exceptions
def thread_exception_handler(args):
    """Catch exceptions in threads."""
    print("\n" + "!" * 80)
    print(f"UNCAUGHT EXCEPTION IN THREAD: {args.thread.name}")
    print("!" * 80)
    print(f"Type: {args.exc_type.__name__}")
    print(f"Value: {args.exc_value}")
    print("\nTraceback:")
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    print("!" * 80 + "\n")

threading.excepthook = thread_exception_handler
print("[OK] Thread exception handler installed")

# Catch signals
def signal_handler(signum, frame):
    """Catch termination signals."""
    print("\n" + "!" * 80)
    print(f"SIGNAL RECEIVED: {signum}")
    print("!" * 80)
    print(f"Signal name: {signal.Signals(signum).name}")
    print("\nStack trace:")
    traceback.print_stack(frame)
    print("!" * 80 + "\n")
    log_all_threads()
    sys.exit(1)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, signal_handler)
print("[OK] Signal handlers installed")

# Log exit
def exit_handler():
    """Log normal exit."""
    print("\n" + "=" * 80)
    print("PROCESS EXITING NORMALLY")
    print("=" * 80)
    print(f"Time: {datetime.now()}")
    log_all_threads()
    print("=" * 80 + "\n")

atexit.register(exit_handler)
print("[OK] Exit handler installed")

# Memory monitoring
def memory_monitor():
    """Monitor memory usage."""
    try:
        import psutil
        process = psutil.Process()
        
        while True:
            time.sleep(10)
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)
            
            print(f"\n[MEMORY] {mem_mb:.0f} MB used")
            
            if mem_mb > 1500:
                print(f"[MEMORY] WARNING: High memory usage ({mem_mb:.0f} MB)")
            
            if mem_mb > 2000:
                print(f"[MEMORY] CRITICAL: Very high memory usage ({mem_mb:.0f} MB)")
                log_all_threads()
    except ImportError:
        print("[WARN] psutil not available - memory monitoring disabled")
    except Exception as e:
        print(f"[MEMORY] Monitor error: {e}")

mem_thread = threading.Thread(target=memory_monitor, daemon=True, name="memory-monitor")
mem_thread.start()
print("[OK] Memory monitor started")

# Watchdog for silent crashes
last_activity = [time.time()]

def update_activity():
    """Call this from main loop to show activity."""
    last_activity[0] = time.time()

def watchdog():
    """Detect if main thread dies unexpectedly."""
    while True:
        time.sleep(15)
        if not threading.main_thread().is_alive():
            print("\n" + "!" * 80)
            print("WATCHDOG: Main thread has died unexpectedly!")
            print("!" * 80)
            log_all_threads()
            print("!" * 80 + "\n")
            sys.exit(1)

watchdog_thread = threading.Thread(target=watchdog, daemon=True, name="watchdog")
watchdog_thread.start()
print("[OK] Watchdog started")

print("\n" + "=" * 80)
print("ALL CRASH DETECTION SYSTEMS ACTIVE")
print("=" * 80)
print(f"Log file: {log_file}")
print("Starting main application...")
print("=" * 80 + "\n")

# Now import and run the actual application
try:
    # Update activity marker
    update_activity()
    
    # Import main_gui
    print("Importing main_gui...")
    import main_gui
    
    # Patch to update activity
    original_start = main_gui.InterviewAssistantGUI._start_pipeline
    
    def patched_start(self):
        update_activity()
        return original_start(self)
    
    main_gui.InterviewAssistantGUI._start_pipeline = patched_start
    
    # Run
    print("Starting GUI...")
    update_activity()
    main_gui.main()
    
except KeyboardInterrupt:
    print("\n\nKeyboard interrupt - exiting cleanly")
    sys.exit(0)
    
except Exception as e:
    print("\n" + "!" * 80)
    print("EXCEPTION IN MAIN")
    print("!" * 80)
    print(f"Type: {type(e).__name__}")
    print(f"Value: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    print("!" * 80 + "\n")
    log_all_threads()
    
    # Keep alive for inspection
    print("\nKeeping process alive for 30 seconds for inspection...")
    time.sleep(30)
    sys.exit(1)

finally:
    print("\n" + "=" * 80)
    print("CRASH DETECTOR SHUTTING DOWN")
    print("=" * 80)
    print(f"Check log file: {log_file}")
    print("=" * 80 + "\n")
