from __future__ import annotations

import re


_QUESTION_WORDS = {"who", "what", "when", "where", "why", "how"}
_SENTENCE_HINT_WORDS = {
    "is",
    "are",
    "was",
    "were",
    "do",
    "does",
    "did",
    "can",
    "could",
    "should",
    "would",
    "will",
    "explain",
}


def should_generate_search_answer(query: str) -> bool:
    text = (query or "").strip()
    if not text:
        return False
    if "?" in text:
        return True

    words = re.findall(r"[a-z0-9']+", text.lower())
    if not words:
        return False
    if words[0] in _QUESTION_WORDS:
        return True
    if len(words) >= 8:
        return True
    if len(words) >= 5 and any(word in _SENTENCE_HINT_WORDS for word in words[1:]):
        return True
    if len(words) >= 5 and text.endswith((".", "!")):
        return True
    return False


def route_search_answer(query: str, *, ai_enabled: bool, model_installed: bool) -> str:
    if not ai_enabled:
        return "off"
    if not should_generate_search_answer(query):
        return "search_only"
    if not model_installed:
        return "not_installed"
    return "generate"


def validate_question(query: str) -> str | None:
    text = (query or "").strip()
    if not text:
        return "Question is required."
    if len(text) < 3:
        return "Question is too short."
    if len(text) > 600:
        return "Question is too long. Please keep it under 600 characters."
    return None
