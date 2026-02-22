from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

SENSITIVE_HINTS = ("token", "password", "secret", "authorization", "cookie")


def _sanitize(text: str) -> str:
    out = text
    for hint in SENSITIVE_HINTS:
        out = out.replace(hint, "[redacted]")
        out = out.replace(hint.upper(), "[redacted]")
    return out


def install_crash_hook(crash_log_path: Path) -> None:
    previous_hook = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        crash_log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": time.time(),
            "type": getattr(exc_type, "__name__", "Exception"),
            "message": _sanitize(str(exc_value)),
            "traceback": _sanitize("".join(traceback.format_exception(exc_type, exc_value, exc_tb))),
        }
        with crash_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
        if previous_hook is not None:
            previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
