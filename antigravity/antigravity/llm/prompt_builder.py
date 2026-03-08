"""
llm/prompt_builder.py — Context-aware prompt assembly.

Builds the prompt string combining persona mapping, resume RAG context,
and the history of this interview so the LLM has full awareness.
Enforces strict response constraints based on the question domain and category.
"""

from __future__ import annotations

import logging

from antigravity.core.app_state import get_app_state

logger = logging.getLogger(__name__)

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


def build_final_prompt(question: str, domain: str = "GENERAL", category: str = "UNKNOWN", rag_retriever: Any = None) -> str:
    """
    Construct the full prompt string for the LLM using the current
    transcript/response history, domain tuning, and RAG context.
    """
    state = get_app_state()
    
    # Retrieve RAG context if retriever provided
    rag_context = ""
    candidate_summary = "A skilled professional."
    candidate_name = ""
    
    if rag_retriever:
        rag_context = rag_retriever.get_context_for_query(question)
        candidate_summary = rag_retriever.get_candidate_summary()
        candidate_name = rag_retriever.candidate_name

    # Safely snapshot history to avoid holding lock while string building
    history_snapshot: list[str] = []
    
    with state._lock:
        t_hist = list(state.transcript_history)
        r_hist = list(state.response_history)
        
    # Get last 4 turns max to avoid context window overflow
    t_hist = t_hist[-4:]
    r_hist = r_hist[-4:]
    
    conv = ""
    for i in range(min(len(t_hist), len(r_hist))):
        conv += f"Q: {t_hist[i]}\nA: {r_hist[i]}\n"
        
    name_str = f"Your name is {candidate_name}." if candidate_name else ""
    
    prompt = f"You are {candidate_name or 'a candidate'} in a professional technical interview.\n"
    prompt += f"Candidate Identity: {candidate_summary} {name_str}\n\n"
    
    prompt += "CRITICAL MISSION:\n"
    prompt += "Provide the EXACT spoken response to the interviewer's question. No introductions, no meta-talk, no 'I'd be happy to help'.\n"
    prompt += "Speak directly in first person as the candidate.\n\n"
    
    # Include RAG-retrieved relevant context (if found)
    if rag_context:
        prompt += f"== CANDIDATE CONTEXT & EXPERIENCE ==\n{rag_context}\n\n"
    
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
