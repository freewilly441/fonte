from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RequestSnapshot:
    request_id: int
    key: str


class RequestCoordinator:
    """Tracks in-flight async requests with dedupe and cancellation support."""

    def __init__(self) -> None:
        self._current_id = 0
        self._inflight_key: str | None = None
        self._inflight_id: int | None = None

    def start(self, key: str, *, dedupe: bool = True) -> RequestSnapshot | None:
        if dedupe and self._inflight_key == key and self._inflight_id is not None:
            return None
        self._current_id += 1
        self._inflight_id = self._current_id
        self._inflight_key = key
        return RequestSnapshot(request_id=self._current_id, key=key)

    def is_active(self, snapshot: RequestSnapshot) -> bool:
        return self._inflight_id == snapshot.request_id

    def complete(self, snapshot: RequestSnapshot) -> bool:
        if not self.is_active(snapshot):
            return False
        self._inflight_id = None
        self._inflight_key = None
        return True

    def cancel(self) -> None:
        self._inflight_id = None
        self._inflight_key = None

    @property
    def inflight_key(self) -> str | None:
        return self._inflight_key
