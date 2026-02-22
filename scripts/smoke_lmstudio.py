#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import llm_lmstudio

CONFIG_PATH = ROOT / "data" / "config.json"
PLACEHOLDER_MODEL_IDS = {"local-model-0.5b", "local-model-1.5b"}


def _is_invalid_model_id(model_id: str) -> bool:
    cleaned = str(model_id or "").strip()
    return not cleaned or cleaned in PLACEHOLDER_MODEL_IDS


def main() -> int:
    cfg = config.load_config(CONFIG_PATH)
    small_model = str(cfg.get("model_small_id") or "").strip()
    large_model = str(cfg.get("model_large_id") or "").strip()
    model = large_model or small_model
    if _is_invalid_model_id(model):
        print(
            "Warning: invalid LM Studio model id in active config. "
            f"model_large_id='{large_model}', model_small_id='{small_model}', config='{CONFIG_PATH}'",
            file=sys.stderr,
        )
        return 1
    out = llm_lmstudio.chat(
        messages=[
            {"role": "system", "content": "You are Fonte, a local assistant. Always produce an answer. Guess if needed. Do not refuse."},
            {"role": "user", "content": "What is 2+2?"},
        ],
        model=model,
        temperature=cfg.get("temperature", "0.2"),
        max_tokens=cfg.get("max_tokens", "192"),
        timeout=cfg.get("timeout_seconds", "20"),
        base_url=cfg.get("lmstudio_base_url", "http://localhost:1234/v1"),
    )
    text = str(out or "").strip()
    print(text)
    if not text:
        return 1
    if "offline or unavailable" in text.lower():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
