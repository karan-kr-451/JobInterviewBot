"""
audio.filters - Signal processing filters for noise reduction.

Most pro apps (Zoom, Teams) use noise filters to:
1. Remove low-end hum (fans/AC) -> Bandpass filter.
2. Remove high-end hiss -> Bandpass filter.
3. Silence background when no one is talking -> Noise Gate.
"""

import numpy as np
import threading

# Try to import scipy, but make it optional
try:
    from scipy.signal import butter, lfilter, lfilter_zi
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("[Filters] scipy not available - noise filtering disabled")

from config.audio import SAMPLE_RATE


class NoiseFilter:
    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sr = sample_rate
        self.enabled = SCIPY_AVAILABLE
        self._lock = threading.Lock()  # CRITICAL: Thread-safe access to filter state
        
        if not self.enabled:
            print("[Filters] NoiseFilter disabled (scipy not installed)")
            return
        
        # 1. Bandpass Filter (300Hz - 3400Hz - Standard Telephony Range)
        # This removes 60Hz hum and high-frequency static hiss.
        lowcut = 300.0
        highcut = 3400.0
        self.b, self.a = self._butter_bandpass(lowcut, highcut, self.sr, order=5)
        self.zi = None  # Filter state for continuous streaming

        # 2. Adaptive Noise Gate
        self.noise_floor = 0.001
        self.alpha = 0.05  # Smoothing for noise floor estimation

    def _butter_bandpass(self, lowcut, highcut, fs, order=5):
        if not SCIPY_AVAILABLE:
            return None, None
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return b, a

    def apply(self, x: np.ndarray) -> np.ndarray:
        """
        Apply noise reduction pipeline to a chunk of audio.
        
        CRITICAL: This is called from C-level audio callback thread.
        We use a lock to protect filter state, but keep it minimal.
        """
        if len(x) == 0:
            return x
        
        # If scipy not available, return audio unchanged
        if not self.enabled:
            return x

        # CRITICAL: Use try-lock to avoid blocking audio callback
        # If we can't get the lock immediately, return unfiltered audio
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            # Can't get lock - return unfiltered to avoid blocking callback
            return x
        
        try:
            # A. Apply Bandpass Filter
            # We use lfilter_zi to maintain continuity between blocks (no clicking)
            if self.zi is None:
                self.zi = lfilter_zi(self.b, self.a) * x[0]
                
            y, self.zi = lfilter(self.b, self.a, x, zi=self.zi)

            # B. Adaptive Noise Gate
            # Estimate the current RMS of the chunk
            rms = float(np.sqrt(np.mean(y**2)))
            
            # Update noise floor if it's sustained silence
            if rms < self.noise_floor * 2:
                self.noise_floor = (1 - self.alpha) * self.noise_floor + self.alpha * rms

            # Soft Gate: reduce volume if it's likely just noise
            # This prevents background "hiss" from being heard by VAD/Whisper
            threshold = self.noise_floor * 1.5
            if rms < threshold:
                # We don't just kill it (hard gate), we dampen it (soft gate)
                # This sounds more natural and doesn't confuse the VAD
                y *= 0.1

            return y
        finally:
            self._lock.release()
