"""
Simple Stress Test: 100 Questions Direct to LLM
Bypasses audio/transcription, tests LLM pipeline directly
"""

import sys
import os
import time
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize safety
import gc
gc.disable()

print("[TEST] Starting simple stress test...")

# Test questions
QUESTIONS = [
    "What is Python?", "Explain decorators", "How does GIL work?",
    "What are generators?", "List vs tuple?", "What is PEP 8?",
    "Explain async await", "What is self?", "Handle exceptions how?",
    "What is lambda?", "Manage dependencies?", "List comprehensions?",
] * 9  # 108 questions

def run_test():
    from llm.router import configure_backends, get_interview_response
    
    print("[INIT] Configuring LLM...")
    if not configure_backends():
        print("[FAIL] No LLM backend")
        return False
    print("[OK] LLM ready")
    
    # Minimal docs
    docs = {
        "resume_text": "Neha Kaithwas - Frontend Developer with React, Angular, TypeScript",
        "candidate_summary": "Neha Kaithwas, a frontend developer",
        "job_title": "Full Stack Developer",
    }
    
    history = []
    history_lock = threading.Lock()
    
    print(f"\n[START] Testing {len(QUESTIONS)} questions...\n")
    
    success_count = 0
    error_count = 0
    start_time = time.time()
    
    for i, q in enumerate(QUESTIONS, 1):
        try:
            print(f"[{i}/{len(QUESTIONS)}] {q[:40]}...")
            response = get_interview_response(q, history, history_lock, docs, None)
            if response:
                print(f"  -> {len(response)} chars")
                success_count += 1
            else:
                print(f"  -> EMPTY")
                error_count += 1
        except Exception as e:
            print(f"  -> ERROR: {e}")
            error_count += 1
        
        if i % 10 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed
            print(f"\n[PROGRESS] {i}/{len(QUESTIONS)} | Success: {success_count} | Errors: {error_count} | Rate: {rate:.1f} q/s\n")
    
    total_time = time.time() - start_time
    print(f"\n[DONE] {success_count}/{len(QUESTIONS)} successful in {total_time:.1f}s ({len(QUESTIONS)/total_time:.1f} q/s)")
    print(f"[RESULT] Errors: {error_count}")
    
    return error_count == 0

if __name__ == "__main__":
    try:
        success = run_test()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[CRASH] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)
