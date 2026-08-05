# SESSION.md — Current Working State

**Last updated:** 2026-08-03
**Session type:** Architectural review and forensic audit. **No code was written or modified
in this session.**
**Next session should begin with:** the prompt in §10.

> **Evidence tags used throughout:** `[VERIFIED]` = observed directly. `[INFERRED]` = reasoned
> from stated evidence. `[UNKNOWN]` = not known; do not guess. See `CLAUDE.md` §0.

---

## 1. Project Overview

| Field | Value |
|---|---|
| **Name** | SportWire — NBA/NFL News & Games Retrieval Assistant. `[VERIFIED]` Renamed from "OpenClaw" 2026-08-04: that name collides with an established open-source project (a *Captain Claw* game reimplementation) — `pypi.org/pypi/openclaw` and `github.com/openclaw` both return HTTP 200 — which would bury this repo in search results. `sportwire` is free on both. |
| **Purpose** | Aggregate NBA and NFL news and game data from multiple sources, deduplicate stories, summarize them, and deliver a periodic brief to the operator's phone. |
| **End goal** | A publishable, generalizable open-source repo, plus — weighted higher — the operator learning system design, end-to-end development, DevOps fundamentals, and agentic coding practice. |
| **Stage** | Pre-implementation. Architecture decided; clean repository not yet created. |
| **Progress (clean repo)** | `[VERIFIED]` 0%. It does not exist. |
| **Progress (legacy repo)** | `[INFERRED]` 15–25% of a much larger design, of which a large fraction is duplicated or superseded. **No end-to-end path has ever executed.** |
| **Runtime target** | `[VERIFIED]` Operator's own Windows machine via WSL2 Ubuntu, Python 3.10, `.venv`. Not cloud. Possible later port to phone. |

---

## 2. What Actually Happened This Session

The operator arrived with `HANDOFF.md`, an architecture PDF, and a flow diagram, all
produced in a prior session with a different model. He believed the project was substantially
built. The session established that it is not.

**Method:** cross-checking the documents against each other and against a full `tree` of the
repository. No Python source was read. This is a limitation of the findings below and is
stated explicitly rather than papered over.

---

## 3. Forensic Findings

### 3.1 The prior handoff document is not a description of the repository

`[VERIFIED]` `HANDOFF.md` omits, among others: `schemas/`, `services/`, `Dockerfile`,
`docker-compose.yml`, `run_pipeline.py`, `delivery/messenger_os.py`, `storage/models.py`, and
eleven files inside `ingestion/`. It presents a clean arrangement that does not exist on disk.

`[VERIFIED]` Internal contradictions between the handoff and the architecture PDF:

| Claim | `HANDOFF.md` | Architecture PDF |
|---|---|---|
| Dedup window | 48-hour lexical window | 8-hour semantic window |
| WhatsApp path | Evolution-API / Twilio | Meta API / WhatsApp Business API |

`[INFERRED]` These are mutually exclusive. Evolution API is an unofficial Baileys-based bridge;
Twilio and Meta Business API are licensed paths. A single module cannot be both. The
documents were generated, not observed.

`[INFERRED]` The narrative in `HANDOFF.md` §4 ("Everything We've Tried and Failed") — memory
saturation from in-memory vector loops, an `ArticleChunk` sharded schema, corrupted rows from
a shared insertion endpoint — reads as lived history but no artifact confirms any of it.
**Treat all of it as unverified.** Designing around fabricated constraints is worse than
designing around none.

### 3.2 Nine concerns are implemented two or three times over

`[VERIFIED]` from the directory listing:

| Concern | Competing implementations |
|---|---|
| Article schema | `ingestion/schemas.py`, `models/schemas.py`, `schemas/normalized.py`, `ingestion/models.py` |
| ORM models | `database/models.py`, `storage/models.py`, `ingestion/models.py` |
| Orchestrator | `ingestion/orchestrator.py`, `pipeline/orchestrator.py` |
| Normalizer | `ingestion/normalization.py`, `ingestion/normalizer.py` |
| DB connection | `database/connection.py`, `storage/database.py` |
| NBA fetching | `ingestion/nba_client.py`, `ingestion/apis/nba_stats.py`, `ingestion/adapters/nba_api_adapter.py` |
| NFL fetching | `ingestion/nfl_client.py`, `ingestion/apis/nfl_stats.py` |
| WhatsApp delivery | `delivery/whatsapp_os.py`, `services/whatsapp_gateway.py` |
| Routing | `delivery/router.py`, `ingestion/subrouters.py` |
| Entrypoint | `run_pipeline.py`, `ingestion/run_ingestion.py` |

`[VERIFIED]` `ingestion/normalization.py` **and** `ingestion/normalizer.py` both have compiled
bytecode, meaning both were imported in the same interpreter session. The handoff's claim of
"uniform data definitions enforced by strict base adapter interfaces" cannot hold when four
modules define the article shape.

### 3.3 Bytecode proves which layers have never run

`[VERIFIED]` Bytecode writing was clearly enabled (`ingestion/` and `storage/` are full of
`.pyc` files). Directories with **no `__pycache__` at all** contain code that has never been
imported:

| Directory | Files | Implication |
|---|---|---|
| `ingestion/scrapers/` | `espn.py`, `hoopshype.py`, `base.py` | **No web scraping has ever run.** |
| `ingestion/apis/` | `nba_stats.py`, `nfl_stats.py`, `sports_clients.py` | **No stats API call has ever run.** |
| `delivery/` | `router.py`, `whatsapp_os.py`, `messenger_os.py`, `base.py` | **The entire delivery layer has never executed.** |
| `services/` | `llm_summarizer.py`, `whatsapp_gateway.py` | **Nothing has ever been summarized.** |
| `config/` | `settings.py` | **No configuration has ever been loaded by running code.** |
| `ingestion/adapters/` | `web_scraper_adapter.py` only | The other two adapters have bytecode; this one has never run. |

`[VERIFIED]` What *has* run: `storage/`, `database/`, `ingestion/deduplicator.py`,
`ingestion/base.py`, and the test suite — i.e. exactly the components that can execute without
touching the outside world.

`[INFERRED]` Caveat that keeps this honest: a file executed directly as `python file.py` does
not write its own `.pyc`, which explains `run_pipeline.py`. That exception does not apply to
modules inside packages, so the table above stands.

### 3.4 The test suite is not evidence

`[VERIFIED]` 12 test files exist. The operator has run only the ones an AI agent suggested —
the author of the code selected the exam. `[VERIFIED]` `test_ingestion_setup.py` passed in
3.32s; that runtime is incompatible with any network or database I/O, so it asserted imports
and class existence only. `[VERIFIED]` The operator has never run the full project.

### 3.5 Root cause

`[INFERRED]` The generating agent exceeded its context window mid-project, lost track of
`ingestion/nba_client.py`, and wrote `ingestion/apis/nba_stats.py` for the same job, then
`adapters/nba_api_adapter.py` again. Python raises no error when four modules define the same
class, so the failure was silent and cumulative.

**Lesson recorded:** agents do not fail loudly on architectural drift; they fail by accretion.
The defenses are a small surface area, a single entrypoint, a duplicate-check before every
file creation, and a human who reads the diff.

---

## 4. Current State by Category

### Completed
- `[VERIFIED]` Architectural direction decided (see §5).
- `[VERIFIED]` External-service constraints researched and confirmed (NBA IP/TLS blocking;
  WhatsApp per-message pricing and BSP requirement).
- `[VERIFIED]` Legacy repo audited at directory level.

### Partially complete
- `[INFERRED]` Legacy `storage/` and `ingestion/deduplicator.py` contain code that at least
  imports and runs under test. Whether it is *correct* is `[UNKNOWN]` — no line has been read.

### Not started
- Clean repository. Vertical slice. Telegram delivery. Persistence. Summarization.
  NFL sources. Scheduling. ADR folder.

### Blockers

| ID | Blocker | Severity | Resolution |
|---|---|---|---|
| B1 | Clean repo does not exist. | Critical | Task C1–C3 in `TASKS.md`. |
| B2 | `[UNKNOWN]` whether legacy `.gitignore` exists and whether `.env` / `__pycache__` are in git history. **Blocks open-sourcing the legacy repo.** | High | `git log --all --name-only \| grep -i "\.env\|\.pyc"` |
| B3 | `[UNKNOWN]` how many `NewsArticle` definitions actually exist in source (directory names imply four; unconfirmed). | Medium | `grep -rn "class NewsArticle" --include="*.py" .` |
| B4 | Telegram bot token and chat ID not yet obtained. | Medium | Operator creates bot via @BotFather. |
| B5 | Operator cannot yet explain the adapter pattern / dependency inversion, or DB migrations. Both are load-bearing in the target design. | Medium (learning-goal blocker) | Teach inline at first use; do not assume. |

---

## 5. Decisions Made This Session

Each should become an ADR file in `docs/decisions/` in the clean repo.

### ADR-001 — Fork clean rather than salvage
- **Decision:** Freeze the legacy repo on a `legacy` branch. Start a new repository. Copy files
  across one at a time, only when a slice needs them, and only after the human has read them.
- **Why:** `[VERIFIED]` Nine duplicated concerns and a delivery layer that has never executed.
  Untangling four article schemas the operator cannot yet read costs more than writing ~150
  lines fresh.
- **Alternatives considered:** (a) Incremental refactor in place — rejected: every future bug
  would have three plausible causes in three files. (b) Delete outright — rejected: the legacy
  repo is a genuine portfolio artifact and a reference for parts that may be salvageable.
- **Tradeoff:** Loses whatever working code exists in `storage/`. Accepted, because that code
  serves a scale problem the project does not have.
- **Reversal condition:** If reading `storage/repository.py` and `ingestion/deduplicator.py`
  shows genuinely correct, tested logic, copy those two files rather than rewriting them.

### ADR-002 — Telegram before WhatsApp
- **Decision:** v1 delivers via Telegram Bot API. WhatsApp becomes an optional second adapter.
- **Why:** `[VERIFIED]` WhatsApp Business API bills every business-initiated message with no
  free tier and requires a BSP (violates C2). `[INFERRED]` Unofficial bridges risk a permanent
  ban of the operator's personal number and cannot be published (violates C3).
- **Alternatives:** WhatsApp Business API via low-margin BSP (rejected: recurring cost);
  Evolution API / Baileys (rejected: ToS, ban risk, unpublishable); email/SMS (rejected: worse
  UX, SMS also costs).
- **Tradeoff:** Departs from the original diagram, which the operator is attached to. Mitigated
  by the delivery-adapter interface — swapping channels later is a small change, and building
  that swap is itself the adapter-pattern lesson (addresses B5).

### ADR-003 — `cdn.nba.com` on the critical path, `stats.nba.com` as optional enrichment
- **Why:** `[VERIFIED]` `stats.nba.com` is blocked on datacenter IPs and behind Akamai TLS
  fingerprinting; `cdn.nba.com` live endpoints are unprotected. `[INFERRED]` The operator's
  residential IP hides this problem today, which makes it more dangerous, not less — the repo
  would be unusable for anyone who clones it.
- **Tradeoff:** Less historical/statistical depth in v1. Accepted.

### ADR-004 — SQLite now; Postgres/pgvector only on demonstrated need
- **Why:** `[INFERRED]` Workload is roughly 50–200 headlines per 8-hour cycle. Exact-hash plus
  fuzzy title matching over 200 items is ~20,000 comparisons — microseconds in pure Python.
- **Alternatives:** Postgres + `pgvector` + `asyncpg` + Alembic as designed in `HANDOFF.md`
  (rejected: weeks of infrastructure debugging before proving a story can reach a phone).
- **Tradeoff:** A later migration if scale grows. `[INFERRED]` Likely never needed; if it is,
  performing that migration under real conditions is a better lesson than pre-building for it
  (also addresses B5's migrations gap).
- **Reaffirmed 2026-08-04** after the operator proposed "our stack will rely on Postgres for
  multi extension use." Clarified against three possible meanings; operator's answers:
  (1) RAG/vector search → **post-v1.0.0**, deferred behind ADR-005's trigger;
  (2) multiple sports/sources → not required, except possibly to route around a single
  source's rate limits, which is not a storage concern;
  (3) multi-user → possibly later, but v1 is for open-source distribution.
- **New argument for SQLite, not present in the original ADR:** `[INFERRED]` open-sourcing the
  repo *strengthens* the SQLite case rather than weakening it. Publishing means many people each
  run their **own instance with their own database** — single-writer per instance. Requiring
  Postgres would force every person who clones the repo to install, configure and migrate a
  database **server** before seeing a single score, which is a severe adoption barrier and
  directly contradicts the deferred goal in §9 Q10 / `TASKS.md` L13 (lower setup friction for
  non-technical users). SQLite is a file created on first run. `[VERIFIED]` `sqlite3` is in the
  standard library — zero install.
- **Distinction worth keeping straight:** *open-source* ≠ *multi-user*. Many instances with one
  writer each is not the workload that breaks SQLite; one instance with many concurrent writers
  is. Only the latter triggers this ADR's reversal condition.

### ADR-005 — Defer embeddings until lexical dedup provably fails
- **Decision:** Semantic dedup is added only after capturing a specific real pair of near-
  duplicate headlines that `difflib.SequenceMatcher` failed to catch. Save the pair as a test
  fixture; it becomes the regression test for the semantic pass.
- **Why:** `sentence-transformers` pulls ~2GB of PyTorch to solve a problem not yet observed.
- **Tradeoff:** Possible brief-quality gap in the interim, which is measurable and acceptable.

### ADR-006 — Human writes interfaces, agent writes implementations
- **Why:** `[INFERRED]` The operator's two constraints — "prefer agentic over hardcoded" and
  "I want to learn to build a system end-to-end" — are in direct conflict. If the agent writes
  the interfaces, the operator ends with pattern recognition and no generative ability. He has
  self-reported difficulty with brute-learning, which makes the feeling of productivity
  especially hazardous.
- **Tradeoff:** Slower. Accepted; goal 2 outranks goal 1.

### ADR-007 — Three-layer explanations at decision points only
- **Why:** `[VERIFIED]` Pro-tier usage and context are finite. `[INFERRED]` Per-change essays
  would exhaust both faster than the coding, and go unread within days.
- **Result:** ~one ADR per working session; one-line rationale for routine work. The ADR folder
  becomes the repo's most valuable open-source artifact.

### ADR-008 — Evidence tagging is mandatory in all project documentation
- **Why:** `[VERIFIED]` The prior fabricated handoff was the project's most expensive failure.
- **Tradeoff:** Documents read as less confident. That is the point.

---

## 6. Implementation Details

**`[UNKNOWN]` — and this section is deliberately near-empty.**

No algorithms, business logic, validation rules or edge cases have been implemented or
specified beyond the design intent in `ARCHITECTURE.md`. The request that generated this
document asked for a complete description of algorithms, workflows, business logic, validation
logic, edge cases and assumptions. **Supplying them would mean inventing them**, which is the
precise failure this session exists to correct.

What *is* decided, at the level of intent only:

- **Dedup, pass 1:** exact hash of a normalized title string. Normalization scheme `[UNKNOWN]`.
- **Dedup, pass 2:** `difflib.SequenceMatcher` ratio over normalized titles within the window.
  Threshold `[UNKNOWN]` — must be tuned against real captured headlines, not guessed.
- **Dedup, pass 3:** deferred (ADR-005).
- **Window:** the two source documents disagree (48h vs 8h). **Unresolved — see Open Questions.**
- **Failure policy:** any source that errors returns an empty list and logs; the run continues.
- **Edge cases:** `[UNKNOWN]`. Will emerge from real payloads. Every one found gets a saved
  fixture in `tests/fixtures/` and a test.

---

## 7. Files Modified This Session

**None.** `[VERIFIED]` This was an analysis session. No file in the repository was created,
edited, or deleted.

Files *discussed*, and what is known about each:

| File | Purpose (as claimed) | Verified state |
|---|---|---|
| `HANDOFF.md` | Prior transfer document | `[VERIFIED]` Does not match the repo. Superseded by this file. Do not trust. |
| `sources/docs/Prototype_APIs_and_Tools_Functional_Overview.pdf` | Tool inventory | `[VERIFIED]` Contradicts `HANDOFF.md` on window length and WhatsApp path. |
| `Prototype Diagram.png` / `.drawio` | Flow diagram | `[VERIFIED]` Depicts the target flow; delivery leg superseded by ADR-002. |
| `ingestion/deduplicator.py` | Lexical + cascade dedup | `[VERIFIED]` Has bytecode, so it has run. Contents `[UNKNOWN]` — never read. |
| `storage/repository.py` | pgvector distance search | `[VERIFIED]` Has bytecode. Contents `[UNKNOWN]`. Superseded by ADR-004. |
| `ingestion/scrapers/espn.py`, `hoopshype.py` | Page parsers | `[VERIFIED]` Never imported. `[INFERRED]` Almost certainly stubs. |
| `delivery/whatsapp_os.py`, `services/whatsapp_gateway.py` | WhatsApp delivery | `[VERIFIED]` Never imported. Superseded by ADR-002. |
| `config/settings.py` | App settings | `[VERIFIED]` Never imported by running code. |
| All other legacy files | — | `[UNKNOWN]`. Not read. |

---

## 8. Known Bugs

`[UNKNOWN]` — **zero runtime bugs are known, because the system has never run end to end.**
Reporting bugs here would be fabrication.

What exist instead are **structural defects**, which are certain:

| ID | Defect | Symptom | Likely cause | Attempted fixes | Remaining work |
|---|---|---|---|---|---|
| D1 | Nine duplicated concerns | Imports ambiguous; four article schemas | Agent context loss mid-build | None | Superseded by ADR-001 (fork clean) |
| D2 | Delivery layer never imported | No brief has ever been sent | Never wired to the pipeline | None | Rebuild as Telegram adapter |
| D3 | `config/settings.py` never imported | Documented thresholds have no effect | Config layer never wired | None | Single settings module in clean repo |
| D4 | Docs contradict repo and each other | Operator planned against fiction | LLM-generated documentation | This document set | Enforce evidence tagging |
| D5 | Two normalizer modules both executed | Data shape non-deterministic | Duplicate implementations | None | One canonical schema module |
| D6 | Possible secrets/bytecode in git history | `[UNKNOWN]` | `.gitignore` status unknown | None | Run B2 command |

---

## 8b. Known Limitations (real, observed, not bugs)

| # | Limitation | Evidence | Consequence |
|---|---|---|---|
| L-1 | **`--date` affects games only; news is always current.** | `[VERIFIED]` 2026-08-05: `python main.py --date 2026-01-15` delivered January's scoreboard alongside today's offseason headlines. Reported by the operator from the delivered brief. | RSS is a feed of what is published *now*; the format has no date parameter, so historical headlines cannot be requested from ESPN at all. Harmless for the intended daily run. **Means SportWire cannot reconstruct a past day** — if that scope is ever wanted, it needs a news source with a date-queryable archive, which none of the free candidates in ADR-009/ADR-010 provide. Surfaced at runtime as a warning rather than hidden. |
| L-2 | **Individual player performances are unavailable.** | ADR-010. | Message 2 is team-level only. `[INFERRED]` Recoverable later by having M7's LLM extract performances from article prose, since the articles are already fetched legally. |
| L-3 | **Live/scheduled game shapes are unobserved.** | `[UNKNOWN]` — every captured game reads `status: "Final"`; it is the offseason, so no in-progress game has been seen. | Adapter handling of a live game is untested. Resolve after 2026-09-30 by capturing a second fixture. |

---

## 9. Open Questions

1. **Dedup window: 8 hours or 48 hours?** The two source documents disagree. The 8-hour figure
   appears tied to the delivery cadence, the 48-hour to the dedup lookback — they may not be
   the same knob. Operator must decide, and the decision must be one named setting.
2. **Delivery cadence.** Is every 8 hours actually wanted, or is once daily sufficient? Affects
   volume, cost, and dedup window.
3. **NBA scope.** News only, game data only, or both? The diagram shows both; v1 may not need both.
4. **Summarization: local model or hosted API?** Local (Ollama) satisfies C2 fully but is slow
   on a laptop. Hosted costs money. Undecided.
5. **Is the legacy repo's git history publishable?** Blocked on B2.
6. ~~**Scraping legality.** Do ESPN or HoopsHype offer RSS or an official feed that avoids the
   ToS problem entirely? Unresearched.~~ **RESOLVED 2026-08-04.** `[VERIFIED]` ESPN publishes
   a public NBA RSS feed at `espn.com/espn/rss/nba/news` (HTTP 200, 15 items, `<ttl>30</ttl>`).
   CBS Sports and Reddit r/nba also verified working. **No scraper is needed for ESPN.**
   See `docs/decisions/ADR-009-nba-news-source.md`. HoopsHype remains unresearched, but is no
   longer on the critical path.
7. **`storage/` salvage.** Is any of it worth copying? Requires reading the files.
8. **Phone port.** What does this mean concretely — Termux? A scheduled remote trigger? Undefined.
9. ~~**Multi-user.** `delivery/router.py` implies a user directory. Is v1 single-user (the
   operator) or multi-user?~~ **RESOLVED 2026-08-04.** v1 is **single-user per instance**.
   Multi-user is "possibly later"; the near-term distribution model is open-source, i.e. many
   people each running their own instance. See the 2026-08-04 amendment to ADR-004 in §5 for
   why that distinction is what keeps SQLite viable.
10. **Non-technical end users — explicitly deferred, not v1.** Operator stated 2026-08-03:
    signing up for API keys and editing `.env` is acceptable setup friction for now, but the
    longer-term generalization goal wants something usable by people without that technical
    background. Not a trigger for any decision today (ADR-003's `balldontlie.io` API key
    requirement stands) — recorded so v1's config/setup approach isn't assumed to be the
    final shape. See `TASKS.md` L13 for the deferred task this becomes.

---

## 10. Exact First Prompt for the Next Claude Code Session

Paste verbatim:

```
Read CLAUDE.md, SESSION.md, TASKS.md and ARCHITECTURE.md in full before doing anything.

Note especially the evidence rule in CLAUDE.md §0: tag every factual claim
[VERIFIED], [INFERRED] or [UNKNOWN], and never fill a gap with plausible prose.
The previous handoff document for this project was fabricated and cost weeks.

Do not write any code yet. First, run these commands against the current
repository and report the raw output, then tell me where it contradicts the
four documents:

  find . -path ./.venv -prune -o -name "*.py" -print | xargs wc -l | sort -n
  grep -rn "NotImplementedError\|TODO\|FIXME\|^\s*pass\s*$" --include="*.py" .
  grep -rn "class NewsArticle" --include="*.py" .
  git log --oneline | head -30
  git log --all --name-only | grep -i "\.env\|\.pyc" | head -20
  ls -la

Then stop and wait. I want to resolve blocker B2 (possible secrets in git
history) before anything else.

After that, the next task is C1-C3 in TASKS.md: freeze the legacy repo on a
`legacy` branch and initialise the clean repo.

Working agreement for this project, from CLAUDE.md §6, which I want you to
follow literally: I write the function signatures, type hints, docstrings and
the failing tests. You write only the function bodies that make my tests pass.
Ask me before creating any file. One file or one function per turn. If a
decision has more than one defensible answer, stop and ask rather than choosing
silently.

I can currently explain async/await and embeddings. I cannot yet explain the
adapter pattern, dependency inversion, or database migrations. Teach those
inline the first time they come up, before using them.
```
