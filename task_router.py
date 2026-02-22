from __future__ import annotations

TASK_MODES = {
    "qa",
    "classify_spam",
    "summarize",
    "keywords",
    "language_detect",
    "product_blurb",
    "translate_es",
    "rewrite_professional",
    "email_reschedule",
    "code_explain",
    "counterargument",
    "json_title_summary_tags",
}

SMALL_MODEL_MODES = {
    "qa",
    "classify_spam",
    "summarize",
    "keywords",
    "language_detect",
    "product_blurb",
}

LARGE_MODEL_MODES = {
    "counterargument",
    "code_explain",
    "json_title_summary_tags",
    "translate_es",
    "rewrite_professional",
    "email_reschedule",
}

SYSTEM_PROMPT = "You are Fonte, a local assistant. Always produce an answer. Guess if needed. Do not refuse."


def detect_mode(query: str) -> str:
    text = str(query or "").strip()
    lower = text.lower()
    if "json_title_summary_tags" in lower or (
        "json" in lower and "title" in lower and "summary" in lower and "tag" in lower
    ):
        return "json_title_summary_tags"
    if "counterargument" in lower or "counter argument" in lower or "argue against" in lower:
        return "counterargument"
    if "code explain" in lower or "explain this code" in lower or "what does this code" in lower:
        return "code_explain"
    if "translate to spanish" in lower or "translate to es" in lower or " al español" in lower:
        return "translate_es"
    if "rewrite professional" in lower or "make this professional" in lower or "formal rewrite" in lower:
        return "rewrite_professional"
    if "reschedule" in lower and "email" in lower:
        return "email_reschedule"
    if "spam" in lower and ("classify" in lower or "is this" in lower):
        return "classify_spam"
    if "keyword" in lower or "keywords" in lower:
        return "keywords"
    if "language detect" in lower or "detect language" in lower or "what language" in lower:
        return "language_detect"
    if "product blurb" in lower or "marketing blurb" in lower or "product description" in lower:
        return "product_blurb"
    if "summarize" in lower or "summary" in lower:
        return "summarize"
    return "qa"


def _is_simple_qa(query: str) -> bool:
    text = str(query or "").strip()
    if len(text) > 220:
        return False
    lower = text.lower()
    complex_markers = (
        "json",
        "analyze",
        "architecture",
        "tradeoff",
        "compare",
        "design",
        "multi-step",
        "counterargument",
    )
    return not any(marker in lower for marker in complex_markers)


def select_model_id(mode: str, query: str, cfg: dict) -> str:
    selected_mode = str(mode or "qa")
    small_id = str(cfg.get("model_small_id") or "").strip()
    large_id = str(cfg.get("model_large_id") or "").strip()

    if selected_mode in LARGE_MODEL_MODES:
        selected = large_id
    elif selected_mode in SMALL_MODEL_MODES:
        if selected_mode == "qa" and not _is_simple_qa(query):
            selected = large_id
        else:
            selected = small_id
    else:
        selected = large_id

    if selected:
        return selected
    if large_id:
        return large_id
    if small_id:
        return small_id
    return ""


def _mode_instruction(mode: str) -> str:
    instructions = {
        "qa": "Answer the user question directly in plain text.",
        "classify_spam": 'Output exactly "SPAM" or "NOT_SPAM".',
        "summarize": "Provide a concise summary.",
        "keywords": "Output exactly 7 keywords, comma-separated, no extra text.",
        "language_detect": "Output language name only.",
        "product_blurb": "Write exactly 4 sentences, no bullets, no title.",
        "translate_es": "Output Spanish translation only.",
        "rewrite_professional": "Output revised professional text only.",
        "email_reschedule": "Write a short email with greeting, 2-5 sentences, and closing.",
        "code_explain": "Explain code with sections: Inputs, Outputs, Side effects.",
        "counterargument": "Format exactly:\nMain claim: ...\nCounterargument: ...",
        "json_title_summary_tags": (
            "Output ONLY valid JSON with keys: title, summary, tags. "
            "tags must be a list of strings. No markdown."
        ),
    }
    return instructions.get(mode, instructions["qa"])


def _render_context(context: list[tuple[int, str, str, str]]) -> str:
    if not context:
        return "No retrieved context. Answer anyway using general knowledge. Guess if needed."
    lines = []
    for rowid, title, source, chunk_text in context[:6]:
        lines.append(f"[{rowid}] {title} ({source})\n{str(chunk_text or '').strip()}")
    joined = "\n\n".join(lines).strip()
    return f"Context:\n{joined}\n\nUse it when helpful, but you may use general knowledge."


def build_messages(query: str, context: list[tuple[int, str, str, str]], mode: str) -> list[dict[str, str]]:
    prompt = "\n\n".join(
        [
            _render_context(context),
            f"Mode: {mode}",
            _mode_instruction(mode),
            f"User input:\n{str(query or '').strip()}",
        ]
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
