"""
rag/document_loader.py - Load and parse resume, job description, and project docs.

Supports PDF (via pypdf), TXT, and Markdown files.
Categorises files by name:
  *resume*, *cv*          → resume
  *job*, *jd*, *description* → job description
  everything else         → projects
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger("rag.loader")


def _parse_pdf(path: Path) -> str:
    """Extract text from a PDF file."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages  = []
        for page in reader.pages:
            content = page.extract_text()
            if content:
                pages.append(content)
        return "\n".join(pages)
    except ImportError:
        log.error("pypdf not installed – run: pip install pypdf")
        return ""
    except Exception as exc:
        log.warning("PDF parse failed for %s: %s", path.name, exc)
        return ""


def _extract_identity(text: str) -> str:
    """Heuristically find candidate name from the first 5 lines."""
    for line in text.split("\n")[:5]:
        s = line.strip()
        if not s:
            continue
        if any(c in s for c in ["@", "+", "|", "http"]):
            continue
        s = s.replace("#", "").strip()
        if s and s[0].isupper() and len(s.split()) <= 4 and len(s) > 3:
            return s
    return ""


def _extract_companies(text: str) -> list[str]:
    """Try to find company names in experience sections."""
    companies = []
    for line in text.split("\n"):
        s = line.strip()
        if "|" in s or " - " in s:
            name = re.split(r"[|,\-]", s)[0].strip()
            if name and name[0].isupper() and len(name.split()) < 5:
                companies.append(name)
    return list(set(companies))[:5]


_SECTION_HEADERS = [
    r"EXPERIENCE", r"PROFESSIONAL EXPERIENCE", r"WORK EXPERIENCE", r"EMPLOYMENT",
    r"EDUCATION", r"ACADEMIC BACKGROUND",
    r"SKILLS", r"TECHNICAL SKILLS", r"CORE COMPETENCIES",
    r"PROJECTS", r"KEY PROJECTS", r"RESEARCH",
    r"SUMMARY", r"ABOUT ME", r"OBJECTIVE", r"AWARDS", r"CERTIFICATIONS",
]
_SECTION_PATTERN = re.compile(
    r"(?m)^(" + "|".join(_SECTION_HEADERS) + r")$", re.IGNORECASE
)


def _split_into_sections(text: str) -> dict:
    """Split resume text into named sections."""
    parts    = _SECTION_PATTERN.split(text)
    sections: dict = {"General": parts[0].strip(), "Candidate Name": _extract_identity(text)}
    for i in range(1, len(parts), 2):
        header  = parts[i].strip().title()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[header] = content
        if "Experience" in header or "Employment" in header:
            sections["Companies"] = _extract_companies(content)
    return sections


def load_documents(docs_folder: str | Path = "interview_docs",
                   job_title: str = "", job_description: str = "") -> dict:
    """
    Load all documents from docs_folder.

    Returns a dict:
      resume           str   – combined resume text
      resume_sections  dict  – parsed sections
      resume_files     list  – filenames loaded
      projects         str   – combined project text
      project_files    list  – filenames loaded
      job_title        str
      job_description  str
      candidate_summary str  – populated later by summarize_candidate()
    """
    folder = Path(docs_folder)
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parent.parent / docs_folder
    folder.mkdir(parents=True, exist_ok=True)

    docs: dict = {
        "resume":            "",
        "resume_sections":   {},
        "resume_files":      [],
        "projects":          "",
        "project_files":     [],
        "job_title":         job_title,
        "job_description":   job_description,
        "candidate_summary": "",
        # Convenience alias used by prompt_builder
        "resume_text":       "",
    }

    for fp in sorted(folder.iterdir()):
        ext = fp.suffix.lower()
        if ext not in (".txt", ".md", ".pdf"):
            continue
        try:
            if ext == ".pdf":
                content = _parse_pdf(fp)
            else:
                content = fp.read_text(encoding="utf-8", errors="replace")

            if not content.strip():
                continue

            stem = fp.stem.lower()

            if any(x in stem for x in ("resume", "cv")):
                docs["resume"] += f"\n\n=== {fp.name} ===\n{content}"
                docs["resume_files"].append(fp.name)
                sections = _split_into_sections(content)
                docs["resume_sections"].update(sections)

            elif any(x in stem for x in ("job", "jd", "description")):
                docs["job_description"] = content

            else:
                docs["projects"] += f"\n\n=== {fp.name} ===\n{content}"
                docs["project_files"].append(fp.name)

        except Exception as exc:
            log.warning("Could not load %s: %s", fp.name, exc)

    docs["resume_text"] = docs["resume"]

    if docs["resume_files"]:
        log.info("Loaded %d resume(s): %s", len(docs["resume_files"]),
                 ", ".join(docs["resume_files"]))
    if docs["project_files"]:
        log.info("Loaded %d project(s): %s", len(docs["project_files"]),
                 ", ".join(docs["project_files"]))
    if not docs["resume"]:
        log.info("No resume found – place a PDF in %s/", folder)

    return docs


def heuristic_summary(docs: dict) -> str:
    """
    Build a concise candidate summary without any API calls.
    Returns a first-person string about the candidate.
    """
    sections  = docs.get("resume_sections", {})
    name      = sections.get("Candidate Name", "a candidate")
    companies = sections.get("Companies", [])
    skills_raw = sections.get("Skills", sections.get("Technical Skills", ""))
    skills    = [s.strip() for s in re.split(r"[,| ]", skills_raw.split("\n")[0])
                 if s.strip()][:4]

    comp_hint  = f" I've worked at {', '.join(companies)}" if companies else ""
    skill_hint = f" and I'm comfortable with {', '.join(skills[:3])}" if skills else ""

    edu = sections.get("Education", "")
    is_student = any(w in edu.lower() for w in ["pursuing", "current", "expected", "2025", "2026"])

    if is_student:
        return (f"{name}, currently pursuing my degree in engineering."
                f"{comp_hint}{skill_hint}. Eager to apply my knowledge in real-world projects.")
    return (f"{name}, a software engineer{comp_hint}{skill_hint}. "
            f"I enjoy solving challenging problems and building scalable solutions.")


def summarize_candidate(docs: dict, rag_instance=None) -> str:
    """
    Return a candidate summary string.
    If RAG index is ready, queries it for a richer summary.
    Falls back to heuristic (zero API calls).
    """
    if rag_instance is not None:
        try:
            query = (
                "Give a 2-3 sentence conversational summary of this candidate in first "
                "person. Include their name, experience/education, and top 3 skills. "
                "Professional but warm. Use phrases like 'I've worked on', 'I'm comfortable with'."
            )
            result = rag_instance.query(query, top_k=2)
            if result and len(result) > 40:
                return result
        except Exception as exc:
            log.debug("RAG summary failed: %s", exc)
    return heuristic_summary(docs)
