"""
Full Pipeline Stress Test: 100 Questions
Simulates audio -> VAD -> transcription -> LLM -> response
Uses main_gui pipeline entry point for realistic testing
"""

import sys
import os
import time
import threading
import numpy as np
from collections import deque

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# -- 1. Initialize Safety Systems ---------------------------------------------
import gc
gc.disable()
print("[STRESS TEST] GC disabled")

from core.session_guardian import install_global_exception_handlers
install_global_exception_handlers()

from core.enterprise_crash_prevention import initialize_enterprise_crash_prevention
initialize_enterprise_crash_prevention()

# -- 2. Prepare 100 Questions -------------------------------------------------
QUESTIONS = [
    "What is Python?", "Explain decorators in Python.", "How does memory management work in Python?",
    "What are generators?", "Difference between list and tuple.", "What is PEP 8?",
    "Explain the Global Interpreter Lock.", "What is use of self in classes?",
    "How do you handle exceptions in Python?", "What is a lambda function?",
    "How to manage dependencies in Python?", "Explain list comprehensions.",
    "What is the difference between deep and shallow copy?", "What are dunder methods?",
    "Explain the difference between is and equals", "What is a virtual environment?",
    "How to use multi-threading in Python?", "Difference between multi-threading and multi-processing.",
    "What is recursion?", "Explain the with statement.",
    "What is React?", "Explain the virtual DOM.", "What are hooks in React?",
    "Difference between functional and class components.", "What is Redux?",
    "How does useEffect work?", "What is the purpose of keys in React?",
    "Explain React Context API.", "What is JSX?", "How to optimize React performance?",
    "What is a Higher-Order Component?", "Explain lifting state up.",
    "What is the difference between state and props?", "What are controlled vs uncontrolled components?",
    "Explain the React lifecycle methods.", "What is React Fiber?",
    "How to handle routing in React?", "What is server-side rendering?",
    "Explain the use of ref in React.", "What are styled-components?",
    "What is JavaScript?", "Explain closures in JS.", "What is the event loop?",
    "Difference between let const and var.", "What are promises?",
    "Explain async await.", "What is this keyword in JS?",
    "Difference between double equals and triple equals", "What is a prototype chain?",
    "What are arrow functions?", "Explain event bubbling and capturing.",
    "What is hoisting?", "How does AJAX work?", "What is strict mode?",
    "Explain the ternary operator.", "What is a callback function?",
    "How to handle JSON in JS?", "What is a spread operator?",
    "Difference between Map and Set.", "What is the DOM?",
    "What is SQL?", "Explain primary key vs foreign key.", "What is a join in SQL?",
    "Difference between INNER and OUTER JOIN.", "What is an index in a database?",
    "Explain database normalization.", "What is an ACID transaction?",
    "What is NoSQL?", "Difference between SQL and NoSQL.", "What is MongoDB?",
    "Explain CAP theorem.", "What is Redis?", "How to optimize SQL queries?",
    "What is a stored procedure?", "Explain database sharding.",
    "What is Docker?", "Explain containers vs virtual machines.", "What is Kubernetes?",
    "What is CI CD?", "Explain Git workflow.", "How to use git rebase?",
    "What is a pull request?", "Explain microservices architecture.",
    "What is an API?", "Difference between REST and GraphQL.",
    "What is OAuth?", "Explain JWT.", "How to secure a web application?",
    "What is CORS?", "Explain the box model in CSS.",
    "What is Flexbox?", "What is CSS Grid?", "Difference between responsive and adaptive design.",
    "What is unit testing?", "Explain Test-Driven Development.",
    "What is a mock object?", "Explain the SOLID principles.",
    "What is Big O notation?", "Explain the binary search algorithm.",
    "What is a linked list?", "Explain the difference between stack and queue."
]

# -- 3. Mock Transcription to Return Questions --------------------------------
question_index = [0]  # Use list to allow modification in nested function
question_lock = threading.Lock()

def mock_transcribe_groq(audio, prompt=None):
    """Mock transcription that returns our test questions."""
    with question_lock:
        if question_index[0] < len(QUESTIONS):
            q = QUESTIONS[question_index[0]]
            question_index[0] += 1
            print(f"  [TRANSCRIBE] Returning question {question_index[0]}/{len(QUESTIONS)}: '{q[:50]}...'")
            return q
        return None

# -- 4. Response Tracker ------------------------------------------------------
class ResponseTracker:
    def __init__(self):
        self.responses = []
        self.lock = threading.Lock()
        self.errors = []
        
    def track_response(self, question, response):
        with self.lock:
            self.responses.append((question, response))
            print(f"  [RESPONSE {len(self.responses)}/{len(QUESTIONS)}] Q: '{question[:40]}...' -> A: {len(response)} chars")
    
    def track_error(self, question, error):
        with self.lock:
            self.errors.append((question, str(error)))
            print(f"  [ERROR] Q: '{question[:40]}...' -> {error}")
    
    def get_stats(self):
        with self.lock:
            return {
                "total": len(QUESTIONS),
                "responses": len(self.responses),
                "errors": len(self.errors),
                "success_rate": len(self.responses) / len(QUESTIONS) * 100 if QUESTIONS else 0
            }

# -- 5. Simulate Audio Chunks -------------------------------------------------
def simulate_audio_for_question(audio_queue, duration_sec=2.0, sample_rate=16000, chunk_duration=0.1):
    """
    Simulate speech by adding audio chunks to the queue.
    This mimics what the audio callback does.
    """
    num_chunks = int(duration_sec / chunk_duration)
    for _ in range(num_chunks):
        # Generate audio with some "voice-like" characteristics
        samples = int(sample_rate * chunk_duration)
        # Add some amplitude to trigger VAD
        audio = np.random.normal(0, 0.05, samples).astype(np.float32)
        audio_queue.append(audio.reshape(-1, 1))
        time.sleep(chunk_duration * 0.8)  # Slightly faster than real-time

# -- 6. Main Stress Test ------------------------------------------------------
def run_stress_test():
    print("\n" + "="*80)
    print("FULL PIPELINE STRESS TEST: 100 QUESTIONS")
    print("Audio Queue -> VAD -> Transcription (Mock) -> LLM -> Response")
    print("="*80 + "\n")
    
    # Import after safety systems initialized
    from llm.documents import load_documents, summarize_candidate
    from llm.router import configure_backends
    from llm.worker import make_llm_worker
    import transcription.worker as tr_worker
    from audio.capture import audio_queue
    
    # Patch transcription to use our mock
    import transcription.groq_whisper as gw
    original_transcribe = gw.transcribe_groq
    gw.transcribe_groq = mock_transcribe_groq
    
    try:
        # Initialize
        print("[INIT] Loading documents...")
        docs = load_documents()
        print(f"  OK Loaded {len(docs.get('resume_files', []))} resume(s), {len(docs.get('project_files', []))} project(s)")
        
        print("[INIT] Generating candidate summary...")
        docs["candidate_summary"] = summarize_candidate(docs)
        print(f"  OK {docs['candidate_summary'][:80]}...")
        
        print("[INIT] Configuring LLM backend...")
        if not configure_backends():
            print("  X No LLM backend available")
            return False
        print("  OK LLM backend ready")
        
        # Shared state
        history = []
        history_lock = threading.Lock()
        tracker = ResponseTracker()
        
        # Create a mock notifier that tracks responses
        class MockNotifier:
            def send_async(self, question, response):
                tracker.track_response(question, response)
        
        notifier = MockNotifier()
        
        # Start workers
        print("[INIT] Starting transcription workers...")
        tr_threads = tr_worker.start_workers(docs)
        print(f"  OK Started {len(tr_threads)} transcription worker(s)")
        
        print("[INIT] Starting LLM worker...")
        llm_worker = make_llm_worker(history, history_lock, docs, notifier)
        llm_worker.start()
        print("  OK LLM worker started")
        
        print("\n" + "="*80)
        print("STARTING TEST - Simulating 100 questions...")
        print("="*80 + "\n")
        
        start_time = time.time()
        
        # Simulate questions
        for i in range(len(QUESTIONS)):
            print(f"\n[{i+1}/{len(QUESTIONS)}] Simulating audio for question...")
            
            # Simulate audio chunks (this will trigger VAD -> transcription -> LLM)
            simulate_audio_for_question(audio_queue, duration_sec=2.0)
            
            # Wait a bit for processing
            time.sleep(1.0)
            
            # Progress update every 10 questions
            if (i + 1) % 10 == 0:
                stats = tracker.get_stats()
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(f"\n{'='*80}")
                print(f"PROGRESS: {i+1}/{len(QUESTIONS)} questions simulated")
                print(f"Responses: {stats['responses']}, Errors: {stats['errors']}")
                print(f"Rate: {rate:.1f} q/s, Elapsed: {elapsed:.1f}s")
                print(f"{'='*80}\n")
        
        # Wait for all responses
        print("\n[WAIT] All questions simulated. Waiting for responses...")
        timeout = 300  # 5 minutes
        wait_start = time.time()
        
        while True:
            stats = tracker.get_stats()
            if stats['responses'] + stats['errors'] >= len(QUESTIONS):
                break
            if time.time() - wait_start > timeout:
                print(f"\n[TIMEOUT] Reached timeout after {timeout}s")
                break
            time.sleep(2.0)
        
        # Final report
        total_time = time.time() - start_time
        stats = tracker.get_stats()
        
        print("\n" + "="*80)
        print("STRESS TEST COMPLETE")
        print("="*80)
        print(f"Total Questions: {stats['total']}")
        print(f"Successful Responses: {stats['responses']} ({stats['success_rate']:.1f}%)")
        print(f"Errors: {stats['errors']}")
        print(f"Total Time: {total_time:.1f}s")
        print(f"Average Time/Question: {total_time/max(1, stats['responses']):.2f}s")
        print("="*80 + "\n")
        
        if tracker.errors:
            print("ERRORS:")
            for q, e in tracker.errors[:10]:
                print(f"  - {q[:50]}... -> {e[:100]}")
            if len(tracker.errors) > 10:
                print(f"  ... and {len(tracker.errors)-10} more")
            print()
        
        return stats['errors'] == 0
        
    finally:
        # Restore original transcription
        gw.transcribe_groq = original_transcribe

if __name__ == "__main__":
    try:
        success = run_stress_test()
        if success:
            print("[PASS] ALL TESTS PASSED")
            sys.exit(0)
        else:
            print("[FAIL] SOME TESTS FAILED")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[STOP] Test interrupted by user")
        sys.exit(2)
    except Exception as e:
        print(f"\n\n[CRASH] Test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)
