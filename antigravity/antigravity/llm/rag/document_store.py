"""
llm/rag/document_store.py — Robust document parsing and metadata extraction.

Ported from legacy bot implementation to support:
- Section-based splitting (Experience, Skills, etc.)
- Metadata extraction (Candidate Name, Companies)
- File categorization (Resume vs Project vs JD)
"""

from __future__ import annotations

import logging
import os
import glob
import re
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

def _extract_identity(text: str) -> str:
    """Extract candidate name - usually the first non-contact line."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        if "@" in line or "+" in line or "|" in line or "http" in line:
            continue
        # Names are usually 2-4 words starting with capitals
        if len(line.split()) <= 4 and line[0].isupper():
            return line
    return ""

def _extract_companies(text: str) -> List[str]:
    """Try to find company names in the experience section."""
    companies = []
    lines = text.split("\n")
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if "|" in s or " - " in s or "," in s:
            parts = re.split(r"[|,-]", s)
            if parts:
                name = parts[0].strip()
                if name and name[0].isupper() and len(name.split()) < 5:
                    companies.append(name)
    return list(set(companies))[:5]

def split_into_sections(text: str) -> Dict[str, Any]:
    """Split resume/doc text into logical sections based on headers."""
    headers = [
        r"EXPERIENCE", r"PROFESSIONAL EXPERIENCE", r"WORK EXPERIENCE", r"EMPLOYMENT",
        r"EDUCATION", r"ACADEMIC BACKGROUND",
        r"SKILLS", r"TECHNICAL SKILLS", r"CORE COMPETENCIES",
        r"PROJECTS", r"KEY PROJECTS", r"RESEARCH",
        r"SUMMARY", r"ABOUT ME", r"OBJECTIVE", r"AWARDS", r"CERTIFICATIONS"
    ]
    pattern = r"(?m)^(" + "|".join(headers) + r")$"
    parts = re.split(pattern, text, flags=re.IGNORECASE)

    sections = {
        "FullText":       text,
        "General":        parts[0].strip(),
        "CandidateName": _extract_identity(text)
    }

    for i in range(1, len(parts), 2):
        header  = parts[i].strip().title()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[header] = content

        if "Experience" in header or "Employment" in header:
            sections["Companies"] = _extract_companies(content)

    return sections

def load_documents(docs_dir: str = "interview_docs") -> Dict[str, Dict[str, Any]]:
    """
    Returns a mapping of filepath -> Structured Data.
    Handles .txt, .md, and .pdf files.
    Categorizes files into 'resume', 'jd', or 'project'.
    """
    if not os.path.exists(docs_dir):
        logger.warning("[RAG] %s folder missing, creating...", docs_dir)
        os.makedirs(docs_dir, exist_ok=True)
        return {}

    all_docs = {}
    
    # Supported extensions
    for ext in ["*.txt", "*.md", "*.pdf"]:
        for path_str in glob.glob(os.path.join(docs_dir, ext)):
            path = Path(path_str)
            text = ""
            
            try:
                if path.suffix.lower() == ".pdf":
                    from pypdf import PdfReader
                    with open(path, "rb") as f:
                        reader = PdfReader(f)
                        text = "\n".join(page.extract_text() or "" for page in reader.pages)
                else:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                        
                if not text.strip():
                    continue

                stem = path.stem.lower()
                category = "project"
                if "resume" in stem or "cv" in stem:
                    category = "resume"
                elif any(x in stem for x in ("job", "jd", "description")):
                    category = "jd"

                sections = split_into_sections(text)
                sections["Category"] = category
                sections["Filename"] = path.name
                
                all_docs[path_str] = sections
                
            except Exception as e:
                logger.error("[RAG] Failed to load %s: %s", path_str, e)
                
    if all_docs:
        logger.info("[RAG] Loaded %d structured documents.", len(all_docs))
    return all_docs
