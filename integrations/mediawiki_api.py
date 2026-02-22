from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import quote, urlencode

import ingest_remote
import kb


@dataclass
class WikiPageMatch:
    title: str
    page_key: str
    url: str
    snippet: str = ""


def _normalize_language(language: str) -> str:
    lang = (language or "en").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,10}", lang):
        return "en"
    return lang


def _wiki_base(language: str) -> str:
    lang = _normalize_language(language)
    return f"https://{lang}.wikipedia.org"


def _clean_snippet(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def search_pages(
    query: str,
    *,
    limit: int = 5,
    language: str = "en",
    timeout_sec: int = 20,
    user_agent: str = "Fonte/1.0 (+local-app)",
    rate_limiter: ingest_remote.RateLimiter | None = None,
) -> list[WikiPageMatch]:
    q = query.strip()
    if not q:
        return []
    cap = max(1, min(int(limit), 20))
    base = _wiki_base(language)

    rest_url = f"{base}/w/rest.php/v1/search/page?{urlencode({'q': q, 'limit': cap})}"
    try:
        payload, _ = ingest_remote.fetch_json(
            rest_url,
            timeout_sec=timeout_sec,
            retries=1,
            user_agent=user_agent,
            rate_limiter=rate_limiter,
        )
        pages = payload.get("pages") or []
        results: list[WikiPageMatch] = []
        for page in pages:
            title = str(page.get("title") or "").strip()
            if not title:
                continue
            key = str(page.get("key") or title.replace(" ", "_")).strip()
            url = (
                str((page.get("content_urls") or {}).get("desktop", {}).get("page") or "").strip()
                or f"{base}/wiki/{quote(key)}"
            )
            results.append(
                WikiPageMatch(
                    title=title,
                    page_key=key,
                    url=url,
                    snippet=_clean_snippet(str(page.get("excerpt") or "")),
                )
            )
        if results:
            return results[:cap]
    except Exception:
        pass

    params = {
        "action": "query",
        "list": "search",
        "srsearch": q,
        "srlimit": str(cap),
        "format": "json",
        "utf8": "1",
    }
    action_url = f"{base}/w/api.php?{urlencode(params)}"
    payload, _ = ingest_remote.fetch_json(
        action_url,
        timeout_sec=timeout_sec,
        retries=1,
        user_agent=user_agent,
        rate_limiter=rate_limiter,
    )
    items = ((payload.get("query") or {}).get("search") or [])
    results = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        key = title.replace(" ", "_")
        results.append(
            WikiPageMatch(
                title=title,
                page_key=key,
                url=f"{base}/wiki/{quote(key)}",
                snippet=_clean_snippet(str(item.get("snippet") or "")),
            )
        )
    return results[:cap]


def fetch_page_text(
    title: str,
    *,
    language: str = "en",
    timeout_sec: int = 20,
    user_agent: str = "Fonte/1.0 (+local-app)",
    rate_limiter: ingest_remote.RateLimiter | None = None,
) -> tuple[str, str, str]:
    page_title = title.strip()
    if not page_title:
        raise ValueError("Page title cannot be empty")
    base = _wiki_base(language)
    key = page_title.replace(" ", "_")

    summary_text = ""
    canonical_url = ""
    summary_url = f"{base}/api/rest_v1/page/summary/{quote(key)}"
    try:
        summary, _ = ingest_remote.fetch_json(
            summary_url,
            timeout_sec=timeout_sec,
            retries=1,
            user_agent=user_agent,
            rate_limiter=rate_limiter,
        )
        summary_text = str(summary.get("extract") or "").strip()
        canonical_url = str((summary.get("content_urls") or {}).get("desktop", {}).get("page") or "").strip()
    except Exception:
        pass

    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": page_title,
        "format": "json",
        "utf8": "1",
    }
    extract_url = f"{base}/w/api.php?{urlencode(params)}"
    payload, _ = ingest_remote.fetch_json(
        extract_url,
        timeout_sec=timeout_sec,
        retries=1,
        user_agent=user_agent,
        rate_limiter=rate_limiter,
    )
    pages = ((payload.get("query") or {}).get("pages") or {})
    for page in pages.values():
        resolved_title = str(page.get("title") or page_title).strip() or page_title
        extract = str(page.get("extract") or "").strip()
        if extract:
            resolved_key = resolved_title.replace(" ", "_")
            url = canonical_url or f"{base}/wiki/{quote(resolved_key)}"
            return resolved_title, extract, url

    if summary_text:
        return page_title, summary_text, canonical_url or f"{base}/wiki/{quote(key)}"
    raise RuntimeError(f"No text extract available for Wikipedia page: {page_title}")


def ingest_query(
    db_path: Path,
    query: str,
    *,
    limit: int = 5,
    language: str = "en",
    source: str = "wikipedia",
    timeout_sec: int = 20,
    user_agent: str = "Fonte/1.0 (+local-app)",
) -> tuple[int, list[str]]:
    kb.init_db(db_path)
    limiter = ingest_remote.RateLimiter(min_interval_sec=0.2)
    matches = search_pages(
        query,
        limit=limit,
        language=language,
        timeout_sec=timeout_sec,
        user_agent=user_agent,
        rate_limiter=limiter,
    )
    if not matches:
        return 0, []

    inserted = 0
    titles: list[str] = []
    for match in matches:
        try:
            title, text, source_url = fetch_page_text(
                match.title,
                language=language,
                timeout_sec=timeout_sec,
                user_agent=user_agent,
                rate_limiter=limiter,
            )
            doc = ingest_remote.normalize_remote_document(
                title=title,
                source=source,
                text=text,
                source_url=source_url,
                license_name="CC BY-SA 4.0",
            )
            doc_id = kb.ingest_remote_text(
                db_path,
                title=doc.title,
                source=doc.source,
                text=doc.text,
                source_url=doc.source_url,
                fetched_at=doc.fetched_at,
                license_name=doc.license_name,
                path=doc.path,
            )
            if doc_id != -1:
                inserted += 1
                titles.append(doc.title)
        except Exception:
            continue
    return inserted, titles
