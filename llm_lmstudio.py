from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_API_KEY = "lm-studio"


def _extract_response_text(response: Any) -> str:
    try:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
    except Exception:
        return ""
    return ""


def _build_error_text(exc: Exception) -> str:
    return f"LM Studio offline or unavailable: {exc.__class__.__name__}: {exc}"


def _coerce_timeout(timeout: int | float | str | None) -> float:
    try:
        value = float(timeout if timeout is not None else 20)
    except (TypeError, ValueError):
        value = 20.0
    return max(1.0, min(120.0, value))


def _coerce_temperature(temperature: float | str | None) -> float:
    try:
        value = float(temperature if temperature is not None else 0.2)
    except (TypeError, ValueError):
        value = 0.2
    return max(0.0, min(1.5, value))


def _coerce_max_tokens(max_tokens: int | str | None) -> int:
    try:
        value = int(max_tokens if max_tokens is not None else 1024)
    except (TypeError, ValueError):
        value = 1024
    return max(16, min(4096, value))


def _chat_via_http(
    messages: list[dict[str, str]],
    model: str,
    temperature: float | str,
    max_tokens: int | str,
    timeout: int | float | str,
    base_url: str,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": _coerce_temperature(temperature),
        "max_tokens": _coerce_max_tokens(max_tokens),
    }
    base = str(base_url or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    url = f"{base.rstrip('/')}/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEFAULT_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_coerce_timeout(timeout)) as response:
        body = json.loads(response.read().decode("utf-8", errors="replace"))
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return ""


def chat(
    messages: list[dict[str, str]],
    model: str,
    temperature: float | str = 0.2,
    max_tokens: int | str = 1024,
    timeout: int | float | str = 20,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    selected_model = str(model or "").strip()
    if not selected_model:
        return "LM Studio model is not configured. Set model_small_id or model_large_id in Settings."
    try:
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=str(base_url or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
                api_key=DEFAULT_API_KEY,
                timeout=_coerce_timeout(timeout),
            )
            response = client.chat.completions.create(
                model=selected_model,
                messages=messages,
                temperature=_coerce_temperature(temperature),
                max_tokens=_coerce_max_tokens(max_tokens),
            )
            text = _extract_response_text(response).strip()
        except ModuleNotFoundError:
            text = _chat_via_http(
                messages=messages,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                base_url=base_url,
            ).strip()
        if text:
            return text
        return "LM Studio returned an empty response. Try loading a local model in LM Studio."
    except Exception as exc:
        return _build_error_text(exc)


def chat_json(
    messages: list[dict[str, str]],
    model: str,
    temperature: float | str = 0.2,
    max_tokens: int | str = 1024,
    timeout: int | float | str = 20,
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    first = chat(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        base_url=base_url,
    )
    try:
        parsed = json.loads(first)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    retry_messages = list(messages)
    retry_messages.append(
        {
            "role": "user",
            "content": "Invalid JSON. Output ONLY valid JSON. No markdown. No commentary.",
        }
    )
    second = chat(
        messages=retry_messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        base_url=base_url,
    )
    try:
        parsed = json.loads(second)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    combined = (first or second or "").strip()
    cleaned = re.sub(r"\s+", " ", combined)[:280].strip()
    if not cleaned:
        cleaned = "Generated summary unavailable."
    title = cleaned[:72].strip()
    if len(cleaned) > 72:
        title = cleaned[:69].rstrip() + "..."
    return {"title": title or "Untitled", "summary": cleaned, "tags": ["general"]}
