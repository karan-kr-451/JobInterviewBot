"""
llm.router - Backend selection and response orchestration.

Routes questions to the appropriate LLM backend (Ollama -> Groq -> Gemini)
and handles retries, fallbacks, and post-processing.
"""

import re
import time
import threading

from config.llm import LLM_BACKEND, RETRY_BASE_DELAY
from config.gemini import (
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACKS, GENERATION_CONFIGS,
)
from config.groq import GROQ_TEMPERATURE, GROQ_FALLBACK_MODEL, get_groq_max_tokens
from config.ollama import get_ollama_model
from config.documents import LOG_FILE

from llm.classifier import classify_question
from llm.prompt_builder import build_prompt
from llm.duplicates import is_duplicate
from llm.gemini_stream import call_gemini_streaming
from llm.ollama_stream import call_ollama_streaming

try:
    from llm.groq_stream import (
        check_groq as _check_groq,
        call_groq_streaming as _call_groq_streaming,
        get_groq_model as _get_groq_model,
        RateLimitError as _GroqRateLimitError,
    )
except ImportError:
    print("WARNING: llm.groq_stream not available - Groq backend disabled")
    _check_groq           = lambda: False
    _call_groq_streaming  = None
    _get_groq_model       = None
    _GroqRateLimitError   = None

try:
    from audio.watchdog import reset_watchdog_timer as _reset_watchdog
except ImportError:
    def _reset_watchdog(): pass

# -- Backend availability ------------------------------------------------------

GENAI_AVAILABLE  = bool(GEMINI_API_KEY)
GROQ_AVAILABLE   = False
OLLAMA_AVAILABLE = False

try:
    import google.generativeai as genai
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False


def configure_backends() -> bool:
    """Configure all LLM backends. Returns True if at least one is ready."""
    global GROQ_AVAILABLE

    # If explicit backend set, only check that one
    if LLM_BACKEND == "ollama":
        return check_ollama()

    if LLM_BACKEND == "groq":
        GROQ_AVAILABLE = _check_groq()
        return GROQ_AVAILABLE
    
    if LLM_BACKEND == "gemini":
        if not GEMINI_API_KEY:
            print("[WARN]  GEMINI_API_KEY missing - Gemini disabled.")
            return False
        if _SDK_AVAILABLE:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                print("[OK] Gemini API key configured (REST streaming)")
            except Exception as e:
                print(f"[WARN]  Gemini SDK configure warning: {e} - continuing with REST")
        return True

    # "auto" mode: check all backends
    groq_ok = False
    try:
        GROQ_AVAILABLE = _check_groq()
        groq_ok = GROQ_AVAILABLE
    except Exception:
        pass

    if not GEMINI_API_KEY:
        print("[WARN]  GEMINI_API_KEY missing - Gemini disabled.")
        return groq_ok

    if _SDK_AVAILABLE:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            print("[OK] Gemini API key configured (REST streaming)")
        except Exception as e:
            print(f"[WARN]  Gemini SDK configure warning: {e} - continuing with REST")
    else:
        print("[OK] Gemini REST configured (SDK not installed - that's fine)")

    return True


def check_ollama() -> bool:
    """Check if Ollama is running and has the required model."""
    global OLLAMA_AVAILABLE
    from config.ollama import OLLAMA_BASE_URL, OLLAMA_SINGLE_MODEL
    session = None
    try:
        from core.http_utils import create_fresh_session
        session = create_fresh_session()
        r = session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        models = [m["name"] for m in r.json().get("models", [])]
        if models:
            OLLAMA_AVAILABLE = True
            print(f"[OK] Ollama available - {len(models)} model(s): {', '.join(models[:5])}")
            model_base = OLLAMA_SINGLE_MODEL.split(":")[0]
            has_model  = any(model_base in m for m in models)
            if not has_model:
                print(f"    Required model not found: {OLLAMA_SINGLE_MODEL}")
                print(f"    Run: ollama pull {OLLAMA_SINGLE_MODEL}")
            return True
        else:
            print(f"  Ollama running but no models. Run: ollama pull {OLLAMA_SINGLE_MODEL}")
            return False
    except Exception as e:
        print(f"  Ollama not available ({type(e).__name__}) - trying Groq -> Gemini")
        return False


def _effective_backend() -> str:
    """Resolve 'auto' to the best available backend."""
    # Explicit backend selection (not auto)
    if LLM_BACKEND == "ollama":  return "ollama"
    if LLM_BACKEND == "gemini":  return "gemini"
    if LLM_BACKEND == "groq":    return "groq"
    
    # Auto mode: prefer Groq (fast, free) over Ollama (local, slow)
    if GROQ_AVAILABLE:    return "groq"
    if OLLAMA_AVAILABLE:  return "ollama"
    return "gemini"


def _extract_retry_delay(err: Exception) -> float:
    s = str(err)
    for pat in [r"retry[_\s]+delay[^\d]+(\d+)", r"retry in\s+([\d.]+)s"]:
        m = re.search(pat, s, re.I)
        if m:
            return float(m.group(1)) + 2
    return RETRY_BASE_DELAY


def _sleep(seconds: float):
    time.sleep(seconds)


# -- Global state --------------------------------------------------------------
_request_count = 0


def get_interview_response(question: str, history: list, history_lock: threading.Lock,
                           docs: dict, overlay=None) -> str:
    """Route a question to the best LLM backend and return the response."""
    global _request_count

    if is_duplicate(question):
        print(f"[WARN]  Duplicate - skipped: '{question[:60]}'")
        return ""

    domain, category = classify_question(question)
    label = f"{domain} | {category}"
    print(f"[SEARCH] {label}")

    with history_lock:
        history_snapshot = list(history[-10:])

    prompt = build_prompt(question, domain, category, history_snapshot, docs)

    if overlay:
        overlay.set_question(f"[{label}]\n{question}")

    backend = _effective_backend()
    candidate_response = None

    # -- Ollama path (if explicitly selected) ----------------------------------
    if backend == "ollama":
        model_name = get_ollama_model(domain)
        print(f"   model: {model_name}  [ollama]")
        try:
            candidate_response = call_ollama_streaming(
                model_name, prompt, overlay, category=domain,
            )
        except RuntimeError as e:
            print(f"  Ollama error: {e}")
            return "Local model unavailable - check Ollama is running."

    # -- Groq + Gemini rotation (auto/groq/gemini mode) ------------------------
    if backend != "ollama":
        _request_count += 1
        
        # Build unified model list: Groq + Gemini models
        all_models = []
        
        # Add Groq models if available (unless explicitly disabled)
        if GROQ_AVAILABLE and _call_groq_streaming and backend != "gemini":
            from config.groq import GROQ_ENTERPRISE_MODELS
            for g_model in GROQ_ENTERPRISE_MODELS:
                all_models.append(("groq", g_model))
        
        # Add Gemini models if available (unless explicitly disabled)
        if GEMINI_API_KEY and backend != "groq":
            from config.gemini import GEMINI_MODEL, GEMINI_FALLBACKS
            gemini_list = [GEMINI_MODEL] + GEMINI_FALLBACKS
            for gm in gemini_list:
                all_models.append(("gemini", gm))
        
        if not all_models:
            return "No LLM backend available - check API keys"
        
        # Rotate through all models
        rotate_idx = _request_count % len(all_models)
        selected_backend, selected_model = all_models[rotate_idx]
        
        print(f"   model: {selected_model} (rotated {_request_count}/{len(all_models)})  [{selected_backend}]")
        
        # -- Enterprise Safe Call --
        from core.enterprise_crash_prevention import safe_http_call
        
        # Try selected model
        try:
            if selected_backend == "groq":
                max_tokens = get_groq_max_tokens(domain)
                # Wrap in circuit breaker
                candidate_response = safe_http_call(
                    _call_groq_streaming, 
                    selected_model, prompt, overlay,
                    max_tokens=max_tokens,
                    temperature=GROQ_TEMPERATURE
                )
            else:  # gemini
                cfg_entry = GENERATION_CONFIGS.get(category, GENERATION_CONFIGS["UNKNOWN"])
                cfg = {k: v for k, v in cfg_entry.items() if k != "model"}
                # Wrap in circuit breaker
                candidate_response = safe_http_call(
                    call_gemini_streaming,
                    selected_model, prompt, cfg, overlay
                )
        
        except (_GroqRateLimitError if _GroqRateLimitError else Exception) as e:
            # Rate limits or Circuit Breaker OPEN errors fall here
            print(f"  [{selected_backend}] Issue on {selected_model} - trying next in rotation: {e}")
            # Try next model in rotation
            next_idx = (rotate_idx + 1) % len(all_models)
            fallback_backend, fallback_model = all_models[next_idx]
            print(f"   -> fallback: {fallback_model}  [{fallback_backend}]")
            
            try:
                if fallback_backend == "groq":
                    max_tokens = get_groq_max_tokens(domain)
                    candidate_response = safe_http_call(
                        _call_groq_streaming,
                        fallback_model, prompt, overlay,
                        max_tokens=max_tokens,
                        temperature=GROQ_TEMPERATURE
                    )
                else:  # gemini
                    cfg_entry = GENERATION_CONFIGS.get(category, GENERATION_CONFIGS["UNKNOWN"])
                    cfg = {k: v for k, v in cfg_entry.items() if k != "model"}
                    candidate_response = safe_http_call(
                        call_gemini_streaming,
                        fallback_model, prompt, cfg, overlay
                    )
            except Exception as e2:
                print(f"  [{fallback_backend}] Fallback also failed: {e2}")
                return "All models unavailable - please try again"
        
        except Exception as e:
            print(f"  [{selected_backend}] Error on {selected_model}: {e}")
            return "Technical issue - could you repeat that?"

    # -- Common post-processing -------------------------------------------------
    if not candidate_response:
        return ""

    if overlay:
        try:
            overlay.finalize()
        except Exception:
            pass

    with history_lock:
        history.append(question)
        history.append(candidate_response)
        if len(history) > 20:
            del history[:-20]

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{label}] [{backend}]\n")
            f.write(f"Q: {question}\nA: {candidate_response}\n{'-'*60}\n")
    except Exception as e:
        print(f"[log] {e}")

    print(f"\n{'='*60}\n[{label}]\nQ: {question}\n{'-'*60}\nA: {candidate_response}\n{'='*60}\n")
    return candidate_response