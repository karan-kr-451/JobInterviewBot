"""
llm/rag/context_retriever.py — Vector-based RAG using ChromaDB.

Indexes loaded documents with basic text chunking into an in-memory
ChromaDB instance, and retrieves top-k relevant chunks based on the query.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from antigravity.llm.rag.document_store import load_documents

logger = logging.getLogger(__name__)


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Splits a long string into overlapping chunks for indexing."""
    chunks = []
    # Fast basic word-level chunking
    words = text.split()
    
    # Approximate words per chunk (avg 5 chars per word)
    words_per_chunk = max(1, chunk_size // 5)
    words_overlap = max(0, overlap // 5)
    
    if len(words) <= words_per_chunk:
        return [" ".join(words)]
        
    i = 0
    while i < len(words):
        end = min(i + words_per_chunk, len(words))
        chunk = " ".join(words[i:end])
        chunks.append(chunk)
        if end == len(words):
            break
        i += (words_per_chunk - words_overlap)
        
    return chunks


class ContextRetriever:
    """
    RAG engine: Loads docs, chunks them, and embeds them into a Chroma DB.
    """

    def __init__(self, docs_dir: str = "interview_docs") -> None:
        self.docs: Dict[str, str] = {}
        self._docs_dir = docs_dir
        self._collection = None
        
        try:
            import chromadb
            # Use an ephemeral in-memory client for speed and simplicity. 
            self._client = chromadb.EphemeralClient()
            self._enabled = True
        except ImportError:
            logger.error("[RAG] chromadb not installed. Semantic search disabled.")
            self._enabled = False
            
        self.candidate_name = ""
        self.companies = []
        self.skills = []

    def load(self) -> None:
        raw_docs = load_documents(self._docs_dir)
        self.docs = {path: data["FullText"] for path, data in raw_docs.items()}
        
        # Extract global metadata for the current candidate
        for data in raw_docs.values():
            if data.get("Category") == "resume":
                if data.get("CandidateName"):
                    self.candidate_name = data["CandidateName"]
                if "Companies" in data:
                    self.companies.extend(data["Companies"])
                if "Skills" in data or "Technical Skills" in data:
                    s_text = data.get("Skills", data.get("Technical Skills", ""))
                    if s_text:
                        # Simple extraction of first line of skills
                        self.skills = [s.strip() for s in re.split(r"[,|]", s_text.split("\n")[0]) if s.strip()][:5]

        if not self._enabled:
            return
            
        try:
            # Drop existing if reloading
            try:
                self._client.delete_collection("interview_docs")
            except Exception:
                pass
                
            self._collection = self._client.create_collection("interview_docs")
            
            doc_ids = []
            doc_texts = []
            doc_metas = []
            
            idx = 0
            for path, data in raw_docs.items():
                base = data["Filename"]
                category = data["Category"]
                
                # Chunk the full text for semantic indexing
                chunks = _chunk_text(data["FullText"])
                
                for i, chunk in enumerate(chunks):
                    doc_ids.append(f"doc_{idx}_chunk_{i}")
                    doc_texts.append(chunk)
                    doc_metas.append({
                        "source": base, 
                        "category": category,
                        "chunk_index": i
                    })
                idx += 1
                
            if doc_texts:
                self._collection.add(
                    ids=doc_ids,
                    documents=doc_texts,
                    metadatas=doc_metas
                )
                logger.info("[RAG] Indexed %d chunks from %d documents into ChromaDB.", len(doc_texts), len(self.docs))
                
            # Pre-warm the embedding model.
            try:
                logger.info("[RAG] Pre-warming embedding model...")
                self._collection.query(query_texts=["warmup"], n_results=1)
                logger.info("[RAG] ChromaDB ready.")
            except Exception:
                pass
                
        except Exception as e:
            logger.error("[RAG] Failed to initialize ChromaDB: %s", e)
            self._enabled = False

    def get_candidate_summary(self) -> str:
        """
        Generates the conversational first-person summary ported from V3 method.
        """
        name = self.candidate_name or "a candidate"
        
        comp_hint = ""
        if self.companies:
            unique_comps = sorted(list(set(self.companies)))[:3]
            comp_hint = f" I've worked at {', '.join(unique_comps)}."

        skill_hint = ""
        if self.skills:
            skill_hint = f" I'm quite comfortable with {', '.join(self.skills[:3])}."

        # Detect student/fresher persona heuristics
        is_student = any(word in str(self.docs).lower() for word in ["pursuing", "current", "expected", "2024", "2025", "2026"])
        
        if is_student:
            return f"My name is {name}, and I'm currently pursuing my degree in engineering.{comp_hint}{skill_hint} I'm eager to apply my knowledge in real-world projects."
        else:
            return f"My name is {name}, and I'm a software engineer.{comp_hint}{skill_hint} I enjoy solving challenging problems and building scalable solutions."

    def get_context_for_query(self, query: str, top_k: int = 3) -> str:
        """
        Similarity search. Returns a single string containing the best matching chunks.
        """
        if not self._enabled or not self._collection:
            # Graceful fallback if Chroma fails: Just return everything (v3 style), 
            # bounded safely
            return self._get_fallback_context()
            
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k
            )
            
            if not results["documents"] or not results["documents"][0]:
                return ""
                
            retrieved_chunks = results["documents"][0]
            metadatas = results["metadatas"][0]
            
            parts = []
            for i, chunk in enumerate(retrieved_chunks):
                source = metadatas[i].get("source", "Unknown")
                parts.append(f"--- Context from {source} ---")
                parts.append(chunk)
                
            return "\n".join(parts)
            
        except Exception as e:
            logger.warning("[RAG] Chroma query failed: %s", e)
            return self._get_fallback_context()

    def _get_fallback_context(self) -> str:
        """Fallback to blind injection if Chroma is busted."""
        parts = []
        for name, text in self.docs.items():
            base = name.split("/")[-1].split("\\")[-1]
            parts.append(f"--- Document: {base} ---")
            parts.append(text[:2000]) # Cap it so we don't blow context optionally
        return "\n".join(parts)
