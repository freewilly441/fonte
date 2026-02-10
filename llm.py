from pathlib import Path
from typing import List, Tuple


def load_llm(model_path: Path):
    try:
        from llama_cpp import Llama
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(f"Missing llama-cpp-python: {exc}") from exc

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    return Llama(
        model_path=str(model_path),
        n_ctx=2048,
        n_threads=4,
        n_batch=256,
        verbose=False,
    )


def build_prompt(question: str, context: List[Tuple[int, str, str, str]]) -> str:
    context_lines = []
    for rowid, title, source, text in context:
        context_lines.append(f"[{rowid}] {title} ({source})\n{text.strip()}")

    joined = "\n\n".join(context_lines)
    return (
        "You are a strictly grounded assistant. Answer only using the provided context. "
        "If the answer is not in the context, respond with 'I don't know.'\n\n"
        f"Context:\n{joined}\n\n"
        f"Question: {question}\n"
        "Answer with citations like [123]."
    )


def generate_answer(
    llm, question: str, context: List[Tuple[int, str, str, str]], max_tokens: int = 256
) -> str:
    prompt = build_prompt(question, context)
    try:
        out = llm(prompt, max_tokens=max_tokens, temperature=0.0, top_p=1.0, top_k=1)
        return out["choices"][0]["text"].strip()
    except Exception:
        # Fallback if the llama-cpp-python API differs
        out = llm.create_completion(
            prompt=prompt, max_tokens=max_tokens, temperature=0.0, top_p=1.0, top_k=1
        )
        return out["choices"][0]["text"].strip()
