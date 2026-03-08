"""
rag/embedding_store.py - pageindex-open (PIO) wrapper for semantic document indexing.

Builds a semantic index for each PDF document and caches it to disk.
Subsequent runs load from cache (zero API calls) until the PDF changes.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional

from core.logger import get_logger

log = get_logger("rag.embedding")

_instances: Dict[str, object] = {}
_instances_lock = threading.Lock()


def _best_rag_model(groq_key: str, gemini_key: str) -> str:
    """Select the best available model for RAG indexing."""
    if groq_key:
        return "groq/llama-3.1-8b-instant"   # Fast, generous free limits
    if gemini_key:
        return "gemini/gemini-2.0-flash"
    return ""


def _cache_paths(pdf_path: Path):
    """Return (md_path, tree_path) that PIO writes after build_index."""
    return (
        pdf_path.with_suffix(".md"),
        pdf_path.with_name(pdf_path.stem + ".tree.json"),
    )


class EmbeddingStore:
    """
    Wraps pageindex_open.PIO to provide semantic search over documents.

    Call index_file() for each PDF on startup.
    Call query() to retrieve relevant snippets.
    """

    def __init__(self, groq_key: str = "", gemini_key: str = "") -> None:
        self._groq_key   = groq_key
        self._gemini_key = gemini_key
        self._pio_map: Dict[str, object] = {}

    def index_file(self, pdf_path: Path) -> bool:
        """
        Register and index a PDF file.
        If the cache (.md + .tree.json) already exists, loads it instantly.
        Otherwise builds the index in a background thread.
        Returns True if PIO is available.
        """
        try:
            from pageindex_open import PIO
        except ImportError:
            log.warning("pageindex_open not installed – RAG indexing disabled")
            return False

        model = _best_rag_model(self._groq_key, self._gemini_key)
        if not model:
            log.warning("No API key for RAG indexing – RAG disabled")
            return False

        path_str = str(pdf_path.absolute())
        with _instances_lock:
            if path_str in self._pio_map:
                return True

        try:
            pio       = PIO(path_str, model_name=model)
            md_path, tree_path = _cache_paths(pdf_path)

            if md_path.exists() and tree_path.exists():
                try:
                    pio.load_index(str(md_path), str(tree_path))
                    log.info("Loaded PageIndex cache for %s", pdf_path.name)
                except Exception as exc:
                    log.warning("Cache load failed for %s, rebuilding: %s", pdf_path.name, exc)
                    threading.Thread(target=pio.build_index, daemon=True,
                                     name=f"pio-build-{pdf_path.stem}").start()
            else:
                log.info("Building PageIndex for %s (first run – happens once)…", pdf_path.name)
                threading.Thread(target=pio.build_index, daemon=True,
                                 name=f"pio-build-{pdf_path.stem}").start()

            with _instances_lock:
                self._pio_map[path_str] = pio
            return True

        except Exception as exc:
            log.error("PIO init failed for %s: %s", pdf_path.name, exc)
            return False

    def query(self, text: str, top_k: int = 2) -> str:
        """Search all indexed documents and return the most relevant snippets."""
        with _instances_lock:
            items = list(self._pio_map.items())

        if not items:
            return ""

        results = []
        for path_str, pio in items:
            try:
                res = pio.query(text, top_k=top_k)
                if res:
                    results.append(f"--- From {Path(path_str).name} ---\n{res}")
            except Exception as exc:
                log.debug("PIO query error for %s: %s", Path(path_str).name, exc)

        return "\n\n".join(results)

    def is_ready(self) -> bool:
        """Return True if at least one document has been indexed."""
        with _instances_lock:
            return bool(self._pio_map)
