# Fonte External API Integration Plan

## Scope
This plan covers the next API augmentations after Ollama:
- MediaWiki REST API (Wikipedia content ingestion)
- Wikidata SPARQL (structured entity/fact ingestion)
- Open Library API (book/author metadata ingestion)
- SearXNG Search API (optional online retrieval mode)
- Qdrant API (optional vector backend upgrade)

## Principles
- Keep Fonte offline-first: all external data is cached into local SQLite and usable offline.
- Make online augmentation opt-in and explicit per source.
- Preserve grounded answers with citations to source URLs and retrieval row IDs.
- Ship incrementally with feature flags and minimal breakage to current `kb.py` behavior.

## Phase 1: Shared Online Ingestion Foundation
Target files:
- `app.py`
- `kb.py`
- `config.py`
- New: `ingest_remote.py`

Deliverables:
1. New config keys:
   - `online_sources_enabled` (`false`)
   - `online_cache_days` (`30`)
   - `online_timeout_sec` (`20`)
   - `online_user_agent` (`Fonte/1.0 (+local-app)`)
2. Shared HTTP helpers in `ingest_remote.py`:
   - timeout, retries (max 2), polite rate limiting
   - normalized metadata (`source_url`, `fetched_at`, `license`)
3. DB metadata extension:
   - add `source_url` and `fetched_at` to `documents` table (with migration-safe `ALTER TABLE` checks)
4. Manage tab controls:
   - toggle online ingest
   - “sync now” per source

Acceptance criteria:
- External ingest can be fully disabled.
- Imported remote docs appear in current document list and are searchable via existing flows.

## Phase 2: MediaWiki REST Integration
Target files:
- New: `integrations/mediawiki_api.py`
- `app.py`, `fonte_mobile_parallel.py`

Deliverables:
1. API actions:
   - search page titles from query
   - fetch page content by title
2. Import command:
   - GUI: “Import from Wikipedia”
   - CLI: `fonte_mobile_parallel.py ingest-wikipedia "query" --limit 5`
3. Store citation metadata:
   - source label `wikipedia`
   - canonical page URL

Acceptance criteria:
- Imported Wikipedia pages are chunked and retrievable by `kb.hybrid_search`.
- Q&A citations include row ID and source URL.

## Phase 3: Wikidata SPARQL Integration
Target files:
- New: `integrations/wikidata_api.py`
- `app.py`, `fonte_mobile_parallel.py`

Deliverables:
1. Query templates for common intents:
   - entity summary
   - key properties (instance of, country, dates)
2. Transform result bindings into compact text blocks for chunk ingestion.
3. CLI command:
   - `ingest-wikidata "entity or SPARQL template input"`

Acceptance criteria:
- At least 3 template query types produce ingestible documents with provenance links.
- Data is grounded and auditable from stored source URLs.

## Phase 4: Open Library Integration
Target files:
- New: `integrations/openlibrary_api.py`
- `app.py`, `fonte_mobile_parallel.py`

Deliverables:
1. Search and import:
   - works by title/author/ISBN
2. Respect API rate guidance:
   - max 1 req/s default (configurable)
3. Save metadata:
   - work key, author key, edition key, Open Library URL

Acceptance criteria:
- Book metadata and summaries are searchable offline after ingest.
- Import path handles missing fields robustly.

## Phase 5: SearXNG Optional Online Retrieval
Target files:
- New: `integrations/searxng_api.py`
- `app.py`, `config.py`

Deliverables:
1. Add optional `answer_with_online_augment` mode:
   - run SearXNG query
   - ingest top-N snippets to temporary cached source records
   - answer using existing grounded pipeline
2. Config:
   - `searxng_base_url`
   - `searxng_enabled_engines`
   - `searxng_max_results`

Acceptance criteria:
- When enabled, answers may include freshly cached web snippets with explicit source links.
- When disabled/offline, app behavior remains unchanged.

## Phase 6: Qdrant Vector Backend Option
Target files:
- `kb.py`
- New: `vector_store.py`
- `config.py`, `app.py`

Deliverables:
1. Abstract vector interface:
   - `build_index`, `search`, `upsert_chunks`
2. Implementations:
   - current local `hnswlib` path
   - Qdrant HTTP path
3. Config:
   - `vector_backend` (`hnswlib` | `qdrant`)
   - `qdrant_url`, `qdrant_collection`, `qdrant_api_key` (optional)

Acceptance criteria:
- `kb.hybrid_search` works identically across both vector backends.
- Backend can be switched without data loss in SQLite chunk store.

## Execution Order
1. Phase 1 foundation
2. Phase 2 MediaWiki
3. Phase 3 Wikidata
4. Phase 4 Open Library
5. Phase 5 SearXNG
6. Phase 6 Qdrant

## Testing Strategy
- Add lightweight integration tests with mocked HTTP responses:
  - ingestion parser tests per source
  - timeout/retry behavior
  - citation/provenance formatting
- Manual end-to-end smoke:
  - ingest remote source
  - search hit verification
  - grounded Q&A with citations
- Regression checks:
  - existing local-only workflow unchanged with online features disabled.

