from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
import urllib.error
import urllib.request


@dataclass
class RemoteFetchResult:
    url: str
    body: str
    content_type: str
    fetched_at: str


@dataclass
class RemoteDocument:
    title: str
    source: str
    text: str
    source_url: str
    fetched_at: str
    license_name: str | None = None
    path: str | None = None


class RateLimiter:
    def __init__(self, min_interval_sec: float = 0.0):
        self.min_interval_sec = max(0.0, float(min_interval_sec))
        self._last_ts = 0.0

    def wait(self) -> None:
        if self.min_interval_sec <= 0:
            return
        now = time.monotonic()
        delta = now - self._last_ts
        if delta < self.min_interval_sec:
            time.sleep(self.min_interval_sec - delta)
        self._last_ts = time.monotonic()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_url(
    url: str,
    *,
    timeout_sec: int = 20,
    retries: int = 2,
    user_agent: str = "Fonte/1.0 (+local-app)",
    rate_limiter: RateLimiter | None = None,
) -> RemoteFetchResult:
    attempts = max(0, int(retries)) + 1
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        if rate_limiter is not None:
            rate_limiter.wait()
        req = urllib.request.Request(url=url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=max(1, int(timeout_sec))) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                content_type = resp.headers.get("Content-Type", "")
            return RemoteFetchResult(
                url=url,
                body=body,
                content_type=content_type,
                fetched_at=utc_now_iso(),
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep(0.4 * attempt)
    raise RuntimeError(f"Failed to fetch URL after {attempts} attempt(s): {url}") from last_exc


def fetch_json(
    url: str,
    *,
    timeout_sec: int = 20,
    retries: int = 2,
    user_agent: str = "Fonte/1.0 (+local-app)",
    rate_limiter: RateLimiter | None = None,
) -> tuple[dict, RemoteFetchResult]:
    result = fetch_url(
        url,
        timeout_sec=timeout_sec,
        retries=retries,
        user_agent=user_agent,
        rate_limiter=rate_limiter,
    )
    try:
        data = json.loads(result.body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON response from: {url}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object response from: {url}")
    return data, result


def normalize_remote_document(
    *,
    title: str,
    source: str,
    text: str,
    source_url: str,
    fetched_at: str | None = None,
    license_name: str | None = None,
    path: str | None = None,
) -> RemoteDocument:
    clean_title = title.strip() or "Untitled"
    clean_source = source.strip() or "remote"
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Remote document text is empty")
    return RemoteDocument(
        title=clean_title,
        source=clean_source,
        text=clean_text,
        source_url=source_url.strip(),
        fetched_at=fetched_at or utc_now_iso(),
        license_name=(license_name or "").strip() or None,
        path=path,
    )
