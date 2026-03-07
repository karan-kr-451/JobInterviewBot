"""
llm.prompt_builder - Prompt construction for interview responses.
"""

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

RESPONSE_INSTRUCTIONS: dict[str, str] = {
    "CODING": """1. APPROACH (1-2 sentences): Brief strategy overview.
2. CODE: Clean Python without comments. Handle edge cases.
3. COMPLEXITY: State time/space complexity concisely.
Keep it under 150 words total. Be direct and technical.""",
    "SYSTEM_DESIGN": """Cover in 4-5 concise points:
- Scale assumptions (users, requests/sec)
- Core components (API, DB, cache, queue)
- Key decisions (sync/async, DB choice, caching strategy)
- Bottlenecks and solutions
- Trade-offs
Under 200 words. Be specific and technical.""",
    "CONCEPT": """Answer in 3-4 sentences:
1. Clear definition (1 sentence)
2. Key characteristics or how it works (1-2 sentences)
3. Practical use case or benefit (1 sentence)
Under 100 words. Be precise and technical.""",
    "PROJECT": """Answer in 4-5 sentences:
- Problem/context (1 sentence)
- Your role and approach (2 sentences)
- Key challenge and solution (1 sentence)
- Impact/outcome with metrics (1 sentence)
Under 120 words. Be specific and results-focused.""",
    "BEHAVIORAL": """Use STAR format, 4-5 sentences:
- Situation (1 sentence)
- Task/challenge (1 sentence)
- Action YOU took (2 sentences)
- Result and learning (1 sentence)
Under 120 words. Be specific and honest.""",
    "UNKNOWN": "Answer directly in 2-4 sentences. Lead with the main point. Be concise and technical. Under 100 words.",
}

# Response style guidelines
PERSONA_GUIDELINES = """
CRITICAL RULES:
- BE CONCISE: Answer in 3-5 sentences maximum
- BE DIRECT: Start with the main point, no filler
- BE SPECIFIC: Use concrete examples, numbers, technologies
- BE TECHNICAL: Use proper terminology, avoid fluff

STYLE:
- Professional and confident
- Clear and structured
- Technical but accessible
- First person ("I", "my", "we")

AVOID:
- Long introductions ("So basically", "You know", "I mean")
- Repetitive explanations
- Excessive hedging ("I think", "kind of", "sort of")
- Conversational filler
- Over-explaining simple concepts

TONE: Direct, professional, technically precise. Answer like you're in a real interview - concise and to the point.
"""


def build_prompt(question: str, domain: str, category: str,
                 history: list, docs: dict) -> str:
    """Build optimized LLM prompt using RAG for relevant context only."""
    summary   = docs.get("candidate_summary", "").strip() or "a skilled professional"
    job_title = docs.get("job_title", "").strip() or "Prospective Role"
    
    # Extract candidate name from resume if available
    candidate_name = ""
    resume_text = docs.get("resume_text", "")
    if resume_text:
        # Name is usually in the first line or first few lines
        first_lines = resume_text.split("\n")[:5]
        for line in first_lines:
            line = line.strip()
            # Look for a line that looks like a name (starts with capital, no special chars)
            if line and line[0].isupper() and not any(c in line for c in ['@', 'http', ':', '|']):
                # Remove markdown formatting
                line = line.replace('#', '').strip()
                if len(line.split()) <= 4 and len(line) > 3:  # Name is usually 1-4 words
                    candidate_name = line
                    break

    # ALWAYS use RAG to find relevant context (not just for specific categories)
    # RAG semantic search is smarter than hardcoded category matching
    relevant_context = ""
    try:
        from llm.documents import query_bio
        # RAG search returns only relevant snippets based on semantic similarity
        relevant_context = query_bio(question, top_k=2)  # Get top 2 relevant chunks
    except Exception:
        pass

    # Conversation history: Only last 4 Q&A pairs for context continuity
    recent_history = []
    if len(history) >= 8:
        recent_history = history[-8:]  # Last 4 Q&A pairs
    elif history:
        recent_history = history

    conv = ""
    if recent_history:
        for i in range(0, len(recent_history) - 1, 2):
            conv += f"Q: {recent_history[i]}\nA: {recent_history[i+1]}\n"

    # Build a direct "You ARE the candidate" prompt
    # No "AI assistant" meta-framing - that causes the "I'd be happy to help" filler.
    name_str = f"Your name is {candidate_name}." if candidate_name else ""
    
    prompt = f"You are {candidate_name or 'a candidate'} in a professional technical interview for the role of '{job_title}'.\n"
    prompt += f"Candidate Identity: {summary}. {name_str}\n\n"
    
    prompt += "CRITICAL MISSION:\n"
    prompt += "Provide the EXACT spoken response to the interviewer's question. No introductions, no meta-talk, no 'I'd be happy to help'.\n"
    prompt += "Speak directly in first person as the candidate.\n\n"
    
    # Include RAG-retrieved relevant context (if found)
    if relevant_context:
        prompt += f"== CANDIDATE CONTEXT & EXPERIENCE ==\n{relevant_context}\n\n"
    
    # Recent conversation for context continuity
    if conv:
        prompt += f"== RECENT INTERVIEW DIALOGUE ==\n{conv}\n"
    
    prompt += (
        f"== INTERVIEW QUESTION ==\n"
        f"Domain: {domain}\n"
        f"Question: {question}\n\n"
        f"== RESPONSE REQUIREMENTS ==\n"
        f"1. {DOMAIN_CONTEXT.get(domain, DOMAIN_CONTEXT['GENERAL'])}\n"
        f"2. {RESPONSE_INSTRUCTIONS.get(category, RESPONSE_INSTRUCTIONS['UNKNOWN'])}\n"
        f"3. {PERSONA_GUIDELINES}\n\n"
        f"== FINAL DIRECTIVE ==\n"
        f"Answer in first person (as the candidate), 3-5 sentences, under 150 words.\n"
        f"STRICTLY FORBIDDEN: Do not say 'I would say', 'Here is an answer', or 'I'd be happy to help'.\n"
        f"Start your response IMMEDIATELY with the answer to the question."
    )
    return prompt
