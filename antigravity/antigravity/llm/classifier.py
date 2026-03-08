"""
llm/classifier.py — Question classification by domain and category.

Uses fast LLM-based classification instead of hardcoded keywords.
"""

from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Fallback keyword matching (only used if LLM classification fails)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "DEEP_LEARNING": ["neural network", "deep learning", "transformer", "bert", "gpt"],
    "NLP": ["nlp", "natural language", "tokenization", "llm", "rag"],
    "COMPUTER_VISION": ["computer vision", "image", "object detection", "cnn"],
    "MACHINE_LEARNING": ["machine learning", "classification", "regression", "sklearn"],
    "MLOPS": ["mlops", "model deployment", "inference", "monitoring"],
    "SOFTWARE_ENGINEERING": ["design pattern", "api", "database", "algorithm", "data structure", "oop", "solid"],
    "DEVOPS": ["docker", "kubernetes", "ci/cd", "aws"],
    "DATA_ENGINEERING": ["data pipeline", "etl", "spark", "airflow"],
    "GENERAL": ["python", "java", "javascript", "programming", "tell me about yourself", "introduce"],
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "CODING": ["write", "implement", "code a function", "write a function", "write code"],
    "BEHAVIORAL": ["tell me about yourself", "strength", "weakness", "challenge", "teamwork"],
    "PROJECT": ["tell me about a project", "what did you build", "describe a project"],
    "SYSTEM_DESIGN": ["design a system", "how would you design", "architect"],
    "CONCEPT": ["what is", "what are", "explain", "how does", "define", "difference between", "what do you mean"],
}


def _classify_with_keywords(question: str) -> Tuple[str, str]:
    """Fallback keyword-based classification."""
    q = question.lower()
    
    scores = {d: sum(1 for kw in kws if kw in q)
              for d, kws in DOMAIN_KEYWORDS.items()}
    best_score = max(scores.values()) if scores else 0
    domain = max(scores, key=lambda d: scores[d]) if best_score > 0 else "GENERAL"
    
    category = next(
        (cat for cat, kws in CATEGORY_KEYWORDS.items() if any(kw in q for kw in kws)),
        "UNKNOWN"
    )
    return domain, category


def classify_question(question: str, groq_api_key: str = "") -> Tuple[str, str]:
    """
    Classify question using fast LLM call.
    Returns (domain, category) tuple.
    
    Uses Groq's llama-3.1-8b-instant for sub-second classification.
    Falls back to keyword matching if LLM fails.
    """
    if not groq_api_key:
        return _classify_with_keywords(question)
        
    try:
        import requests
        
        classification_prompt = f"""Classify this interview question into domain and category.

Question: {question}

DOMAINS (pick the MOST specific match, or GENERAL if broad/basic):
- DEEP_LEARNING: neural networks, transformers, backpropagation, CNN, RNN, attention
- NLP: tokenization, embeddings, LLMs, RAG, text processing, language models
- COMPUTER_VISION: image processing, object detection, segmentation, OpenCV
- MACHINE_LEARNING: specific ML algorithms (random forest, SVM, gradient boosting, k-means)
- MLOPS: model deployment, monitoring, feature stores, ML pipelines
- SOFTWARE_ENGINEERING: design patterns, OOP, APIs, databases, algorithms, data structures
- DEVOPS: Docker, Kubernetes, CI/CD, cloud infrastructure, AWS/GCP/Azure
- DATA_ENGINEERING: ETL, data pipelines, Spark, Airflow, data warehousing
- GENERAL: broad questions, language basics, introductions, general tech concepts

CATEGORIES:
- CODING: "write code", "implement", "function to", explicit code request
- SYSTEM_DESIGN: "design a system", "how would you architect"
- BEHAVIORAL: "tell me about yourself", strengths, weaknesses, teamwork
- PROJECT: "describe a project", "what did you build"
- CONCEPT: "what is", "explain", "how does", "define", definitional/conceptual questions
- UNKNOWN: doesn't fit any above

RULES:
- Use GENERAL for broad questions like "What is Python?", "What is programming?", "Tell me about yourself"
- Use CONCEPT for "what is X" or "explain X" questions (NOT CODING)
- Use CODING only when explicitly asked to write/implement code
- If unsure between specific domain and GENERAL, prefer GENERAL

Respond ONLY with: DOMAIN|CATEGORY
Example: GENERAL|CONCEPT"""

        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": classification_prompt}],
            "temperature": 0.1,
            "max_tokens": 20,
        }
        
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=3.0
        )
        
        if resp.status_code == 200:
            result = resp.json()["choices"][0]["message"]["content"].strip()
            
            # Parse response: "DOMAIN|CATEGORY"
            if "|" in result:
                parts = result.split("|")
                domain = parts[0].strip().upper()
                category = parts[1].strip().upper()
                
                # Validate domain
                valid_domains = list(DOMAIN_KEYWORDS.keys()) + ["GENERAL"]
                if domain not in valid_domains:
                    domain = "GENERAL"
                
                # Validate category
                valid_categories = list(CATEGORY_KEYWORDS.keys()) + ["UNKNOWN"]
                if category not in valid_categories:
                    category = "UNKNOWN"
                
                return domain, category
                
    except Exception as e:
        logger.debug("[CLASSIFIER] Fast classification failed, using keywords: %s", e)
        
    # Fallback to keyword matching
    return _classify_with_keywords(question)
