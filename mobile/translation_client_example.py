"""Example mobile/frontend client for the local Fonte translation service.

Usage:
    python mobile/translation_client_example.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8765"


def _request_json(method: str, path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(
        url=f"{BASE_URL}{path}",
        method=method,
        data=data,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"success": False, "error": {"code": "http-error", "message": body or str(exc)}}
    except urllib.error.URLError as exc:
        return {"success": False, "error": {"code": "connection-error", "message": str(exc)}}


def health_check() -> dict:
    return _request_json("GET", "/health")


def translate_text(text: str, source: str, target: str) -> dict:
    return _request_json(
        "POST",
        "/translate",
        {
            "text": text,
            "source": source,
            "target": target,
        },
    )


def translate_batch(texts: list[str], source: str, target: str) -> dict:
    return _request_json(
        "POST",
        "/translate_batch",
        {
            "texts": texts,
            "source": source,
            "target": target,
        },
    )


def main() -> int:
    print("Health:")
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))

    print("\nSingle translation:")
    single = translate_text("hello world", "en", "pt")
    print(json.dumps(single, ensure_ascii=False, indent=2))

    print("\nBatch translation:")
    batch = translate_batch(["hello", "good night", "water"], "en", "de")
    print(json.dumps(batch, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
