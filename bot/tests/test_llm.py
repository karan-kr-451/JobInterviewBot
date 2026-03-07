"""
test_llm.py - LLM and classification tests.

Tests:
- Question classification
- Prompt building
- Backend selection
- Duplicate detection
- Response generation (mocked)
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemini_client import (
    classify_question, build_prompt, _is_duplicate,
    _effective_backend, DOMAIN_KEYWORDS, CATEGORY_KEYWORDS
)


def test_question_classification():
    """Test question classification accuracy."""
    print("\n" + "="*60)
    print("TEST: Question Classification")
    print("="*60)
    
    try:
        test_cases = [
            ("write a function to reverse a linked list", "CODING"),
            ("explain the difference between tcp and udp", "CONCEPT"),
            ("tell me about yourself", "BEHAVIORAL"),
            ("how would you design a url shortener", "SYSTEM_DESIGN"),
            ("walk me through your resume", "PROJECT"),
        ]
        
        for question, expected_category in test_cases:
            domain, category = classify_question(question)
            
            if category != expected_category:
                print(f"[FAIL] Misclassified: '{question}'")
                print(f"  Expected: {expected_category}, Got: {category}")
                return False
        
        print("[OK] Question classification working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Classification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_domain_detection():
    """Test domain detection."""
    print("\n" + "="*60)
    print("TEST: Domain Detection")
    print("="*60)
    
    try:
        test_cases = [
            ("explain backpropagation in neural networks", "DEEP_LEARNING"),
            ("what is named entity recognition", "NLP"),
            ("how does yolo object detection work", "COMPUTER_VISION"),
            ("explain random forest algorithm", "MACHINE_LEARNING"),
        ]
        
        for question, expected_domain in test_cases:
            domain, category = classify_question(question)
            
            if domain != expected_domain:
                print(f"[FAIL] Wrong domain: '{question}'")
                print(f"  Expected: {expected_domain}, Got: {domain}")
                return False
        
        print("[OK] Domain detection working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Domain detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_prompt_building():
    """Test prompt construction."""
    print("\n" + "="*60)
    print("TEST: Prompt Building")
    print("="*60)
    
    try:
        question = "what is the difference between tcp and udp"
        domain = "SOFTWARE_ENGINEERING"
        category = "CONCEPT"
        history = []
        docs = {
            "resume": "Software Engineer with 5 years experience",
            "projects": "Built distributed systems",
        }
        
        prompt = build_prompt(question, domain, category, history, docs)
        
        # Check prompt contains key elements
        if question not in prompt:
            print("[FAIL] Prompt missing question")
            return False
        
        if domain not in prompt:
            print("[FAIL] Prompt missing domain")
            return False
        
        if docs["resume"] not in prompt:
            print("[FAIL] Prompt missing resume")
            return False
        
        print("[OK] Prompt building working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Prompt building test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_duplicate_detection():
    """Test duplicate question detection."""
    print("\n" + "="*60)
    print("TEST: Duplicate Detection")
    print("="*60)
    
    try:
        # Clear recent questions
        from gemini_client import _recent_questions, _recent_lock
        with _recent_lock:
            _recent_questions.clear()
        
        # First question - not duplicate
        q1 = "what is the time complexity of quicksort"
        if _is_duplicate(q1):
            print("[FAIL] First question marked as duplicate")
            return False
        
        # Same question immediately - should be duplicate
        if not _is_duplicate(q1):
            print("[FAIL] Duplicate not detected")
            return False
        
        # Similar question - should be duplicate
        q2 = "what is time complexity of quick sort"
        if not _is_duplicate(q2):
            print("[FAIL] Similar question not detected as duplicate")
            return False
        
        # Different question - not duplicate
        q3 = "explain the difference between tcp and udp"
        if _is_duplicate(q3):
            print("[FAIL] Different question marked as duplicate")
            return False
        
        print("[OK] Duplicate detection working correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Duplicate detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backend_selection():
    """Test LLM backend selection logic."""
    print("\n" + "="*60)
    print("TEST: Backend Selection")
    print("="*60)
    
    try:
        backend = _effective_backend()
        
        if backend not in ["ollama", "groq", "gemini"]:
            print(f"[FAIL] Invalid backend: {backend}")
            return False
        
        print(f"[OK] Backend selection working (selected: {backend})")
        return True
        
    except Exception as e:
        print(f"[FAIL] Backend selection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_keyword_coverage():
    """Test keyword dictionaries are comprehensive."""
    print("\n" + "="*60)
    print("TEST: Keyword Coverage")
    print("="*60)
    
    try:
        # Check domain keywords
        if len(DOMAIN_KEYWORDS) < 5:
            print(f"[FAIL] Too few domain categories: {len(DOMAIN_KEYWORDS)}")
            return False
        
        # Check category keywords
        if len(CATEGORY_KEYWORDS) < 4:
            print(f"[FAIL] Too few question categories: {len(CATEGORY_KEYWORDS)}")
            return False
        
        # Check each domain has keywords
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if len(keywords) < 5:
                print(f"[FAIL] Domain {domain} has too few keywords: {len(keywords)}")
                return False
        
        print(f"[OK] Keyword coverage adequate ({len(DOMAIN_KEYWORDS)} domains, {len(CATEGORY_KEYWORDS)} categories)")
        return True
        
    except Exception as e:
        print(f"[FAIL] Keyword coverage test failed: {e}")
        return False


def run_all_tests():
    """Run all LLM tests."""
    print("\n" + "="*70)
    print(" LLM TEST SUITE")
    print("="*70)
    
    tests = [
        ("Question Classification", test_question_classification),
        ("Domain Detection", test_domain_detection),
        ("Prompt Building", test_prompt_building),
        ("Duplicate Detection", test_duplicate_detection),
        ("Backend Selection", test_backend_selection),
        ("Keyword Coverage", test_keyword_coverage),
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
