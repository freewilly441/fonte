from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import config
import kb


@dataclass(slots=True)
class DocumentItem:
    doc_id: int
    title: str
    source: str
    path: str
    is_favorite: bool


@dataclass(slots=True)
class DocumentsPage:
    items: list[DocumentItem]
    total_count: int
    page: int
    page_size: int
    cached_at: float


def apply_optimistic_favorite(
    docs: list[DocumentItem], index: int
) -> tuple[list[DocumentItem], DocumentItem]:
    item = docs[index]
    updated = list(docs)
    updated[index] = DocumentItem(
        doc_id=item.doc_id,
        title=item.title,
        source=item.source,
        path=item.path,
        is_favorite=not item.is_favorite,
    )
    return updated, item


class DocumentsRepository:
    def __init__(self, db_path: Path, config_path: Path, *, cache_ttl_sec: float = 30.0) -> None:
        self.db_path = db_path
        self.config_path = config_path
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: list[DocumentItem] | None = None
        self._cache_ts: float = 0.0
        self._cached_total_count: int = 0

    def get_cached_documents(self) -> list[DocumentItem] | None:
        if self._cache is None:
            return None
        return list(self._cache)

    def load_documents(self) -> list[DocumentItem]:
        now = time.time()
        if self._cache is not None and (now - self._cache_ts) <= self.cache_ttl_sec:
            return list(self._cache)
        return self.refresh_documents()

    def refresh_documents(self) -> list[DocumentItem]:
        favorites = self._favorite_ids()
        rows = kb.list_documents(self.db_path)
        docs = [
            DocumentItem(
                doc_id=doc_id,
                title=title,
                source=source,
                path=path or "",
                is_favorite=doc_id in favorites,
            )
            for doc_id, title, source, path in rows
        ]
        self._cache = docs
        self._cache_ts = time.time()
        self._cached_total_count = len(rows)
        return list(docs)

    def set_cache(self, docs: list[DocumentItem], *, total_count: int | None = None) -> None:
        self._cache = list(docs)
        self._cache_ts = time.time()
        self._cached_total_count = int(total_count) if total_count is not None else len(docs)

    def get_documents_page(
        self,
        *,
        page: int,
        page_size: int,
        force_refresh: bool = False,
    ) -> DocumentsPage:
        page_index = max(0, int(page))
        size = max(1, int(page_size))
        favorites = self._favorite_ids()

        if not force_refresh and self._cache is not None and self._cached_total_count:
            start = page_index * size
            end = start + size
            items = self._cache[start:end]
            return DocumentsPage(
                items=list(items),
                total_count=self._cached_total_count,
                page=page_index,
                page_size=size,
                cached_at=self._cache_ts,
            )

        offset = page_index * size
        rows = kb.list_documents_paged(self.db_path, limit=size, offset=offset)
        total_count = kb.count_documents(self.db_path)
        items = [
            DocumentItem(
                doc_id=doc_id,
                title=title,
                source=source,
                path=path or "",
                is_favorite=doc_id in favorites,
            )
            for doc_id, title, source, path in rows
        ]
        # Keep a fresh full cache only when result set is reasonably bounded.
        if total_count <= 5000:
            self.refresh_documents()
        return DocumentsPage(
            items=items,
            total_count=total_count,
            page=page_index,
            page_size=size,
            cached_at=time.time(),
        )

    def toggle_favorite(self, doc_id: int, is_favorite: bool) -> None:
        cfg = config.load_config(self.config_path)
        favorites = self._favorite_ids_from_cfg(cfg)
        if is_favorite:
            favorites.add(doc_id)
        else:
            favorites.discard(doc_id)
        cfg["favorite_doc_ids"] = ",".join(str(i) for i in sorted(favorites))
        config.save_config(self.config_path, cfg)

    def _favorite_ids(self) -> set[int]:
        cfg = config.load_config(self.config_path)
        return self._favorite_ids_from_cfg(cfg)

    @staticmethod
    def _favorite_ids_from_cfg(cfg: dict) -> set[int]:
        raw = (cfg.get("favorite_doc_ids") or "").strip()
        if not raw:
            return set()
        ids: set[int] = set()
        for token in raw.split(","):
            token = token.strip()
            if token.isdigit():
                ids.add(int(token))
        return ids
