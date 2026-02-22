from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppState:
    qa_draft: str = ""
    selected_tab: str = "search"
    docs_page: int = 0
    onboarding_dismissed: bool = False


def load_state(path: Path) -> AppState:
    if not path.exists():
        return AppState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return AppState()
    return AppState(
        qa_draft=str(payload.get("qa_draft", "")),
        selected_tab=str(payload.get("selected_tab", "search")),
        docs_page=max(0, int(payload.get("docs_page", 0))),
        onboarding_dismissed=bool(payload.get("onboarding_dismissed", False)),
    )


def save_state(path: Path, state: AppState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "qa_draft": state.qa_draft,
        "selected_tab": state.selected_tab,
        "docs_page": state.docs_page,
        "onboarding_dismissed": state.onboarding_dismissed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
