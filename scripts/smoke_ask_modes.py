#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import llm_lmstudio
import task_router


TEST_PROMPTS = [
    "What is the capital of France?",
    "Classify spam: You won a free gift card, click now!",
    "Summarize: Fonte is a local app for retrieval and answers.",
    "keywords: local ai retrieval desktop app citations",
    "Detect language: Bonjour tout le monde",
    "Write a product blurb for a local note-taking app",
    "Translate to Spanish: The report is ready for review.",
    "Rewrite professional: hey team can we move this meeting",
    "Write an email to reschedule tomorrow's meeting",
    "Explain this code: def add(a,b): return a+b",
    "Counterargument: Remote work always lowers productivity.",
    "json_title_summary_tags: New features shipped in Fonte",
]


def main() -> int:
    cfg = config.DEFAULT_CONFIG.copy()
    base_url = cfg.get("lmstudio_base_url", "http://localhost:1234/v1")
    timeout = cfg.get("timeout_seconds", "20")
    temperature = cfg.get("temperature", "0.2")
    max_tokens = cfg.get("max_tokens", "192")
    for prompt in TEST_PROMPTS:
        mode = task_router.detect_mode(prompt)
        model = task_router.select_model_id(mode, prompt, cfg)
        messages = task_router.build_messages(prompt, [], mode)
        if mode == "json_title_summary_tags":
            payload = llm_lmstudio.chat_json(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                base_url=base_url,
            )
            output = str(payload).strip()
        else:
            output = llm_lmstudio.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                base_url=base_url,
            ).strip()
        print(f"{mode}: {output}")
        if not output:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
