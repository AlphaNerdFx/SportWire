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
    created pointing at the same commit.
  - **Published 2026-08-06** to `https://github.com/AlphaNerdFx/SportWire` (public).
    `[VERIFIED]` `git ls-remote` shows `main`, `legacy` and the `pre-release-legacy-frozen`
    tag. `[VERIFIED]` Pre-push audit: the live bot token and balldontlie key appear **0
    times** in full history (`git log --all -p | grep -cF`), `.env` was never committed, and
    `git ls-tree -r origin/main` confirms no `.env`, `.venv`, `*.db` or `__pycache__` on the
    remote. Personal Telegram identifiers were redacted from `TASKS.md` beforehand, though
    they remain in earlier commits — not credentials, and judged acceptable.

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

- [x] **C4b. Find a working NBA data source before writing any adapter** — 2026-08-04
  - Proof: `balldontlie.io` v1, free tier, API key by signup. `[VERIFIED]` Returns games
    with per-period scores and team ids; rate-limited, and the free tier returned 429 from
    the sixth request in one run, which is why head-to-head is computed locally instead.
    `[VERIFIED]` The free tier does **not** include `/v1/stats` — that is what forced
    ADR-010 (no individual player statistics). Full rationale in ADR-003.
  - Original research notes retained below.
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
  - **Superseded 2026-08-04 by the project rename to SportWire.** The record above is left
    unedited because it is the proof of what was actually verified at the time. `[Likely]`
    BotFather cannot rename an existing bot's username, so a replacement bot must be created
    and C5 re-verified with the new token. **Tracked as C5b below.**
  - Proof: `curl -X POST https://api.telegram.org/bot<token>/sendMessage -d chat_id=<id>
    -d "text=OpenClaw C5 delivery test..."` → **HTTP 200**,
    `{"ok":true,"result":{"message_id":5,...,"chat":{"id":<id>,"first_name":"Youssef",
    "type":"private"}}}`. **A real message was delivered to the operator's Telegram.**
  - `[VERIFIED]` Telegram delivery works with zero dependencies — a single HTTP POST. This
    confirms ADR-002's "~15 lines to send a message" claim.

- [x] **C5b. Recreate the Telegram bot under the SportWire name** — 2026-08-04
  - Via @BotFather: `/newbot`, e.g. display name "SportWire", username `@sportwire_bot`
    (or `@sportwire_sports_bot` if taken). Then `/deletebot` the old `@openclaw_sports_bot`.
  - Replace `TELEGRAM_BOT_TOKEN` in `.env` with the new token. `TELEGRAM_CHAT_ID` is the
    operator's own chat ID and **does not change** — it identifies the recipient, not the bot.
  - Re-run the C5 send to prove the new token works before any delivery code is written.
  - Proof: `getMe` → **HTTP 200**, `{"ok":true,"result":{"id":<bot-id>,"is_bot":true,
    "first_name":"SportWire","username":"sportwire_news_bot",...}}`. `[VERIFIED]` This is a
    genuinely different bot — the old one had a different id and username.
    `@sportwire_bot` was already taken on Telegram; `@sportwire_news_bot` was used instead.
  - Proof: `sendMessage` → **HTTP 200**, `{"ok":true,"result":{"message_id":4,...}}`, and the
    operator confirmed receipt on his phone.
  - `[VERIFIED]` `TELEGRAM_CHAT_ID` was unchanged across the bot swap, confirming it
    identifies the **recipient**, not the bot. Only `TELEGRAM_BOT_TOKEN` had to change.

---

## HIGH — Slice 1: one story, end to end

> **H1-H10 were written under the superseded ADR-006 contract** (human writes signatures,
> docstrings and test assertions; agent writes bodies). The operator reversed that on
> 2026-08-05: *"You'll write the code not me."* They are recorded here as **[x] superseded**
> rather than deleted, because the file rule says completed tasks are not removed and because
> the reversal is the single most consequential process change this project has made.
>
> `[VERIFIED]` Every file H1-H10 named exists, works, and is agent-written. The target itself
> also changed: `cdn.nba.com` returns 403, so games come from balldontlie (ADR-003), and the
> slice grew past "no database" once dedup had to survive restarts.

- [x] **H1-H3. `models/schemas.py` + its tests.** *Superseded contract; agent-written.*
  `GameData`, `NewsArticle`, `GameHighlight`, `SeriesContext`, all frozen.
- [x] **H4-H5. Games ingestion.** *Superseded contract; agent-written.* Landed as
  `ingestion/nba_games.py` against balldontlie, not `nba_live.py` against `cdn.nba.com`.
- [x] **H6-H7. `processing/dedup.py`.** *Superseded contract; agent-written.* Both passes
  exist; the in-memory `set` became a SQLite-backed one in M1, as anticipated.
- [x] **H8-H9. `delivery/base.py` + `delivery/telegram.py`.** *Superseded contract;
  agent-written.* The adapter pattern was taught inline as B5 required. `[VERIFIED]` It was
  **not** retained — H13 Q5 asked why there are two ABCs and the answer asserted a shared
  superclass that does not exist. Teaching a pattern once at its first appearance is not
  sufficient; it needs revisiting at each reuse.
- [x] **H10. `main.py`.** *Superseded contract; agent-written.* Single entrypoint, and still
  the only file naming a concrete adapter or channel.

- [x] **H11. Run it. A real message arrives on the phone.** — 2026-08-05
  - Proof: `python main.py --date 2026-01-15` delivered three messages to the operator's
    Telegram at 19:46, confirmed by screenshot: **SCORES** (9 games), **NOTABLE**
    (`Comeback — Orlando Magic came back from 16 down`, `Closest finish — decided by 3`,
    `Biggest win — Dallas Mavericks by 22`), and **NEWS** (16 ESPN articles).
  - Proof: `python main.py --dry-run` on today's date → `fetched 0 games, 16 articles`,
    one message, nothing sent, nothing recorded. `[VERIFIED]` The offseason path works:
    zero games is handled as "omit the section", not as an error.
  - `[VERIFIED]` ESPN returned **16** articles live versus 15 in the captured fixture, so
    the feed genuinely moved between capture and run.
- [x] **H12. Write an ADR recording what was actually learned building slice 1.** — 2026-08-05
  - Proof: `docs/decisions/ADR-011-slice-1-retrospective.md`. Seven findings, each with the
    measurement behind it: verified evidence going stale (`cdn.nba.com`), six assumptions
    that real data contradicted, three rules converted from prose into mechanisms, one
    boundary that answered three unrelated questions, two features declined on evidence
    rather than deferred on principle, the two defects that proved tests and real usage catch
    different bug classes, and the ADR-006 reversal recorded as the project's largest open
    risk.
- [ ] **H13. Operator explains every file in slice 1 aloud, unaided.** Any file he cannot explain
  is deleted and regenerated (ADR-006).
  - **ATTEMPT 1 — 2026-08-05: NOT PASSED. 2 of 8 correct.**
  - Eight questions covering the ten slice-1 files. Passed: why `author` is optional (Q4),
    which files change when a source is added (Q6, missed the `main.py` line). Failed: why
    `state_hash` excludes a timestamp (Q1 — the exact error the operator had proposed
    mid-build), the `_fetch`/`fetch` split (Q2), record-after-send ordering (Q3, answered
    "concurrency"), why there are two ABCs (Q5, asserted a shared superclass that does not
    exist), why dedup takes an injected set (Q7, answered performance rather than
    testability), and why the brief is plain text (Q8, asserted Telegram lacks Markdown
    support — it has it; the issue is MarkdownV2's ~18 reserved characters).
  - **ADR-006's remedy is deliberately NOT applied.** `[INFERRED]` That remedy — delete and
    regenerate — assumes the human wrote the interfaces and the agent wrote bodies, so a
    failure to explain implies the implementation was too clever. That is not this situation:
    all ten files were agent-written after the operator instructed *"you'll write the code
    not me"* (see ADR-011 §7). Regenerating produces ten files he also has not read.
    Deleting working software would not address the cause.
  - **Corrected 2026-08-07.** An earlier substitute remedy had the operator rewrite
    `processing/dedup.py` himself. That was the superseded ADR-006 contract returning under
    another name — the operator had already instructed that the agent writes the code, and
    `OPERATING_RULES.md` §0 now states the agent never sets him code to write.
  - **Actual remedy: guided walkthrough, then a re-check on the same questions.** The agent
    explains the specific mechanisms that were missed, in this codebase's terms; if an
    explanation does not land, the code is simplified rather than the operator retested. The
    re-check happens after a gap, since understanding measured immediately after an
    explanation is recall.
  - Proof:

---

## MEDIUM — all complete, 2026-08-12

Every M-band task is done. Proof is in `git log` and in the ADRs; the summary below records
what each turned into, since several changed shape on contact with real data.

- [x] **M1. SQLite persistence.** `storage/db.py`. Rows kept indefinitely rather than pruned —
  `[VERIFIED]` a window shorter than the feed's reach re-sends stories, and ESPN reaches back
  ~4 days. Later extended with `game_results` for local head-to-head.
- [x] **M2. `config/settings.py`.** `[VERIFIED]` No `os.getenv` remains anywhere else. Paths
  anchor to `PROJECT_ROOT`, which fixed scheduled runs finding no `.env` at all.
- [x] **M3. Dedup window and cadence separated.** 168h window, 8h cadence (PRD D1/D2). They are
  different knobs; the original documents conflated them.
- [x] **M4. Structured logging.** Level from settings. Every fetch, drop, cap and rejection is
  logged — `[VERIFIED]` this is how nine bugs were actually found.
- [x] **M5. More sources.** CBS Sports, Yahoo Sports, r/nba. `[VERIFIED]` The Athletic,
  Sporting News and NYT were evaluated and rejected with recorded reasons.
- [x] **M6. The adapter-boundary test.** Honest result: adding source 2 required **one line**
  in `main.py` — the orchestrator had hardcoded a single source. It now iterates `FEEDS`, and
  sources 3 and 4 needed no code at all. The boundary held; the caller had a gap.
- [x] **M7. Summarisation.** ADR-012. Local Ollama, validated, with retry. See `SESSION.md` §6
  for the nuanced state.
- [x] **M8. Scheduling.** cron every 8h, `docs/SCHEDULING.md` covers both schedulers.
  `[VERIFIED]` Running unattended for days, surviving terminal closes.
- [x] **M9. Error resilience.** Enforced structurally in `ingestion/base.py` and
  `delivery/base.py` rather than by convention. `[VERIFIED]` A dead source returns `[]`; three
  separate rate limits (Reddit, balldontlie twice) degraded correctly in production.
- [x] **M10. CI.** GitHub Actions running `make check`. Green.

---

## CURRENT — the only priority

- [ ] **P1. Write tests for `processing/` (issue #15).**
  `[VERIFIED]` 16 source modules, 3 tests, all three testing rendering. Nine real bugs were
  found in six days **by reading live output, never by a test** — full list in `SESSION.md` §8.
  Every one would have been a two-line test and every one can silently return.
  **Do not add features before this unless the operator asks.**

  - [x] **`newsworthy.py`** — 2026-08-13, commit `19dabf3`. Chosen first: five of the eleven
    recorded bugs are in it, and it is the only module permitted to delete an article, so its
    failures are invisible by construction.
    - Proof: `pytest -v` → **27 passed in 0.71s** (24 new + the 3 existing rendering tests).
    - Proof — `[VERIFIED]` **the tests were mutation-tested, not trusted because they passed.**
      Resurrecting Rule 2 in place: `5 failed, 19 passed`, the failures being all four
      `test_year_in_title_no_longer_drops_current_reporting` cases plus
      `test_removing_rule_2_did_not_weaken_the_other_rules`. Making `_strip_invisible` a
      no-op: `1 failed, 23 passed`, the failure being exactly
      `test_invisible_character_before_tag_does_not_defeat_the_match`. Source restored from
      git after each; `git diff HEAD -- processing/newsworthy.py` empty.
    - `[INFERRED]` This is the step the legacy repo skipped. `test_ingestion_setup.py` passed
      in 3.32s while asserting only that imports resolve, and a suite that has never been
      seen to fail is indistinguishable from that one.
  - [x] **`validate.py`** — 2026-08-13, commit `19bd2a0`. Chosen second: it is the last check
    before the phone, and two of the eleven recorded bugs are in it.
    - Proof: `make check` → **40 passed, 1 xfailed**. The xfail is P5, asserted rather than
      omitted so it flips to XPASS when fixed.
    - Proof — `[VERIFIED]` mutation results, one failing test per mechanism:

      | Mutation | Result |
      |---|---|
      | sentence splitting disabled | 1 failed — names matched across a boundary |
      | leading-stopword strip disabled | 1 failed — reported-name text |
      | last-word grounding removed | 2 failed — `New York Knicks`, `Oklahoma City Thunder` |
      | possessive stripping disabled | 1 failed — `Kawhi Leonard's` |

    - `[VERIFIED]` **Two of these four guards were fake on the first attempt** — the sentence
      and stopword tests passed with their mechanism disabled, because the generous last-word
      grounding rescued the broken cases. Both were rewritten against discriminating data.
      `[INFERRED]` A test written from the same reasoning as the code inherits the code's
      blind spots; only trying to break it exposes that.
    - Diagnosing the second one found a real defect, opened as **P6**.
  - [x] **`priority.py`** — 2026-08-13, commit pending. Chosen third: three recorded bugs,
    and one of them was structural rather than a tokenising slip.
    - Proof: `make check` → **59 passed, 1 xfailed**.
    - Proof — `[VERIFIED]` mutation results:

      | Mutation | Result |
      |---|---|
      | tonight promoted to a top-level tier (the 2026-08-07 bug) | 1 failed — the tiebreaker test |
      | hyphen splitting removed | 2 failed — `ex-fiancée`, `sign-and-trade` |
      | possessive handling removed | 1 failed — `Warriors'` |
      | `high` checked before `low` | 1 failed — wedding-plus-"deal" |
      | team keyword takes the first word | 2 failed — keywords, and the within-tier tiebreak |

    - `[INFERRED]` **The structural bug is the one worth noting.** Making "tonight" a tier of
      its own broke nothing about tokenising, so every token-level test passes under it. Only
      an ordering assertion across two tiers catches it — which is why the fix is asserted in
      both directions (it must outrank, *and* it must still break ties within a tier).
  - [x] **`dedup.py`** — 2026-08-13, commit pending. Chosen fourth despite **no recorded
    bugs**: it is load-bearing and quiet, and it is where three of H13's failed questions
    live (Q1, Q3, Q7), so the tests double as the written form of those answers.
    - Proof: `make check` → **70 passed, 1 xfailed**.
    - Proof — `[VERIFIED]` mutation results:

      | Mutation | Result |
      |---|---|
      | pass 1 (already-delivered) removed | 2 failed |
      | pass 2 (near-identical) removed | 2 failed |
      | games matched on `game_id` not `state_hash` | 1 failed — the unchanged-game test |
      | `normalise_title` stops lowercasing | 1 failed |
      | threshold lowered 0.85 → 0.40 | 2 failed — **including the real-data test** |

    - `[INFERRED]` The last row is the useful one: `test_real_cross_source_pairs_do_not_collapse`
      re-measures ADR-005's evidence from the committed fixtures on every run, so the
      threshold is guarded by data rather than by a comment. Lowering it below what real
      headlines actually score fails the suite.
  - [ ] `cluster.py`, `highlights.py`, `storage/db.py`, `settings.py`, both RSS parsers,
    the Telegram message splitter.
  - Proof:

- [x] **P2. Verify the paragraph and subject-grouping prompt.** — 2026-08-13, **provisionally**
  `[VERIFIED]` The operator supplied both delivered briefs from 2026-08-13. The commit clock
  is what makes them readable: `71b2fa9` landed **14:43**, so the 08:00 brief ran on the *old*
  prompt and the 16:00 brief is the *first* run of the new one.
  - Proof — **08:00, old prompt.** One unbroken block. Westbrook's retirement opens it, then
    Jalen Duren, then Lakers ownership, then it **returns** to Westbrook for the Michael B.
    Jordan narration and LeBron's "HELLUVA CAREER BRODIE!! HOF next!!" — the reactions
    separated from the event by two unrelated subjects. This is the failure the prompt was
    written to fix, and it is not a test of the fix.
  - Proof — **16:00, new prompt.** Two paragraphs. ¶1 is Westbrook: retirement, the
    LeBron/Giannis tributes, the triple-double record — **the reaction sits with the event it
    reacts to.** ¶2 is everything else: Mavericks schedule, Suns waiving Highsmith, Clippers
    investigation. Both criteria met.
  - `[UNKNOWN]` **Whether it holds.** n=1, and `SESSION.md` §11 records concluding from one
    run as a mistake this project has made twice. The 16:00 input was also *smaller* — 7
    stories over 2 chunks against the 08:00 run's 12 over 3 — so the structural risk this task
    predicted (notes arriving in chunk order, related items far apart) is **untested at 3
    chunks under the new prompt.** The next 12-story run is the real test; if grouping breaks
    there, order notes by subject before the reduce step.

- [ ] **P3. Decide what to do about `newsworthy.py` Rule 2 (past-year outside quotes).** (#16)
  `[VERIFIED]` 2026-08-13 it dropped r/nba's `[Charania] After 18 NBA seasons, Russell
  Westbrook has retired…` because the title cited his 2008 debut. **Second false positive
  from this rule**; the first was a current Ballmer story citing 2015, after which the rule
  was narrowed rather than reconsidered.
  `[VERIFIED]` The diagnosis is fixed — `drop_non_news` now logs which rule fired, the
  offending text, and the untruncated title. **The rule is not**, deliberately: there are at
  least four defensible fixes and `CLAUDE.md` §6 forbids picking silently.
  - a. Delete Rule 2. Rules 0/1/1b already carry most of the load; measure what returns.
  - b. Require two or more past years — one citation is context, several is a retrospective.
  - c. Require the year in the first few words, where a retrospective announces itself.
  - d. Exempt retirement, contract, draft and anniversary wording.
  `[INFERRED]` (a) is the one to test first. This project's evidence is that narrow rules
  keep producing invisible false positives, and Rule 2 is the only one that reads a number
  rather than a phrase.

  **Operator chose (a) on 2026-08-13. Done — commit `06110ab`.**
  - Proof — verified against the real titles from `logs/sportwire.log`, not invented ones:

    | Title | Before | Now |
    |---|---|---|
    | `[Charania] After 18 NBA seasons… Westbrook has retired… 2017 MVP` | dropped | **kept** |
    | Ballmer cap circumvention, `"In 2015…"` | dropped, then narrowed | **kept** |
    | `[Highlight] Westbrook gets intentionally fouled…` | dropped | dropped (rule 1) |
    | `On this day in Bucks history…` | dropped | dropped (rule 1b) |
    | `During his NBA career, Bill Russell…` | dropped | dropped (rule 1b) |
    | `[Highlight] Chris Mullin beats Durant (2017)` | dropped | dropped (rule 1) |
    | `After Leonard signed with the Clippers in 2019, Masai Ujiri was asked…` | dropped | **kept** |

  - `[VERIFIED]` **The accepted cost is the last row** — Rule 2's one documented true positive
    now reaches the brief, capped by `cluster.py` and ranked low by `priority.py`, so it costs
    a line rather than a slot. It is asserted explicitly in
    `test_removing_rule_2_did_not_weaken_the_other_rules` so the trade stays visible in the
    suite rather than only in a commit message.
  - `[VERIFIED]` Removing the rule orphaned `_YEAR`, `_QUOTED`, `_strip_quoted` and
    `_current_season_year`; all four deleted, recoverable from git history.
  - **What to watch:** the drop log, for retrospectives returning. That is the measurement
    option (a) was chosen to produce.

- [ ] **P4. Establish the summariser's actual pass rate.** (#17)
  `[VERIFIED]` The "~84%" figure came from 3/5 on one sitting and is repeated in several
  places; two runs on 2026-08-13 went 0/3 then pass. `[UNKNOWN]` The real rate.
  Count validation outcomes across the soak from `logs/sportwire.log` rather than quoting
  a number from one sitting. `[VERIFIED]` Every occurrence in `main.py` and `SESSION.md`
  has been corrected to `[UNKNOWN]`; check ADR-012 has not been missed.

  **2026-08-13: attempted, and blocked by a defect in the log itself.**
  - `[VERIFIED]` **The log recorded no date** — `main.py:65` set `datefmt="%H:%M:%S"`. Runs
    are 8h apart and cron skips whenever WSL sleeps, so two consecutive `08:00:17` lines
    could be one day apart or four. The log cannot be segmented by code version, which is
    exactly what this task needs: `7323396` (last-word grounding) changed rejection behaviour
    mid-soak. **Fixed in `ec7bc3c`;** existing lines stay undated, so an honest count starts
    from the next run.
  - Proof — raw count over all 483 lines, offered as a **floor, not the rate**: 8 summarisation
    runs. **2 delivered a validated summary, 5 fell back after 3 rejections each, 1 errored.**
    Per attempt that is **2 accepted / 19 ≈ 11%**.
  - `[VERIFIED]` The count mixes code versions and cannot be cleaned: at least one logged run
    predates the current summariser, its traceback naming the pre-rename directory
    `/mnt/c/DSC/.../NBA and NFL News and Games Assistant/` and its wording not matching
    today's `summarize.py`.
  - `[VERIFIED]` **What is safe to state: nothing in this log supports 84%.** The gap is not
    marginal — 11% against 84% is a factor of eight, and even the intermediate "1/2" in
    `SESSION.md` §6 was optimistic.
  - `[UNKNOWN]` The real rate. Re-count after ~2 weeks of dated logs.
  - Proof:

- [ ] **P5. The validator grounds entities, not claims — a bug class not in `SESSION.md` §8.**
  Found 2026-08-13 by reading the two delivered briefs the operator supplied. **This one
  reached the phone**, which the eleven recorded bugs' whole point is to prevent.
  `[VERIFIED]` The 08:00 brief passed validation **on attempt 1** and contains: *"His
  retirement marked the end of playoff runs for basketball greats like Kobe Bryant, Tim
  Duncan, Dirk Nowitzki, and Kawhi Leonard."* `[INFERRED]` Kawhi Leonard is active — the same
  run's feed carries *"As the Kawhi Leonard investigation drags on… his trade to the
  Raptors."*
  `[VERIFIED]` The 16:00 run shows the same shape from the other side: attempt 2 was rejected
  for `Los Angeles Clippers-approved`, and **attempt 3 was accepted saying "team-approved beat
  writers"** — the model rephrased around the validator rather than becoming correct.
  `[INFERRED]` **Every name in both sentences is real and appears in the sources, so
  `validate.py` passes them.** It catches invented *entities* and is blind to false
  *relationships* between real ones. This is a different failure class from the Joe
  Dumars / Ayo Dosunmu one, which retry and grounding were both built for.
  `[UNKNOWN]` How often it happens — nothing currently detects it, so it has never been
  counted. **Do not assume it is rare because it was noticed twice in one day; it was noticed
  because the operator read the output, which is how all eleven others were found.**
  Options, none picked — `CLAUDE.md` §6:
  - a. Accept and document. Claim-level verification is a research problem, not a validator.
  - b. Constrain the prompt to one sentence per source note, so a sentence cannot fuse two.
  - c. Add an entity-pair check: flag a sentence whose named entities never co-occur in any
    single source article. Cheap, no model, catches exactly this fusion shape.
  - d. Second-pass LLM check of each sentence against the source notes. Doubles an already
    5–9-minute run.
  `[INFERRED]` (c) is the one to cost first — it is the only option that is mechanical,
  testable offline against the two captured briefs, and consistent with this project's
  record that bounding structure beats classifying meaning (`SESSION.md` §11).
  - Proof:

- [ ] **P6. `_drop_leading_stopword` no longer affects any verdict.** Found 2026-08-13 while
  writing `tests/test_validate.py`, **by mutation testing rather than by reading code**.
  `[VERIFIED]` Disabling it changes no pass/fail outcome in the suite.
  `[INFERRED]` It cannot, by construction. It strips only the **first** word of a name, and
  `_grounded` returns True whenever the **last** word appears in the sources. Stripping the
  first word never changes the last, so a grounded name stays grounded and an ungrounded one
  stays ungrounded.
  `[VERIFIED]` The cause is a dated overlap: `c522d8e` added the strip on 2026-08-11 07:50,
  and `7323396` added last-word grounding on 2026-08-12 01:54. **The second made the first
  redundant one day later.** Both were fixing the same live symptom — a correct summary
  rejected over a name the sources did contain — so neither commit had reason to look at the
  other.
  `[VERIFIED]` What survives is diagnostic: the *reported* name. A log reading
  `invented names: Portland` points at the real problem; `In Portland` sends the reader after
  a preposition. `test_sentence_initial_preposition_is_stripped_from_the_reported_name`
  asserts exactly that and nothing more.
  - a. Keep it, as log-quality only. Rename it and say so in its docstring.
  - b. Delete it and accept prepositions in the drop log.
  `[INFERRED]` (a). It is nine lines and the log is the only diagnosis available after an
  unattended run — `SESSION.md` §8 records eleven bugs found by reading output. But the
  docstring currently claims a correctness role it does not have, and that is the part worth
  fixing either way.
  `[INFERRED]` **The general lesson is the bigger one:** two mechanisms fixed the same
  symptom a day apart and the overlap was invisible until something tried to break each one
  individually. Reading the code did not reveal it; reading the code is what wrote it.
  - Proof:

- [ ] **P7. `priority.py`'s word-boundary comment claims a benefit it does not deliver.**
  Found 2026-08-13 while writing `tests/test_priority.py`.
  `[VERIFIED]` The comment at `processing/priority.py:100` reads: *"Substring matching would
  classify 'signs of improvement' as a signing and 'designated' as containing 'sign'."* Only
  the second half holds. `classify()` on the three real shapes:

  | Title | Tier |
  |---|---|
  | `Curry shows signs of improvement in return` | **high** ← the comment says this is prevented |
  | `Coach praises the designated starter` | medium ✓ |
  | `Jokic signs a max extension` | high ✓ |

  `[INFERRED]` Word-boundary matching cannot help here, because `signs` **is** a standalone
  word in "shows signs of improvement". The comment describes a protection that does not
  exist, which is the documentation failure `CLAUDE.md` §0 exists to prevent — in a comment
  rather than a handoff document, but the same kind.
  Two things to decide, and they are separable:
  - a. Fix the comment only. The misclassification is one article ranked high that should be
    medium; `[INFERRED]` cheap and low-risk.
  - b. Also narrow the rule — drop bare `signs`/`signed` and require a roster context.
    `[INFERRED]` Risky: this project's record is that narrowing keyword rules produces
    invisible false negatives (P3, twice).
  `[INFERRED]` (a). The comment is wrong and should be corrected regardless; the ranking cost
  is one story ordered too high in a list nothing is dropped from, which is the cheapest
  possible error here.
  - Proof:

- [ ] **P8. ADR-005's headline measurement cannot be reproduced from this repository.**
  Found 2026-08-13 while writing `tests/test_dedup.py`. **The decision is not in doubt; the
  number is not checkable.**
  `[VERIFIED]` `processing/dedup.py:38` and `SESSION.md` §5 both record **612 real
  cross-source pairs (17 ESPN × 36 CBS), highest similarity 0.439.** Re-measured from the
  committed fixtures: **540 pairs (15 ESPN × 36 CBS), highest similarity 0.425.** The ESPN
  fixture holds 15 items — `conftest.py` says so and `TASKS.md` H11 already records that a
  live fetch returned 16 against the fixture's 15 — so the 612 figure came from a **live**
  fetch of 17 and no artefact in the repo reproduces it.
  `[INFERRED]` The conclusion is unchanged and slightly **stronger**: 0.425 is further from
  the 0.85 threshold than 0.439. Nothing about ADR-005 needs revisiting.
  `[INFERRED]` What needs fixing is that a load-bearing measurement was recorded from data
  that was never committed, so it could not be re-checked until something tried to. That is
  the same shape as the `cdn.nba.com` failure in `OPERATING_RULES.md` §2 — a number carried
  forward as fact — merely benign this time.
  - a. Correct both figures in place to the reproducible ones, with a dated note that the
    original was measured live. `[INFERRED]` Preferred: `OPERATING_RULES.md` §2 requires
    correction in place with a strikethrough, never silent deletion.
  - b. Re-capture a 17-item ESPN fixture so the original number reproduces. `[INFERRED]` Not
    possible — the feed has moved on; those 17 items are gone.
  `[VERIFIED]` `test_real_cross_source_pairs_do_not_collapse` now re-measures this on every
  run, so whichever number the documents carry, the *threshold* is guarded by live
  arithmetic rather than by prose.
  - Proof:

---

## LOW — deferred; each requires a trigger condition

- [ ] **L1. NFL sources (`nflreadpy`).** Trigger: NBA path stable across several real runs.
  `[INFERRED]` **This trigger has now fired** — the NBA path has run unattended on cron for
  days. Held anyway behind P1: adding a second league doubles the surface of nine untested
  processing modules. PRD D3 keeps v1.0.0 NBA-only.
- [ ] **L2. Semantic dedup.** Trigger: a captured real near-duplicate pair that
  `SequenceMatcher` missed, saved as a fixture (ADR-005). `[VERIFIED]` The trigger was
  tested and did **not** fire: 612 real cross-source pairs, highest similarity 0.439.
  `processing/cluster.py` solved the actual problem — same story, different words —
  by shared rare names, with no model.
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
- [ ] **L12. Write a "what went wrong with v1" post-mortem.** `README.md` exists. The
  post-mortem does not; it is `[INFERRED]` the most valuable thing in the repo for a
  portfolio, and the material for it is already written — `docs/AUDIT.md`, ADR-011, and
  `SESSION.md` §8/§11.
- [ ] **L13. Lower setup friction for non-technical users** (hosted config UI, a managed
  key-proxy, one-click deploy — undecided, do not design yet). Trigger: v1 works for the
  operator and someone without his technical background wants to run it. Operator flagged
  2026-08-03 that `.env`/API-key setup (e.g. ADR-003's `balldontlie.io` key) is acceptable
  for now but not the intended final shape — see `SESSION.md` §9 Q10.

---

## Where tasks live now

`[VERIFIED]` Seventeen issues, fifteen open (#6 and #14 closed), at
https://github.com/AlphaNerdFx/SportWire/issues. **This file owns the plan; GitHub owns the
queue.** When they disagree, check the issue — it is likelier to be current.

Standing items not otherwise listed above:

| # | Item | State |
|---|---|---|
| 1 | 14-day observation run | `[VERIFIED]` Running. **The clock resets on every behaviour change**, and 2026-08-12 changed the prompt. |
| 5 | Capture a live/scheduled game fixture | Blocked until the season starts, **after 2026-09-30**. Every game ever captured reads `Final`. |
| 11 | Non-technical setup | Deferred (L13). |
| 15 | Tests for `processing/` | **P1 above. The priority.** |

