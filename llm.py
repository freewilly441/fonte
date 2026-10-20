from pathlib import Path
from typing import List, Tuple

STOP_SEQUENCES = [
    "\nQ:",
    "\nQuestion:",
    "\nUser:",
    "\nAssistant:",
]

DEFAULT_N_CTX = 8192
FALLBACK_N_CTX = 4096
DEFAULT_MAX_TOKENS = 1024


def load_llm(
    *,
    backend: str = "llama_cpp",
    model_path: Path | None = None,
    n_ctx: int = DEFAULT_N_CTX,
    n_threads: int = 4,
    n_batch: int = 128,
):
    if backend != "llama_cpp":
        raise RuntimeError("Only embedded local llama.cpp inference is supported.")
    if model_path is None:
        raise FileNotFoundError("Model path is required for llama_cpp backend")
    try:
        from llama_cpp import Llama
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(f"Missing llama-cpp-python: {exc}") from exc

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    safe_n_ctx = max(512, int(n_ctx))
    model = Llama(
        model_path=str(model_path),
        n_ctx=safe_n_ctx,
        n_threads=max(1, int(n_threads)),
        n_batch=max(64, int(n_batch)),
        verbose=False,
    )
    return model


def build_prompt(question: str, context: List[Tuple[int, str, str, str]]) -> str:
    context_lines = []
    for rowid, title, source, text in context:
        context_lines.append(f"[{rowid}] {title} ({source})\n{text.strip()}")

    joined = "\n\n".join(context_lines)
    prompt_parts = [
        "You are a helpful assistant. Answer directly, clearly, and with enough detail to fully address the question.",
        "Do not repeat the question.",
        "Finish with a complete final sentence when possible.",
    ]
    if joined:
        prompt_parts.extend(["", "Context:", joined])
    prompt_parts.extend(
        [
            "",
            "Q: What is the number after 9?",
            "A: 10",
            f"Q: {question}",
            "A:",
        ]
    )
    return "\n".join(prompt_parts)


def _remove_leading_query_echo(answer_text: str, question: str) -> str:
    answer = (answer_text or "").strip()
    query = (question or "").strip()
    if not answer or not query:
        return answer
    if answer.lower().startswith(query.lower()):
        trimmed = answer[len(query) :].lstrip(" \t\r\n:,-")
        if trimmed.lower().startswith("a:"):
            trimmed = trimmed[2:].lstrip(" \t\r\n:,-")
        return trimmed
    return answer


def generate_answer(
    llm,
    question: str,
    context: List[Tuple[int, str, str, str]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.35,
    top_p: float = 0.9,
    top_k: int = 40,
) -> str:
    prompt = build_prompt(question, context)
    safe_max_tokens = max(32, min(4096, int(max_tokens)))
    try:
        out = llm(
            prompt,
            max_tokens=safe_max_tokens,
            temperature=float(temperature),
            top_p=float(top_p),
            top_k=int(top_k),
            stop=STOP_SEQUENCES,
        )
        text = out["choices"][0]["text"]
        return _remove_leading_query_echo(text, question)
    except Exception:
        # Fallback if the llama-cpp-python API differs
        out = llm.create_completion(
            prompt=prompt,
            max_tokens=safe_max_tokens,
            temperature=float(temperature),
            top_p=float(top_p),
            top_k=int(top_k),
            stop=STOP_SEQUENCES,
        )
        text = out["choices"][0]["text"]
        return _remove_leading_query_echo(text, question)
