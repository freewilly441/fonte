import sqlite3
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


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "id INTEGER PRIMARY KEY,"
            "title TEXT NOT NULL,"
            "source TEXT NOT NULL,"
            "path TEXT"
            ")"
        )
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


def add_document(db_path: Path, title: str, source: str, text: str, path: str | None) -> int:
    chunks = _chunk_text(text)
    if not chunks:
        return -1
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO documents(title, source, path) VALUES(?, ?, ?)",
            (title, source, path),
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


def search(db_path: Path, query: str, limit: int = 5) -> List[ChunkResult]:
    if not query.strip():
        return []
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT rowid, title, source, chunk_text, bm25(chunks_fts) as score "
            "FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY score LIMIT ?",
            (query, limit),
        )
        return [ChunkResult(*row) for row in cur.fetchall()]


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
    try:
        import numpy as np
        import hnswlib
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(f"Missing vector dependencies: {exc}") from exc

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
    try:
        import numpy as np
        import hnswlib
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(f"Missing vector dependencies: {exc}") from exc

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

    if embed_model_path and embed_model_path.exists():
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


def list_documents(db_path: Path) -> List[Tuple[int, str, str, str]]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT id, title, source, path FROM documents ORDER BY id DESC")
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
