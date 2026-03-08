"""
llm/prompt_builder.py - Interview response prompt construction.

Builds a persona-framed prompt that instructs the LLM to respond
directly as the candidate – no meta-talk, no "I'd be happy to help".
Injects RAG-retrieved context and recent conversation history.
"""

from __future__ import annotations

# ── Domain-specific terminology hints ────────────────────────────────────────
DOMAIN_CONTEXT: dict[str, str] = {
    "DEEP_LEARNING":        "Use DL-specific terminology. Reference PyTorch/TensorFlow.",
    "NLP":                  "Use NLP/LLM terminology. Reference HuggingFace, spaCy.",
    "COMPUTER_VISION":      "Use CV terminology. Reference OpenCV, torchvision.",
    "MACHINE_LEARNING":     "Use classical ML terminology. Reference scikit-learn, XGBoost.",
    "MLOPS":                "Use MLOps/infrastructure terminology. Reference MLflow, Kubeflow.",
    "SOFTWARE_ENGINEERING": "Use SWE best-practice terminology. Reference design patterns.",
    "DEVOPS":               "Use DevOps/cloud terminology. Reference Docker, Kubernetes, CI/CD.",
    "DATA_ENGINEERING":     "Use data engineering terminology. Reference Spark, Airflow, dbt.",
    "GENERAL":              "Answer from your general technical background with clear, precise language.",
}

# ── Response format instructions per question category ────────────────────────
RESPONSE_INSTRUCTIONS: dict[str, str] = {
    "CODING": (
        "1. APPROACH (1-2 sentences): Brief strategy overview.\n"
        "2. CODE: Clean Python without comments. Handle edge cases.\n"
        "3. COMPLEXITY: State time/space complexity concisely.\n"
        "Keep it under 150 words total. Be direct and technical."
    ),
    "SYSTEM_DESIGN": (
        "Cover in 4-5 concise points:\n"
        "- Scale assumptions (users, requests/sec)\n"
        "- Core components (API, DB, cache, queue)\n"
        "- Key decisions (sync/async, DB choice, caching strategy)\n"
        "- Bottlenecks and solutions\n"
        "- Trade-offs\n"
        "Under 200 words. Be specific and technical."
    ),
    "CONCEPT": (
        "Answer in 3-4 sentences:\n"
        "1. Clear definition (1 sentence)\n"
        "2. Key characteristics or how it works (1-2 sentences)\n"
        "3. Practical use case or benefit (1 sentence)\n"
        "Under 100 words. Be precise and technical."
    ),
    "PROJECT": (
        "Answer in 4-5 sentences:\n"
        "- Problem/context (1 sentence)\n"
        "- Your role and approach (2 sentences)\n"
        "- Key challenge and solution (1 sentence)\n"
        "- Impact/outcome with metrics (1 sentence)\n"
        "Under 120 words. Be specific and results-focused."
    ),
    "BEHAVIORAL": (
        "Use STAR format, 4-5 sentences:\n"
        "- Situation (1 sentence)\n"
        "- Task/challenge (1 sentence)\n"
        "- Action YOU took (2 sentences)\n"
        "- Result and learning (1 sentence)\n"
        "Under 120 words. Be specific and honest."
    ),
    "UNKNOWN": (
        "Answer directly in 2-4 sentences. Lead with the main point. "
        "Be concise and technical. Under 100 words."
    ),
}

PERSONA_GUIDELINES = """
CRITICAL RULES:
- BE CONCISE: Answer in 3-5 sentences maximum
- BE DIRECT: Start with the main point, no filler
- BE SPECIFIC: Use concrete examples, numbers, technologies
- BE TECHNICAL: Use proper terminology, avoid fluff

STYLE:
- Professional and confident
- First person ("I", "my", "we")

AVOID:
- "So basically", "You know", "I'd be happy to help"
- Repetitive explanations
- Excessive hedging ("I think", "kind of")
- Over-explaining simple concepts

TONE: Direct, professional, technically precise.
"""


def _extract_name(resume_text: str) -> str:
    """Try to find the candidate's name from the first lines of the resume."""
    for line in resume_text.split("\n")[:5]:
        line = line.strip().replace("#", "").strip()
        if (
            line
            and line[0].isupper()
            and not any(c in line for c in ["@", "http", ":", "|"])
            and len(line.split()) <= 4
            and len(line) > 3
        ):
            return line
    return ""


def build_prompt(
    question: str,
    domain: str,
    category: str,
    history: list,
    docs: dict,
    rag_context: str = "",
) -> str:
    """
    Construct the full LLM prompt.

    Args:
        question:    The interview question text.
        domain:      Classified domain (e.g. "MACHINE_LEARNING").
        category:    Classified category (e.g. "CODING").
        history:     Recent Q&A list (alternating question/answer strings).
        docs:        Document dict from document_loader.
        rag_context: Pre-fetched RAG context (from context_builder).

    Returns:
        Full prompt string ready to send to any LLM backend.
    """
    summary   = docs.get("candidate_summary", "").strip() or "a skilled professional"
    job_title = docs.get("job_title", "").strip()        or "Software Engineer"
    resume_text = docs.get("resume", "")
    name      = _extract_name(resume_text)

    #── Conversation history (last 4 Q&A pairs) ───────────────────────────────
    conv_lines: list[str] = []
    recent = history[-8:] if len(history) >= 8 else history
    for i in range(0, len(recent) - 1, 2):
        conv_lines.append(f"Q: {recent[i]}\nA: {recent[i+1]}")

    # ── Build prompt ──────────────────────────────────────────────────────────
    name_str = f"Your name is {name}." if name else ""
    candidate = name or "a candidate"

    lines = [
        f"You are {candidate} in a professional technical interview for the role of '{job_title}'.",
        f"Candidate Identity: {summary}. {name_str}",
        "",
        "CRITICAL MISSION:",
        "Provide the EXACT spoken response to the interviewer's question. No introductions, no meta-talk.",
        "Speak directly in first person as the candidate.",
        "",
    ]

    if rag_context:
        lines += ["== CANDIDATE CONTEXT & EXPERIENCE ==", rag_context, ""]

    if conv_lines:
        lines += ["== RECENT INTERVIEW DIALOGUE ==", *conv_lines, ""]

    domain_hint   = DOMAIN_CONTEXT.get(domain,   DOMAIN_CONTEXT["GENERAL"])
    category_hint = RESPONSE_INSTRUCTIONS.get(category, RESPONSE_INSTRUCTIONS["UNKNOWN"])

    lines += [
        "== INTERVIEW QUESTION ==",
        f"Domain: {domain}",
        f"Question: {question}",
        "",
        "== RESPONSE REQUIREMENTS ==",
        f"1. {domain_hint}",
        f"2. {category_hint}",
        f"3. {PERSONA_GUIDELINES}",
        "",
        "== FINAL DIRECTIVE ==",
        "Answer in first person (as the candidate), 3-5 sentences, under 150 words.",
        "STRICTLY FORBIDDEN: Do not say 'I would say', 'Here is an answer', or 'I'd be happy to help'.",
        "Start your response IMMEDIATELY with the answer to the question.",
    ]

    return "\n".join(lines)


# ── Question classification (simple keyword-based) ────────────────────────────
_CODING_KW    = {"implement", "code", "write", "function", "algorithm", "complexity",
                 "sort", "search", "tree", "graph", "dynamic", "recursion", "debug"}
_DESIGN_KW    = {"design", "system", "scalable", "architecture", "distribute",
                 "microservice", "database", "cache", "queue", "scale"}
_BEHAV_KW     = {"tell me", "describe", "experience", "challenge", "conflict",
                 "situation", "example", "why", "strength", "weakness"}
_PROJECT_KW   = {"project", "built", "worked on", "your role", "achieve"}
_CONCEPT_KW   = {"what is", "explain", "difference", "define", "how does", "why use"}

_DEEP_KW      = {"neural", "deep", "cnn", "rnn", "transformer", "bert", "gpt", "backprop",
                 "gradient", "attention", "model", "training", "loss", "epoch"}
_NLP_KW       = {"nlp", "ner", "tokenize", "embedding", "language model", "text",
                 "classification", "sentiment", "huggingface", "spacy"}
_CV_KW        = {"image", "vision", "opencv", "detection", "segmentation", "yolo",
                 "convolution", "pixel", "feature extraction"}
_ML_KW        = {"regression", "classification", "random forest", "xgboost", "sklearn",
                 "feature engineering", "overfitting", "bias", "variance", "hyperparameter"}
_MLOPS_KW     = {"mlflow", "kubeflow", "pipeline", "deployment", "inference", "serving",
                 "monitoring", "drift", "a/b test", "experiment"}
_DEVOPS_KW    = {"docker", "kubernetes", "ci/cd", "jenkins", "terraform", "cloud",
                 "aws", "gcp", "azure", "deploy"}
_DE_KW        = {"spark", "airflow", "kafka", "etl", "data pipeline", "warehouse",
                 "redshift", "bigquery", "dbt", "hadoop"}
_SWE_KW       = {"solid", "pattern", "refactor", "api", "rest", "microservice",
                 "object", "class", "interface", "inheritance"}


def classify_question(question: str) -> tuple[str, str]:
    """
    Returns (domain, category) for the question.
    Simple keyword matching – fast, no API call required.
    """
    q = question.lower()

    # Category
    if any(kw in q for kw in _CODING_KW):
        category = "CODING"
    elif any(kw in q for kw in _DESIGN_KW):
        category = "SYSTEM_DESIGN"
    elif any(kw in q for kw in _CONCEPT_KW):
        category = "CONCEPT"
    elif any(kw in q for kw in _PROJECT_KW):
        category = "PROJECT"
    elif any(kw in q for kw in _BEHAV_KW):
        category = "BEHAVIORAL"
    else:
        category = "UNKNOWN"

    # Domain
    if any(kw in q for kw in _DEEP_KW):
        domain = "DEEP_LEARNING"
    elif any(kw in q for kw in _NLP_KW):
        domain = "NLP"
    elif any(kw in q for kw in _CV_KW):
        domain = "COMPUTER_VISION"
    elif any(kw in q for kw in _ML_KW):
        domain = "MACHINE_LEARNING"
    elif any(kw in q for kw in _MLOPS_KW):
        domain = "MLOPS"
    elif any(kw in q for kw in _DEVOPS_KW):
        domain = "DEVOPS"
    elif any(kw in q for kw in _DE_KW):
        domain = "DATA_ENGINEERING"
    elif any(kw in q for kw in _SWE_KW):
        domain = "SOFTWARE_ENGINEERING"
    else:
        domain = "GENERAL"

    return domain, category
