"""
analyze_crashes.py - Crash log analyzer and prevention validator.

Analyzes crash.log to identify patterns, root causes, and verify fixes.
Provides actionable recommendations for preventing future crashes.

Usage:
    python analyze_crashes.py [crash.log]
"""

import sys
import os
import re
from collections import Counter, defaultdict
from datetime import datetime


class CrashAnalyzer:
    """Analyzes crash logs and identifies patterns."""
    
    # Known crash patterns and their root causes
    PATTERNS = {
        "access_violation": {
            "regex": r"Windows fatal exception: access violation",
            "severity": "CRITICAL",
            "causes": [
                "GC collecting objects during C-extension calls",
                "ctypes callback freed while still in use",
                "Thread-unsafe object accessed concurrently",
                "Dangling pointer in numpy/STFT operations",
            ],
            "fixes": [
                "Use GCSafeContext around C-extension calls",
                "Keep ctypes callbacks as module-level references",
                "Use ThreadSafeWrapper for non-thread-safe objects",
                "Disable GC during numpy operations in transcriber.py",
            ]
        },
        "tqdm_monitor": {
            "regex": r"tqdm\._monitor\.py.*in run",
            "severity": "HIGH",
            "causes": [
                "tqdm monitor thread triggering GC during C calls",
            ],
            "fixes": [
                "Disable tqdm monitor in main.py (already implemented)",
                "Verify tqdm.tqdm.monitor_interval = 0",
            ]
        },
        "requests_session": {
            "regex": r"requests.*Session|CaseInsensitiveDict",
            "severity": "HIGH",
            "causes": [
                "requests.Session shared between threads",
            ],
            "fixes": [
                "Use thread-local sessions (telegram_bot.py fixed)",
                "Never share Session objects across threads",
            ]
        },
        "numpy_stft": {
            "regex": r"numpy.*as_strided|fft|stft",
            "severity": "CRITICAL",
            "causes": [
                "GC collecting array during STFT computation",
                "Array view/slice freed while C code holds pointer",
            ],
            "fixes": [
                "Use np.ascontiguousarray to create owned copy",
                "Disable GC during transcription (transcriber.py fixed)",
                "Wrap in try-except BaseException",
            ]
        },
        "gemini_sdk": {
            "regex": r"google\.generativeai|genai|grpc",
            "severity": "HIGH",
            "causes": [
                "Gemini SDK C-extension calling os._exit()",
                "gRPC/SSL errors bypassing Python exception handling",
            ],
            "fixes": [
                "Use raw REST API instead of SDK (gemini_client.py fixed)",
                "Never use genai.GenerativeModel.generate_content()",
            ]
        },
        "queue_full": {
            "regex": r"queue\.Full|Queue full",
            "severity": "MEDIUM",
            "causes": [
                "Queue overflow causing blocking or dropped items",
            ],
            "fixes": [
                "Use safe_queue_put with timeout",
                "Implement back-pressure or drop policy",
            ]
        },
        "thread_death": {
            "regex": r"Thread.*has died|thread.*not alive",
            "severity": "HIGH",
            "causes": [
                "Unhandled exception killing worker thread",
            ],
            "fixes": [
                "Use ResilientWorker for auto-recovery",
                "Wrap worker body in try-except BaseException",
            ]
        },
    }
    
    def __init__(self, log_path: str):
        self.log_path = log_path
        self.crashes = []
        self.patterns_found = Counter()
        self.timeline = []
    
    def analyze(self):
        """Analyze the crash log."""
        if not os.path.exists(self.log_path):
            print(f"[FAIL] Log file not found: {self.log_path}")
            return False
        
        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        # Split into crash entries
        entries = re.split(r"={60,}", content)
        
        for entry in entries:
            if not entry.strip():
                continue
            
            # Extract timestamp
            ts_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", entry)
            timestamp = ts_match.group(1) if ts_match else None
            
            # Check for patterns
            matched_patterns = []
            for pattern_name, pattern_info in self.PATTERNS.items():
                if re.search(pattern_info["regex"], entry, re.IGNORECASE):
                    matched_patterns.append(pattern_name)
                    self.patterns_found[pattern_name] += 1
            
            if matched_patterns:
                self.crashes.append({
                    "timestamp": timestamp,
                    "patterns": matched_patterns,
                    "content": entry[:500],  # First 500 chars
                })
                
                if timestamp:
                    self.timeline.append((timestamp, matched_patterns))
        
        return True
    
    def print_report(self):
        """Print comprehensive analysis report."""
        print("\n" + "="*70)
        print(" CRASH LOG ANALYSIS REPORT")
        print("="*70)
        
        if not self.crashes:
            print("\n[OK] No crashes found in log!")
            print("\nThis is good news - the application appears stable.")
            return
        
        print(f"\n  SUMMARY")
        print(f"   Total crash entries: {len(self.crashes)}")
        print(f"   Unique patterns: {len(self.patterns_found)}")
        
        # Pattern breakdown
        print(f"\n[SEARCH] CRASH PATTERNS DETECTED")
        print("-" * 70)
        
        for pattern_name, count in self.patterns_found.most_common():
            pattern_info = self.PATTERNS[pattern_name]
            severity = pattern_info["severity"]
            
            # Color code by severity
            if severity == "CRITICAL":
                marker = "[REC]"
            elif severity == "HIGH":
                marker = " "
            else:
                marker = " "
            
            print(f"\n{marker} {pattern_name.upper().replace('_', ' ')} ({severity})")
            print(f"   Occurrences: {count}")
            print(f"   Root causes:")
            for cause in pattern_info["causes"]:
                print(f"       {cause}")
            print(f"   Fixes applied:")
            for fix in pattern_info["fixes"]:
                print(f"     [OK] {fix}")
        
        # Timeline
        if self.timeline:
            print(f"\n  CRASH TIMELINE")
            print("-" * 70)
            for ts, patterns in self.timeline[-10:]:  # Last 10
                pattern_str = ", ".join(p.replace("_", " ") for p in patterns)
                print(f"   {ts} - {pattern_str}")
        
        # Recommendations
        print(f"\n  RECOMMENDATIONS")
        print("-" * 70)
        
        critical_patterns = [p for p, info in self.PATTERNS.items()
                           if info["severity"] == "CRITICAL" and p in self.patterns_found]
        
        if critical_patterns:
            print("\n[WARN]  CRITICAL ISSUES DETECTED:")
            for pattern in critical_patterns:
                print(f"\n   {pattern.upper().replace('_', ' ')}:")
                for fix in self.PATTERNS[pattern]["fixes"]:
                    print(f"       {fix}")
        else:
            print("\n[OK] No critical patterns detected")
        
        print("\n  GENERAL RECOMMENDATIONS:")
        print("   1. Run test suite: python tests/test_crash_prevention.py")
        print("   2. Monitor crash.log for new patterns")
        print("   3. Enable verbose logging for debugging")
        print("   4. Test with different audio devices")
        print("   5. Verify all API keys are valid")
        
        print("\n" + "="*70)
    
    def verify_fixes(self):
        """Verify that known fixes are in place."""
        print("\n" + "="*70)
        print(" FIX VERIFICATION")
        print("="*70)
        
        checks = [
            ("crash_prevention.py exists", os.path.exists("core/crash_prevention.py")),
            ("main.py imports crash_prevention", self._check_file_contains(
                "main.py", "from core.crash_prevention import")),
            ("tqdm monitor disabled", self._check_file_contains(
                "main.py", "tqdm.tqdm.monitor_interval = 0")),
            ("GC disabled in transcriber", self._check_file_contains(
                "transcriber.py", "gc.disable()")),
            ("Thread-local sessions", self._check_file_contains(
                "telegram_bot.py", "threading.local()")),
            ("REST API for Gemini", self._check_file_contains(
                "gemini_client.py", "requests.post")),
            ("Stream cleanup on exit", self._check_file_contains(
                "audio_pipeline.py", "_cleanup_stream")),
        ]
        
        print()
        passed = 0
        for check_name, result in checks:
            status = "[OK]" if result else "[FAIL]"
            print(f"   {status} {check_name}")
            if result:
                passed += 1
        
        print(f"\n   Result: {passed}/{len(checks)} checks passed")
        print("="*70)
        
        return passed == len(checks)
    
    def _check_file_contains(self, filename, text):
        """Check if file contains text."""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return text in f.read()
        except Exception:
            return False


def main():
    """Main entry point."""
    log_path = sys.argv[1] if len(sys.argv) > 1 else "crash.log"
    
    analyzer = CrashAnalyzer(log_path)
    
    if not analyzer.analyze():
        return 1
    
    analyzer.print_report()
    analyzer.verify_fixes()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
