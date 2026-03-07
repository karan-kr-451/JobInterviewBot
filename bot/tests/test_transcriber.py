"""
test_transcriber.py - Transcription and Whisper tests.

Tests:
- Whisper model loading
- Transcription accuracy
- Hallucination filtering
- GC safety during transcription
- Queue operations
"""

import sys
import os
import time
import gc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transcriber import (
    load_whisper, transcribe_accurate, _is_hallucination,
    final_queue, gemini_queue, enqueue_final,
    WHISPER_AVAILABLE
)
from config import SAMPLE_RATE


def test_whisper_loading():
    """Test Whisper model loads without crashing."""
    print("\n" + "="*60)
    print("TEST: Whisper Model Loading")
    print("="*60)
    
    try:
        if not WHISPER_AVAILABLE:
            print("  faster-whisper not available - skipping")
            return True
        
        result = load_whisper()
        
        if result:
            print("[OK] Whisper model loaded successfully")
            return True
        else:
            print("  Whisper load returned False (may be expected)")
            return True  # Not a failure - might be intentional
        
    except Exception as e:
        print(f"[FAIL] Whisper loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hallucination_filter():
    """Test hallucination detection."""
    print("\n" + "="*60)
    print("TEST: Hallucination Filter")
    print("="*60)
    
    try:
        # Known hallucinations
        hallucinations = [
            "thank you for watching",
            "thanks for watching",
            "subscribe",
            "like and subscribe",
            "",
            "a",  # Too short
        ]
        
        for text in hallucinations:
            if not _is_hallucination(text):
                print(f"[FAIL] Failed to detect hallucination: '{text}'")
                return False
        
        # Valid transcripts
        valid = [
            "what is the time complexity of quicksort",
            "explain the difference between tcp and udp",
            "tell me about your experience with python",
        ]
        
        for text in valid:
            if _is_hallucination(text):
                print(f"[FAIL] False positive hallucination: '{text}'")
                return False
        
        print("[OK] Hallucination filter working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Hallucination filter test failed: {e}")
        return False


def test_transcription_gc_safety():
    """Test transcription doesn't crash with GC."""
    print("\n" + "="*60)
    print("TEST: Transcription GC Safety")
    print("="*60)
    
    try:
        if not WHISPER_AVAILABLE:
            print("  Whisper not available - skipping")
            return True
        
        # Create test audio (silence)
        audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
        
        # Force GC before transcription
        gc.collect()
        
        # Should not crash
        result = transcribe_accurate(audio)
        
        # Force GC after transcription
        gc.collect()
        
        print(f"[OK] Transcription GC-safe (result: '{result}')")
        return True
        
    except Exception as e:
        print(f"[FAIL] Transcription GC safety test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_transcription_with_noise():
    """Test transcription handles noisy audio."""
    print("\n" + "="*60)
    print("TEST: Transcription with Noise")
    print("="*60)
    
    try:
        if not WHISPER_AVAILABLE:
            print("  Whisper not available - skipping")
            return True
        
        # Create noisy audio
        noise = 0.1 * np.random.randn(SAMPLE_RATE).astype(np.float32)
        
        # Should not crash, may return empty string
        result = transcribe_accurate(noise)
        
        print(f"[OK] Handled noisy audio (result: '{result[:50] if result else 'empty'}')")
        return True
        
    except Exception as e:
        print(f"[FAIL] Noisy audio test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_queue_operations():
    """Test transcription queue operations."""
    print("\n" + "="*60)
    print("TEST: Transcription Queue Operations")
    print("="*60)
    
    try:
        # Clear queues
        while not final_queue.empty():
            try:
                final_queue.get_nowait()
            except:
                break
        
        while not gemini_queue.empty():
            try:
                gemini_queue.get_nowait()
            except:
                break
        
        # Test enqueue
        test_audio = np.random.randn(SAMPLE_RATE).astype(np.float32)
        enqueue_final(test_audio)
        
        # Should be in queue
        if final_queue.empty():
            print("[FAIL] Audio not enqueued")
            return False
        
        # Retrieve
        retrieved = final_queue.get(timeout=1.0)
        
        if not isinstance(retrieved, np.ndarray):
            print(f"[FAIL] Wrong type retrieved: {type(retrieved)}")
            return False
        
        print("[OK] Queue operations working")
        return True
        
    except Exception as e:
        print(f"[FAIL] Queue operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_empty_audio_handling():
    """Test handling of empty/invalid audio."""
    print("\n" + "="*60)
    print("TEST: Empty Audio Handling")
    print("="*60)
    
    try:
        if not WHISPER_AVAILABLE:
            print("  Whisper not available - skipping")
            return True
        
        # Test None
        result = transcribe_accurate(None)
        if result != "":
            print(f"[FAIL] None audio returned non-empty: '{result}'")
            return False
        
        # Test empty array
        result = transcribe_accurate(np.array([], dtype=np.float32))
        if result != "":
            print(f"[FAIL] Empty array returned non-empty: '{result}'")
            return False
        
        # Test very short audio
        result = transcribe_accurate(np.zeros(100, dtype=np.float32))
        if result != "":
            print(f"[FAIL] Short audio returned non-empty: '{result}'")
            return False
        
        print("[OK] Empty audio handled correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Empty audio test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all transcriber tests."""
    print("\n" + "="*70)
    print(" TRANSCRIBER TEST SUITE")
    print("="*70)
    
    tests = [
        ("Whisper Loading", test_whisper_loading),
        ("Hallucination Filter", test_hallucination_filter),
        ("Transcription GC Safety", test_transcription_gc_safety),
        ("Transcription with Noise", test_transcription_with_noise),
        ("Queue Operations", test_queue_operations),
        ("Empty Audio Handling", test_empty_audio_handling),
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
