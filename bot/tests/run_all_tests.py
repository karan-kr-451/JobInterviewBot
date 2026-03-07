"""
run_all_tests.py - Master test runner.

Runs all test suites and generates comprehensive report.
"""

import sys
import os
import time
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all test modules
import test_crash_prevention
import test_transcriber
import test_audio_pipeline
import test_llm
import test_telegram


def run_test_suite(name, module):
    """Run a test suite and return results."""
    print(f"\n{'='*70}")
    print(f" Running: {name}")
    print(f"{'='*70}")
    
    start_time = time.time()
    
    try:
        success = module.run_all_tests()
        elapsed = time.time() - start_time
        return {
            "name": name,
            "success": success,
            "elapsed": elapsed,
            "error": None
        }
    except Exception as e:
        elapsed = time.time() - start_time
        import traceback
        return {
            "name": name,
            "success": False,
            "elapsed": elapsed,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def main():
    """Run all test suites."""
    print("\n" + "="*70)
    print(" INTERVIEW BOT - COMPREHENSIVE TEST SUITE")
    print(f" Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    test_suites = [
        ("Crash Prevention", test_crash_prevention),
        ("Transcriber", test_transcriber),
        ("Audio Pipeline", test_audio_pipeline),
        ("LLM & Classification", test_llm),
        ("Telegram Notifications", test_telegram),
    ]
    
    results = []
    total_start = time.time()
    
    for name, module in test_suites:
        result = run_test_suite(name, module)
        results.append(result)
        
        # Brief pause between suites
        time.sleep(0.5)
    
    total_elapsed = time.time() - total_start
    
    # Generate comprehensive report
    print("\n" + "="*70)
    print(" COMPREHENSIVE TEST REPORT")
    print("="*70)
    
    passed_suites = sum(1 for r in results if r["success"])
    total_suites = len(results)
    
    print(f"\nOverall: {passed_suites}/{total_suites} test suites passed")
    print(f"Total time: {total_elapsed:.2f}s\n")
    
    print("Suite Results:")
    print("-" * 70)
    
    for result in results:
        status = "[OK] PASS" if result["success"] else "[FAIL] FAIL"
        elapsed = result["elapsed"]
        name = result["name"]
        
        print(f"{status:8} {name:30} ({elapsed:.2f}s)")
        
        if result["error"]:
            print(f"         Error: {result['error']}")
    
    print("-" * 70)
    
    # Detailed failures
    failures = [r for r in results if not r["success"]]
    if failures:
        print("\n" + "="*70)
        print(" FAILURE DETAILS")
        print("="*70)
        
        for result in failures:
            print(f"\n{result['name']}:")
            print("-" * 70)
            if result.get("traceback"):
                print(result["traceback"])
            else:
                print(f"Error: {result['error']}")
    
    # Recommendations
    print("\n" + "="*70)
    print(" RECOMMENDATIONS")
    print("="*70)
    
    if passed_suites == total_suites:
        print("\n[OK] All test suites passed!")
        print("\nNext steps:")
        print("  1. Application is ready for production testing")
        print("  2. Monitor crash.log during real usage")
        print("  3. Run tests periodically to catch regressions")
    else:
        print(f"\n[WARN]  {total_suites - passed_suites} test suite(s) failed")
        print("\nAction items:")
        print("  1. Review failure details above")
        print("  2. Fix failing tests")
        print("  3. Re-run: python tests/run_all_tests.py")
        print("  4. Check dependencies are installed:")
        print("     - pip install faster-whisper sounddevice numpy requests")
    
    # Save report to file
    report_file = "test_report.txt"
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"Interview Bot Test Report\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*70}\n\n")
            f.write(f"Overall: {passed_suites}/{total_suites} test suites passed\n")
            f.write(f"Total time: {total_elapsed:.2f}s\n\n")
            
            for result in results:
                status = "PASS" if result["success"] else "FAIL"
                f.write(f"{status:8} {result['name']:30} ({result['elapsed']:.2f}s)\n")
                if result["error"]:
                    f.write(f"         Error: {result['error']}\n")
            
            if failures:
                f.write(f"\n{'='*70}\n")
                f.write("FAILURE DETAILS\n")
                f.write(f"{'='*70}\n\n")
                for result in failures:
                    f.write(f"{result['name']}:\n")
                    f.write("-" * 70 + "\n")
                    if result.get("traceback"):
                        f.write(result["traceback"] + "\n")
        
        print(f"\n  Report saved to: {report_file}")
    except Exception as e:
        print(f"\n[WARN]  Could not save report: {e}")
    
    print("\n" + "="*70)
    
    return 0 if passed_suites == total_suites else 1


if __name__ == "__main__":
    sys.exit(main())
