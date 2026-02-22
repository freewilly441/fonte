from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

SENSITIVE_KEYS = ("token", "password", "secret", "authorization", "cookie")


def _sanitize_payload(payload: dict[str, object]) -> dict[str, object]:
    clean: dict[str, object] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if any(hint in lowered for hint in SENSITIVE_KEYS):
            clean[key] = "[redacted]"
            continue
        if isinstance(value, str) and len(value) > 400:
            clean[key] = value[:400] + "...(truncated)"
            continue
        clean[key] = value
    return clean


class AnalyticsTracker:
    def __init__(self, log_path: Path, debug_logger: Callable[[str], None] | None = None) -> None:
        self.log_path = log_path
        self.debug_logger = debug_logger
        self._lock = threading.Lock()

    def track(self, event: str, **payload: object) -> None:
        sanitized = _sanitize_payload(payload)
        row = {
            "ts": time.time(),
            "event": event,
            **sanitized,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        if self.debug_logger is not None:
            self.debug_logger(f"event={event} payload={sanitized}")

    def start_timer(self, screen_name: str) -> "ScreenTimer":
        return ScreenTimer(self, screen_name)


class ScreenTimer:
    def __init__(self, tracker: AnalyticsTracker, screen_name: str) -> None:
        self.tracker = tracker
        self.screen_name = screen_name
        self.start = time.perf_counter()
        self.stopped = False

    def stop(self, *, state: str = "success") -> float:
        if self.stopped:
            return 0.0
        self.stopped = True
        ms = (time.perf_counter() - self.start) * 1000.0
        self.tracker.track("time_to_value", screen=self.screen_name, state=state, value_ms=round(ms, 2))
        return ms

    def cancel(self) -> None:
        self.stopped = True
