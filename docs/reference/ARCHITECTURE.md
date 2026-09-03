# ARCHITECTURE.md

**Status:** `[VERIFIED]` This describes a **target** architecture. As of 2026-08-03, none of
it is implemented in the clean repository. Part II is an autopsy of the legacy prototype and
describes what **not** to build.

Evidence tags per `CLAUDE.md` §0.

---

# Part I — Target Architecture (clean repo)

## 1. Design Principles

1. **Local-first.** Runs on one Windows machine under WSL2 (constraint C1). No cloud, no
   container orchestration, no managed database.
2. **Vertical slices, not horizontal layers.** Build one complete path from source to phone,
   then widen it. `[INFERRED]` The legacy repo was built horizontally — every layer partially
   present, no path complete — which is why nothing runs.
3. **One concern, one module.** Enforced by a duplicate-check before every file creation.
4. **Adapters at the boundary.** Source-specific ugliness stops at the adapter. The pipeline
   never learns what ESPN's HTML looks like.
5. **Add complexity on evidence, not anticipation.** Every deferred component in `TASKS.md`
   has a written trigger condition.
6. **Degrade, do not crash.** A dead source produces a shorter brief, never a stack trace.

## 2. Target Directory Layout

```
sportwire/
├── main.py                     # THE single entrypoint. No others, ever.
├── pyproject.toml
├── requirements.txt
├── .env                        # NEVER committed
├── .env.example                # committed, placeholder values
├── .gitignore
├── README.md
├── LICENSE                     # MIT
│
├── config/
│   └── settings.py             # ONLY place .env is read. Typed settings object.
│
├── models/
│   └── schemas.py              # THE canonical NewsArticle / GameData. One file. Only file.
│
├── ingestion/
│   ├── base.py                 # SourceAdapter ABC: fetch() -> list[NewsArticle]
│   ├── nba_live.py             # balldontlie.io games adapter (see ADR-003)
│   └── <one file per source>   # added one at a time, each a slice
│
├── processing/
│   ├── dedup.py                # hash pass + SequenceMatcher pass
│   └── summarize.py            # deferred until slice 3
│
├── storage/
│   └── db.py                   # sqlite3 stdlib. Seen-hashes and article history.
│
├── delivery/
│   ├── base.py                 # DeliveryChannel ABC: send(text: str) -> bool
│   └── telegram.py             # v1 channel
│
├── docs/
│   ├── AUDIT.md                # real, measured state of the legacy code
│   └── decisions/
│       └── ADR-NNN-<slug>.md   # one per architectural decision
│
└── tests/
    ├── conftest.py
    ├── fixtures/               # saved REAL payloads captured once from live sources
    └── test_*.py               # behaviour tests; network tests marked @pytest.mark.network
```

`[INFERRED]` Roughly 12 Python files at completion of slice 1 and its follow-ons, against 60+
in the legacy repo. Smaller surface area is the primary defense against agent-driven drift.

## 3. Data Flow

```
  ┌──────────────┐
  │ balldontlie.io│  (later: NBA news feed, nflreadpy, others)
  └──────┬───────┘
         │  raw JSON / HTML — shape is the source's business
         ▼
  ┌──────────────────────────────────────────────┐
  │ ingestion/<source>.py                        │
  │   implements SourceAdapter.fetch()           │
  │   converts source shape → NewsArticle        │
  │   catches ALL exceptions → returns []        │
  └──────┬───────────────────────────────────────┘
         │  list[NewsArticle]  ← uniform from here on
         ▼
  ┌──────────────────────────────────────────────┐
  │ processing/dedup.py                          │
  │   pass 1: exact hash of normalized title     │
  │   pass 2: SequenceMatcher ratio > threshold  │
  │   pass 3: [DEFERRED — ADR-005]               │
  └──────┬───────────────────────────────────────┘
         │  deduplicated list[NewsArticle]
         ▼
  ┌──────────────────────────────────────────────┐
  │ storage/db.py  (sqlite3)                     │
  │   record hashes so dedup survives restarts   │
  └──────┬───────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────┐
  │ processing/summarize.py   [SLICE 3]          │
  └──────┬───────────────────────────────────────┘
         │  formatted brief string
         ▼
  ┌──────────────────────────────────────────────┐
  │ delivery/telegram.py                         │
  │   implements DeliveryChannel.send()          │
  └──────┬───────────────────────────────────────┘
         ▼
     operator's phone

  main.py orchestrates the above, top to bottom, synchronously.
  The OS scheduler (cron / Task Scheduler) invokes main.py — NOT an in-process loop.
```

**Dependency direction:** `main.py` depends on the abstract interfaces in `ingestion/base.py`
and `delivery/base.py`. Concrete modules depend on those same interfaces. Nothing depends on
a concrete source or channel. `[INFERRED]` That inversion is what makes adding a source or
swapping Telegram for WhatsApp a local change — and demonstrating it is task M6.

## 4. Design Patterns in Use

| Pattern | Where | Why | Note |
|---|---|---|---|
| **Adapter** | `ingestion/*.py` | One converter per source; pipeline stays source-agnostic | Operator cannot yet explain this — teach at task H8 |
| **Dependency inversion** | `base.py` ABCs in ingestion and delivery | Orchestrator depends on abstractions, so channels and sources are swappable | Same; teach at H8 |
| **Strategy** | `delivery/` | Telegram now, WhatsApp later, same call site | The concrete payoff of ADR-002 |
| **Pipeline / stages** | `main.py` | Each stage takes and returns a list; independently testable | — |
| **DTO** | `models/schemas.py` | Pydantic models as the shared contract across boundaries | — |

**Deliberately not used:** repository pattern over an ORM, unit-of-work, async workers,
message queues, dependency-injection containers. `[INFERRED]` Each appears in the legacy design
and each serves a scale problem this project does not have.

## 5. External Services

| Service | Role | Status | Cost | Risk |
|---|---|---|---|---|
| `balldontlie.io` | NBA scores, schedule | v1 critical path | Free tier (key required) | `[VERIFIED]` 2026-08-03: documented public API, intended for third-party use — see ADR-003 |
| `cdn.nba.com` live endpoints | NBA scores, boxscores, play-by-play | **Rejected** — superseded by ADR-003 | Free | `[VERIFIED]` 2026-08-03: returns HTTP 403 from Akamai; the earlier "no bot protection" claim did not hold on retest |
| Telegram Bot API | Delivery | v1 critical path | Free | Low |
| `stats.nba.com` (`nba_api`) | Deep stats | Optional enrichment | Free | `[VERIFIED]` Datacenter IPs blocked, Akamai TLS fingerprinting. Portability hazard — see ADR-003 |
| `nflreadpy` / nflverse | NFL data | Deferred (L1) | Free | Low; community-maintained |
| ESPN / HoopsHype | News, rumours | Deferred (M5) | Free | `[INFERRED]` ToS and licensing exposure. Check for RSS/official feed first |
| Apify actors | Managed scrapers | Deferred (L7) | **Paid** | Cost; violates C2 without approval |
| WhatsApp Business API | Delivery | Deferred (L6) | **Paid per message** | `[VERIFIED]` No free tier for business-initiated sends; BSP required |
| Unofficial WhatsApp bridges | — | **Prohibited** | Free | `[INFERRED]` ToS violation, personal-number ban risk, unpublishable (C3) |

## 6. Configuration

Single source: `config/settings.py`, reading `.env` via `python-dotenv`, exposing a typed
object. `[VERIFIED]` The legacy `config/settings.py` was never imported by any running code —
this is why the single-source rule exists.

See `CLAUDE.md` §10 for the placeholder list.

## 7. Testing Architecture

- **Fixtures over network.** One real payload per source is captured once into
  `tests/fixtures/` and every adapter test runs against it. Fast, deterministic, and it
  documents the true source shape.
- **Network tests** carry `@pytest.mark.network` and are excluded by default and in CI.
- **Behaviour, not structure.** `[VERIFIED]` A test asserting imports resolve passes in 3.32s
  and proves nothing; that is exactly what the legacy suite's headline result was.
- **The human writes assertions; the agent makes them pass** (ADR-006).

---

# Part II — Legacy Prototype Autopsy

`[VERIFIED]` from directory listing, 2026-08-03. Preserved as a reference for what went wrong.

## 8. What the legacy design intended

Multi-source ingestion → strict base-adapter normalization → three-pass cascade dedup (exact
hash → Jaccard/SequenceMatcher lexical → `all-MiniLM-L6-v2` 384-dim embeddings with `pgvector`
cosine distance pushed into Postgres) → LLM synthesis → WhatsApp broadcast, on an 8-hour loop.

`[INFERRED]` The design is coherent and would be defensible at scale. It is wrong here for one
reason: it was built entirely before any part of it was proven, on a workload of roughly
50–200 headlines per cycle.

## 9. What actually existed

`[VERIFIED]` 136 files, 28 directories. Nine concerns implemented two or three times over
(full table in `SESSION.md` §3.2). Five package directories with **no bytecode at all**,
proving they were never imported:

- `ingestion/scrapers/` — no scraping has ever run
- `ingestion/apis/` — no stats API call has ever run
- `delivery/` — **no message has ever been sent**
- `services/` — nothing has ever been summarized
- `config/` — no configuration has ever been loaded

`[VERIFIED]` What ran: `storage/`, `database/`, `ingestion/deduplicator.py`, `ingestion/base.py`
and the test suite — precisely the parts that need no external world.

`[VERIFIED]` Both `ingestion/normalization.py` and `ingestion/normalizer.py` have bytecode,
meaning two competing normalizers were imported in one session.

`[VERIFIED]` `HANDOFF.md` omits `schemas/`, `services/`, `Dockerfile`, `docker-compose.yml`,
`run_pipeline.py`, `delivery/messenger_os.py`, `storage/models.py` and eleven `ingestion/`
files, and contradicts the architecture PDF on both the dedup window (48h vs 8h) and the
WhatsApp path (Evolution-API/Twilio vs Meta Business API).

## 10. Root cause and lessons

`[INFERRED]` The generating agent exceeded its context window mid-build, lost sight of existing
modules, and re-implemented them under new names. Python raises no error when four modules
define the same class, so the drift was silent and cumulative. It then generated a handoff
document describing the architecture it *intended*, not the repository it *produced*, including
a fabricated history of failures overcome.

**Lessons, carried into Part I:**

1. **Agents fail by accretion, not by exception.** Small surface area, one entrypoint, and a
   duplicate-check before every file creation.
2. **Bytecode does not lie.** `__pycache__` reveals what has actually executed, independent of
   any document. Keep using it.
3. **A test count is not a health metric.** Twelve test files, zero working features.
4. **Documentation written by the thing that wrote the code is not evidence.** Hence the
   evidence-tagging rule.
5. **Horizontal building hides the fact that nothing works.** Vertical slices make failure
   visible on day one, which is the point.
6. **Optimising for a scale you have not reached costs the scale you have.** Weeks of pgvector,
   asyncpg and Alembic infrastructure, and not one story ever reached a phone.
