# TASKS.md

**Rules for this file:**
- A task is checked off **only** when the command output or test result proving it is pasted
  into the "Proof" line beneath it. `[INFERRED]` The legacy repo's milestone list was checked
  off on assertion alone, and every one of those assertions turned out to be unverifiable.
- Slices are built one at a time. Do not start a lower-priority slice before the one above it
  runs end to end.
- Add new tasks at the bottom of the correct priority band. Do not delete completed tasks.

---

## COMPLETED

- [x] **Audit the legacy repository at directory level** — 2026-08-03
  - Proof: `tree` output, 136 files / 28 directories. Nine duplicated concerns identified.
    Bytecode analysis showed `scrapers/`, `apis/`, `delivery/`, `services/` and `config/`
    have never been imported.
- [x] **Verify NBA API network constraints** — 2026-08-03
  - Proof: `stats.nba.com` blocks datacenter IPs and uses Akamai TLS fingerprinting;
    `cdn.nba.com` live endpoints are unprotected.
- [x] **Verify WhatsApp Business API cost and access model** — 2026-08-03
  - Proof: per-message pricing since 2025-07-01, no free tier for business-initiated
    messages, BSP required with markup.
- [x] **Decide architecture direction** — 2026-08-03
  - Proof: ADR-001 through ADR-008 recorded in `SESSION.md` §5.

- [x] **Rebuild the virtual environment clean** — 2026-08-04
  - `[VERIFIED]` The legacy `.venv` was **5.6 GB / 151 packages**, including `torch`,
    `sentence-transformers`, `alembic`, `asyncpg`, `pgvector`, `SQLAlchemy` — the entire
    *deferred* column of `CLAUDE.md` §11, installed before anything in the *required* column
    had been proven. Confirmed `requirements.txt` recoverable from the `legacy` branch first,
    then deleted and rebuilt with only the v1 required column.
  - Proof: `.venv` now **68 MB / 21 packages**: `requests==2.34.2`, `pydantic==2.13.4`,
    `python-dotenv==1.2.2`, `pytest==9.1.1`, `ruff==0.16.1`, on Python 3.10.12 (WSL2 Ubuntu).
  - Proof: enforcement verified, not assumed — `import requests, pydantic, dotenv, pytest`
    succeeds; `torch`, `sentence_transformers`, `sqlalchemy`, `alembic`, `asyncpg`, `pgvector`
    all raise `ImportError`. `[INFERRED]` An accidental use of a deferred dependency now fails
    at import time instead of silently succeeding, so the environment enforces §11 rather than
    relying on the agent re-reading it.

---

## CRITICAL — do these before writing any application code

- [x] **C0. Resolve blocker B2: check git history for secrets and bytecode** — 2026-08-03
  - `[VERIFIED]` No `.git` existed yet, so there was no history to check — B2 as originally
    framed did not apply. `[VERIFIED]` No `.gitignore` existed (`cat .gitignore` → No such
    file). Ran instead: a working-tree scan for `.env` files (`find . -iname "*.env*"` →
    only `.env.example`, no real `.env`) and a grep across every source directory for
    `api[_-]?key|secret|password|token|Bearer|AKIA...|sk-...` (case-insensitive).
  - Findings: only field names (`APIFY_API_TOKEN`, `OPENAI_API_KEY` as `Optional[str] = None`
    in `config/settings.py`) and placeholder values in `.env.example`
    (`your_apify_token_here`, etc.). Two files hardcode **dummy local dev DB credentials**
    as connection-string defaults: `database/connection.py` and `storage/database.py`
    (`openclaw_user:openclaw_password`, `sports_user:sports_password`) — not real secrets,
    but bad practice; flag for cleanup in the rebuild, do not carry the pattern forward.
  - Proof: no real secret found; safe to commit. `.gitignore` written before first commit
    (`.venv/`, `__pycache__/`, `*.pyc`, `.env`, `*.db`, `.pytest_cache/`, `.ruff_cache/`,
    `.coverage`, `*.egg-info/`, `.claude/settings.local.json`, `*.bkp`).

- [x] **C1. Run the full forensic command set and record real numbers** — 2026-08-03
  - The four commands in `CLAUDE.md` §7 "Forensics", plus commit log.
  - Proof: `docs/AUDIT.md`. Headline findings beyond what `SESSION.md` already had: 17
    zero-length files including `run_pipeline.py` (the implied entrypoint) and all of
    `ingestion/apis/` and `services/llm_summarizer.py` / `whatsapp_gateway.py` — there is no
    partial implementation to salvage in those, just empty files. `NewsArticle` is defined
    in 4 places, one of them inside `tests/conftest.py` itself, meaning the one test that
    was ever run may not have tested either real candidate schema. 3,428 total lines across
    tracked `.py` files. Confirms `SESSION.md` §3.3 bytecode findings exactly, no discrepancy.

- [x] **C2. Freeze the legacy repository** — 2026-08-03
  - No prior repo existed, so this was `git init` (not `checkout -b`) at the repository root,
    then the freeze commit, then a `legacy` branch marking it.
  - Proof: root commit `e8953e0` on `main`, message "chore: freeze legacy prototype as
    pre-release snapshot", 97 files. Tagged `pre-release-legacy-frozen`. Branch `legacy`
    created pointing at the same commit. **Not pushed** — no GitHub remote configured yet;
    that is a separate decision (visible/shared action) not taken here.

- [x] **C3. Initialise the clean repository** — 2026-08-03
  - Resolved structure ambiguity (branch vs. new directory) with the operator: one repo,
    two branches. `legacy` keeps the full 97-file snapshot; `main` was wiped to just the
    governance docs and rebuilt.
  - Proof: commit `ba10e94`. `main` now contains only `.gitignore`, `ARCHITECTURE.md`,
    `CLAUDE.md`, `SESSION.md`, `TASKS.md`, `docs/AUDIT.md`, plus newly added `README.md`,
    `LICENSE` (MIT), `pyproject.toml` (no dependencies yet — added per-slice), a
    Telegram-aligned `.env.example`, and `docs/decisions/TEMPLATE.md`. Zero Python files
    on `main`. `git ls-files` confirms 11 tracked files total.

- [x] **C4a. Prove NBA connectivity by hand — FAILED, ADR-003 reopened** — 2026-08-03
  - `curl https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json`
  - Proof: HTTP 403, Akamai `errors.edgesuite.net` block page. `[VERIFIED]` from the agent's
    sandboxed shell (twice, with and without browser `User-Agent`/`Referer`) **and**
    `[VERIFIED]` from the operator's own machine, real residential IP, no sandbox. Same
    result both times — this rules out "sandbox/proxy egress IP" as the explanation.
    `CLAUDE.md` §4 and `ADR-003` corrected in place; do not treat the old claim as live.
  - Proof: no `tests/fixtures/nba_scoreboard.json` written — nothing to save from a 403.

- [ ] **C4b. Find a working NBA data source before writing any adapter**
  - Candidates to research, cheapest/least-risky first: (1) other `cdn.nba.com` /
    `stats.nba.com` endpoint paths — maybe only this specific path is blocked; (2) the
    `nba_api` PyPI package, which has historically handled the header/cookie dance
    `stats.nba.com` requires — test it live before trusting its README; (3) third-party
    free APIs (e.g. balldontlie.io) — check current auth requirements, rate limits, and
    whether they mirror live/in-progress game state or only final box scores; (4) ESPN's
    undocumented public JSON endpoints — same ToS caution as ESPN scraping (§4 Scraping).
  - Record findings as `[VERIFIED]` HTTP status + payload shape for each candidate actually
    tried, not documentation claims. This becomes ADR-003's replacement decision.
  - Proof — live-tested 2026-08-03:
    - `cdn.nba.com/.../odds_todaysGames.json` (different path, same host) → `[VERIFIED]` 403,
      same Akamai block. Not path-specific; the whole host is blocked from here.
    - `stats.nba.com/stats/scoreboardv2` → `[VERIFIED]` connection hangs / times out (curl
      exit 56) from the agent's sandbox. Consistent with the existing (still-standing)
      datacenter-IP-block claim. **Not retested from the operator's residential machine.**
    - `api.balldontlie.io/v1/teams` → `[VERIFIED]` HTTP 401 `Unauthorized`. Now requires a
      free API key (signup) — no longer fully anonymous, but it is a documented, intended-
      for-third-party-use public API, which is exactly what C3's scraping guidance asks to
      prefer over an undocumented endpoint.
    - `site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard` → `[VERIFIED]` HTTP
      200, real structured JSON (season, teams, live status). Zero auth, zero setup. **Not an
      officially documented public API** — same category of legal/stability grayness as the
      ESPN scraping caution already in `CLAUDE.md` §4, just JSON instead of HTML.
  - **Decision: `balldontlie.io`.** Full rationale in
    `docs/decisions/ADR-003-nba-data-source.md`. `CLAUDE.md` §4 and `.env.example` updated.
  - Proof: ADR-003 written and committed.

- [x] **C4c. Operator obtains a free `balldontlie.io` API key and proves an authenticated call** — 2026-08-04
  - Key obtained by operator, stored in `.env` as `BALL_DONT_LIE_API_KEY` (36 chars).
    `[VERIFIED]` `.env` is gitignored (`git check-ignore -v .env` → `.gitignore:4:.env`).
  - Proof: `curl -H "Authorization: <key>" https://api.balldontlie.io/v1/teams` → **HTTP 200**,
    real team data (`{"data":[{"id":1,...,"full_name":"Atlanta Hawks","abbreviation":"ATL"}...`).
  - Proof: `.../v1/games?dates[]=2026-08-04` → **HTTP 200** `{"data":[],"meta":{"per_page":25}}`
    — empty because August is NBA offseason. `[VERIFIED]` The 2026-27 season starts 2026-09-30.
    **Consequence for slice 1: there is no live NBA data to fetch right now.** The adapter must
    be built and tested against the fixture below, and an empty-list return is a normal,
    expected case — not an error. This is a real edge case discovered by testing, not guessed.
  - Proof: `.../v1/games?dates[]=2026-01-15` (mid-season) → **HTTP 200**, 9 real games. Saved
    to `tests/fixtures/nba_games.json` (7,782 bytes). Payload shape includes: `id`, `date`,
    `season`, `status`, `period`, `time`, `postseason`, `home_team_score`,
    `visitor_team_score`, `datetime`, per-quarter scores, and nested `home_team`/`visitor_team`
    objects. **Note: this endpoint returns game/score data only — no news articles.** Feeding
    the `NewsArticle` schema needs a separate source (task M5).

- [x] **C5. Create the Telegram bot and prove delivery by hand** — 2026-08-04
  - Bot created via @BotFather: display name "OpenClaw Sports Brief", username
    `@openclaw_sports_bot`. Token and chat ID in `.env`.
  - Proof: `curl -X POST https://api.telegram.org/bot<token>/sendMessage -d chat_id=<id>
    -d "text=OpenClaw C5 delivery test..."` → **HTTP 200**,
    `{"ok":true,"result":{"message_id":5,...,"chat":{"id":<id>,"first_name":"Youssef",
    "type":"private"}}}`. **A real message was delivered to the operator's Telegram.**
  - `[VERIFIED]` Telegram delivery works with zero dependencies — a single HTTP POST. This
    confirms ADR-002's "~15 lines to send a message" claim.

---

## HIGH — Slice 1: one story, end to end

> Target: `cdn.nba.com` → `NewsArticle` → hash dedup → formatted string → Telegram message
> on the operator's phone. **No database. No embeddings. No async. No scrapers. No Apify.**
> If it exceeds ~150 lines, it is over-built.

- [ ] **H1. Human writes `models/schemas.py`** — the canonical `NewsArticle` Pydantic model.
  Fields, types, docstring. **Human writes this alone; it is the central design decision of
  the project.**
  - Proof:
- [ ] **H2. Human writes `tests/test_schemas.py`** — assertions about valid and invalid articles.
  - Proof:
- [ ] **H3. Agent implements validators to make H2 pass.** One turn, one file.
  - Proof:
- [ ] **H4. Human writes the signature of `ingestion/nba_live.py::fetch_games() -> list[GameData]`.**
  - Proof:
- [ ] **H5. Agent implements `fetch_games()` against the saved fixture, then against live.**
  - Proof:
- [ ] **H6. Human writes `tests/test_dedup.py`** with three cases: identical titles, near-identical
  titles, genuinely different titles.
  - Proof:
- [ ] **H7. Agent implements `dedup.py`** — hash pass plus `difflib.SequenceMatcher` pass.
  In-memory `set`, no DB.
  - Proof:
- [ ] **H8. Human writes `delivery/base.py`** — the abstract `DeliveryChannel` interface.
  **Agent teaches the adapter pattern and dependency inversion inline here (blocker B5) before
  the human writes it.**
  - Proof:
- [ ] **H9. Agent implements `delivery/telegram.py` against that interface.**
  - Proof:
- [ ] **H10. Human writes `main.py`** wiring fetch → dedup → format → send. Single entrypoint.
  - Proof:
- [ ] **H11. Run it. A real message arrives on the phone.** This is the first genuine milestone
  the project has ever had.
  - Proof:
- [ ] **H12. Write ADR-010 recording what was actually learned building slice 1.**
  (Renumbered from ADR-009, which was taken by the news-source decision on 2026-08-04.)
  - Proof:
- [ ] **H13. Operator explains every file in slice 1 aloud, unaided.** Any file he cannot explain
  is deleted and regenerated (ADR-006).
  - Proof:

---

## MEDIUM — after slice 1 runs

- [ ] **M1. Add persistence: SQLite, one `articles` table, seen-hash lookup.** Dedup survives
  restarts. `sqlite3` stdlib, no ORM.
  - Proof:
- [ ] **M2. Add `config/settings.py`** — one module, `python-dotenv`, typed settings. Every other
  module reads settings only from here.
  - Proof:
- [ ] **M3. Resolve open question 1** — decide the dedup window and the delivery cadence as two
  distinct named settings. Record in an ADR.
  - Proof:
- [ ] **M4. Add structured logging** — `logging`, INFO to stdout, level from settings. Every
  source logs what it fetched and what dedup discarded.
  - Proof:
- [ ] **M5. Add source 2: an NBA news source.** Research an official feed or RSS **before**
  writing a scraper (constraint C3). Record what was found.
  - Proof:
- [ ] **M6. Confirm the orchestrator required zero changes to add source 2.** If it needed
  changes, the adapter boundary is wrong — fix it. **This is the test of whether the adapter
  pattern was understood.**
  - Proof:
- [ ] **M7. Add summarization** — resolve open question 4 (local vs hosted) in an ADR first.
  - Proof:
- [ ] **M8. Add scheduling** — cron or Windows Task Scheduler invoking `main.py`. Not an
  in-process loop; the OS is a better scheduler than a `while True`.
  - Proof:
- [ ] **M9. Add error resilience** — every source wrapped so one failure degrades rather than
  crashes. Test with a deliberately broken source.
  - Proof:
- [ ] **M10. Add CI** — GitHub Actions running `ruff check` and `pytest -m "not network"` on push.
  First real DevOps artifact; explain what CI is and why network tests are excluded.
  - Proof:

---

## LOW — deferred; each requires a trigger condition

- [ ] **L1. NFL sources (`nflreadpy`).** Trigger: NBA path stable across several real runs.
- [ ] **L2. Semantic dedup.** Trigger: a captured real near-duplicate pair that
  `SequenceMatcher` missed, saved as a fixture (ADR-005).
- [ ] **L3. Postgres + `pgvector`.** Trigger: SQLite measurably too slow. `[INFERRED]` Unlikely.
- [ ] **L4. Alembic migrations.** Trigger: L3, or a schema change against a table with real rows.
  Teach migrations properly at that point (blocker B5).
- [ ] **L5. Async ingestion.** Trigger: a synchronous run measurably too slow, with the number recorded.
- [ ] **L6. WhatsApp delivery adapter.** Trigger: operator accepts recurring per-message cost.
  Official BSP path only — never an unofficial bridge (C3).
- [ ] **L7. Apify actors.** Trigger: cost estimate produced and approved (C2).
- [ ] **L8. Multi-user routing.** Trigger: open question 9 resolved in favour of multi-user.
- [ ] **L9. RAG chatbot query interface.** Trigger: the one-way brief works and is genuinely used.
- [ ] **L10. Phone port.** Trigger: open question 8 defined concretely.
- [ ] **L11. Docker.** Trigger: someone other than the operator needs to run it. `[INFERRED]`
  Premature under constraint C1; a `Dockerfile` and `docker-compose.yml` already exist in the
  legacy repo and have never been used.
- [ ] **L12. Write the public README and a "what went wrong with v1" post-mortem.** The
  post-mortem, backed by the ADR folder, is `[INFERRED]` the most valuable thing in the repo
  for a portfolio.
- [ ] **L13. Lower setup friction for non-technical users** (hosted config UI, a managed
  key-proxy, one-click deploy — undecided, do not design yet). Trigger: v1 works for the
  operator and someone without his technical background wants to run it. Operator flagged
  2026-08-03 that `.env`/API-key setup (e.g. ADR-003's `balldontlie.io` key) is acceptable
  for now but not the intended final shape — see `SESSION.md` §9 Q10.
