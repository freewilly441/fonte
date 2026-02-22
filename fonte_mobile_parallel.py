#!/usr/bin/env python3
"""Headless parallel CLI for Fonte on mobile Linux/Android (e.g., Termux)."""

from __future__ import annotations

import argparse
import re
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable, Sequence

import kb
from integrations import mediawiki_api

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "kb.sqlite"
USER_DIR = DATA_DIR / "user_docs"


def ensure_dirs() -> None:
    for path in (DATA_DIR, USER_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _read_text_file(path: Path) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = path.stem.replace("_", " ").strip() or "Untitled"
    return title, str(path), text


def iter_txt_files(inputs: Sequence[str]) -> list[Path]:
    results: list[Path] = []
    for value in inputs:
        candidate = Path(value).expanduser().resolve()
        if candidate.is_dir():
            results.extend(sorted(candidate.glob("*.txt")))
        elif candidate.is_file() and candidate.suffix.lower() == ".txt":
            results.append(candidate)
    return list(dict.fromkeys(results))


def cmd_init(args: argparse.Namespace) -> int:
    ensure_dirs()
    db_path = Path(args.db).resolve()
    kb.init_db(db_path)
    print(f"Initialized: {db_path}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    ensure_dirs()
    db_path = Path(args.db).resolve()
    kb.init_db(db_path)

    files = iter_txt_files(args.paths)
    if not files:
        print("No .txt files found in provided paths.")
        return 1

    workers = max(1, min(args.workers, len(files)))
    print(f"Parsing {len(files)} files with {workers} worker(s)...")

    parsed: list[tuple[str, str, str]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for item in pool.map(_read_text_file, files):
            parsed.append(item)

    inserted = 0
    for title, source_path, text in parsed:
        doc_id = kb.add_document(db_path, title, args.source, text, source_path)
        if doc_id != -1:
            inserted += 1

    print(f"Ingested {inserted}/{len(files)} documents into {db_path}")
    return 0


def cmd_ingest_wikipedia(args: argparse.Namespace) -> int:
    ensure_dirs()
    db_path = Path(args.db).resolve()
    kb.init_db(db_path)

    query = args.query.strip()
    if not query:
        print("Wikipedia query cannot be empty.")
        return 1

    print(
        f'Importing from Wikipedia: query="{query}", limit={args.limit}, lang={args.lang}'
    )
    try:
        inserted, titles = mediawiki_api.ingest_query(
            db_path,
            query,
            limit=args.limit,
            language=args.lang,
            source=args.source,
            timeout_sec=args.timeout,
            user_agent=args.user_agent,
        )
    except Exception as exc:
        print(f"Wikipedia import failed: {exc}")
        return 1

    print(f"Imported {inserted} page(s) into {db_path}")
    if titles:
        print("Pages:")
        for title in titles:
            print(f"- {title}")
    return 0


def ask_once(db_path: Path, query: str, limit: int) -> tuple[str, list[str]]:
    try:
        return kb.answer(db_path, query, limit=limit)
    except sqlite3.OperationalError:
        normalized = " ".join(re.findall(r"[A-Za-z0-9_]+", query))
        if not normalized:
            return "I don't know. The local knowledge base doesn't contain this information.", []
        return kb.answer(db_path, normalized, limit=limit)


def batch_worker(item: tuple[Path, str, int]) -> tuple[str, str, list[str]]:
    dbp, q, lim = item
    ans, cits = ask_once(dbp, q, lim)
    return q, ans, cits


def cmd_ask(args: argparse.Namespace) -> int:
    db_path = Path(args.db).resolve()
    answer_text, citations = ask_once(db_path, args.query, args.limit)
    print(answer_text)
    if citations:
        print("\nCitations:")
        for c in citations:
            print(f"- {c}")
    return 0


def cmd_batch_ask(args: argparse.Namespace) -> int:
    db_path = Path(args.db).resolve()
    query_file = Path(args.file).resolve()
    if not query_file.exists():
        print(f"Query file not found: {query_file}")
        return 1

    queries = [line.strip() for line in query_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not queries:
        print("No queries found in file.")
        return 1

    workers = max(1, min(args.workers, len(queries)))
    payload = [(db_path, q, args.limit) for q in queries]

    print(f"Running {len(queries)} queries with {workers} worker(s)...")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for query, answer_text, citations in pool.map(batch_worker, payload):
            print(f"\nQ: {query}\nA: {answer_text}")
            if citations:
                print("Citations:")
                for c in citations:
                    print(f"- {c}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fonte mobile parallel CLI")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to sqlite DB")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize DB and data dirs")
    p_init.set_defaults(func=cmd_init)

    p_ingest = sub.add_parser("ingest", help="Ingest .txt files from paths in parallel")
    p_ingest.add_argument("paths", nargs="+", help="Text file(s) or folder(s)")
    p_ingest.add_argument("--source", default="mobile-user", help="Source label")
    p_ingest.add_argument("--workers", type=int, default=2, help="Parallel workers")
    p_ingest.set_defaults(func=cmd_ingest)

    p_wiki = sub.add_parser("ingest-wikipedia", help="Ingest pages from Wikipedia by query")
    p_wiki.add_argument("query", help="Wikipedia search query")
    p_wiki.add_argument("--limit", type=int, default=5, help="Maximum pages to import")
    p_wiki.add_argument("--lang", default="en", help="Wikipedia language code")
    p_wiki.add_argument("--source", default="wikipedia", help="Source label")
    p_wiki.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    p_wiki.add_argument(
        "--user-agent",
        default="Fonte/1.0 (+local-app)",
        help="HTTP User-Agent for requests",
    )
    p_wiki.set_defaults(func=cmd_ingest_wikipedia)

    p_ask = sub.add_parser("ask", help="Ask one grounded question")
    p_ask.add_argument("query", help="Question text")
    p_ask.add_argument("--limit", type=int, default=3, help="Retrieved chunks")
    p_ask.set_defaults(func=cmd_ask)

    p_batch = sub.add_parser("batch-ask", help="Run multiple queries in parallel")
    p_batch.add_argument("file", help="UTF-8 file with one query per line")
    p_batch.add_argument("--workers", type=int, default=2, help="Parallel workers")
    p_batch.add_argument("--limit", type=int, default=3, help="Retrieved chunks")
    p_batch.set_defaults(func=cmd_batch_ask)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
