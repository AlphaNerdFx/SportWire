# OpenClaw Prototype Handoff Document

This document tracks the precision architecture, implementation milestones, historical hurdles, and immediate next steps for the OpenClaw NBA/NFL News & Games Retriever Assistant.

---

## 1. The Goal We Are Working Toward
The ultimate objective is to construct a production-ready, highly decoupled, automated sports aggregation and Retrieval-Augmented Generation (RAG) context engine. 
* **Multi-Source Ingestion:** Ingest raw telemetry and text streams from structured providers (`nba_api`, `nfl_stats`) and unstructured web scrapes (`hoopshype.py`, `espn.py`, Apify outputs).
* **Defensive Normalization:** Pass all incoming streams through strict base adapter interfaces to enforce uniform data definitions (`NewsArticle`, `GameData`).
* **High-Performance Cascade Deduplication:** Implement an advanced multi-pass filter:
  1. *Exact Natural Hash Pass:* Prevent immediate duplicate processing at zero overhead.
  2. *Lexical Pass:* Use word-level token alignment (Jaccard Similarity / Sequence matching) across running headlines within a 48-hour window.
  3. *Semantic Vector Pass:* Trigger localized open-source embeddings via `all-MiniLM-L6-v2` (384 dimensions) and offload the similarity match down to PostgreSQL using native `pgvector` distance metrics.
* **Intelligent Delivery:** Synthesize context chunks through an LLM synthesis tier (`services/llm_summarizer.py`) and broadcast updates to users via automated messaging engines (`delivery/whatsapp_os.py`).

---

## 2. Current State of Code
The project structure is professionally decoupled into explicit sub-systems:

```
.
├── config/                  # Global system & environment variables definitions
│   └── settings.py          # App-wide settings and thresholds
├── database/                # Primary relational engines and database adapters
│   ├── connection.py        # Async pgvector/asyncpg driver wrappers
│   └── models.py            # Primary database ORM model layouts
├── storage/                 # Embedding pipeline and repository execution tiers
│   ├── config.py            # Hardcoded 384-dimension local model constraints
│   ├── database.py          # Relational session pool configurations
│   ├── embedding_engine.py  # Local sentence-transformers (all-MiniLM-L6-v2) pipeline
│   ├── repository.py        # Database execution layer with integrated pgvector metrics
│   └── vector_store.py      # Abstracted low-level vector query operations
├── ingestion/               # Multi-pass data gathering and format parsing framework
│   ├── adapters/            # Normalizers (apify_news_adapter.py, nba_api_adapter.py, web_scraper_adapter.py)
│   ├── apis/                # Raw downstream API connectors (nba_stats.py, nfl_stats.py)
│   ├── scrapers/            # Raw text page parsers (espn.py, hoopshype.py)
│   ├── base.py              # Abstract class enforcing safe parsing structures
│   └── deduplicator.py      # Lexical SequenceMatcher & cascading filter mechanics
├── models/                  # App-wide shared object interfaces
│   └── schemas.py           # Unified Pydantic schema constraints (NewsArticle, GameData)
├── pipeline/                # Global automation lifecycles
│   └── orchestrator.py      # Master sequence loop coordinating ingestion-to-delivery
├── delivery/                # Downstream user notification router
│   ├── router.py            # Multi-channel user directory routing mechanics
│   └── whatsapp_os.py       # Core Evolution-API / Twilio execution protocols
└── tests/                   # Strict test framework verifying isolation boundaries
```

### Key Working Milestones:
* **Infrastructure Layer Connected:** `storage/config.py` is configured for **384-dimension vectors** via local embedding inference, saving cloud API overhead.
* **Adapter Verification Passed:** `tests/test_ingestion_setup.py` executed successfully inside the `.venv` workspace (passing in `3.32s`), proving that path resolutions, base classes, and official API mappings function perfectly.
* **Alembic Tracking Active:** Initial structural updates are successfully captured in migration scripts (`migrations/versions/4df412ef740a_...`).

---

## 3. Files Actively Changing
* `storage/repository.py`: Integrating the database-side `pgvector` distance search metrics (`cosine_distance`) to evaluate article fragments down in the PostgreSQL engine rather than pulling them into memory.
* `ingestion/deduplicator.py`: Adapting the cascading decision framework so that lexical checks exit early, while the fallback semantic pass connects natively to the chunk-based repository lookup.
* `ingestion/adapters/web_scraper_adapter.py`: Filling out the underlying parsing schemas to consume the outputs of raw text scrapers (`hoopshype.py`, `espn.py`).

---

## 4. Everything We've Tried and Failed
* **Monolithic Sequential Pipeline Failures:** Attempting to pipe web scraping blocks, AI embedding loops, and live messaging calls within a single execution sequence led to timeouts. Remedied by isolating the workflow into asynchronous workers and persistent queues.
* **In-Memory Python Similarity Searches:** Early design assumptions mapped embeddings directly onto the parent `NewsArticle` model, fetching complete article vectors into local Python runtime arrays to run similarity loops. This failed because it conflicted with the production database schema, which shards long articles across multiple child `ArticleChunk` rows. It also threatened severe memory saturation as the dataset scaled. This was rewritten to push the vector search queries down into Postgres via `pgvector` operations.
* **Uniform Interface Assumptions:** Attempting to let scrapers and structured APIs share a raw insertion endpoint led to corrupted table rows. This was resolved by creating the intermediate `BaseSourceAdapter` validation layer to guarantee data sanity.

---

## 5. The Next Step We'd Take
1. **Unify Ingestion & Deduplication Interfaces:** Fully update `ingestion/deduplicator.py` to match the chunk-based relational models of the repository. Ensure that `SportsNewsDeduplicator` passes its text tokens and embedding requests smoothly down to `SportsPersistenceRepository.find_semantic_duplicate`.
2. **Execute Ingestion Validation Tests:** Run `pytest tests/test_news_ingestion.py` and `pytest tests/test_deduplicator.py` to assert that near-duplicate breaking sports headlines are successfully caught and thrown away before calling the embedding engine.
3. **Flesh Out Unstructured Scrapers:** Code the concrete `parse` text functions inside `ingestion/scrapers/hoopshype.py` and `ingestion/scrapers/espn.py` to continuously provide the ingestion pipeline with unfiltered news feeds.
