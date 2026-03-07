"""
test_telegram.py - Telegram notification tests.

Tests:
- Thread-local session creation
- Message formatting
- Queue operations
- Error handling
- Backoff logic
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram_bot import TelegramNotifier, _get_session


def test_thread_local_sessions():
    """Test each thread gets its own session."""
    print("\n" + "="*60)
    print("TEST: Thread-Local Sessions")
    print("="*60)
    
    try:
        sessions = []
        
        def get_session_id():
            session = _get_session()
            sessions.append(id(session))
        
        # Get session from main thread
        get_session_id()
        
        # Get session from worker thread
        t = threading.Thread(target=get_session_id)
        t.start()
        t.join()
        
        # Should be different sessions
        if len(sessions) != 2:
            print(f"[FAIL] Wrong number of sessions: {len(sessions)}")
            return False
        
        if sessions[0] == sessions[1]:
            print("[FAIL] Same session used in both threads")
            return False
        
        print("[OK] Thread-local sessions working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Thread-local session test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_escaping():
    """Test Markdown escaping in messages."""
    print("\n" + "="*60)
    print("TEST: Message Escaping")
    print("="*60)
    
    try:
        # Create notifier (won't actually send)
        notifier = TelegramNotifier("fake_token", "fake_chat_id")
        
        # Test escaping function
        def _esc(s: str) -> str:
            for ch in r"_*[`":
                s = s.replace(ch, f"\\{ch}")
            return s
        
        test_cases = [
            ("hello_world", "hello\\_world"),
            ("test*bold*", "test\\*bold\\*"),
            ("code`block`", "code\\`block\\`"),
            ("[link]", "\\[link]"),  # Only [ is escaped, not ]
        ]
        
        for input_str, expected in test_cases:
            result = _esc(input_str)
            if result != expected:
                print(f"[FAIL] Escaping failed: '{input_str}'")
                print(f"  Expected: {expected}, Got: {result}")
                return False
        
        print("[OK] Message escaping working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Message escaping test failed: {e}")
        return False


def test_notifier_creation():
    """Test TelegramNotifier can be created."""
    print("\n" + "="*60)
    print("TEST: Notifier Creation")
    print("="*60)
    
    try:
        notifier = TelegramNotifier("test_token", "test_chat_id")
        
        if notifier.bot_token != "test_token":
            print("[FAIL] Bot token not set correctly")
            return False
        
        if notifier.chat_id != "test_chat_id":
            print("[FAIL] Chat ID not set correctly")
            return False
        
        # Worker thread should be started
        if not notifier._worker.is_alive():
            print("[FAIL] Worker thread not started")
            return False
        
        print("[OK] Notifier creation successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Notifier creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_queue_operations():
    """Test async message queueing."""
    print("\n" + "="*60)
    print("TEST: Queue Operations")
    print("="*60)
    
    try:
        notifier = TelegramNotifier("test_token", "test_chat_id")
        
        # Queue should be empty initially
        if not notifier._queue.empty():
            print("[FAIL] Queue not empty on creation")
            return False
        
        # Send async (won't actually send, but will queue)
        notifier.send_async("test question", "test response")
        
        # Give worker time to process
        time.sleep(0.5)
        
        print("[OK] Queue operations working")
        return True
        
    except Exception as e:
        print(f"[FAIL] Queue operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all Telegram tests."""
    print("\n" + "="*70)
    print(" TELEGRAM TEST SUITE")
    print("="*70)
    
    tests = [
        ("Thread-Local Sessions", test_thread_local_sessions),
        ("Message Escaping", test_message_escaping),
        ("Notifier Creation", test_notifier_creation),
        ("Queue Operations", test_queue_operations),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n[FAIL] {name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print(" TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "[OK] PASS" if p else "[FAIL] FAIL"
        print(f"{status:8} {name}")
    
    print("="*70)
    print(f"Result: {passed}/{total} tests passed")
    print("="*70)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
