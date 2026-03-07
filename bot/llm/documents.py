import re
import threading
from pathlib import Path

from config.documents import DOCS_FOLDER
from config.gemini import GEMINI_API_KEY

# Global PageIndex instances for deep search
_pio_instances = {}


def _get_best_rag_model() -> str:
    """
    Pick the best available model for RAG.
    Prefer Groq (free, fast, no daily quota) over Gemini.
    Gemini free tier only allows 20 requests/day - don't use it for doc indexing.
    """
    try:
        from config.groq import GROQ_API_KEY
        if GROQ_API_KEY:
            return "groq/llama-3.1-8b-instant"   # fast, generous limits
    except Exception:
        pass

    if GEMINI_API_KEY:
        try:
            from config.gemini import GEMINI_MODEL
            return f"gemini/{GEMINI_MODEL}"
        except Exception:
            return "gemini/gemini-2.5-flash-lite"

    return ""


def _index_cache_paths(file_path: Path):
    """Return the expected .md and .tree.json paths that PIO saves after build_index."""
    md_path   = file_path.with_suffix(".md")
    tree_path = file_path.with_name(file_path.stem + ".tree.json")
    return md_path, tree_path


def _get_pio(file_path: Path):
    """Get or create a PIO instance for a PDF. Only builds index if cache missing."""
    try:
        from pageindex_open import PIO
        path_str = str(file_path.absolute())

        if path_str in _pio_instances:
            return _pio_instances[path_str]

        model = _get_best_rag_model()
        if not model:
            return None

        pio = PIO(path_str, model_name=model)

        md_path, tree_path = _index_cache_paths(file_path)

        if md_path.exists() and tree_path.exists():
            # Cache exists - load without any API call
            try:
                pio.load_index(str(md_path), str(tree_path))
                print(f"[docs] Loaded PageIndex cache for {file_path.name} ({model})")
            except Exception as e:
                print(f"[docs] Cache load failed for {file_path.name}, rebuilding: {e}")
                threading.Thread(target=pio.build_index, daemon=True).start()
        else:
            # First time - build index in background (makes API calls once, then cached)
            print(f"[docs] Building PageIndex for {file_path.name} (first run only)...")
            threading.Thread(target=pio.build_index, daemon=True).start()

        _pio_instances[path_str] = pio
        return pio

    except ImportError:
        return None
    except Exception as e:
        print(f"[docs] PIO init failed: {e}")
        return None


def query_bio(query: str, top_k: int = 1) -> str:
    if not _pio_instances:
        return ""
    results = []
    for path_str, pio in _pio_instances.items():
        try:
            res = pio.query(query, top_k=top_k)
            if res is None:
                continue          # index not ready yet, skip silently
            results.append(f"--- From {Path(path_str).name} ---\n{res}")
        except Exception as e:
            print(f"[docs] Query error {Path(path_str).name}: {e}")
    return "\n\n".join(results)



def _parse_pdf(path: Path) -> str:
    """Extract text from PDF and register for deep indexing."""
    text = ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"

        # Register for deep RAG indexing (loads cache if available, else builds once)
        _get_pio(path)

        return text
    except Exception as e:
        print(f"[docs] PDF extraction failed {path.name}: {e}")
        return ""


def _heuristic_summary(docs: dict) -> str:
    """Build a basic summary from document text without any API calls.
    Creates a personalized Indian employee/student style summary."""
    sections   = docs.get("resume_sections", {})
    name       = sections.get("Candidate Name", "a candidate")
    comps      = sections.get("Companies", [])
    skills_text = sections.get("Skills", sections.get("Technical Skills", ""))

    skills = []
    if skills_text:
        first_line = skills_text.split("\n")[0]
        skills = [s.strip() for s in re.split(r"[,| ]", first_line) if s.strip()][:4]

    # More personalized, conversational summary
    if comps:
        comp_hint = f" I've worked at {', '.join(comps)}"
    else:
        comp_hint = ""
    
    if skills:
        skill_hint = f" and I'm quite comfortable with {', '.join(skills[:3])}"
    else:
        skill_hint = ""
    
    # Check if likely a student/fresher
    edu_section = sections.get("Education", "")
    is_student = any(word in edu_section.lower() for word in ["pursuing", "current", "expected", "2024", "2025", "2026"])
    
    if is_student:
        return f"{name}, currently pursuing my degree in engineering.{comp_hint}{skill_hint}. I'm eager to apply my knowledge in real-world projects"
    else:
        return f"{name}, a software engineer{comp_hint}{skill_hint}. I enjoy solving challenging problems and building scalable solutions"


def summarize_candidate(docs: dict = None) -> str:
    """
    Generate a professional yet conversational summary in Indian employee/student style.
    Only queries PIO if the index cache is already on disk (no API call on first run).
    Falls back to heuristic summary so startup is never blocked.
    """
    # Only attempt RAG query if index files already exist on disk
    # (avoids burning Gemini quota or Groq RPM on every startup)
    folder = Path(DOCS_FOLDER)
    index_ready = any(
        _index_cache_paths(fp)[0].exists() and _index_cache_paths(fp)[1].exists()
        for fp in folder.glob("*.pdf")
    )

    if index_ready and _pio_instances:
        query = (
            "Give a 2-3 sentence conversational summary of this candidate in first person. "
            "Include their name, experience/education, and top 3 skills. "
            "Make it sound like an Indian employee or student introducing themselves - "
            "professional but warm, confident but humble. Use phrases like 'I've worked on', "
            "'I'm comfortable with', 'I enjoy'. Keep it natural and personable."
        )
        res = query_bio(query, top_k=2)
        if res and len(res) > 40:
            return res

    # Fast heuristic - zero API calls
    return _heuristic_summary(docs or {})


def _extract_companies(text: str) -> list[str]:
    """Try to find company names in the experience section."""
    companies = []
    lines = text.split("\n")
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if "|" in s or " - " in s or "," in s:
            name = re.split(r"[|,-]", s)[0].strip()
            if name and name[0].isupper() and len(name.split()) < 5:
                companies.append(name)
    return list(set(companies))[:5]


def _extract_identity(text: str) -> str:
    """Extract candidate name - usually the first non-contact line."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        if "@" in line or "+" in line or "|" in line or "http" in line:
            continue
        return line
    return ""


def _split_into_sections(text: str) -> dict:
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
        "General":        parts[0].strip(),
        "Candidate Name": _extract_identity(text)
    }

    for i in range(1, len(parts), 2):
        header  = parts[i].strip().title()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[header] = content

        if "Experience" in header or "Employment" in header:
            sections["Companies"] = _extract_companies(content)

    return sections


def load_documents() -> dict:
    """Load resume, projects, job title, and description from folder.
    
    Supports multiple resumes and project files:
    - All files with 'resume' in name are combined
    - All other PDF/TXT/MD files are treated as projects
    - Files with 'job' or 'jd' in name are job descriptions
    """
    from core.env_helpers import read_settings
    sets = read_settings()

    folder = Path(DOCS_FOLDER)
    folder.mkdir(exist_ok=True)

    docs = {
        "resume":           "",
        "resume_sections":  {},
        "projects":         "",
        "job_title":        sets.get("job_title", ""),
        "job_description":  sets.get("job_description", ""),
        "candidate_summary": "",
        "resume_files":     [],  # NEW: Track individual resume files
        "project_files":    [],  # NEW: Track individual project files
    }

    for fp in folder.glob("*"):
        ext = fp.suffix.lower()
        if ext not in (".txt", ".md", ".pdf"):
            continue

        try:
            if ext == ".pdf":
                content = _parse_pdf(fp)
            else:
                content = fp.read_text(encoding="utf-8")

            if not content.strip():
                continue

            stem = fp.stem.lower()
            
            # Categorize by filename
            if "resume" in stem or "cv" in stem:
                docs["resume"] += f"\n\n=== {fp.name} ===\n{content}"
                docs["resume_files"].append(fp.name)
                sections = _split_into_sections(content)
                docs["resume_sections"].update(sections)
                
            elif any(x in stem for x in ("job", "jd", "description")):
                docs["job_description"] = content
                
            else:
                # Everything else is a project
                docs["projects"] += f"\n\n=== {fp.name} ===\n{content}"
                docs["project_files"].append(fp.name)

        except Exception as e:
            print(f"[docs] {fp}: {e}")

    # Log what was loaded
    if docs["resume_files"]:
        print(f"[docs] Loaded {len(docs['resume_files'])} resume(s): {', '.join(docs['resume_files'])}")
    if docs["project_files"]:
        print(f"[docs] Loaded {len(docs['project_files'])} project(s): {', '.join(docs['project_files'])}")

    return docs