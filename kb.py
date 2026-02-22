import sqlite3
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict


@dataclass
class ChunkResult:
    rowid: int
    title: str
    source: str
    chunk_text: str
    score: float

CHUNK_SIZE = 800  # characters
CHUNK_OVERLAP = 120
_FTS5_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_VECTOR_SETUP_HINT = "Install optional semantic dependencies with: pip install -r requirements-semantic.txt"


def sanitize_fts5_query(query: str) -> str:
    if not query:
        return ""
    tokens = _FTS5_TOKEN_RE.findall(query.strip())
    if not tokens:
        return ""
    safe_tokens = [token.replace('"', '""') for token in tokens if token]
    return " ".join(f'"{token}"' for token in safe_tokens)


def _ensure_documents_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(documents)")
    columns = {str(row[1]) for row in cur.fetchall()}
    required = {
        "source_url": "TEXT",
        "fetched_at": "TEXT",
        "license": "TEXT",
    }
    for name, col_type in required.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {col_type}")


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "id INTEGER PRIMARY KEY,"
            "title TEXT NOT NULL,"
            "source TEXT NOT NULL,"
            "path TEXT,"
            "source_url TEXT,"
            "fetched_at TEXT,"
            "license TEXT"
            ")"
        )
        _ensure_documents_columns(conn)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "chunk_text, title, source, doc_id UNINDEXED"
            ")"
        )


def _chunk_text(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i : i + CHUNK_SIZE]
        chunks.append(chunk)
        if i + CHUNK_SIZE >= len(text):
            break
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def add_document(
    db_path: Path,
    title: str,
    source: str,
    text: str,
    path: str | None,
    source_url: str | None = None,
    fetched_at: str | None = None,
    license_name: str | None = None,
) -> int:
    chunks = _chunk_text(text)
    if not chunks:
        return -1
    with sqlite3.connect(db_path) as conn:
        _ensure_documents_columns(conn)
        cur = conn.execute(
            "INSERT INTO documents(title, source, path, source_url, fetched_at, license) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (title, source, path, source_url, fetched_at, license_name),
        )
        doc_id = cur.lastrowid
        for chunk in chunks:
            conn.execute(
                "INSERT INTO chunks_fts(chunk_text, title, source, doc_id) VALUES(?, ?, ?, ?)",
                (chunk, title, source, doc_id),
            )
        return doc_id


def ingest_text_file(db_path: Path, file_path: Path, source: str) -> int:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    title = file_path.stem.replace("_", " ").strip() or "Untitled"
    return add_document(db_path, title, source, text, str(file_path))


def ingest_remote_text(
    db_path: Path,
    *,
    title: str,
    source: str,
    text: str,
    source_url: str,
    fetched_at: str,
    license_name: str | None = None,
    path: str | None = None,
) -> int:
    return add_document(
        db_path,
        title=title,
        source=source,
        text=text,
        path=path,
        source_url=source_url,
        fetched_at=fetched_at,
        license_name=license_name,
    )


def search(db_path: Path, query: str, limit: int = 5) -> List[ChunkResult]:
    results, _warning = search_with_feedback(db_path, query, limit=limit)
    return results


def search_with_feedback(
    db_path: Path,
    query: str,
    limit: int = 5,
) -> Tuple[List[ChunkResult], str | None]:
    if not query.strip():
        return [], None
    safe_query = sanitize_fts5_query(query)
    if not safe_query:
        return [], None
    with sqlite3.connect(db_path) as conn:
        try:
            cur = conn.execute(
                "SELECT rowid, title, source, chunk_text, bm25(chunks_fts) as score "
                "FROM chunks_fts WHERE chunks_fts MATCH ? "
                "ORDER BY score LIMIT ?",
                (safe_query, limit),
            )
        except sqlite3.OperationalError:
            return [], "We couldn't search that exact punctuation. Try simpler keywords."
        return [ChunkResult(*row) for row in cur.fetchall()], None


def get_chunk_by_rowid(db_path: Path, rowid: int) -> ChunkResult | None:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT rowid, title, source, chunk_text, 0.0 as score FROM chunks_fts WHERE rowid = ?",
            (rowid,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return ChunkResult(*row)


def list_all_chunks(db_path: Path) -> List[ChunkResult]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT rowid, title, source, chunk_text, 0.0 as score FROM chunks_fts"
        )
        return [ChunkResult(*row) for row in cur.fetchall()]


def answer(db_path: Path, query: str, limit: int = 3) -> Tuple[str, List[str]]:
    results = search(db_path, query, limit=limit)
    if not results:
        return "I don't know. The local knowledge base doesn't contain this information.", []

    snippets = []
    citations = []
    for result in results:
        snippets.append(result.chunk_text.strip())
        citations.append(f"[{result.rowid}] {result.title} ({result.source})")

    answer_text = "\n\n".join(snippets[:2])
    return answer_text, citations


def build_vector_index(
    db_path: Path,
    embed_model_path: Path,
    index_path: Path,
    meta_path: Path,
) -> Tuple[int, int]:
    np, hnswlib, SentenceTransformer = _load_vector_dependencies()

    chunks = list_all_chunks(db_path)
    if not chunks:
        return 0, 0

    model = SentenceTransformer(str(embed_model_path))
    texts = [c.chunk_text for c in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    dim = embeddings.shape[1]

    index = hnswlib.Index(space="cosine", dim=dim)
    index.init_index(max_elements=len(chunks), ef_construction=100, M=16)
    ids = np.array([c.rowid for c in chunks], dtype=np.int64)
    index.add_items(embeddings, ids)
    index.set_ef(50)
    index.save_index(str(index_path))

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(meta_path, ids=ids, dim=dim)
    return len(chunks), dim


def vector_search(
    query: str,
    embed_model_path: Path,
    index_path: Path,
    meta_path: Path,
    limit: int = 5,
) -> List[Tuple[int, float]]:
    np, hnswlib, SentenceTransformer = _load_vector_dependencies()

    if not query.strip():
        return []
    if not index_path.exists() or not meta_path.exists():
        return []

    meta = np.load(meta_path)
    dim = int(meta["dim"])
    index = hnswlib.Index(space="cosine", dim=dim)
    index.load_index(str(index_path))
    index.set_ef(50)

    model = SentenceTransformer(str(embed_model_path))
    q = model.encode([query], convert_to_numpy=True, show_progress_bar=False)
    labels, distances = index.knn_query(q, k=limit)
    results = []
    for rowid, dist in zip(labels[0].tolist(), distances[0].tolist()):
        score = 1.0 - float(dist)
        results.append((int(rowid), score))
    return results


def hybrid_search(
    db_path: Path,
    query: str,
    embed_model_path: Path | None,
    index_path: Path,
    meta_path: Path,
    limit: int = 5,
) -> List[ChunkResult]:
    lex_results = search(db_path, query, limit=limit)
    scores: Dict[int, float] = {}
    for rank, result in enumerate(lex_results):
        scores[result.rowid] = scores.get(result.rowid, 0.0) + 1.0 / (rank + 1)

    if embed_model_path and embed_model_path.exists() and _vector_dependencies_available():
        try:
            vec_results = vector_search(query, embed_model_path, index_path, meta_path, limit=limit)
            for rank, (rowid, score) in enumerate(vec_results):
                scores[rowid] = scores.get(rowid, 0.0) + score
        except RuntimeError:
            pass

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results: List[ChunkResult] = []
    for rowid, score in ranked[:limit]:
        chunk = get_chunk_by_rowid(db_path, rowid)
        if not chunk:
            continue
        chunk.score = score
        results.append(chunk)
    return results


def _load_vector_dependencies():
    try:
        import numpy as np
        import hnswlib
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            f"Missing vector dependencies ({exc}). {_VECTOR_SETUP_HINT}"
        ) from exc
    return np, hnswlib, SentenceTransformer


def _vector_dependencies_available() -> bool:
    try:
        _load_vector_dependencies()
    except RuntimeError:
        return False
    return True


def list_documents(db_path: Path) -> List[Tuple[int, str, str, str]]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT id, title, source, path FROM documents ORDER BY id DESC")
        return cur.fetchall()


def count_documents(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM documents")
        row = cur.fetchone()
    return int(row[0]) if row else 0


def list_documents_paged(
    db_path: Path,
    *,
    limit: int,
    offset: int,
) -> List[Tuple[int, str, str, str]]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT id, title, source, path FROM documents ORDER BY id DESC LIMIT ? OFFSET ?",
            (max(1, int(limit)), max(0, int(offset))),
        )
        return cur.fetchall()


def list_documents_with_meta(
    db_path: Path,
) -> List[Tuple[int, str, str, str | None, str | None, str | None, str | None]]:
    with sqlite3.connect(db_path) as conn:
        _ensure_documents_columns(conn)
        cur = conn.execute(
            "SELECT id, title, source, path, source_url, fetched_at, license "
            "FROM documents ORDER BY id DESC"
        )
        return cur.fetchall()


def delete_document(db_path: Path, doc_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))


def rebuild_from_folder(db_path: Path, folder: Path, source: str) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM chunks_fts")
    for path in sorted(folder.glob("*.txt")):
        ingest_text_file(db_path, path, source)
