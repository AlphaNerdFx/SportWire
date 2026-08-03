# AUDIT.md — Forensic Audit of the Legacy Repository

**Date:** 2026-08-03
**Scope:** `TASKS.md` C1. Runs the four forensic commands in `CLAUDE.md` §7 against the
repository as committed at `e8953e0` (branch `legacy`) and records real numbers.
**This replaces `HANDOFF.md` as the source of truth about the legacy code.**

> Evidence tags: `[VERIFIED]` = command run in this session, output below. `[INFERRED]` =
> reasoned from that output. `[UNKNOWN]` = not established — no Python source was read line
> by line in this audit, only line counts and pattern matches. Do not treat "stub or real"
> below as a correctness judgement; it is a size/pattern classification only.

---

## 1. Line counts, bytecode status, and classification

`has_run` = `[VERIFIED]` a `__pycache__` directory exists for that package (see §3). A file
run directly as `python file.py` would not show this — noted where relevant.

| File | Lines | Package ever run? | Classification |
|---|---:|:---:|---|
| `run_pipeline.py` | 0 | n/a (script, not package) | `[VERIFIED]` empty file |
| `config/__init__.py` | 0 | No | `[VERIFIED]` empty |
| `config/settings.py` | 43 | No | `[UNKNOWN]` content unread; never imported by running code |
| `database/__init__.py` | 0 | Yes | `[VERIFIED]` empty |
| `database/connection.py` | 23 | Yes | `[UNKNOWN]` |
| `database/models.py` | 115 | Yes | contains 1 `pass` — `[UNKNOWN]` whether abstract or stub |
| `delivery/__init__.py` | 0 | No | `[VERIFIED]` empty |
| `delivery/base.py` | 20 | No | contains 1 `pass` — `[UNKNOWN]` |
| `delivery/messenger_os.py` | 0 | No | `[VERIFIED]` empty |
| `delivery/router.py` | 22 | No | contains 1 `pass` — `[UNKNOWN]` |
| `delivery/whatsapp_os.py` | 91 | No | `[UNKNOWN]` |
| `ingestion/__init__.py` | 0 | Yes | `[VERIFIED]` empty |
| `ingestion/base.py` | 82 | Yes | 5 `pass` — `[INFERRED]` plausibly an abstract base (5 methods), not necessarily a stub; unread |
| `ingestion/models.py` | 24 | Yes | defines `class NewsArticle` — one of four (§2) |
| `ingestion/normalization.py` | 64 | Yes | `[UNKNOWN]` |
| `ingestion/normalizer.py` | 45 | Yes | `[UNKNOWN]` — coexists with `normalization.py`, both have bytecode |
| `ingestion/nba_client.py` | 37 | Yes | `[UNKNOWN]` |
| `ingestion/nfl_client.py` | 40 | Yes | `[UNKNOWN]` |
| `ingestion/news_clients.py` | 142 | Yes | 1 `pass` — `[UNKNOWN]` |
| `ingestion/orchestrator.py` | 146 | Yes | `[UNKNOWN]` |
| `ingestion/run_ingestion.py` | 69 | Yes | `[UNKNOWN]` |
| `ingestion/scheduler.py` | 62 | Yes | 1 `pass` — `[UNKNOWN]` |
| `ingestion/schemas.py` | 20 | Yes | `[UNKNOWN]` |
| `ingestion/deduplicator.py` | 199 | Yes | `[UNKNOWN]` — largest ingestion file |
| `ingestion/subrouters.py` | 0 | Yes (dir has `__pycache__`) | `[VERIFIED]` empty |
| `ingestion/adapters/__init__.py` | 0 | Yes | `[VERIFIED]` empty |
| `ingestion/adapters/apify_news_adapter.py` | 85 | Yes | 1 `pass` — `[UNKNOWN]` |
| `ingestion/adapters/nba_api_adapter.py` | 130 | Yes | `[UNKNOWN]` |
| `ingestion/adapters/web_scraper_adapter.py` | 26 | **No** | `[VERIFIED]` never imported (matches `SESSION.md` §3.3) |
| `ingestion/apis/__init__.py` | 0 | **No** | `[VERIFIED]` empty, never imported |
| `ingestion/apis/nba_stats.py` | 0 | **No** | `[VERIFIED]` empty **and** never imported — HANDOFF.md's "raw downstream API connector" does not exist |
| `ingestion/apis/nfl_stats.py` | 0 | **No** | `[VERIFIED]` empty, never imported |
| `ingestion/apis/sports_clients.py` | 0 | **No** | `[VERIFIED]` empty, never imported |
| `ingestion/scrapers/__init__.py` | 3 | **No** | `[UNKNOWN]` |
| `ingestion/scrapers/base.py` | 86 | **No** | 1 `pass`, never imported |
| `ingestion/scrapers/espn.py` | 30 | **No** | `[VERIFIED]` never imported — confirms "no web scraping has ever run" |
| `ingestion/scrapers/hoopshype.py` | 61 | **No** | `[VERIFIED]` never imported |
| `migrations/env.py` | 65 | Yes | `[UNKNOWN]` |
| `migrations/script.py.mako` | — | n/a (template) | — |
| `migrations/versions/4df4...py` | 77 | Yes | `[UNKNOWN]` |
| `models/__init__.py` | 0 | Yes | `[VERIFIED]` empty |
| `models/schemas.py` | 26 | Yes | defines `class NewsArticle` — second of four |
| `pipeline/orchestrator.py` | 101 | Yes | `[UNKNOWN]` — second orchestrator (see §2) |
| `schemas/__init__.py` | 0 | Yes | `[VERIFIED]` empty |
| `schemas/normalized.py` | 103 | Yes | `[UNKNOWN]` |
| `services/__init__.py` | 0 | **No** | `[VERIFIED]` empty, never imported |
| `services/llm_summarizer.py` | 0 | **No** | `[VERIFIED]` empty **and** never imported — "nothing has ever been summarized" confirmed at the file level, not just the import level: there is no summarization code to import |
| `services/whatsapp_gateway.py` | 0 | **No** | `[VERIFIED]` empty, never imported |
| `storage/config.py` | 7 | Yes | `[UNKNOWN]` |
| `storage/database.py` | 46 | Yes | `[UNKNOWN]` |
| `storage/embedding_engine.py` | 69 | Yes | `[UNKNOWN]` |
| `storage/models.py` | 55 | Yes | 1 `pass`, defines `class NewsArticle` — third of four |
| `storage/repository.py` | 155 | Yes | `[UNKNOWN]` — largest storage file |
| `storage/vector_store.py` | 87 | Yes | 2 `pass` — `[UNKNOWN]` |
| `tests/*` (11 files) | 30–209 | Yes | see §4 — test count is not evidence of health |

**Total:** `[VERIFIED]` 3,428 lines across all tracked `.py` files (excluding `.venv`).

---

## 2. `NewsArticle` is defined four times — confirmed, and a fifth surprise

`[VERIFIED]` `grep -rn "class NewsArticle"`:

| File | Base type |
|---|---|
| `ingestion/models.py:17` | plain class (unread whether dataclass or plain) |
| `models/schemas.py:5` | `BaseModel` (Pydantic) |
| `storage/models.py:11` | `Base` (SQLAlchemy ORM) |
| `tests/conftest.py:8` | `BaseModel` (Pydantic) — **defined locally in the test fixture file, not imported from either real schema module** |

`[INFERRED]` This is worse than `SESSION.md` §3.2 stated. It found four schema files by
directory listing; this confirms four *class definitions*, and one of them is inside the
shared test fixture (`conftest.py`), which every test file that imports from it would use
**instead of** the "real" schema. That means `tests/test_ingestion_setup.py` passing in
3.32s (`SESSION.md` §3.4) may have validated a fixture-local stand-in class, not either
candidate for the canonical `NewsArticle`. This strengthens, not weakens, ADR-001 (fork
clean rather than salvage).

---

## 3. Bytecode — which packages have ever executed

`[VERIFIED]` `find . -name "__pycache__" -type d` (excluding `.venv`):

**Has run:** `database/`, `ingestion/` (root + `adapters/`), `migrations/` (+ `versions/`),
`models/`, `pipeline/`, `schemas/`, `storage/`, `tests/`.

**Has never run:** `config/`, `delivery/`, `ingestion/apis/`, `ingestion/scrapers/`,
`services/`, `ingestion/adapters/web_scraper_adapter.py` specifically (its sibling adapters
did run).

This matches `SESSION.md` §3.3 exactly — no discrepancy found.

---

## 4. Empty files — a finding `SESSION.md` did not have

`[VERIFIED]` 17 files are **zero-length**, not merely "never imported":

```
config/__init__.py, database/__init__.py, delivery/__init__.py, delivery/messenger_os.py,
ingestion/__init__.py, ingestion/adapters/__init__.py, ingestion/apis/__init__.py,
ingestion/apis/nba_stats.py, ingestion/apis/nfl_stats.py, ingestion/apis/sports_clients.py,
ingestion/subrouters.py, models/__init__.py, run_pipeline.py, schemas/__init__.py,
services/__init__.py, services/llm_summarizer.py, services/whatsapp_gateway.py
```

`[INFERRED]` The most consequential of these: **`run_pipeline.py` — the file `HANDOFF.md`
and the repo layout imply is the entrypoint — is completely empty.** So are all three files
under `ingestion/apis/` (the "raw downstream API connectors" `HANDOFF.md` §1 claims exist)
and both non-`__init__` files under `services/` (summarization, WhatsApp gateway). These
aren't unfinished implementations to salvage — there is nothing there to read.

---

## 5. Unimplemented markers (`pass`, `TODO`, `FIXME`, `NotImplementedError`)

`[VERIFIED]` 15 bare `pass` statements found, zero `TODO`/`FIXME`/`NotImplementedError`.
Full list in command output above. `[UNKNOWN]` per-instance whether each is a legitimate
abstract-method body (e.g. `ingestion/base.py`'s 5 instances, consistent with an abstract
base class) or a genuine stub — this requires reading the file, not yet done.

---

## 6. Commit log

`[VERIFIED]`
```
808db0d docs: record proof for C0 and C2
e8953e0 chore: freeze legacy prototype as pre-release snapshot
```
No prior history existed (repo was un-initialized before this session — see `TASKS.md` C0/C2).

---

## 7. Net effect on `SESSION.md` §5 decisions

None of ADR-001 through ADR-008 are weakened by this audit; §2 and §4 above are new evidence
that *strengthens* ADR-001 (fork clean) specifically. No reversal condition in ADR-001 is met —
`storage/repository.py` and `ingestion/deduplicator.py` remain unread, so "genuinely correct,
tested logic" is still `[UNKNOWN]`, not confirmed.
