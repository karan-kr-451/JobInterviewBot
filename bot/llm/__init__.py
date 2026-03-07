"""
llm - LLM backend package.

Public API for the rest of the application.
"""

from llm.router import configure_backends, check_ollama, get_interview_response  # noqa: F401
from llm.documents import load_documents                                         # noqa: F401
from llm.worker import make_llm_worker                                           # noqa: F401
from llm.classifier import classify_question                                     # noqa: F401
from llm.prompt_builder import build_prompt                                      # noqa: F401

# Backward-compat aliases used by main.py
configure_genai = configure_backends
make_gemini_worker = make_llm_worker
