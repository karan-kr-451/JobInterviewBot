"""
rag/context_builder.py - Orchestrates document loading + semantic search.

ContextBuilder is a singleton. Call get_instance() after load_config() and
load_documents(). Provides get_context(question) for use in prompt_builder.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger("rag.context")

_instance: Optional["ContextBuilder"] = None
_cb_lock   = threading.Lock()


class ContextBuilder:
    """
    Loads documents and indexes PDFs for semantic retrieval.

    Usage:
        cb = ContextBuilder.initialise(cfg, docs)
        context = cb.get_context("What is gradient descent?")
    """

    def __init__(self, groq_key: str, gemini_key: str, docs_folder: str, top_k: int = 2) -> None:
        from rag.embedding_store import EmbeddingStore
        self._store    = EmbeddingStore(groq_key=groq_key, gemini_key=gemini_key)
        self._top_k    = top_k
        self._folder   = Path(docs_folder)
        if not self._folder.is_absolute():
            self._folder = Path(__file__).resolve().parent.parent / docs_folder

    def index_documents(self) -> None:
        """Index all PDFs in the docs folder. Safe to call multiple times."""
        if not self._folder.exists():
            log.info("Docs folder does not exist: %s", self._folder)
            return
        for pdf in self._folder.glob("*.pdf"):
            self._store.index_file(pdf)

    def get_context(self, question: str) -> str:
        """Return RAG-relevant context snippets for the given question."""
        if not self._store.is_ready():
            return ""
        try:
            return self._store.query(question, top_k=self._top_k)
        except Exception as exc:
            log.debug("Context retrieval failed: %s", exc)
            return ""

    # ── Singleton helpers ─────────────────────────────────────────────────────

    @classmethod
    def initialise(cls, cfg, docs_folder: Optional[str] = None) -> "ContextBuilder":
        """Create and store the singleton instance."""
        global _instance
        with _cb_lock:
            folder = docs_folder or cfg.rag.docs_folder
            _instance = cls(
                groq_key=cfg.llm.groq.api_key,
                gemini_key=cfg.llm.gemini.api_key,
                docs_folder=folder,
                top_k=cfg.rag.top_k,
            )
            _instance.index_documents()
        return _instance

    @classmethod
    def instance(cls) -> "ContextBuilder":
        """Return the singleton (raises if not yet initialised)."""
        if _instance is None:
            raise RuntimeError("ContextBuilder not initialised. Call ContextBuilder.initialise() first.")
        return _instance
