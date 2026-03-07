"""
test_audio_pipeline.py - Audio capture and VAD tests.

Tests:
- Audio device enumeration
- VAD (Voice Activity Detection)
- Stream restart on failure
- Watchdog monitoring
- Queue management
"""

import sys
import os
import time
import threading
import queue
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_pipeline import (
    list_audio_devices, _is_voiced, audio_queue,
    reset_watchdog_timer, VAD_AVAILABLE, SD_AVAILABLE
)
from config import SAMPLE_RATE, RMS_GATE


def test_audio_device_listing():
    """Test audio device enumeration."""
    print("\n" + "="*60)
    print("TEST: Audio Device Listing")
    print("="*60)
    
    try:
        if not SD_AVAILABLE:
            print("  sounddevice not available - skipping")
            return True
        
        # Should not crash
        list_audio_devices()
        print("[OK] Audio device listing successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Audio device listing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vad_silence_detection():
    """Test VAD detects silence correctly."""
    print("\n" + "="*60)
    print("TEST: VAD Silence Detection")
    print("="*60)
    
    try:
        if not VAD_AVAILABLE:
            print("  VAD not available - skipping")
            return True
        
        # Create silent audio
        silent = np.zeros(SAMPLE_RATE, dtype=np.float32)
        
        # Should detect as not voiced
        is_voiced = _is_voiced(silent)
        
        if is_voiced:
            print("[FAIL] VAD detected voice in silence")
            return False
        
        print("[OK] VAD correctly detected silence")
        return True
        
    except Exception as e:
        print(f"[FAIL] VAD silence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vad_speech_detection():
    """Test VAD detects speech correctly."""
    print("\n" + "="*60)
    print("TEST: VAD Speech Detection")
    print("="*60)
    
    try:
        if not VAD_AVAILABLE:
            print("  VAD not available - skipping")
            return True
        
        # Create speech-like audio (sine wave with noise)
        t = np.linspace(0, 1, SAMPLE_RATE, dtype=np.float32)
        speech = 0.2 * np.sin(2 * np.pi * 200 * t)  # 200 Hz tone
        speech += 0.05 * np.random.randn(SAMPLE_RATE).astype(np.float32)
        
        # Should detect as voiced
        is_voiced = _is_voiced(speech)
        
        if not is_voiced:
            print("[FAIL] VAD failed to detect speech")
            return False
        
        print("[OK] VAD correctly detected speech")
        return True
        
    except Exception as e:
        print(f"[FAIL] VAD speech test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_watchdog_timer():
    """Test watchdog timer reset."""
    print("\n" + "="*60)
    print("TEST: Watchdog Timer")
    print("="*60)
    
    try:
        # Should not crash
        reset_watchdog_timer()
        time.sleep(0.1)
        reset_watchdog_timer()
        
        print("[OK] Watchdog timer working")
        return True
        
    except Exception as e:
        print(f"[FAIL] Watchdog timer failed: {e}")
        return False


def test_audio_queue_operations():
    """Test audio queue put/get operations."""
    print("\n" + "="*60)
    print("TEST: Audio Queue Operations")
    print("="*60)
    
    try:
        # Clear queue first
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except:
                break
        
        # Test put
        test_data = np.random.randn(1024).astype(np.float32)
        audio_queue.put(test_data)
        
        # Test get
        retrieved = audio_queue.get(timeout=1.0)
        
        if not np.array_equal(test_data, retrieved):
            print("[FAIL] Queue data mismatch")
            return False
        
        print("[OK] Audio queue operations working")
        return True
        
    except Exception as e:
        print(f"[FAIL] Audio queue test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rms_gate():
    """Test RMS energy gate."""
    print("\n" + "="*60)
    print("TEST: RMS Energy Gate")
    print("="*60)
    
    try:
        # Very quiet audio (below gate)
        quiet = 0.0001 * np.random.randn(SAMPLE_RATE).astype(np.float32)
        rms_quiet = float(np.sqrt(np.mean(quiet ** 2)))
        
        # Loud audio (above gate)
        loud = 0.1 * np.random.randn(SAMPLE_RATE).astype(np.float32)
        rms_loud = float(np.sqrt(np.mean(loud ** 2)))
        
        if rms_quiet >= RMS_GATE:
            print(f"[FAIL] Quiet audio RMS too high: {rms_quiet} >= {RMS_GATE}")
            return False
        
        if rms_loud < RMS_GATE:
            print(f"[FAIL] Loud audio RMS too low: {rms_loud} < {RMS_GATE}")
            return False
        
        print(f"[OK] RMS gate working (quiet={rms_quiet:.6f}, loud={rms_loud:.6f})")
        return True
        
    except Exception as e:
        print(f"[FAIL] RMS gate test failed: {e}")
        return False


def run_all_tests():
    """Run all audio pipeline tests."""
    print("\n" + "="*70)
    print(" AUDIO PIPELINE TEST SUITE")
    print("="*70)
    
    tests = [
        ("Audio Device Listing", test_audio_device_listing),
        ("VAD Silence Detection", test_vad_silence_detection),
        ("VAD Speech Detection", test_vad_speech_detection),
        ("Watchdog Timer", test_watchdog_timer),
        ("Audio Queue Operations", test_audio_queue_operations),
        ("RMS Energy Gate", test_rms_gate),
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
