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

## RELEASES

Tags are `vMAJOR.MINOR.PATCH`. A tag is annotated (`git tag -a -F <file>`), and **its message
becomes the GitHub Release notes** — there is one source of truth, not two. Pushing a `v*` tag
runs `make check` first and publishes only if it passes; `[INFERRED]` a tag on a red commit is
a claim, published under a version number, that something works.

Before tagging: bump `version` in `pyproject.toml` to match. `release.yml` refuses to publish
when the two disagree.

- [x] **v0.1.0** — 2026-08-14, first tagged pre-release.
  - Proof: <https://github.com/AlphaNerdFx/SportWire/releases/tag/v0.1.0>, marked
    **pre-release**. `[VERIFIED]` Both workflows green on the tag: `CI` and `Release`.
  - Proof: `make check` → **126 passed, 1 xfailed**, links resolving across repo *and* wiki.
  - The notes state what works, what is unproven (`[UNKNOWN]` in-season payloads L-3, and the
    summariser's pass rate) and what is known-broken (P5, with the delivered example). `[INFERRED]`
    A pre-release that hides its limits is the failure this repository was founded on.
  - `[VERIFIED]` **The first publish shipped the wrong notes, and the guard did not catch it.**
    `actions/checkout` materialises a tag as a **lightweight** pointer, so the annotated object
    was absent and `git tag --format='%(contents)'` fell back to the *commit* message. The
    guard only rejected *empty* notes, so it passed while validating the wrong thing.
    **Fixed:** the workflow re-fetches the tag and asserts `git cat-file -t` returns `tag`,
    which only an annotated tag does. The v0.1.0 notes were corrected in place.
  - `[INFERRED]` Worth naming: that is the same shape as the legacy suite passing in 3.32s —
    a check that reports success it has not earned. It is now the third instance this week,
    after the hollow tests and the mutation that silently failed to apply.

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
  - [x] **`cluster.py`** — 2026-08-13, commit pending. 14 tests.
    - Proof: `make check` → **84 passed, 1 xfailed**.
    - Proof — `[VERIFIED]` mutation results, after two rounds:

      | Mutation | Result |
      |---|---|
      | `MIN_SHARED_NAMES` 2 → 1 | 1 failed |
      | frequency ceiling effectively removed | 2 failed *(caught only after a fix — see below)* |
      | cap counts the last member, not the leader | 1 failed |
      | r/nba's special cap removed | 1 failed |
      | cap stops logging what it dropped | 1 failed |
      | group fingerprint stops widening | 1 failed *(uncovered on the first round)* |

    - `[VERIFIED]` **Two defects in the tests, both found by mutation, neither by review.**
      `test_a_name_appearing_everywhere_does_not_group` shared only *one* common name, so it
      was held up by `MIN_SHARED_NAMES` and passed with the frequency ceiling removed
      entirely — it did not test the mechanism its name credits. And nothing at all covered
      the fingerprint-widening line, so a story that develops vocabulary across posts could
      fragment into two clusters with no test objecting.
    - `[INFERRED]` That is now **four** fake or missing tests caught this way across three
      modules. The pattern is consistent: a test written from the same reasoning as the code
      inherits the code's blind spots, and only trying to break it reveals that.
  - [x] **`highlights.py`** — 2026-08-13, commit pending. 20 tests.
    - Proof: `make check` → **106 passed, 1 xfailed**.
    - Proof — `[VERIFIED]` mutation results, all six caught:

      | Mutation | Result |
      |---|---|
      | blowout threshold removed | 3 failed |
      | closest-finish threshold removed | 7 failed |
      | one-slot rule removed | 4 failed |
      | wire-to-wire band removed | 3 failed |
      | comebacks never detected | 3 failed |
      | only the first overtime game reported | 1 failed |

    - `[VERIFIED]` **Three of my own tests were wrong on the first run, and the code was
      right.** Each constructed game accidentally qualified for an *earlier* category that
      claimed it — an "ordinary" 14-point win was inside the `wire_to_wire` band, and a
      `second_half_takeover` case was also a 20-point comeback. `[INFERRED]` With eight
      categories and a precedence order, constructing a game that exercises exactly one is
      genuinely hard, which is itself an argument for the tests existing.
    - `[VERIFIED]` One conftest error, caught by the full suite rather than the module's own:
      adding scores to `make_game`'s derived `game_id` made one game at half time and at full
      time read as two different games, breaking `test_a_game_whose_score_changed_is_not_a_duplicate`.
      `game_id` identifies a game; `state_hash` distinguishes its states. Reverted.
  - [x] **`summarize.py`** — 2026-08-13, commit pending. 20 tests, **no model and no
    network**. The largest module in `processing/` and the least verifiable — what
    `mistral:7b` writes on a given night cannot be asserted — but both recorded bugs here
    were in the machinery around it, and that is fully testable.
    - `[VERIFIED]` The `Summarizer` ABC is what makes this possible: `_summarise` is the only
      abstract piece, so a stub subclass exercises the retry-and-validate loop with no Ollama
      running. This is the `_fetch`/`fetch` pattern in a second place — H13 Q2 asked why that
      split exists and the answer did not land; these tests are what it buys.
    - Proof: `make check` → **126 passed, 1 xfailed**.
    - Proof — `[VERIFIED]` mutation results, all five caught:

      | Mutation | Result |
      |---|---|
      | give up on the first request failure (the 08-10 bug) | 1 failed |
      | `_tidy` flattens paragraphs again (the 08-12 bug) | 2 failed |
      | validation bypassed entirely | 3 failed |
      | chunking disabled | 1 failed |
      | note preamble no longer discarded | 1 failed |

    - `[VERIFIED]` The `_tidy` mutation **silently failed to apply on the first try** (shell
      escaping), and its "20 passed" was meaningless rather than reassuring. Re-run properly
      it fails 2 tests. `[INFERRED]` A mutation that does not apply looks exactly like a
      mutation the suite survived — worth asserting `s != before` in every mutation script,
      which is now done.

  **`processing/` is covered.** `[VERIFIED]` 7 of 8 modules have behaviour tests; the eighth,
  `openrouter.py`, is dormant until an API key exists and is not on `SESSION.md` §8's list.

  - [ ] **Outside `processing/`, still uncovered** (all from `SESSION.md` §8): `storage/db.py`,
    `config/settings.py`, both RSS parsers, the Telegram message splitter.
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

- [x] **P4. Establish the summariser's actual pass rate.** (#17) **Closed 2026-08-26.**
  The rate is counted: 4 of 13 dated runs delivered prose (31%), 25% before the validator
  fixes and 50% after, 4 of 30 attempts accepted (13%). GitHub #17 closed with the table.
  `[INFERRED]` The condition was "the rate is a measured number", and it is. Whether that rate
  is *good enough* is a different question and belongs to GitHub #1, the fourteen-run soak.
  `[VERIFIED]` The "~84%" figure came from 3/5 on one sitting and is repeated in several
  places; two runs on 2026-08-13 went 0/3 then pass. `[UNKNOWN]` The real rate.
  Count validation outcomes across the soak from `logs/sportwire.log` rather than quoting
  a number from one sitting. `[VERIFIED]` Every occurrence in `main.py` and `SESSION.md`
  has been corrected to `[UNKNOWN]`; check ADR-012 has not been missed.

  **2026-08-16, from the log: the first end-to-end rate this task has ever had.**
  `[VERIFIED]` Counted from `logs/sportwire.log`, restricted to runs dated after `ec7bc3c`
  added the date to the log format. Six earlier runs are undated and remain uncountable.

  | run | outcome |
  |---|---|
  | 2026-08-15 00:00 | prose, attempt 2 |
  | 2026-08-15 08:00 | prose, attempt 1 |
  | 2026-08-15 16:00 | **fallback** |
  | 2026-08-16 00:00 | **fallback** |
  | 2026-08-16 16:00 | **fallback** |

  **2 of 5 delivered prose — 40% — and the last three consecutive runs all fell back.**

  **2026-08-17 — the operator asked to "revert back to what worked". There is nothing to
  revert to.** `[VERIFIED]` Every run in the log, with the names it was rejected for:

  | run | new articles | outcome | rejected for |
  |---|---|---|---|
  | 2026-08-14 16:00 | 81 | prose | — |
  | 2026-08-15 00:00 | 29 | prose | — |
  | 2026-08-15 08:00 | 48 | prose | — |
  | 2026-08-15 16:00 | 19 | **fallback** | Warriors, Lakers, `Hollywood Ending. Meanwhile` → P20 + sentence break |
  | 2026-08-16 00:00 | 17 | **fallback** | Kobe Bryant, Quentin Grimes |
  | 2026-08-16 16:00 | 46 | **fallback** | Klay Thompson, Kawhi Leonard |
  | 2026-08-17 00:00 | 12 | **fallback** | `Mike D'Antoni` → P22; Eastern/Western Conference → P23 |
  | 2026-08-17 08:00 | 23 | **fallback** | LeBron James, **Karl-Anthony Towns** |

  `[VERIFIED]` **Each fallback has a different cause, and no cause recurs once fixed.**
  `Golden State Warriors` and `Los Angeles Lakers` appeared on 2026-08-15 16:00 and never
  again after P20. `Mike D'Antoni` appeared on 2026-08-17 00:00 and never again after P22.
  There is no single commit whose reversion restores the prose runs; reverting would restore
  four already-retired bugs.

  ~~`[VERIFIED]` **The 08:00 fallback was the check working, not failing.** `Karl-Anthony
  Towns` appears **0 times** across all 127 live articles captured that day — as do `Towns`
  and `NBA TV`. The model invented a player on all three attempts.~~
  **Retracted 2026-08-18. This was wrong, and it was reported to the operator as fact.**
  `[VERIFIED]` The search was for "karl-anthony towns", "karl-anthony" and "towns", all of
  which are genuinely absent. It never looked for the abbreviation. That batch carries
  *"💍 KAT, Jordyn Woods tie the knot in Malibu"*, confirmed by reconstructing the 23 recorded
  ids. `Karl-Anthony Towns` was a **correct expansion of KAT**, so the 08:00 run was a false
  accusation after all, and it is P21 rather than a fabrication. `NBA TV` is unaffected and
  stays a genuine invention. `[INFERRED]` The lesson is narrower than "check harder": a name
  absent in full is not absent, because the feeds abbreviate.

  `[INFERRED]` The one variable that tracks the outcome is volume: the prose runs averaged
  **49** new articles, the five fallback runs **23**. Mid-August feeds are quiet, so each
  batch is thin and the model pads from its training prior — which is exactly the ADR-012
  failure. `[UNKNOWN]` Whether this is causal. It is a correlation over 8 runs with two
  exceptions in it (29 → prose, 46 → fallback), and it is the thing P4's soak must settle.

  **2026-08-25: the full count, which is what GitHub #17 asked for.**

  `[VERIFIED]` Every dated run in `logs/sportwire.log`, 13 of the 21 logged (the rest predate
  the date being added to the log format):

  | | runs | prose | rate |
  |---|---|---|---|
  | all dated runs | 13 | 4 | **31%** |
  | before the v0.1.3-v0.1.5 validator fixes | 8 | 2 | 25% |
  | after them | 4 | 2 | 50% |

  Per **attempt** rather than per run: 4 accepted of 30 attempts, 13%. Two of the four prose
  runs passed on attempt 1.

  `[VERIFIED]` **A single rate is the wrong shape for this number, and that is the finding.**
  The two post-fix fallbacks are not the same kind of event:

  - **2026-08-18 16:00** rejected `Toronto Raptors`, `Steve Ballmer`, `Commissioner Adam
    Silver` and `Collective Bargaining Agreement`. **All four were false accusations**, and
    all four causes have since been fixed (P32, P33, and the CBA vocabulary entry). That run
    would pass today.
  - **2026-08-19 00:00** rejected ten names, of which **nine were the model completing a Hall
    of Fame roster** from a "HOF predictions" story, and the tenth was corrected on 2026-08-25
    to also be right. That fallback was the check working exactly as designed.

  `[INFERRED]` So "pass rate" conflates two things that should be counted separately: how
  often the validator is **wrong** (a bug, and the number that has been falling), and how
  often the model **fabricates** (a model property, and the number the fallback exists for).
  A brief that falls back because the model invented seven Hall of Famers is a success, not a
  failure, and averaging it with a false accusation hides both.

  `[UNKNOWN]` Whether 50% post-fix holds. Four runs is not a rate either, and the honest
  reading is that the sample restarts every time a validator bug is fixed. GitHub #1, fourteen
  consecutive unattended days, is the measurement that settles it.

  **2026-08-18 00:00, the first scheduled run after P25, P26 and P27. Prose, on attempt 3.**
  `[VERIFIED]` The six-run fallback streak ends here. 15 new articles, 7 stories, and the
  batch is reconstructed exactly rather than guessed: `seen_articles` recorded 15 ids at
  `2026-08-17T16:04` UTC, all 15 matched against a capture taken minutes later.

  `[VERIFIED]` **Every rejection was a genuine fabrication, and that is the new part.** All
  seven names across attempts 1 and 2 occur **zero** times in that batch, in any spelling:
  `Zion Williamson`, `Brandon Ingram`, `Ben McLemore`, `Dennis Schröder`, `Pat Connaughton`,
  `PJ Tucker`, `Bobby Portis`. No false accusation in the run at all, which has not been true
  of any earlier logged run.

  `[VERIFIED]` **The model is completing rosters from team names**, which is ADR-012's
  substitution failure with a mechanism attached:

  | in the batch | invented from it |
  |---|---|
  | `Watford, Pels agree to 1-yr, $2.9M deal`, `Trendon Watford signs with the Pelicans` | Zion Williamson, Brandon Ingram, Ben McLemore |
  | `Bucks Reacts Survey: How many ex-Heat players should the Bucks start?` | Pat Connaughton, PJ Tucker, Bobby Portis |
  | `Report: Cavaliers actively searching to move key contributor` | Dennis Schröder |

  `[VERIFIED]` `Dennis Schröder` is worth singling out because it looks like a P22 diacritic
  failure and is not. He appears 3 times in full and 6 times by surname across the 104-article
  capture, but **0 times in this batch**: the Cavaliers traded him in the previous day's news,
  which was already delivered and deduplicated out. The model knew the team and supplied the
  player. `[INFERRED]` This is the same effect P4 recorded as `[UNKNOWN]` for `Klay Thompson`
  and `Kawhi Leonard` on 2026-08-16, and it is now confirmed with a reconstructed batch.

  `[INFERRED]` Retry works on this failure where it did not on the fixed-prior ones, because
  which roster the model reaches for varies between attempts. Attempt 1 invented Pelicans,
  attempt 2 invented Bucks, attempt 3 invented nobody.

  `[UNKNOWN]` The pass rate still. One run is one run, and this one needed all three attempts.

  `[VERIFIED]` **This retracts the "ordinary bad luck" reading recorded above.** That reading
  assumed roughly 87% end-to-end; three consecutive failures at that rate has a 0.2% chance.
  Whatever the real rate is, it is not 87%.

  `[VERIFIED]` **The transcribed benchmark is easier than production, not harder.** The
  reconstruction of the 00:00 batch scores ~11/12 while the run it was built from failed 3/3.
  The note above claiming the transcription is "harder… less source text" is wrong and should
  not be relied on. `[UNKNOWN]` Why — candidates are the story count (9 transcribed against 11
  in the 16:00 run) and summaries the brief truncated with an ellipsis.

  `[VERIFIED]` The 2026-08-16 16:00 run rejected `Klay Thompson` and `Kawhi Leonard` on all
  three attempts. `[UNKNOWN]` Whether those are genuine — both were *deduplicated out* of that
  batch after appearing on 2026-08-16 00:00, so the model may be completing a pattern from a
  topic rather than from its notes. Resolve by capturing the batch, not by reasoning.

  ~~`[VERIFIED]` **The schedule is irregular**: no 08:00 run exists on 2026-08-16, between the
  00:00 and 16:00 runs. That compounds the open `[UNKNOWN]` about what schedules these at
  all.~~ **Half right, and the open question is now closed.** `[VERIFIED]` 2026-08-16 via
  `crontab -l`: there is an **active** entry, and it is correct —

  ```
  0 */8 * * * cd "/mnt/c/DSC/Career/Projects/SportWire" && ./.venv/bin/python main.py >> ".../logs/sportwire.log" 2>&1
  ```

  A WSL path, not the Windows one; not commented out; appending to the log the runs appear in.
  `0 */8` fires at 00:00, 08:00 and 16:00, which matches every dated run exactly.
  **`HANDOVER.md` is wrong on this point** — it records the line as commented out with a
  Windows path and lists the scheduler as `[UNKNOWN]`. That document lives on the
  `worktree-handover-2026-08-15` branch and has not been merged; the operator fixed cron
  during the 2026-08-15 session, so the finding was already stale when it was written.

  `[INFERRED]` The missing 08:00 run on 2026-08-16 is therefore not a mystery: cron does not
  fire while the machine is asleep, which this file already noted as the reason the log could
  not be segmented by time. **The soak will have gaps, and a rate must be counted per run
  rather than assumed from elapsed days.**

  **2026-08-16: first controlled measurement, and it changes what P4 is about.**
  `[VERIFIED]` The three delivered runs either side of it: 08:00 accepted on attempt 1 of 3;
  16:00 and 00:00 both failed all three attempts and fell back to the headline list.

  `[VERIFIED]` Measured against `mistral:7b`, **single attempt, six trials per variant**, on
  the nine stories of the 2026-08-16 00:00 run transcribed from the delivered brief:

  | batch | passed |
  |---|---|
  | committed fixtures (76 articles → 9 stories) | **6 / 6** |
  | the real 00:00 batch | **3 / 6** |

  `[VERIFIED]` **The fixtures cannot measure this.** They pass six times out of six, so any
  fix A/B-ed against them shows no difference for the same reason a passing test on easy data
  shows nothing. A real failing batch has to be transcribed from the brief.

  `[VERIFIED]` **The dominant cause is wholesale fabrication, not a validator defect and not
  a prompt defect.** Across twelve trials the most-rejected names were `Phoenix Suns` (6),
  `Quentin Grimes` (4), `Boston Celtics` (3), `Houston Rockets` (2), `Julius Randle` (1) —
  teams and players with **no story in that batch at all**. The validator is right about
  every one of them.

  `[VERIFIED]` **A prompt fix was measured and rejected.** `SYSTEM_PROMPT` — the reduce step
  that writes the prose — forbids adding "scores, statistics, dates or outcomes" and never
  mentions names, while `NOTES_PROMPT` does say "keep names… exactly as given". Adding an
  explicit rule to write names exactly as the notes have them scored **3/6, identical to the
  3/6 without it**. Not shipped, on the P6 precedent: a change with no measured effect reads
  as protection it does not provide.

  `[VERIFIED]` **Two more hypotheses were tested on the same batch and both are closed.**

  *Shared state or concurrency between calls.* There is none. `main.py:178` already builds a
  fresh `OllamaSummarizer` per run; `_generate` posts `model`, `system`, `prompt`, `stream`
  and `options` and **never sends Ollama's `context` field**, which is the only mechanism that
  would carry state between requests; and `grep` for `Thread|asyncio|concurrent|Pool|await`
  across `main.py`, `processing/`, `ingestion/` and `delivery/` returns nothing but the word
  "Thread" inside a docstring. Instantiating per delivery is already what happens.

  *Temperature.* Measured at ten trials per setting, single attempt:

  | temperature | passed |
  |---|---|
  | 0.0 | **0 / 10** |
  | **0.3 — shipped** | **5 / 10** |
  | 0.6 | 4 / 10 |
  | 0.9 | 3 / 10 |

  `[VERIFIED]` **0.0 is catastrophic, and the reason matters**: `Quentin Grimes` was invented
  on **all ten** trials. A deterministic model reproduces the identical fabrication every
  attempt, so the retry loop cannot help — which is the mechanism `summarize.py:61` already
  recorded for `Ayo Dosunmu`, now measured. **Retry works only because sampling varies**, so
  the temperature cannot be lowered to buy accuracy. Raising it is also worse. The shipped
  value is at the optimum of those tested; nothing to change.

  `[VERIFIED]` **Local models are exhausted.** `llama3.2:3b` scored **0 / 6** on this batch.
  `mistral:7b` sits near 50% across three independent samples (3/6, 5/6, 5/10).

  `[VERIFIED]` **Six trials is too few to compare anything.** The same model on the same batch
  scored 3/6 and then 5/6. The earlier prompt A/B in this entry — 3/6 versus 3/6 — is within
  that noise, so it establishes "no large effect" and not "no effect".

  `[VERIFIED]` **A retry-feedback mechanism was built, measured and reverted** (`3042962`,
  reverted in `8f89e02`). Telling attempt 2 which names attempt 1 invented is sound in theory
  — every attempt otherwise receives a byte-identical prompt — but produced no effect:

  | measurement | with feedback | without |
  |---|---|---|
  | end-to-end, 3 attempts | 10/10 | 10/10 |
  | end-to-end, 3 attempts | 11/12 | **12/12** |
  | attempt 2 succeeding after attempt 1 failed | 2/6 | 3/4 |

  **The most important number in this entry is a null one.** `[VERIFIED]` Attempt 1 is
  byte-identical in both arms by construction, since the avoid-list is empty until something
  is rejected — and it scored **6/12 and 8/12**. That is the same process sampled twice, so
  the noise floor is about ±2 in 12. No effect smaller than that is detectable at this sample
  size, and resolving one costs hours of local inference per arm.

  `[INFERRED]` **The benchmark does not reproduce the failure it was built from, and this
  reframes P4.** The real 00:00 run failed all three attempts; its reconstruction succeeds
  roughly 11 times in 12 with no change at all. At ~50% per attempt, three consecutive
  failures has a ~12.5% chance, so **the two fallback briefs the operator saw are consistent
  with ordinary bad luck rather than a reliably hard batch.** Before concluding the model is
  the constraint, count fallbacks across a real soak: three runs is not a rate, and this entry
  should not be read as one.

  `[INFERRED]` This is the outcome `ROADMAP.md` §3 anticipated for v0.2.0 — *"if it does not,
  the honest outcome is an ADR on model choice, not more validator tuning."* Every free lever
  has now been measured and none moved. `config/settings.py:41` already defaults the hosted
  path to `google/gemma-4-31b-it:free`, so a larger model costs an API key rather than money
  (C2). `[VERIFIED]` No key is configured today, so the hosted path is untested here.
  `[INFERRED]` **But the soak comes first** — switching models on three runs of evidence would
  repeat the "~84% from one sitting" mistake this task exists to correct.

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

- [x] **P5. The validator grounds entities, not claims — a bug class not in `SESSION.md` §8.**
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

  **2026-08-18: a third delivered instance, reported by the operator, and (c) is now costed.**

  `[VERIFIED]` The 00:00 brief reached the phone saying *"The Pelicans, who are welcoming back
  star point guard Damian Lillard following his trade from Portland"*. There was no such trade.
  The batch's only Lillard article is *"Blazers offseason recap and early season preview:
  Lillard is back but questions remain"*, whose body reads *"With noise outside the hardwood
  growing in Portland, how will the Blazers respond?"*. Lillard is back with Portland. The
  model moved him to New Orleans and invented a trade.

  `[VERIFIED]` Counted in that batch: `lillard` 1, `pelicans` 3, `portland` 1, `new orleans` 0,
  `trade` 0, `damian` 0. The validator extracted exactly two names from the sentence,
  `Pelicans` and `Damian Lillard`, and grounded both. Both are real and both are present. Only
  the relationship is invented, which is this task restated.

  `[VERIFIED]` **Today's P25, P26 and P27 changes did not cause this.** The same sentence passes
  under the 2026-08-14 rules, tested by restoring last-word-only grounding, the old index, no
  alias table and no colon separator. It is a pre-existing gap, not something the loosening let
  through.

  `[VERIFIED]` **Option (c) works, with one correction to how it must be built.** Keying on
  every word pairwise flags true sentences, because `New Orleans` and `Portland Trail Blazers`
  are expansions the sources never write in full. Keying **one word per entity, its last word**,
  and reading source entities with a one-word scanner so a bare `Pelicans` counts:

  | | result |
  |---|---|
  | the false Lillard sentence | **flagged** |
  | four true sentences from the same brief | all pass |
  | sentences flagged in a separately accepted 11-sentence brief | **0 of 11** |

  `[UNKNOWN]` The real false-accusation rate. The 0 of 11 used a 103-article superset as the
  source rather than that brief's true 12-story batch, and a superset makes co-occurrence easier,
  so it understates flagging. Settle it by capturing batch and accepted summary together over
  several runs before shipping.

  `[VERIFIED]` **The decision this forces, stated plainly because it is a trade and not a fix.**
  Option (c) rejects the sentence, so it rejects the whole summary, so the 00:00 run would have
  fallen back to the headline list on all three attempts. The operator asked on 2026-08-17 not
  to see the headline format at all. Those two wants are in direct opposition here: entity-only
  checking delivers prose more often and lets a false relationship through occasionally, while
  pair checking catches the false relationship and falls back more often. `[INFERRED]` No
  amount of measurement dissolves that; it is a choice about which error is worse.

  **Resolved 2026-08-18: mark, do not reject.** The operator chose visibility over a stricter
  check. `unsupported_sentences` in `processing/validate.py` is additive and never touches
  `is_safe`, the brief appends a mark to a flagged sentence plus one legend line, and `main.py`
  logs the sentences so they can be counted over a soak. Commits `f966313`, `2bd436e`,
  `535fbfb`, `90ed113`.

  `[VERIFIED]` On the 00:00 brief, reconstructed from the database: 1 of 5 sentences flagged,
  and it is the false one. On a separately accepted 11-sentence brief: 0 flagged.

  `[VERIFIED]` **Two wrong versions were built first, and both were caught only by running the
  real string rather than a tidied one.** Reading source entities with grounding's two-word
  rule contributes no `pelicans` from "signs with the Pelicans", where it is a lone capitalised
  word, so the true Watford sentence was flagged. Then the opener "In NBA news" extracts as
  `In NBA` and keys on `nba`, which shares no article with `watford`, flagging it again. The
  first measurement reported 5 of 5 correct and was **wrong**, because it was run on sentences
  with the opener already stripped.

  `[VERIFIED]` Mutation-tested four ways, all caught: two-word source scanner, no opener trim,
  no vocabulary filter, and never flagging.

  `[UNKNOWN]` The false-flag rate over time. One brief flagged correctly and one flagged
  nothing is not a rate. The log now names every flagged sentence, so a soak can count it.

  **The xfail stays xfail, and that is correct rather than unfinished.** It asserts that a
  sentence asserting a false relationship is *rejected*. The operator chose marking over
  rejecting, so that assertion is now a description of a road not taken rather than a pending
  fix. `[INFERRED]` Deleting it would erase the record of the choice; leaving it as a declared
  expected failure keeps the alternative visible, which is what `OPERATING_RULES.md` §4 means
  by not hiding a known gap. If the trade is ever revisited, that test is the specification.
  - Proof:

- [x] **P6. `_drop_leading_stopword` no longer affects any verdict.** Found 2026-08-13 while
  writing `tests/test_validate.py`, **by mutation testing rather than by reading code**.
  **Resolved as a decision, box reconciled 2026-08-18:** the mechanism is kept for its
  diagnostic value and that purpose is asserted in
  `test_sentence_initial_preposition_is_stripped_from_the_reported_name`. Nothing is pending.
  `[INFERRED]` It has since earned its keep twice over as a *name*, not a mechanism: P6 is the
  rule invoked to delete a redundant normalisation (`31a2eb8`) and a dead reporter-tag guard
  in `newsworthy.py` (P34).
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

- [x] **P9. `group_related` silently groups nothing in a batch under 25 articles.**
  Found 2026-08-13 by testing. **The most consequential of the four findings this session,
  because the degradation is invisible and the margin is thin.**

  **Closed 2026-08-16, in two stages.** `[VERIFIED]` Stage one was option (c) on 2026-08-13:
  the behaviour stood and a warning was added, asserted by
  `test_a_batch_too_small_to_group_says_so`. `[VERIFIED]` Stage two removed the condition
  itself — P19's `MIN_RARITY_CEILING` floor in `95e7c2e` means the ceiling can no longer fall
  below 5, so at default settings the warning cannot fire and small batches group normally.
  The reasoning recorded below for *not* raising the ceiling — that it risked a false merge —
  was measured under P19 and did not hold: zero false merges at any batch size tested.
  `[INFERRED]` Left as a closed entry rather than deleted, because the option (a)/(b)/(c)
  analysis below is what P19 eventually had to overturn, and the overturning is the lesson.
  `[VERIFIED]` `ceiling = max(1, int(len(articles) * MAX_NAME_FREQUENCY))` with
  `MAX_NAME_FREQUENCY = 0.08` evaluates to **1** for any batch below 25. A name shared by two
  articles has document frequency 2, which exceeds that ceiling, so it is discarded as
  non-distinctive — and `MIN_SHARED_NAMES = 2` then cannot be satisfied by anything.
  `[VERIFIED]` Measured with the two real Kawhi/Daktronics titles from the module's own
  docstring: **not merged at 24 articles, merged at 25.**
  `[VERIFIED]` It has not bitten yet — `logs/sportwire.log` shows 27 and 64 articles past
  dedup on 2026-08-13. `[INFERRED]` **27 is one quiet day away from 24.** When it happens the
  brief carries duplicate coverage of one story, `limit_per_source` counts those duplicates
  as separate stories and spends the cap on them, and **no log line says any of it** — the
  "grouped N articles into M stories" line only fires when something merged.
  - a. Floor the ceiling at 2: `max(2, ...)`. `[INFERRED]` Smallest change, restores grouping
    at any batch size. Risk: in a 10-article batch a name in 2 articles is 20% frequency,
    which is not rare, so small batches could over-merge.
  - b. Make the ceiling absolute rather than proportional below some size.
  - c. Log when grouping is skipped for this reason, and change nothing else. `[INFERRED]`
    Turns an invisible failure into a visible one, which is this project's recurring remedy
    (`SESSION.md` §8: nine of eleven bugs found by reading output).
  - d. Accept and document.
  `[INFERRED]` (c) first, then measure. This project's record is that making a failure
  visible beats guessing at a threshold — and unlike (a) it cannot cause a false merge, which
  is the expensive error here since a merged story is one the brief never reports separately.

  **Operator chose (c) on 2026-08-13. Done — commit pending.**
  - `[VERIFIED]` `group_related` now emits a `WARNING` when `ceiling < min_shared_names`,
    naming the batch size, the ceiling and the requirement. **Behaviour is unchanged**; only
    the silence is fixed.
  - Proof: `make check` → **86 passed, 1 xfailed**.
  - Proof — `[VERIFIED]` mutation: replacing the guard condition with `if False:` fails
    `test_a_batch_too_small_to_group_says_so` and nothing else.
  - Proof — the complement is asserted too: `test_a_batch_large_enough_to_group_stays_quiet`.
    `[INFERRED]` A warning that fires on every normal run is one nobody reads, which would
    reproduce the original problem in a louder form.
  - **What to watch:** whether this line ever appears in `logs/sportwire.log`. If it does, the
    threshold question (options a/b) becomes real and there will be data to settle it with.
    `[VERIFIED]` The dated log format from `ec7bc3c` makes that countable.

- [ ] **P10. A superlative category can be silently emptied by an earlier one.** Found
  2026-08-13 by testing. **User-facing, and it happens on the committed fixture.**
  `[VERIFIED]` `_CATEGORY_ORDER` puts `biggest_period` before `largest_margin`, and a game is
  reported once under its first matching category. On the real 2026-01-15 slate, Dallas beat
  Utah by **22 — the widest margin of the night — with a 43-point quarter**, so
  `biggest_period` claims it. `largest_margin` then has no candidate and is **not reassigned
  to the second-widest game**, so the brief never mentions the biggest win at all.
  `[VERIFIED]` `TASKS.md` H11 records the 2026-08-05 delivered brief as containing
  *"Biggest win — Dallas Mavericks by 22"*. It no longer would. The category order changed
  when `biggest_period`, `wire_to_wire` and `second_half_takeover` were added in the M band,
  and nothing flagged that an existing line had been displaced.
  `[INFERRED]` The same shadowing applies to `highest_scoring`, which the Dallas game also
  tops (266 points) on that slate. Two of eight categories produce nothing because one game
  holds three superlatives.
  - a. After claiming, re-run each superlative over the *unclaimed* games. `[INFERRED]` Most
    faithful to "the biggest win of the night", and makes the brief richer on exactly the
    nights that have a standout game. Costs one more pass.
  - b. Reorder `_CATEGORY_ORDER` so margin outranks period. `[INFERRED]` Cheap, but only
    moves which category goes silent.
  - c. Allow a game to hold more than one category. `[INFERRED]` Rejected by the existing
    design on purpose — one game would occupy several slots in a short brief.
  - d. Accept and document.
  `[INFERRED]` (a). It is the only option that keeps every category meaningful, and the
  "report once" rule it must respect is already expressed by the `claimed` set — the change
  is where the superlatives are computed, not what they mean.

  **Operator chose (a) on 2026-08-13. Done — commit pending.**
  - `[VERIFIED]` `find_notable_games` now recomputes `available` before each category, so a
    superlative is measured over the games still unclaimed. Every-instance and superlative
    categories are separated into `_EVERY_INSTANCE` and `_SUPERLATIVES`, which the old code
    expressed only in comments.
  - **`[VERIFIED]` Implementing (a) exposed a second problem the option did not anticipate,
    and it was NOT shipped silently.** Reassigning a ranked category makes its label false:
    `_CATEGORY_LABELS` said *"Biggest win"*, so the brief would have read **"Biggest win —
    Oklahoma City Thunder by 20"** on a slate containing Dallas's 22-point win, and
    **"Highest scoring — 252"** against Dallas/Utah's 266. `[INFERRED]` That is strictly worse
    than the bug being fixed: the old behaviour *omitted* a line, this would have *stated an
    untruth*, which is the failure class `processing/validate.py` exists to prevent.
  - **Resolved with the operator:** the four ranked labels drop their superlative claim —
    `Closest finish → Close finish`, `Biggest quarter → Big quarter`,
    `Biggest win → Big win`, `Highest scoring → High scoring`. The `_describe` clauses were
    already factual ("Thunder by 20", "252 combined points") and are unchanged. `[INFERRED]`
    A brief that understates is better than one that overstates.
  - Proof — `[VERIFIED]` the real 2026-01-15 slate goes from **four** notable lines to
    **six**; `largest_margin` and `highest_scoring` had both been produced-then-discarded
    because Dallas held all three records.
  - Proof — snapshot diff reviewed and **approved by the operator** before re-recording, per
    `OPERATING_RULES.md` §4:

    ```diff
    - Closest finish — decided by 3          + Close finish — decided by 3
    - Biggest quarter — a 43-point quarter   + Big quarter — a 43-point quarter
    + Big win — Oklahoma City Thunder by 20
    + High scoring — 252 combined points
    ```

  - Proof: `make check` → **106 passed, 1 xfailed**.

- [x] **P11. A summary accepted on the first attempt logged nothing.** Found 2026-08-14 by
  reading the log of a live run. `[VERIFIED]` `summarize.py` guarded the acceptance line
  behind `if attempt > 1`, so the 16:00 run read `summarising 12 stories` then, 36 seconds
  later, `delivered 1/1 messages` — with no verdict between. That is indistinguishable from
  a summariser that was never called.
  `[INFERRED]` It corrupts P4 in the direction that flatters the model: the measured floor of
  **2 accepted / 19 attempts** could not have counted a single attempt-1 success, because
  none was ever written down. Rejections logged, fallbacks logged, only the cheapest success
  was silent.
  **Fixed in `4c7c4ed`** — every acceptance now logs `accepted on attempt N of M`.
  - Proof — mutation: restoring the `if attempt > 1` guard fails
    `test_a_valid_summary_is_returned_on_the_first_attempt`, and the diff was asserted to
    have applied before the run was trusted.
  - **What to watch:** P4 is now countable for the first time. Do not quote a pass rate until
    ~2 weeks of runs have accumulated under this commit, and do not restate 84%.

- [x] **P12. A name blended from two real players passed validation and reached the phone.**
  Found 2026-08-14 in the delivered 16:00 brief. **User-facing.**
  `[VERIFIED]` The brief said *"January will see Giannis Antetokounmpo and Jayson Brown
  reunions."* There is no Jayson Brown — the model fused **Jayson Tatum** and **Jaylen
  Brown**, who share the feed because they were teammates. Last-word grounding accepted it on
  "Brown". It passed on **attempt 1**.
  `[VERIFIED]` `validate.py`'s own docstring predicted this and dismissed it: *"The failure
  mode it would miss is a wrong first name beside a right surname, which is a smaller error
  than inventing a person."* `[INFERRED]` It is not smaller — it **is** inventing a person,
  and unlike "Joe Dumars" it inherits the credibility of two real ones.
  `[VERIFIED]` Measured on the committed fixtures: the old rule caught **0 of 5,442**
  synthetic blends. Not an edge case — every blend was a guaranteed pass.
  - a. Require the whole phrase. `[VERIFIED]` Rejected — this is the every-word rule that
    threw away three correct summaries on 2026-08-11.
  - b. Subset-or-superset of a single source name, applied as a **refutation** on top of the
    existing ladder. `[INFERRED]` Separates the classes exactly: every legitimate case is one
    source name expanded or contracted, while a blend is drawn from two and is a subset of
    neither.
  - c. A first-name check only. `[INFERRED]` Narrower, and the third one-case-at-a-time
    narrowing of this module — the pattern `SESSION.md` §11 warns about.
  - d. Accept and document.
  `[INFERRED]` (b).

  **Operator chose (b) on 2026-08-14. Done — `f1a38a6`.**
  - Proof — `[VERIFIED]` against the committed fixtures (76 articles, 88 two-word source
    names): real source names newly rejected **0 of 88**; blends caught **0 → 5,402 of
    5,442 (99.3%)**. The 40 escapes are tokenizer fragments (`chris p`, `kawhi le`), not
    plausible names.
  - Proof — mutation, five mutations each asserted to have applied: never-refute (killed, 2
    tests), `any` for `all` (killed), refute-before-verbatim (killed), index-the-joined-blob
    (killed, 89 verdicts differ), superset-only (killed).
  - **`[VERIFIED]` Three of the five survived the first pass and two of my tests asserted
    nothing** — both were acquitted by the verbatim rule before ever reaching the code under
    test. `SESSION.md` §11 names this pattern; it recurred unprompted, in a session that
    began by reading the warning about it.
  - `[VERIFIED]` Hyphen splitting was written into `_name_words` and **removed before it
    shipped**: it changed 0 of 5,530 verdicts and cannot, because `_PROPER_NAME` truncates
    "Karl-Anthony" to "Anthony" before `_name_words` sees it. `[INFERRED]` This re-diagnoses
    the 2026-08-11 "Anthony Towns" bug — the model was not shortening a hyphenated first
    name, the **validator** was truncating it and then failing to ground its own truncation.

- [x] **P13. `_PROPER_NAME` cannot see a camelCase name, so LeBron James has never been
  validated.** Found 2026-08-14 while probing the tokenizer for P12. **Fixed in `fca4298`**
  by asking Python what a capital letter is instead of listing them; proof is in this entry.
  `[VERIFIED]` The checkbox said `- [ ]` and the header said "Open — needs a decision" for
  two days after the fix shipped, which is why `ROADMAP.md` §5 warns that the open count here
  cannot be trusted mechanically. Reconciled 2026-08-16.
  `[VERIFIED]` `_PROPER_NAME.findall("LeBron James attended the game.")` returns `[]`, and so
  does `"DeMar DeRozan scored 30 points."` The pattern is anchored with `\b`, and there is no
  word boundary inside `LeBron` — "e" and "B" are both word characters — so no match can
  start at the capital.
  `[VERIFIED]` All 5 camelCase tokens in the committed fixtures are unmatchable: `DeMar`,
  `DeRozan`, `LeBron`, plus two junk tokens. `[VERIFIED]` The 2026-08-14 16:00 run's drop log
  alone carried **9** lines naming LeBron (`grep -c` on the dated run), so this is
  live, not theoretical.
  `[INFERRED]` **Consequence: any sentence whose only proper names are camelCase is delivered
  unexamined.** The model can assert anything about LeBron James, DeMar DeRozan, LaMelo Ball,
  De'Aaron Fox or Shai Gilgeous-Alexander and the validator has no opinion. This is a
  *coverage* hole, not a grounding hole — different from P12, which was a wrong verdict.
  `[VERIFIED]` A related truncation: `"Shai Gilgeous-Alexander"` matches as `"Shai
  Gilgeous-"`, dropping the surname that identifies him.
  - a. Allow an internal capital in the token: extend the character class so `LeBron` matches
    as one word. `[INFERRED]` Smallest change, targets exactly the observed cause.
  - b. Match on Unicode title-case runs instead of `\b`-anchored ASCII.
  - c. Accept and document — record that camelCase names are unvalidated.
  `[UNKNOWN]` What (a) does to the false-accusation rate. **Measure against the fixtures
  before choosing**, the same way P12 was measured; a change to the extractor moves every
  verdict in the module, not just the camelCase ones.

  **Operator rejected all three on 2026-08-14** — *"it needs to be a solution that isn't
  hard coded"* — and was right: (a), (b) and the (a+) variant recommended here are all
  enumerated character ranges that go stale. **Done — `fca4298`, using neither.**
  - `[VERIFIED]` The measurement that settled it. (a), (a+) and (b) are **verdict-identical**
    — 0 differences across 5,530–5,600 shared cases — so the choice was never about
    detection. What separated them was which names they can see at all:

    | probe | current | (a) `A-Za-z` | (a+) `+Ā-ſ` | (b) `[^\W\d_]` | **shipped** |
    |---|---|---|---|---|---|
    | `LeBron James` | — | ✓ | ✓ | ✓ | ✓ |
    | `Luka Dončić` | `Luka Don` | `Luka Don` | ✓ | ✓ | ✓ |
    | `Kristaps Porziņģis` | `Kristaps Porzi` | `Kristaps Porzi` | ✓ | ✓ | ✓ |
    | `Alperen Şengün` | ✗ | ✗ | ✗ | ✗ | ✓ |

  - `[VERIFIED]` **`Ş` is what killed the range approach.** It is an uppercase letter outside
    `A-Z`, so every candidate — including the one recommended in this file — required
    `[A-Z]` to start a word and dropped him. `[INFERRED]` The next range fails on the next
    alphabet; `str.isupper` and `str.isalpha` read the Unicode database, which is maintained
    by someone else and updated without editing this repository.
  - Proof — `[VERIFIED]` fixtures: titles wrongly flagged **0/76** (unchanged), camelCase
    blends caught **0 → 4 of 4**, committed suite **181 passed, 1 xfailed** (unchanged).
  - `[VERIFIED]` **Trailing punctuation only, never leading**, and the same line caused both
    a false accusation and a missed fabrication: stripping the leading quote turned
    `a Sixer: "I'm still processing it"` into the invented name `Sixer I'm`, and the same
    erased boundary welded a run large enough to acquit the invented "LeBron Tatum" by
    superset. `[INFERRED]` Opening punctuation *is* the boundary evidence.
  - Proof — mutation, six mutations each asserted to have applied, **all killed**:
    strip-both, isalpha-for-isupper (22 tests), single-word-is-a-name (7),
    any-character-inside-a-word, apostrophe-not-in-a-name, no-end-of-text-flush.
  - `[VERIFIED]` Two of the six survived the first pass, both because a lowercase word broke
    the run before the mechanism under test was reached — the same diagnosis as P12's two
    survivors, in the same session.

- [ ] **P14. A blend whose surname is elsewhere a first name still passes.** Found 2026-08-14
  while measuring P13. **Open — not yet measured.**
  `[VERIFIED]` `"Luka Donovan posted a triple-double."` validates as **safe** against the
  committed fixtures, while `"Luka Donaldson"` is correctly rejected.
  `[INFERRED]` The cause is that P12's refutation only fires when a source name shares the
  candidate's **last** word. "Donovan" appears in the sources as a *first* name (Donovan
  Mitchell), so nothing in the index ends in "Donovan", nothing refutes it, and the
  every-word rule then grounds it because both words appear somewhere.
  `[UNKNOWN]` How large the class is. **Measure before proposing options** — count blends of
  the form (first name of X, first name of Y) against the fixtures, the way P12 was counted.
  `[INFERRED]` Not a regression: this class passed before P12 as well.

- [x] **P15. The subreddit's own weekly thread reached the brief as a news story.** Found
  2026-08-15 by the operator reading the delivered 00:00 brief. **User-facing.**
  `[VERIFIED]` The brief ended with *"the r/nba community thread for content creators to
  share NBA-related work continues every Friday"*. From a live fetch of
  `reddit.com/r/nba/.rss` this session, that is `Weekly Friday Self-Promotion and Fan Art
  Thread`, posted by `/u/NBA_MOD`.
  `[VERIFIED]` **Why nothing already caught it:** it carries no content-type tag, no
  retrospective phrase, and it is 5h old — so rules 0, 1 and 1b all pass it. And because the
  moderators post a **new** thread every Friday with a new `article_id`, cross-run dedup
  never suppresses it and the 168h age rule never reaches it. It recurs weekly, forever.
  - a. **Drop posts authored by a moderator account** — an *identity* signal, not a text
    pattern. **Chosen by the operator 2026-08-15. Done — `b38c80d`.**
  - b. Title patterns (`Thread`, `Self-Promotion`, `Fan Art`). `[VERIFIED]` Rejected — this
    is the approach `SESSION.md` §11 records failing twice on this exact feed.
  - c. (a) plus a rule for subreddit-meta posts by **ordinary** accounts. Deferred; see P16,
    which is the measurement the operator asked for before building it.
  - Proof — `[VERIFIED]` end to end over the live 25-item feed, through `RssNewsAdapter.parse`
    and `rejection_reason`: **23 kept, 2 dropped** — the moderator thread by rule 3, one
    `[Highlights]` post by the pre-existing tag rule. No other verdict changed.
  - Proof — mutation, five mutations each asserted to have applied, **four killed**:
    never-fire (4 tests), rule-3-unwired-from-`rejection_reason` (4), substring-for-suffix
    (1), missing-author-reads-as-moderator (1).
  - `[VERIFIED]` **The fifth survived, and it was dead code, not a weak test.** Replacing
    `author.strip().lstrip("/").removeprefix("u/").lower()` with `author.strip().lower()`
    killed nothing, because removing characters from the **front** of a string cannot change
    its **end** and the rule is a suffix test. Measured verdict-identical across 149 author
    shapes (36 real, the rest adversarial). Removed in `31a2eb8`. **This is P6's shape a
    second time** — code implying a protection it does not provide — and mutation caught it
    again where review did not.

- [ ] **P16. A subreddit-meta post from an ordinary account is not caught, and every
  mechanism measured costs more than it saves.** Opened 2026-08-15 as option (c) of P15.
  **Measured; recommendation is to hold. Needs a decision.**
  `[VERIFIED]` The live case: `/u/twistedlogicx`, *"Looking for old.reddit users interested
  in giving feedback and beta testing a redesign of the old subreddit theme"*, stickied and
  currently passing all four rules.
  `[VERIFIED]` **Its blast radius is one brief, not many.** It is in `seen_articles` as
  `r/nba:t3_1vjy1d3` seen `2026-08-10T00:00`, so cross-run exact-id dedup has suppressed it
  on every run since, and at 118h old rule 0 drops it outright in ~50h. Unlike P15's weekly
  thread, this class does not recur under a new id.
  Mechanisms measured this session, all rejected:
  - a. **Self-post vs link-post** (structural: does the entry's `[link]` anchor point back at
    its own comments page). `[VERIFIED]` **Inverted on this feed.** Live: 12 of 25 are
    self-posts, and they include the `[Charania]` Beal signing, the PTFO Kawhi scoop and the
    O'Connor contract report, while the *link* posts are 9 streamable.com and 3 YouTube clips.
    Dropping self-posts would delete the news and keep the highlights.
  - b. **Require the item to name a proper noun.** `[VERIFIED]` Drops **5 of 25 live** and 4
    of 25 fixture items to catch one meta post — including `[Jaylen Brown]`'s quote,
    `[Pablo Torre]`'s Clippers scoreboard scoop and the Westbrook/Zubac item. It is a
    whitelist, and `SESSION.md` §11 records a whitelist dropping the biggest story of the day.
  - c. **Fetch the subreddit's live moderator list** — the honest version of P15's handle
    heuristic. `[VERIFIED]` Not available: `reddit.com/r/nba/about/moderators.json` and
    `about.json` both returned **HTTP 403 Blocked** this session. The legitimate route is
    OAuth with a registered reddit app, which means operator signup and credentials in
    `.env`; a browser User-Agent was **not** tried, because working around a block is exactly
    what C3 forbids.
  - d. **Hold.** `[INFERRED]` **The recommendation.** The cost is bounded at one appearance
    per post by dedup, no available mechanism is cheaper than that, and every candidate above
    repeats a failure this project has already recorded.
  `[INFERRED]` **This may not be a separate class at all.** An account that redesigns the
  subreddit's theme and posts a stickied thread about it is almost certainly an r/nba
  moderator whose handle simply does not advertise it — in which case (c) is not a new rule,
  it is P15's rule with a real identity source instead of a suffix guess. `[UNKNOWN]`
  Unverifiable while the moderator endpoint returns 403.
  **Trigger to revisit:** a meta post from an ordinary account reaching a brief a *second*
  time. Revisit (c) first, and the decision it needs is whether reddit OAuth credentials are
  acceptable — not which pattern to match.

- [ ] **P17. `cluster.py` is blind to the same camelCase names P13 fixed in `validate.py`,
  and the obvious fix is wrong.** Found 2026-08-15 while costing the cross-run dedup work.
  **Measured — needs a decision, and it blocks the Beal fix.**
  `[VERIFIED]` `processing/cluster.py:46` is `\b[A-Z][a-zà-ÿ']+(?:\s+[A-Z][a-zà-ÿ']+)*` —
  the same enumerated-range pattern `fca4298` removed from `validate.py`:

  | title | `cluster._names` sees | `validate` sees |
  |---|---|---|
  | `LeBron James passes Kareem…` | `James`, `Kareem` | `LeBron James` |
  | `DeMar DeRozan scored 30 points` | **nothing at all** | `DeMar DeRozan` |
  | `Luka Dončić posted a triple-double` | `Luka Don` | `Luka Dončić` |
  | `Shai Gilgeous-Alexander wins MVP` | `Shai Gilgeous`, `Alexander` | `Shai Gilgeous-Alexander` |
  | `Alperen Şengün leads the Rockets` | `Alperen` | `Alperen Şengün` |

  `[INFERRED]` **Consequence:** an article whose only names are camelCase carries *no*
  fingerprint, so it cannot group with anything and each outlet's version of that story
  reaches the brief separately. `[VERIFIED]` This is not theoretical — `LeBron` appeared 9
  times in a single dated run's drop log (P13).
  `[VERIFIED]` **The obvious fix — reuse `validate.py`'s extractor — is wrong, measured.**
  Across 101 fixture + live articles the two disagree on **52 titles**, because the shipped
  Unicode extractor is deliberately greedy across punctuation: it yields `Cavs Celtics`,
  `Kawhi Leonard Daktronic`, `Anthony Davis Don't`. `[INFERRED]` That is correct for
  grounding — the question there is *"is this string backed by the sources"*, and a welded
  run is checked as a whole and by subset. It is wrong for clustering, where the question is
  *"which entity does this title name"* and a welded run matches nothing.
  `[VERIFIED]` **A conservative hand-written replacement is also not free.** The first attempt
  this session, preserving cluster's punctuation-bounded runs, gained 21 names (`LeBron`,
  `LeBron James`, `Luka Dončić's`, `LA Clippers`) but **lost 23**, including bare `Clippers`,
  `Ballmer`, `Luka`, `James` and `Russell Westbrook`. Losing `Russell Westbrook` from the
  fingerprint would be a worse regression than the bug.
  **Correction to the previous session's claim.** It was recorded there as a `CLAUDE.md` §5
  duplication — "two modules with their own name extractor". `[INFERRED]` The measurement
  says otherwise: they are two *policies* over one *mechanism*. The duplicated part is the
  scanner (what counts as an uppercase letter, in any alphabet); the part that must differ is
  how far a name is allowed to run. Merging them wholesale would break clustering.
  - a. One shared scanner, per-caller run policy. `[INFERRED]` The honest shape, but it needs
    a new module — **operator approval required first** (`CLAUDE.md` §6).
  - b. Fix `cluster.py` in place with its own `str.isupper`-based scan, duplicating ~15 lines
    of scanning to keep the policies independent.
  - c. Leave it; document that clustering is blind to camelCase names.
  `[UNKNOWN]` What either fix does to grouping on real data. **Measure the way P13 was
  measured** — grouping today is 76 articles → 68 stories, 6 multi-article, and that number
  must be compared before and after, not assumed.
  **Dependency:** the cross-run "already delivered this story" fix for the repeated Bradley
  Beal item is built on this fingerprint. `[INFERRED]` Fixing it on top of an extractor that
  cannot see `LeBron` or `DeMar DeRozan` would bake the blindness into a second module.

  **Progress 2026-08-15 — `processing/names.py` exists, wired into nothing** (`cd73f45`).
  Operator asked for it "for testing for now", and that is exactly what it is.
  - `[VERIFIED]` `GROUNDING` is output-identical to the shipped `validate._PROPER_NAME`
    across **215 texts** — every title and summary in all three committed fixtures plus P13's
    edge cases — asserted by `test_grounding_preset_matches_the_shipped_extractor_exactly`.
    **Adopting it in `validate.py` is therefore a no-op**, and that is the only part of P17
    that is currently safe to do.
  - `[VERIFIED]` `CLUSTERING` is **not** adoptable, with numbers in the module: 25 names
    gained, 28 lost. Three further causes were found and closing all three still leaves
    9 gained / 16 lost while introducing new mismatches. `[INFERRED]` cluster's tokenizer is
    an accumulated pile of specifics rather than a policy; converging on it by adding flags
    trades one silent grouping change for another.
  - Proof — mutation: 7 of 8 killed. The survivor is a **provably equivalent** mutant, which
    exposed a false claim in the docstring (`8678c8f`). `[VERIFIED]` `validate.py:55` still
    carries the same wrong sentence — *"Digits keep 76ers and 2026-27 out, since neither
    starts with an uppercase letter"* — and is untouched pending the operator's call.
  - `[VERIFIED]` `tests/conftest.py` gained `reddit_articles`. **No test had ever loaded the
    r/nba capture**, so the only community feed in the pipeline was covered entirely by
    hand-written titles.

- [x] **P18. The brief's paragraph order is fetch order, because every story is the same
  tier.** Found 2026-08-15 from the operator reading the 08:00 brief — *"a bit weird that
  Demar is at the end with transactions… I would like the ordering to be less random."*
  **Open — measured, needs a decision.**
  `[VERIFIED]` Reproduced against today's live feeds through the real pipeline functions:
  **all 15 stories classify `high`.** `sort_by_priority` sorts on
  `(_TIER_ORDER[classify(article)], not mentions_team_in_play(...))`, and with 0 games in the
  offseason the second key is inert for every article. A stable sort with two constant keys
  is the identity, so the surviving order is exactly fetch order — every ESPN story, then
  every CBS story, then Yahoo, then r/nba:

  | # | tier | source | story |
  |---|---|---|---|
  | 1 | high | ESPN | Cavs deal Schröder for Hornets' Mann |
  | 2 | high | ESPN | Beal stays with Clippers |
  | 5 | high | CBS Sports | Schröder trade grades |
  | 6 | high | CBS Sports | Timberwolves retire Garnett's No. 21 |
  | 9 | high | Yahoo Sports | Schröder traded 9 times — a record? |
  | 14 | high | r/nba | Schröder one team from tying Ish Smith |

  `[INFERRED]` This is not randomness and it is not the model: the summariser is handed the
  stories in this order and `main.py:129` already records that it will not reliably reorder
  on instruction. DeRozan reads as stranded because his signing arrived from a later feed
  than the Schröder trade, not because it ranked lower.
  `[VERIFIED]` **`classify` has no resolving power on a real batch.** It is a 3-value tier and
  the offseason puts everything in one. P7 already recorded one misclassification; this is the
  larger finding — the ranking is not wrong, it is *absent*.
  `[UNKNOWN]` Whether the tie should break on recency, on topic (transactions together), or
  on outlet agreement (a story three outlets carry outranks one only r/nba has). **Do not
  pick silently** — this is the most user-visible ordering in the product.

- [x] **P19. One story occupies four slots in the same brief, and the Yahoo feed is
  mojibake.** Found 2026-08-15 while measuring P18. **Both causes fixed 2026-08-15**
  (`91a056b`, `95e7c2e`, `097a835`) — and the recorded link between them was measured and
  retracted; see the strikethrough below.
  `[VERIFIED]` The Schröder trade appears as stories 1, 5, 9 and 14 in the same ranking, and
  the Beal signing as 2 and 7. `group_related` merged none of them.
  `[INFERRED]` Cause one is `MIN_SHARED_NAMES = 2`: `Clippers` is above the 8% frequency cap
  so it is not distinctive, leaving `Beal` as the single shared rare name — one short of the
  threshold. This is the same complaint the operator raised as "the Beal repeat", and it is
  **within** one run, not across runs, so the planned cross-run fingerprint would not have
  caught it.
  `[VERIFIED]` Cause two is an encoding bug, and it is one line. Yahoo serves
  `Content-Type: application/xml` with **no charset**, so `requests` falls back to
  `apparent_encoding` — chardet guesses **Windows-1254 (Turkish)** — and `response.text`
  yields `SchrÃ¶der` from the bytes `Schr\xc3\xb6der`. The feed's own XML declaration says
  `encoding="UTF-8"` and is ignored. `[VERIFIED]` `response.content.decode("utf-8")` gives
  `Schröder` correctly.

  **Cause two is FIXED** in `91a056b`, `fix: let the XML declaration decide the encoding, not
  a guess`. `[VERIFIED]` 2026-08-15, mutation-tested after the fact: restoring the guess as
  `response.content.decode("windows-1254", errors="replace")` fails
  `test_a_name_survives_a_feed_served_without_a_charset` and
  `test_the_body_is_decoded_too_not_only_the_title`, and fails with the mojibake itself
  (`'Dennis SchrÃ¶der traded to the Hornets'`, `'Luka DonÄ\x8diÄ‡ reacts'`) rather than with an
  incidental error, so the tests are load-bearing. Reverted; `make check` → 219 passed,
  1 xfailed, exit 0.

  ~~`[INFERRED]` The two compound: `Schröder` and `SchrÃ¶der` can never share a name, so the
  encoding bug actively prevents grouping of exactly the story that repeated four times.~~
  **REFUTED 2026-08-15** by the re-measurement this task asked for. `[VERIFIED]` Parsing one
  live capture twice — once forcing the Windows-1254 guess the 08:00 run actually got, once
  from raw bytes — gives **identical group membership**: 0 differences across 99 groups, and
  again across 78 on a second capture. The Schröder story grouped into 5 *either way*,
  because it groups on `Cavaliers`/`Hornets`/`Tre Mann`, not on the surname — and Yahoo's own
  titles spell it `Schroder` without the umlaut in three of ten cases, so the mangled surname
  was never the shared mark. The claim was plausible and wrong, which is why it was measured.

  `[VERIFIED]` The fix is still not cosmetic, but its real effect is narrower and different
  from the one claimed: **10 of 101 articles have a different extracted name set**, and the
  dominant mechanism is the **curly apostrophe**, not the umlaut. `’` (U+2019) mangles to
  `â€™`, and `cluster.py`'s `[A-Z][a-zà-ÿ']+` matches `â` (U+00E2, inside `à-ÿ`), so it welds
  junk onto the end of a clean name: `Lakers` → `Lakersâ`, `Kevin Garnett` → `Kevin Garnettâ`,
  `Don Nelson` → `Don Nelsonâ`, `Warriors` → `Warriorsâ`. Those can never match another
  outlet's spelling. The umlaut case is the smaller half (`Dennis Schröder` → `Dennis Schr`).
  So the bug degraded ~10% of grouping fingerprints while changing no grouping decision on
  the batches measured.

  **`[VERIFIED]` Cause one is the rarity ceiling, not `MIN_SHARED_NAMES`.** Measured
  2026-08-15 against a live capture of 109 newsworthy articles, sweeping
  `ceiling = int(n × MAX_NAME_FREQUENCY)` with `MIN_SHARED_NAMES` held at 2:

  | ceiling | 1 | 2 | 3 | 4 | 5 | 6 | 8 |
  |---|---|---|---|---|---|---|---|
  | stories | 109 | 109 | 106 | 105 | 102 | 100 | 99 |
  | largest Schröder group | 1 | 1 | 2 | 2 | **5** | 5 | 5 |

  The 08:00 run grouped 48 articles after dedup, so its ceiling was `int(48 × 0.08) = 3` and
  the story could reach a group of 2 at best — four slots. Today's probe fetched 109, ceiling
  8, and the same story held together as one group of 5. **Same code, same story, different
  batch size.**

  `[VERIFIED]` The mechanism is visible in the extracted names: `Dennis Schroder` appears in
  10 of the 109 articles, `Hornets` in 6, `Cavaliers` in 4, `Tre Mann` in 4. At a ceiling of
  3 *every one of those is discarded as non-distinctive*, including the player's own name.
  `[INFERRED]` **This is self-defeating: `MAX_NAME_FREQUENCY` is a share of the batch, so the
  more outlets cover a story, the less distinctive its own name becomes.** The rule erases the
  fingerprint of exactly the story it most needs to merge.

  `[VERIFIED]` `MIN_SHARED_NAMES` is the wrong knob. Held at the 08:00 ceiling of 3, lowering
  it to 1 collapses 109 stories to 81 to reach a Schröder group of 4 — mass merging — while
  raising it to 3 fragments the story completely.

  `[VERIFIED]` A **floor under the ceiling** — `max(floor, int(n × 0.08))` — was measured at
  six batch sizes. A floor of 5 is **inert at 80 and 109 articles** (the shipped ceiling is
  already higher) and repairs every smaller batch. Every merge it creates was inspected by
  hand and **all of them are the Schröder trade; there are no false merges** at any tested
  size. Floor 6 is identical to floor 5 in every row, so 5 is the cheaper choice; floor 4
  leaves the story split as 2+2 at a batch of 48.

  | batch | 24 | 36 | 48 | 60 | 80 | 109 |
  |---|---|---|---|---|---|---|
  | shipped ceiling | 1 | 2 | 3 | 4 | 6 | 8 |
  | shipped: merged groups | 0 | 0 | 1 (size 2) | 2 (sizes 2, 2) | 3 | 5 |
  | floor 5: merged groups | 1 (size 2) | 1 (size 4) | 1 (size 4) | 1 (size 4) | 3 | 5 |

  `[VERIFIED]` At a batch of 60 the shipped code produces **two separate groups of the same
  Schröder story**, which is the reported four-slot brief in miniature. At 24 and 36 it merges
  nothing at all — the condition `P9` chose to log rather than fix. This is the evidence that
  the logged-but-unfixed condition has a real cost.

  **RESOLVED 2026-08-15 as option (a),** chosen by the operator. Shipped in `95e7c2e` with
  the pinning test in `097a835`. `[VERIFIED]` `make check` → 221 passed, 1 xfailed, exit 0.
  Mutation-tested four ways — floor removed, floor 4, floor 99, `max` → `min` — and the first
  pass left **floor 4 alive**, because every other grouping test uses a two-article story and
  any ceiling ≥ 2 admits those equally. Closed with a test built on the five real trade
  titles, where `Dennis Schroder` has a document frequency of exactly 5.
  `[VERIFIED]` Both brief snapshots moved `+ 3 more` → `+ 2 more`; the merge behind it is two
  ESPN articles on one Donovan Mitchell / Coco Jones wedding, sharing two rare names. The
  15-article fixture had a ceiling of 1 and merged nothing at all before this.

  Options as they stood:
  - a. **Floor the ceiling** at 5: `ceiling = max(5, int(n × max_name_frequency))`. One line,
    measured inert above ~62 articles, no false merges observed. Does not address *why* the
    threshold is proportional. **← chosen**
  - b. **Make the ceiling absolute** — a name is non-distinctive above N articles regardless
    of batch size. Simpler to explain, but unmeasured at large batches, where the proportional
    rule is currently doing its job.
  - c. **Leave it and cap repeats downstream** instead, by suppressing a story whose lead
    names already appeared earlier in the same brief. Avoids touching a silent threshold, but
    adds a second mechanism for one concern.
  - d. **Fix `cluster.py`'s extractor first (P17)** and re-measure, on the grounds that the
    `â`-welding above proves the extractor is also wrong. `[INFERRED]` Independent of this —
    the ceiling table was produced with clean UTF-8 and the fragmentation is unchanged by it.

- [x] **P20. A capitalised common word in front of a real name refutes that name.** Found
  2026-08-15 while diagnosing why the 16:00 brief fell back to the headline list. **Fixed the
  same day, in two parts; see below.**
  `[VERIFIED]` `_index_source_names` indexes any run of two capitalised words as a *name*, so
  `Inside Lakers mega-deal` yields `{inside, lakers}`, the book title `the LeBron Lakers`
  yields `{lebron, lakers}`, ESPN's `Retired Heat` yields `{heat, retired}` and CBS's
  sentence-initial `The Warriors` yields `{the, warriors}`. The P12 refutation rule then reads
  each as an entity that disagrees with a real name sharing its last word.
  `[VERIFIED]` Cost, measured on the real 16:00 batch: **`Los Angeles Lakers` is refused as
  invented** — refuted by `{inside, lakers}` and `{lebron, lakers}`. On the committed fixtures,
  **2 of 11** teams named by their short form are refused when a summary expands them, down
  from 3 of 11 after the comma fix in `b0d8499`.
  `[INFERRED]` This is the same class as P13 and the comma bug: the extractor over-generates
  on title-case and headline text, and the refutation rule is the first consumer strict enough
  to be hurt by it. The rule itself is not obviously wrong — the *input* is.
  **FIXED 2026-08-15 in two parts**, because one did not reach the whole problem.

  **Part 1 — option (b)** (`4fcfa3a`, pinned by `abfc447`), chosen by the operator.
  `_index_source_names` drops words the sources also write in lower case, and requires two
  words to remain. `[VERIFIED]` Fixture teams refused when expanded: **2/11 → 0/11**, all
  seven curated blends kept. `[VERIFIED]` **It did not fix the case that opened the item**:
  on the real 16:00 batch `Los Angeles Lakers` was still refused by `{inside, lakers}` from
  *"Inside Lakers mega-deal"* and `{lebron, lakers}` from the book title *"the LeBron
  Lakers"*. Neither word appears in lower case there, so a corpus filter cannot see them —
  the heuristic is only as strong as the batch's vocabulary, and a small batch has little.

  **Part 2 — option (i), a length rule** (`487130c`). A source name may only refute one at
  least as long as itself. `[INFERRED]` A **longer** summary name sharing a last word with a
  **shorter** source name is an expansion, which is writing; an **equal-length** disagreement
  is a substitution, which is the failure ADR-012 measured. A blend is the same length as the
  name it displaces, so the rule never reaches it.

  `[VERIFIED]` Final state, measured across the fixtures, the seven curated blends and the
  live 16:00 batch together:

  | check | result |
  |---|---|
  | fixture teams refused when expanded | **0 / 11** |
  | curated real-player blends caught | **7 / 7** |
  | auto-generated blend set, with vs without the length rule | 5590/5760 either way — **no cost** |
  | 16:00 `Los Angeles Lakers` | now accepted |
  | 16:00 `Golden State Warriors` | still refused, **correctly** — that batch has no Warriors story |

  `[VERIFIED]` Mutation-tested three ways: filter removed, `>=` weakened to `>`, comparison
  inverted. All three fail, and `>` fails six tests, which is the guard that the rule has not
  been loosened into disarming blend detection.

  `[UNKNOWN]` A fabrication *longer* than the name it displaces — `Jayson Marcus Brown`
  against a source's `Jaylen Brown` — is no longer refuted. No such case has been observed;
  the measured failures swap words rather than add them. Reopen if one appears.

  `[VERIFIED]` Options measured side by side on the committed fixtures. "Curated blends" are
  seven fusions of two real players; the auto-generated 5,760-pair figure is **not** used
  here because it is contaminated with junk-derived pairs and understates every option:

  | option | teams refused | genuine names refused | curated blends | fixes the Lakers case |
  |---|---|---|---|---|
  | baseline | 2/11 | 0 | 7/7 | no |
  | (a) hardcoded stop-words | 1/11 | 0 | 7/7 | no |
  | **(b) corpus lower case** | **0/11** | **0** | **7/7** | **no** |
  | (d) refuter seen ≥2× | 0/11 | 0 | **6/7** | yes |
  | (b)+(d) | 0/11 | 0 | 6/7 | yes |

  `[VERIFIED]` (d) was **not** taken. It fixes the motivating case but costs a real blend
  (`LeBron Tatum`), and that is the expensive direction — a false accusation costs a brief its
  prose, while a missed blend puts an invented person's name on the phone. Option (i) was
  found by looking for the way to keep both, and does: it fixes the same case at no measured
  detection cost.

  `[VERIFIED]` One objection to (b) was raised and measured rather than argued: NBA teams are
  named after common words (`Heat`, `Magic`, `Jazz`, `Kings`, `Thunder`, `Bucks`), so the
  filter could strip the names it must keep. **None of the 28 team words appears in lower case
  anywhere in the fixtures.** `[UNKNOWN]` Whether that holds on every live batch — but the
  failure direction is safe, since stripping a word shortens a *refuter* and can only make the
  rule accuse less.

  Options as they stood:
  - a. **Exclude common words from the index**, as `cluster.py` already does with `_NOT_NAMES`.
    Small and proven in-repo, but it is a hardcoded English list, and the operator rejected
    exactly that shape for P13. `[INFERRED]` Weaker objection here than there: P13 enumerated
    *characters*, where the next alphabet always breaks the list, while function words are a
    closed and stable set.
  - b. **Derive it from the corpus instead of listing it** — a word that also appears in
    lower case somewhere in the batch is ordinary vocabulary, not part of a name. Not
    hardcoded, and `The`/`Inside`/`Retired` all appear lower case constantly. `[UNKNOWN]`
    Whether it misfires on names that are also words (`Heat`, `Magic`, `Jazz`, `Kings`) —
    **measure before building**, since those are team names and would be the expensive miss.
  - c. **Only refute when the two names have the same length**, so a 2-word source name cannot
    refute a 3-word summary name. `[VERIFIED]` Does not help: `{inside, lakers}` and
    `{heat, retired}` are both 2 words, and so is `Miami Heat`.
  - d. **Require the refuting source name to appear more than once.** A one-off headline
    artefact is discarded; a real person named repeatedly still refutes. `[UNKNOWN]` Effect
    unmeasured.

- [x] **P21. Expanding an abbreviation reads as invention.** Found the same way.
  ~~**Open.**~~ **Closed 2026-08-18**, commits `5f35e55` and `0003b67`.
  `[VERIFIED]` The 16:00 run was rejected in part for `Madison Square Garden`, whose sources
  say only `MSG` — twice, in the title and the body. Nothing in the sources contains
  "Madison", "Square" or "Garden", so every grounding rule correctly fails, and the index is
  empty: this is **not** the P20 refutation path.
  `[INFERRED]` It is nonetheless a false accusation of the kind `SESSION.md` §8 says costs the
  most, because the fallback is silent — the model expanded a well-known abbreviation
  correctly and the brief lost its prose for it.
  `[UNKNOWN]` How often this happens; `MSG`, `OKC`, `LA` and `NBA` are the plausible set.
  Resolve by counting abbreviation expansions across a week of rejected attempts before
  building anything — `[INFERRED]` a rule mapping abbreviations to expansions is a lookup
  table, which is the shape this project keeps deciding it does not want.

  **Counted first, as that instruction required, and the count changed the answer twice.**

  `[VERIFIED]` **It has cost two briefs, not one.** Besides `Madison Square Garden` (rejected
  3 times, against `MSG` printed 7 times in the corpus), the 2026-08-17 08:00 run was rejected
  for `Karl-Anthony Towns` on all three attempts while its own batch carried *"💍 KAT, Jordyn
  Woods tie the knot in Malibu"*. Batch reconstructed from `seen_articles`, 19 of 23 ids
  matched. **That run is recorded elsewhere in this file, and was reported to the operator, as
  the model inventing a player. It was not.** See the correction under P4.

  `[VERIFIED]` **The general version is unsafe, which settles the lookup-table objection with
  evidence rather than taste.** Deriving initials from a name and looking for them in the
  sources acquits `Ayo Dosunmu` — the fabrication this module was built to catch — because its
  initials spell `AD` and the feeds print `AD`. `Anthony Davis` collides on the same letters.

  `[VERIFIED]` **Matching must respect word boundaries.** Across 239 articles: `ad` occurs 181
  times as a substring against 1 as a word, `la` 352 against 9, `kat` 3 against 2 because
  "skate" contains it. Only `msg` is safe either way, at 7 and 7.

  **Fixed** with a two-entry phrase table keyed on the whole name, so `garden` cannot ground
  every name ending in "Garden". `[VERIFIED]` Mutation-tested six ways, all caught. One
  mutation *survived* on the first attempt and was a false negative in my own harness:
  `{} or {...}` is textually applied but evaluates to the second dict, so the table was never
  emptied. Verifying the table's *size* rather than the edit is what caught it.

- [x] **P22. One name spelled two ways is read as two names.** Found 2026-08-17 00:10 by an
  autonomous check watching the pipeline log, then generalised on the operator's instruction
  to anticipate the whole class rather than fix instances. **Fixed** in `4e98cc1` and
  `2ba3dd7`.
  `[VERIFIED]` The trigger: the 00:00 run rejected `Mike D'Antoni` on all three attempts
  while lead 3 of its own batch was Yahoo's *"Honoring new Hall of Fame inductee, former
  Rockets coach Mike D’Antoni"*. U+2019 in the feed against U+0027 from the model, compared
  as literal strings. **Both shapes render identically**, so this bug is invisible to reading
  output — the technique that found the other eleven.
  `[VERIFIED]` Scoped by scanning 329 live and fixture articles for every non-ASCII character
  actually present: U+2019 (137), curly double quotes (109), em dash (15), `ö`/`ć`/`é`/`č`
  (24 combined), ellipsis (7), en dash (1).
  `[VERIFIED]` **Three of the six accented names also appear unaccented in the same corpus** —
  `Dončić`/`Doncic`, `Jokić`/`Jokic`, `Schröder`/`Schroder` (9 accented against 17 plain).
  Yahoo prints both spellings of one player in different headlines of the **same story**, so
  this is not correctable at the prompt: the sources disagree with themselves.
  `[VERIFIED]` Folding is for comparison only; extraction still reads real Unicode, per P13.
  No detection lost: fixture teams falsely refused 0/11, curated blends 7/7, known
  fabrications `Joe Dumars` and `Ayo Dosunmu` both still caught. Mutation-tested two ways.

- [x] **P23. The model uses generic NBA vocabulary the sources never write.** Found
  2026-08-17 in the same run. ~~**Open — and it is not obviously a defect.**~~
  **Closed 2026-08-17 by option (c), on the operator's explicit authorisation:** *"If
  Hard-Coded Vocabulary list is what it takes than go for it."* Commits `ecef1e9`, `6d0c57a`.
  `[VERIFIED]` That run's other two rejections were `Eastern Conference` and `Western
  Conference`, and both are **correct**: neither phrase appears in any of the 8 leads, which
  were reconstructed exactly (the replay produced 8 leads, matching the log's "8 articles").
  `[INFERRED]` These are not fabrications in any harmful sense — they are structural terms of
  the sport, like naming a conference a team plays in. But the validator cannot tell them
  from an invented person, and one of them fails a whole brief.
  `[UNKNOWN]` How often this costs a run. Two of the five most recent fallbacks involved it.
  Options, none picked and none measured:
  - a. **Leave it.** The prompt already says to state only what the notes say; a model adding
    conference names is doing more than asked. Cheapest, and keeps the check strict.
  - b. **Strengthen the prompt** against structural commentary. `[VERIFIED]` A prompt change
    of this shape was measured for names and moved nothing (3/6 vs 3/6), so expect little.
  - c. **Treat a fixed set of competition terms as always-grounded.** Small and effective,
    but it is a hardcoded vocabulary list — the shape rejected for P13 and avoided for P20 —
    and every entry is a permanent hole in the check. **← chosen.**

  **Why the corpus could not decide it instead.** `[VERIFIED]` P20's `_ordinary_words` learns
  from words the sources write in *lower* case. `Eastern Conference` is written capitalised or
  not at all, so no amount of corpus evidence reaches it. This is the one place a list is not
  laziness.

  **What bounds the hole: the all-words rule.** Every word of a name must be vocabulary, so a
  single city, surname or nickname sends it back through grounding.
  `[VERIFIED]` Measured 2026-08-17 against 31 team names and 311 distinct proper names in a
  203-article live-plus-fixture corpus:

  | | result |
  |---|---|
  | teams exempted without grounding | **0 of 31** |
  | people exempted | **0** |
  | source names exempted | 5 — `NBA Finals`, `NBA Draft`, `Eastern Conference`, `Eastern Conference Finals`, `WNBA All-Star Weekend` |
  | historical rejections acquitted | **2 of 55** — exactly `Eastern Conference` and `Western Conference` |
  | `Joe Dumars`, `Ayo Dosunmu`, `LeBron Tatum`, `Jayson Brown` | all still caught |

  **What may enter the list later**, recorded so it does not grow by habit: a formal name of
  an NBA structure, competition or honour, capitalised when written, that cannot be part of a
  person's or a team's name. Re-run the measurement before adding one.

  `[VERIFIED]` **What this gives up.** Where the sources name only the Western Conference and
  the model writes `Eastern Conference`, refutation *would* have refused it; putting the
  exemption before `_contradicted` gives that up. Two reasons it is there anyway. First, no
  such case appears in the log — the observed rejections had **neither** conference in their
  sources. Second, the alternative ordering was measured to break a real case: the live corpus
  writes `Eastern Conference Finals`, which refutes a summary's `NBA Finals` under P20's
  length rule. `[INFERRED]` A wrong conference is a *claim* error, and P5 already records that
  this module grounds entities rather than claims.

  `[VERIFIED]` Mutation-tested three ways, each verified to have applied by printing the
  resulting vocabulary size: emptying the list (size 0) → 12 failures; `all` → `any` (size 41)
  → 1 failure; dropping `"conference"` (size 40) → 4 failures. The `all` → `any` mutant
  **survived the first campaign** and its test is `6d0c57a`; see that commit for why the
  obvious test did not exercise the rule.

- [x] **P24. Grounding matches substrings, so one name can ground another.** Found
  2026-08-17 while writing P23's team-safety test. ~~**Open, not yet costing anything.**~~
  **Closed 2026-08-18** as a side effect of P21, commit `5f35e55`. Its own example is now
  caught: against `Sources: Cavs deal Schroder for Hornets' Mann`, `Brooklyn Nets` is refused.

  `[VERIFIED]` **The "leave it alone" conclusion below was wrong, and dated evidence is why.**
  That measurement ran before P25 let the *first* word ground a name. While only the last word
  counted, an accidental substring had to land on a surname and never did; afterwards every
  short first name was exposed, and `Ayo Dosunmu` grounded against a batch that never mentions
  him because "ayo" sits inside **playoffs** and **layoffs**. Word boundaries went in with P21.
  `[INFERRED]` The lesson is about the shelf life of a measurement, not about substrings: a
  result that says "changes nothing" is only true of the code it was measured against.
  `[VERIFIED]` `_grounded` ends in `words[-1] in normalised_source`, a plain substring test.
  Against the source `Sources: Cavs deal Schroder for Hornets' Mann`, the summary name
  `Brooklyn Nets` is **grounded** — because `"nets"` occurs inside `"Hornets"`. The test that
  found it now uses a headline containing no team nickname as a substring, so it tests P23
  rather than this.
  `[INFERRED]` The direction of the error is the expensive one for correctness and the cheap
  one for the operator: it makes the check too *lenient*, so it can miss a fabrication but
  cannot cost a brief. That is why it is not urgent.
  `[UNKNOWN]` How often it fires on real data, and whether word-boundary matching would
  reintroduce false accusations that possessives and plurals currently slide past. Resolve by
  measuring both readings across the fixtures before changing anything — the same method that
  settled P20.

  **Measured 2026-08-17, and the answer is leave it alone.** `[VERIFIED]` Word boundary
  matching scored identically to the shipped substring rule on the P20 population of 226 real
  names and 3,000 blends: 3 refused and 1956 detected either way, with 0 names newly refused
  and 0 fabrications newly caught. `[INFERRED]` That population cannot probe the gap, since
  every blend's last word is a corpus word that appears exactly, so read this as "no measured
  benefit" rather than "no difference exists".

  `[VERIFIED]` More importantly, P26 shows the substring behaviour is load bearing in the
  other direction. A source writing `Timberwolves` grounds a summary's `Wolves` only because
  `wolves` occurs inside it. Tightening to word boundaries would turn that into a false
  accusation. Do not fix this without fixing P26 first.

- [x] **P26. The feeds and the model use different short forms of the same team.**
  Found 2026-08-17 16:00, which fell back after all three attempts were rejected for
  `Philadelphia Sixers`. ~~Open, measured, and the biggest known cause left alongside P25.~~
  **Closed 2026-08-17** by an alias table, commits `25e2906` and `5e666a8`.

  `[VERIFIED]` The live feeds write `76ers` 11 times and `Sixers` once. `76ers` starts with a
  digit, so `_is_name_word` deliberately refuses it, and grounding never sees it. When the
  batch says only `76ers` and the brief says `Philadelphia Sixers`, the last word `sixers`
  appears nowhere and a real team is reported as invented. Confirmed in isolation: source
  `76ers`, summary `Philadelphia Sixers`, rejected.

  `[VERIFIED]` Five of ten real alias pairs are rejected: `76ers` against
  `Philadelphia Sixers`, `Cavs` against `Cleveland Cavaliers`, `Wolves` against
  `Minnesota Timberwolves`, `T-Wolves` against the same, `Mavs` against `Dallas Mavericks`.
  The five that pass do so because the short form keeps the same last word, as with `Knicks`,
  `Nets` and `Blazers`.

  `[VERIFIED]` These are not hypothetical. The feeds captured at 2026-08-17 16:20 use
  `76ers` 11 times against `Sixers` once, `Cavs` 4 against `Cavaliers` 6, and `Wolves` 5
  against `Timberwolves` 5.

  `[INFERRED]` It shows up in the rejection history as `Philadelphia Sixers`,
  `Philadelphia Sixer` and `NY Knicks`, and it was hit by accident while writing a P23 test
  that used `Timberwolves` against a source saying `Wolves`.

  The fix is an alias table mapping each short form to the team it names, consulted when the
  last word test fails. It is a hardcoded list, the same shape approved for P23, but a plainer
  one: `Cavs` and `Cavaliers` are the same team as a matter of fact, not of judgement.

  **What shipped.** Ten groups, each one team under the names the feeds actually print. Six
  were counted in the corpus, four are the same kind of name and unambiguous but not yet seen.

  `[VERIFIED]` Alias pairs rejected went from 5 of 10 to **0 of 10**. On the P20 population of
  267 real names and 3,000 blends the table costs nothing measurable: real names refused stays
  at 1, blends detected stays at 1761, and **0** fabrications stop being caught. Both teams the
  model actually invented that day, `Miami Heat` and `Dallas Mavericks`, are still caught.

  `[VERIFIED]` **Three candidates were measured and left out**, because the short form is an
  ordinary word rather than a team here: `king` occurs 5 times and never means the Kings (it is
  LeBron, and a quarterback named Haynes King), `clips` occurs once and means video, `net`
  occurs once and is a safety net. Each has a test asserting it does not ground a team.

  `[INFERRED]` The table opens no new class of hole. Grounding on the last word already accepts
  any city in front of a correct nickname, which is what P11 decided when it let `Knicks`
  become `New York Knicks`. This only makes `Cavs` behave the way `Knicks` already did.

  `[VERIFIED]` Mutation-tested three ways, each verified applied by printing the table size:
  emptying it (0 entries) gave 8 failures; adding `king` as an alias for the Kings (25 entries)
  gave 1; skipping the table on the last-word test (23 entries) gave 8.

- [x] **P25. A player the sources name by first name alone cannot be written in full.**
  Found 2026-08-17 while diagnosing that morning's fallback. ~~**Open — measured, and the fix
  needs the operator's decision because it changes `_grounded`'s central rule.**~~
  **Closed 2026-08-17 by reading (c), on the operator's instruction** *"go ahead with fixes for
  P25, P23 and P26"*. Commits `8a508dc` and `7ac0a1f`.

  `[VERIFIED]` The 08:00 run was rejected for `LeBron James` on all three attempts. Grounding
  ends on the **last** word, so a name is grounded by its surname; when the feeds write only
  `LeBron`, the full name has no surname to match and is reported as invented.

  `[VERIFIED]` This is not a one-off. Counted across the 127 live articles captured that day,
  **four NBA players appear only as bare first names**: `Ja` (33 occurrences, `Ja Morant` 0),
  `LeBron` (26 against 15), `Wemby` (4 against 0), `Giannis` (2 against 0), `Luka` (2 against
  0). Behaviour check: **6 of 6** expansions tested were rejected.

  `[INFERRED]` It plausibly accounts for a large share of the fallback history. The rejection
  log's most frequent names are `LeBron James` (6), `Kawhi Leonard` (6), `Klay Thompson` (3),
  `Kobe Bryant` (2), `Giannis Antetokounmpo` (2) — every one a player the feeds routinely
  name by first name alone, and `Kobe` appears bare in a real 2026-08-17 headline. `[UNKNOWN]`
  Whether each specific rejection had that cause; per-run batches were not preserved.

  **This is the mirror of the bug the last-word rule was built for.** P11 fixed `Knicks` →
  `New York Knicks`, where the *last* word identifies. Here the *first* word does, and the
  same rule that fixed one causes the other.

  Three readings measured 2026-08-17 across 203 live-plus-fixture articles — 226 real
  two-word names (must pass) and 3,000 synthetic blends built from them (must fail), the
  population P20 used:

  | | real names refused | blends detected | mononyms rescued |
  |---|---|---|---|
  | **a. leave it** (shipped) | 3/226 | 1956/3000 — 65.2% | 0/8 |
  | **b. also ground on the first word** | — | — | 7/8 |
  | **c. b, plus index source names by first word too** | **3/226** | **2628/3000 — 87.6%** | **7/8** |

  `[VERIFIED]` **Reading (b) alone is not acceptable and is recorded so it is not retried:**
  it misses **6 of 6** fabricated surnames hung on a grounded first name — `Anthony Edwards`
  and `LeBron Smith` against sources naming Anthony Davis and LeBron James both pass. Making
  the first word ground a name without also letting it *refute* one invents people.

  `[VERIFIED]` **Reading (c) is not a trade-off.** It refuses no more real names than the
  shipped rule (3/226 either way), detects **22 points more** blends, misses 0 of 6 fabricated
  surnames, and rescues 7 of 8 expansions. The 8th is `Wemby` → `Victor Wembanyama`, where
  neither word matches — a nickname rather than a first name, and correctly still refused.

  `[UNKNOWN]` Whether (c) accepts anything a *model* would really write that the synthetic
  blends do not represent. Resolve by replaying captured batches, not by reasoning.

  **What shipped.** Grounding now accepts either end of a name, and `_index_source_names` keys
  both ends so refutation can answer at either end too. `_contradicted` takes the key word as
  an argument instead of assuming the last one. Those two halves are one change and must not be
  separated: the first without the second is reading (b), which invents people.

  `[VERIFIED]` Measured on 331 live and fixture articles, 267 real names and 3,000 blends,
  with the P26 alias table also in place:

  | | before | after |
  |---|---|---|
  | real names refused | 1/267 | 2/267 |
  | blends detected | 1761 (58.7%) | **2520 (84.0%)** |
  | mononym expansions accepted | 0/8 | **7/8** |
  | fabricated surnames missed | 0/6 | **0/6** |

  `[VERIFIED]` The one extra refusal is not a real name. Before, the single refusal was
  `Edit I've`; after, it is `Edit Curry` and `Redick On`. All three are extraction artifacts
  from Reddit posts, not players or teams, so the count moved but nothing real was lost.
  `[INFERRED]` Refusals rose because a wider index gives `_contradicted` more to disagree with,
  which is the same mechanism that raised detection by 25 points.

  `[VERIFIED]` The 8th expansion, `Wemby` to `Victor Wembanyama`, is still refused and should
  be: neither word matches, because it is a nickname rather than a first name. Handling those
  would need a player alias table, which is guesswork rather than something the feeds state.

  `[VERIFIED]` Mutation-tested three ways: reverting grounding to the last word only gave 7
  failures; not indexing the first word gave 6; not refuting on the first word gave 6.

- [x] **P27. A headline's opening label was read as part of a name.** Found and fixed
  2026-08-17, and it is the first bug here found by a dry run rather than by a delivered brief.

  `[VERIFIED]` With P25 and P26 both in, a full 12-story dry run still rejected
  `Philadelphia Sixers` on two of three attempts. The batch carried the real headline
  `Report: Sixers hire Tommy Balcetis to front office`, which was read as the single name
  `{report, sixers}`. That is two words sharing a last word with the team and disagreeing about
  the other, so the refutation rule treated a headline's label as a rival entity.

  **This is P20 for the third time, through a gap in its own fix.** `_ordinary_words` only
  learns a word is vocabulary when the batch writes it in lower case somewhere, and a 12-story
  batch never wrote "report". `[VERIFIED]` Confirmed by adding one article containing "per
  report" to the same batch, after which the team grounded.

  `[VERIFIED]` The shape is common, not exotic: 61 of 331 live and fixture titles, 18%, open
  with a label and a colon. `Sources:`, `NBA odds:`, `NBA Power Rankings:`, `NBA HOF week:`,
  `SB Nation Reacts:`.

  **Fixed by making a colon a separator**, the same way a comma became one for P20. A name that
  *ends* at a colon is still kept, because the run is recorded before it is cleared, so
  `Jordan Goodwin: a quiet week` keeps `Jordan Goodwin` and only one-word labels are lost.

  `[VERIFIED]` Strictly better on both axes, on 331 articles with 267 real names and 3,000
  blends: false refusals dropped from 2 to 1, and blend detection rose from 84.0% to 85.2%.
  The remaining refusal is `Redick On`, an extraction artifact rather than a name.

  `[VERIFIED]` `processing/names.py` needed the same change, and the test asserting the two
  extractors stay output-identical is what caught the drift, on the real title `Sources: Knicks
  executive Rosas leaving team`. Commits `ca5eceb`, `7e13899`, `90627ea`, `383ff99`.

  `[VERIFIED]` One existing test asserted the old behaviour outright, that grounding *should*
  weld `Report:` onto the following name. That is the same assumption its own docstring already
  retracts for the comma, so it was corrected in place with the measurement rather than
  deleted. `[INFERRED]` Worth noting as the one case this session where a test was changed to
  pass: it encoded a wrong expectation, which `OPERATING_RULES.md` §4 allows only when said out
  loud first.

  `[VERIFIED]` Mutation-tested per file, each verified applied by printing both separator
  strings: removing the colon from `validate.py` alone gave 2 failures, and from
  `processing/names.py` alone gave 2.

---

- [x] **P28. A dead source vanished from the brief with only a log line.** Closed 2026-08-18.
  `[VERIFIED]` Reddit answered HTTP 500 for the whole 00:00 run and again five minutes later,
  costing 25 of 87 articles. The brief carried on and said nothing, because `fetch()` returns
  `[]` on failure and a dead feed is then indistinguishable from a quiet one. Second observed
  case, after CBS timed out on 2026-08-15 and contributed 0 stories.
  The empty list stays the contract (`CLAUDE.md` §5 rule 6). `last_error` is set alongside it,
  as a **class attribute** so no adapter author has to remember to initialise it, and the brief
  names any source that failed. Commits `c4be9cf`, `c19aa31`, `a135368`, `cad0990`, `115d14e`.
  `[VERIFIED]` **A mutation deleting the collection entirely left all 315 tests green**, because
  the loop lived inline in `main` and nothing could reach it without the network. The loop is
  now `main.fetch_news`, extracted for that reason alone, and the mutant now fails.
  `[INFERRED]` This is part of what `ROADMAP.md` v0.3.0 folds in, but the visibility half was
  cheap and independent of ADR-014, so it shipped early rather than waiting.

---

- [x] **P29. A fan speculation thread became a claim in the brief.** Closed 2026-08-18,
  reported by the operator from a delivered brief.
  `[VERIFIED]` The brief said *"speculation swirls around Nikola Jokic's potential contract,
  suggesting he cannot sign for the veteran minimum while still receiving an additional
  $300M"*. The whole thing traces to one r/nba post: *"Can Nikola Jokic now sign for veteran
  minimum and get 300 million on the side for planting few trees?"*, a reader being sarcastic.
  `[VERIFIED]` **Nothing downstream could have caught it, and the validator was right.**
  `$300M` grounded because the post contains "300 million"; `Nikola Jokic` grounded because the
  post names him. The summary is a faithful reading of a source that should never have been in
  the batch. `[INFERRED]` This is the clearest case yet that grounding answers "did a source
  say this", not "is this true", and that the filter upstream is what decides which sources
  get to say things.
  **Fixed by one structural signal, scoped three ways:** an untagged, question-shaped title on
  the community feed. `[VERIFIED]` This is title-based classification of r/nba, which
  `SESSION.md` §11 records failing twice, so it was measured before shipping rather than
  reasoned about. Across 239 unique articles from four captures it drops **exactly one**, and
  it is that post. r/nba writes 1 question title in 64; the editorial outlets write 18 in 175
  and every one is reporting, which is why the rule cannot apply to them. A reporter tag
  exempts an item, so `[Charania] Will X sign?` survives.
  `[VERIFIED]` Mutation-tested four ways, all caught: never dropping, applying to every source,
  ignoring the reporter tag, and dropping untagged community posts regardless of punctuation
  (9 failures, the widest). Commits `b986a1e`, `159958f`.

- [x] **P30. The brief interleaves unrelated stories.** Reported by the operator
  2026-08-18. ~~**Not fixed.**~~ **Closed with P18 on 2026-08-18**, commits `100bc24`,
  `56653be`, `99eb88f`, `c575530`, `891d964`, `25823d8`.

  **Fixed by ordering, not by grouping, and the distinction is the finding.** `[VERIFIED]`
  `group_related` requires `MIN_SHARED_NAMES` = 2, and four reports of one trade share only
  the player's name, so they are correctly four stories. Lowering that threshold would merge
  any two articles mentioning one player. Relatedness is weaker than sameness, and ordering is
  where it belongs.

  `processing/cluster.order_by_relatedness` chains greedily: after each story, take whichever
  remaining story shares the most names with it. Ties keep the caller's ranking, so a batch
  where nothing is related comes back unchanged, and the top-ranked story always leads. It
  runs **after** the per-source cap, because the cap keeps the highest-ranked stories and
  reordering first would change which ones those are.

  `[VERIFIED]` Names are compared as **folded words**, not whole strings. The feeds print
  `Dennis Schröder` and bare `Schroder` for one person; without folding they never meet, which
  is why `validate.comparable` became public.

  `[VERIFIED]` On the live feeds, the three Schröder stories moved from positions 4, 5 and 8
  to 4, 5 and 6, with the two NBA-statement items landing together at 7 and 8. On P18's
  recorded 15-story brief the four reports of one trade go from 1, 5, 9, 14 to adjacent.

  `[VERIFIED]` Mutation-tested five ways, all caught after one survived: deleting the call
  from the pipeline left all 341 tests green, the **third** wiring mutant of the day. The
  sequence is now `main.build_story_groups` and a test asserts the consequence.
  **Same root as P18, and they should be worked together.** `[VERIFIED]` P18 recorded on
  2026-08-15 that every story classifies to the same tier, so `sort_by_priority` degenerates
  to fetch order. P30 is what that order looks like once the summariser chunks it: related
  stories land in different chunks and the reduced narrative interleaves them. `[INFERRED]`
  One is the cause and the other the symptom, so fixing the ordering is likely to close both.
  Do not fix them separately.
  `[VERIFIED]` In the delivered brief, two Clippers/Kawhi items are separated by the Jokic
  thread, and the Jeanie Buss items are separated by the San Antonio arena vote. The operator's
  words: *"why is jeanie buss section separated by vote in san antonio"*.
  `[INFERRED]` The likely mechanism, not yet confirmed: `processing/summarize.py` chunks at
  `CHUNK_SIZE = 5` and the 12 stories went to 3 chunks. Notes are extracted per chunk and then
  reduced, so two articles about one story land in different chunks whenever priority order
  separates them. `processing/cluster.py` groups related coverage, but the order handed to the
  summariser is priority order, and nothing keeps a group contiguous across a chunk boundary.
  `[UNKNOWN]` Whether that is the whole cause, and whether ordering stories by group before
  chunking fixes it without disturbing priority. Resolve by replaying a captured batch with
  the two orderings and comparing, not by reasoning.

- [ ] **P31. `_figure_grounded` compares digits against the whole batch.** Open, found
  2026-08-18 while checking whether `$300M` was invented.
  `[VERIFIED]` It strips every non-digit from the entire source text and asks whether the
  figure's digits appear as a substring of that stream. On the 42-article reconstruction the
  stream is 111 digits long, so `$489M` and `$10B` ground while `$300M`, `$999M` and `$7777`
  do not. `[INFERRED]` The looseness scales with batch size: a longer digit stream makes any
  short number likelier to appear by coincidence, and a two-digit figure like `$10B` is
  already near-certain to match something.
  `[UNKNOWN]` Whether it has ever produced a false acquittal. It did **not** cause the Jokic
  case, which is why this is recorded rather than fixed: that figure was genuinely in a source.
  Resolve by measuring how many invented figures a real batch would ground before changing it.

---

- [x] **P32. A headline label or sentence is indexed as a rival entity.** Found
  2026-08-18 16:00, which fell back on all three attempts. ~~**Not fixed.**~~
  **Fixed the same day**, commits `fb2e8c1`, `8e1b9cd`, `365c54d`, `8e8daa2`, `f1a…` (tests).
  `[VERIFIED]` Two of that run's three rejections come from this. `Toronto Raptors` was
  refuted by `{raptors, reacts}`, from *"Raptors Reacts: Which player needs to elevate their
  game next to Kawhi?"*. `Commissioner Adam Silver` was refuted by `{adam, fire, silver}`,
  from the r/nba post *"Fire Adam Silver"*. Neither refuter is an entity: one is a recurring
  section label, the other is a sentence beginning with a verb.
  `[VERIFIED]` **P27's colon fix does not reach this.** A colon ends the run, but the run is
  recorded first when it already has two words, so `Raptors Reacts` is still indexed. The
  colon only ever discarded one-word labels.
  `[VERIFIED]` **P20's `_ordinary_words` does not reach it either**, for the reason P27
  recorded: it only learns a word is vocabulary when the batch writes it in lower case, and
  this batch never wrote "reacts" or "fire" that way.
  ~~`[UNKNOWN]` The fix. At least three defensible answers and none measured: discard a run
  that a separator terminated regardless of length; require a refuter to look like a name
  rather than a sentence; or drop leading imperatives the way `_SENTENCE_STARTERS` drops
  prepositions.~~ **None of those was needed.**

  **The cause was the sample size, not the rule.** `[VERIFIED]` P20's `_ordinary_words` only
  learns that a capitalised word is ordinary when the same batch writes it in lower case, and
  it was being given the **twelve summarised stories**. That is too small a sample of English:
  in that batch neither "reacts" nor "fire" appears in lower case, while across 258 captured
  articles both plainly do.

  So the vocabulary is now learned from a **wider sample** than the names are indexed from.
  `main.py` hands over everything newsworthy it fetched, roughly 90 articles against the 12
  summarised. `[INFERRED]` The two must stay separate arguments: `articles` is what a name is
  *grounded* against, so widening that would let a story the brief never summarised vouch for
  a name in it. A test asserts exactly that, and a mutation swapping one for the other fails.

  `[VERIFIED]` On the real 16:00 batch it takes the rejections from
  `['Toronto Raptors', 'Commissioner Adam Silver', 'Steve Ballmer']` down to
  `['Steve Ballmer']`, which is P33 and a different cause. Measured cost on the P20 population:
  **none** — 3 of 292 names refused and 2620 of 3000 blends detected either way.

  `[VERIFIED]` Mutation-tested three ways. One **survived**: deleting the pass-through in
  `processing/summarize.py` left all 331 tests green, so the widening could have been inert in
  production while every validator unit test still passed. That is the second surviving mutant
  of the day from the same cause, a branch that only exists in wiring, and it now has a test.

  `[INFERRED]` Recorded because it generalises: three of this module's bugs have now been
  "the rule is fine, the evidence was too thin" rather than a wrong rule. P20's fix, P27's
  colon, and this. The pattern to watch is any rule that learns from one batch.
  Resolve by measuring each against the P20 population before choosing.

- [x] **P33. A source's misspelling refutes the correct spelling.** Found 2026-08-18
  16:00. ~~**Not fixed, and it is a consequence of P25.**~~ **Closed 2026-08-19** after a
  second instance, commits `7cf9306`, `9769bda`, `6a7de74`, `cfb7310`.
  `[VERIFIED]` `Steve Ballmer` was rejected on all three attempts. The batch spells it
  **"Steve Balmer"**, one L, in *"Pablo Torre on ESPN's report regarding negotiations between
  Steve Balmer and the NBA"*. Indexed as `{balmer, steve}`, which shares the first word with
  `{steve, ballmer}` and disagrees about the rest.
  `[VERIFIED]` **P25 caused it.** With last-word-only indexing the two names key on `balmer`
  and `ballmer`, different buckets, and no refutation happens. Keying both ends is what puts
  them in the same bucket. That change is still worth its keep — it raised blend detection
  from 65.2% to 87.6% — so this is a cost to pay down, not a reason to revert it.
  `[INFERRED]` A near-match test would separate these cleanly. Measured on six pairs with
  `difflib.SequenceMatcher`: typos score 0.923 (`balmer`/`ballmer`) and 0.933
  (`schroder`/`schrder`), while genuinely different players score 0.667 (`jayson`/`jaylen`)
  and 0.545 (`doncic`/`jokic`).
  ~~`[UNKNOWN]` Whether that gap holds beyond six hand-picked pairs.~~ **Measured 2026-08-19,
  after a second instance made it worth the work.**

  `[VERIFIED]` **The second case is not a typo at all.** The 2026-08-19 00:00 run refused
  `LeBron James` because an r/nba headline reads *"Anthony Edwards meets **Lebwrong** James
  and company in the Philippines"* — a reader's deliberate joke spelling, indexed as a rival
  entity. `[INFERRED]` That widens the class usefully: the sources are not merely careless,
  they are sometimes playing, and either way a near-identical spelling is one name.

  `[VERIFIED]` **This one is not a P25 regression**, unlike the Ballmer case. Checked against
  a reconstructed pre-P25 index: `Lebwrong James` ends in "James", so it sits under that key
  even with last-word-only indexing, and refutes either way.

  ~~`[VERIFIED]` 0.80 is measured. Pairs that must merge: `balmer`/`ballmer` 0.923,
  `lebwrong`/`lebron` 0.857.~~ **Corrected 2026-08-25 by the operator, and it reversed the
  second case.** `Lebwrong James` is not a misspelling: the post is a video of Anthony Edwards
  meeting a LeBron **impersonator**, so it names a different person on purpose.

  `[VERIFIED]` Merging them was actively harmful, not merely generous. The real LeBron appears
  **zero** times in that batch, so at 0.80 the summary *"LeBron James signed a new deal"* was
  **accepted**. The fix converted a correct rejection into a missed fabrication.

  `[VERIFIED]` The two cases separate by ratio, swept against the committed fixtures with 92
  real names and 3,000 blends: 0.80 and 0.85 wrongly accept LeBron; **0.88 to 0.92** ground the
  Ballmer typo and reject the parody; 0.95 wrongly rejects Ballmer. Blend detection is flat at
  2821 of 3000 across the entire sweep. `_SAME_NAME_RATIO` is now **0.90**, the middle of that
  window. Pairs that must stay refuted are unchanged: `jayson`/`jaylen` 0.667,
  `doncic`/`jokic` 0.545, `edwards`/`davis` 0.500, `durant`/`garnett` 0.462.

  `[UNKNOWN]` The window rests on **two** real observations, one typo and one parody. A third
  should be measured before the number is trusted further.

  `[INFERRED]` The lesson is not about thresholds. The measurement was sound and the reading of
  the data was wrong: I classified a deliberate parody as a spelling error because the two are
  mechanically identical. Domain knowledge set the boundary, not the corpus.

  `[VERIFIED]` Cost on the P20 population, 318 real names and 3,000 blends over 288 articles:
  real names refused unchanged at 3, blend detection **2593 → 2592**. The single loss is
  `Stephen Steph's`, a nonsense synthetic string matched through `steph`/`stephen` at 0.833,
  which is one person. All six curated real-player blends survive.

  `[VERIFIED]` An equal-length guard was written and then deleted before shipping, on P6:
  removing it changes **0** of 4,000 mixed-length probes, because `_contradicted` already
  filters candidates by length. Third dead guard caught by a mutant rather than review.

  `[VERIFIED]` **The run this closed was a correct fallback in full.** ~~Only `LeBron James`
  was a false accusation~~ — after the 2026-08-25 correction, `LeBron James` was a correct
  rejection too, since the real LeBron is absent from that batch. The other nine rejections (`Yao Ming`, `Chris Webber`, `Tim Duncan`,
  `Reggie Miller`, `Ben Wallace`, `David Thompson`, `Adrian Dantley`) were the model completing
  a Hall of Fame roster from a "HOF predictions" story, and none appears in the 11 leads.

---

- [x] **P34. An opinion rant on the community feed reaches the brief.** Reported by the
  operator 2026-08-18 from the delivered headline list. ~~**Measured and ready, not
  implemented.**~~ **Closed the same day** on the operator's go-ahead, commits `e40f99b`,
  `caed8dd`, `21d6e26`, plus `refactor`/`test` follow-ups.
  `[VERIFIED]` The 16:00 brief carried *"Fire Adam Silver"* by `/u/FineCan8373`, whose body
  begins *"Adam Silver is either a coward, corrupt, or both"*. That is an opinion piece, not
  reporting. P29's rule only catches questions, and this is an imperative.
  `[VERIFIED]` **The obvious rule fails, and this is the third time title classification of
  r/nba has.** Dropping untagged posts that do not lead with a name catches all 3 rants in the
  sample but also drops **11 real items**, including the breaking *"Lakers controlling owner
  Jeanie Buss opposes sale of family's stake to Bob Iger, Joshua Kushner"*. Unusable alone.
  `[VERIFIED]` **Two weak signals combine into a usable one.** Across 36 untagged r/nba posts
  from five captures, "does not lead with a name **and** is 12 words or fewer" drops exactly
  two, both rants — `Fire Adam Silver` (3 words) and `Take away their picks or stop pretending
  the cap exists` (10) — and no real item. The gap is comfortable: the shortest real item that
  does not lead with a name is 15 words, so 12 sits between them rather than on an edge.
  `[INFERRED]` "Leads with a name" is corpus-derived, not a verb list: it asks whether the
  first word is one the batch also writes in lower case, which is P20's `_ordinary_words`
  mechanism. That is the shape this project chose over a hand-written list once already.
  `[UNKNOWN]` **Where the shared helper should live**, and this is why it is not built.
  `_ordinary_words` is currently private to `processing/validate.py`. `processing/newsworthy.py`
  importing from the validator inverts the sensible layering; the tidier home is
  `processing/names.py`, which is already the shared text module. Either way it touches
  `validate.py`, `names.py`, `newsworthy.py` and tests, which is `OPERATING_RULES.md` §7's
  four-file tripwire, so it needs the operator's go-ahead rather than a quiet refactor.
  `[UNKNOWN]` Whether 2 positives in 36 posts is enough. It is a small sample and the rule
  should be re-measured on a wider capture. It shipped anyway, because the failure direction
  is a lost community post rather than a lost brief, and the drop log names every one.

  **What shipped**, and two decisions changed along the way.

  `[VERIFIED]` The helper did **not** move to `processing/names.py` as proposed. It also
  depends on `_depossess` and `_TRAILING_PUNCTUATION`, so the move would drag three functions
  through a module already regressed twice that day. Instead `ordinary_words` became public
  where it lives, and a new public `normalise_word` is shared by both callers. `[INFERRED]`
  Sharing the normalisation is the part that matters: two copies fail *quietly*, because a
  lookup against a set built by different rules simply never matches and nothing raises.

  `[VERIFIED]` **A reporter-tag exemption was written and then deleted before shipping**, on
  the P6 rule. A surviving mutant showed it cannot change a verdict: this rule only runs when
  `rejection_reason` returned None, and of 22 distinct tag tokens only `highlight` and
  `highlights` are ordinary words, both already in `REJECTED_TAGS`. Every other tag is a
  reporter's name, distinctive by definition. Restore it if a reporter tag is ever added whose
  lower-case form is ordinary English.

  `[VERIFIED]` Final measurement on 256 articles: drops **exactly two**, both rants, and
  nothing else. Mutation-tested five ways. **Two survived** the first campaign — the word
  ceiling, because the long-post test opened with "Lakers" and never reached it, and the tag
  guard, which was inert. One has a test now; the other is deleted.

---

- [ ] **P35. NFL stories reach the NBA brief.** Open, noticed 2026-08-18 in two separate
  runs. **Not investigated.**
  `[VERIFIED]` A dry run's prose carried *"Za'Darius Smith may choose the Falcons over the
  Browns due to Stefanski connection, but football news is for another day"*, and the live
  ordering check showed *"Za'Darius Smith free agency update: Could spurn Browns for..."* as
  story 12 of 12. Earlier the same day, `newsworthy.py` dropped *"Rookie QBs Carson Beck,
  Haynes King shine in Hall of Fame Game; MLB playoff predictions"* only because it was stale,
  not because it was football.
  `[INFERRED]` The cause is the feeds, not the pipeline: CBS and Yahoo publish league-wide
  sports RSS, and nothing downstream asks which sport an item is about.
  ~~`[UNKNOWN]` How often~~ **Measured 2026-08-26: rare.** Across 128 live articles from the
  four NBA-scoped feeds, **1 (0.8%)** reads as another sport, a CBS item pairing an NFL
  contract story with a list. `[INFERRED]` The feed URLs are league-scoped
  (`/rss/nba/`, `/nba/rss/`), so the leakage is cross-promotional rather than systematic, and
  a filter built to catch 0.8% would be more machinery than the problem deserves.

  `[INFERRED]` **The priority is therefore not the filter, it is the routing**, and they are
  different problems that happen to share a symptom. `ROADMAP.md` v0.5.0 and v0.6.0 add NFL,
  MLB and NHL, at which point every article needs to be *attributed* to a league so it reaches
  the right brief. Once that exists, the stray CBS item is handled by the same mechanism at no
  extra cost, and building a discard rule first would be work thrown away.

  So this stays open but is superseded in practice by the multi-league work. See ADR-015.

- [ ] **P36. Pipeline wiring in `main.py` is invisible to the suite.** Open, and it is a
  pattern rather than a defect. **Recorded 2026-08-18 after it happened three times in a day.**
  `[VERIFIED]` Three mutations that deleted a whole pipeline step left the entire suite green,
  because the calls sat inline in `main` where no test can reach them without the network:
  the failed-source collection, the vocabulary pass-through, and the relatedness ordering.
  Each was closed individually, two by extracting a named function (`fetch_news`,
  `build_story_groups`) and one by a pass-through test.
  `[INFERRED]` Extracting a function per defect works but is reactive, and the next inline
  step will be just as invisible. The question worth answering is whether `main.run` should be
  a sequence of named, individually testable steps by construction.
  `[UNKNOWN]` Whether that is worth the churn. Resolve by counting how much of `main` is
  currently unreachable from the suite before restructuring anything.

---

- [x] **P37. Four tests depended on the wall clock and rotted.** Found and fixed 2026-08-19
  by the tests failing on their own, six days after they were written.
  `[VERIFIED]` `test_an_untagged_question_on_the_community_feed_is_dropped`,
  `test_an_editorial_question_headline_is_kept`, `test_a_reporter_tag_exempts_a_community_question`
  and `test_a_community_statement_is_not_dropped_for_being_untagged` all called
  `is_newsworthy(article)` **without a `now`**, so the age rule compared a fixture article
  fixed at 2026-08-13 14:00 against the real clock. At 2026-08-25 that is 279h against a 168h
  limit, and all four failed.
  `[VERIFIED]` `tests/conftest.py` says exactly why this must not happen: *"A fixed `now`, so
  'is this too old' is arithmetic rather than a race against the clock."* The existing test at
  line 180 threads `now` correctly; the four added on 2026-08-18 did not.
  `[INFERRED]` Worth recording rather than quietly fixing, because the failure mode is
  delayed: these passed for six days and would have passed review, CI and a release. Anything
  that reads `datetime.now()` in a test is a time bomb with a known fuse length, and here the
  fuse was `MAX_ARTICLE_AGE_HOURS`.

---

- [x] **P38. The reproduction captures live in `/tmp` and were lost.** ~~Open, and it has now
  actually happened. **Not fixed.**~~ **Fixed 2026-08-25** on the operator's instruction,
  commits `456c73b`, `2c1664c`, `ead9c51`, `053a679`.
  `[VERIFIED]` 2026-08-25: the operator shut the machine down for a break, `/tmp` was cleared,
  and every live feed capture from 2026-08-17 to 2026-08-19 is gone. Six days of batches, the
  only assets that could reproduce a validation failure against real data.
  `[VERIFIED]` The threshold sweep that corrected P33 had to be re-run against
  `tests/fixtures/` instead, which worked but is a 76-article snapshot rather than the 288
  articles the original measurement used. Every number in P33 measured on the live corpus is
  therefore no longer reproducible.
  `[INFERRED]` The risk was flagged early and never acted on, which is the whole finding: the
  captures were treated as scratch because they lived in a scratch directory, while in practice
  they were the evidence base for a dozen decisions.
  ~~`[UNKNOWN]` What to keep.~~ **Answered: keep the batch, not the feeds.**

  `[VERIFIED]` Every diagnosis this week needed the same thing, and it was never the feeds: it
  was **the dozen articles that were actually summarised**. Reconstructing that took two steps
  each time, reading delivered ids out of `seen_articles` and matching them against a whole
  feed capture, and both halves broke within a week.

  `storage/evidence.py` writes one JSON record per run into `evidence/`, holding the batch, the
  accepted prose or `null`, any flagged claims and any failed sources. `[VERIFIED]` Measured on
  a real run: **6,414 bytes for 12 articles**, against roughly 400 KB for the four feeds it came
  from. At three runs a day that is under 6 MB a year, and it is pruned to the newest 120
  records, about six weeks.

  `[VERIFIED]` `load_batch` reads it back as real `NewsArticle` objects rather than
  dictionaries, so a replay exercises the same schema the pipeline does. Verified end to end:
  a live run wrote a record and it round-tripped into 12 articles.

  `evidence/` is git-ignored. `[INFERRED]` Feed text is the C3 exposure ADR-009 exists to avoid
  and the directory grows with every run, so the promotion path stands: move a specific batch
  into `tests/fixtures/` when a task cites it, which is what the three fixtures there already
  are.

  `[VERIFIED]` Recording never raises. A failed write is logged and swallowed, because losing a
  delivered brief to protect its evidence would be an absurd trade. Mutation-tested four ways
  including letting the exception escape, and all four fail.

  `[INFERRED]` This does not recover what was lost. The 288-article measurements behind P33 and
  P4 remain unreproducible, and the six purged days of delivery history are gone. It stops the
  next one.

---

- [x] **P39. A dry run deleted six days of dedup state.** Found and fixed 2026-08-25, the
  same day the cause was introduced.
  `[VERIFIED]` The seen-store purge added for GitHub #10 sits inside the `with SeenStore(...)`
  block at `main.py:185`, and the `--dry-run` early return is at line 328. So the purge ran
  first, on every dry run, while the log said *"dry run: nothing sent, nothing recorded"*.
  `[VERIFIED]` It cost real state. A `--date 2026-01-15 --dry-run` issued while investigating
  #3 removed every article delivered before 2026-08-18, leaving one day of 45 rows where six
  days had been. Those rows were the record used to reconstruct batches for P32, P33 and P4.
  `[INFERRED]` No article was put at risk of re-delivery, because everything purged was past
  `MAX_ARTICLE_AGE_HOURS` and would be dropped as non-news anyway. The damage was to
  **evidence**, not to behaviour, which is why it was invisible.
  Fixed in `54336c2` by guarding the purge, with a regression test in `505b838` asserted
  against `main` rather than the store: the store was right either way, and the bug was in who
  called it. Mutation-tested, and the mutant fails.
  `[INFERRED]` Two lessons worth keeping. A command that promises to change nothing must be
  audited against everything it touches, not just the thing it obviously does. And this is the
  second time in a week that reproduction evidence has been destroyed by something incidental,
  after `/tmp` was cleared (P38) — the evidence base is being treated as more durable than it
  is.

---

- [ ] **P40. Two reports of one story at different stages are blended into the wrong tense.**
  Open, found 2026-08-26 by the operator reading a delivered brief. **Not fixed.**
  `[VERIFIED]` The brief said *"Thompson signed a two-year deal with the Heat and is expected
  to clear waivers soon."* He had already cleared them. The batch carried both stages:

  - CBS, earlier: *"Klay Thompson **expected to sign** with Heat after agreeing to buyout"*
  - ESPN, later: *"Thompson **clears waivers**... officially agreed to a two-year deal... after
    clearing waivers on Sunday"*

  The model took the completed fact from the later report and the pending tense from the
  earlier one. `[VERIFIED]` Every other claim in that brief is correct, including four separate
  reports of the Brandon Williams signing reconciled into one accurate paragraph, so this is
  narrow rather than general.

  `[VERIFIED]` **Nothing currently detects it and the existing checks cannot.** Grounding sees
  real names, and the P5 pair check sees `thompson`, `heat` and `waivers` co-occurring in one
  article, which they do. Both are about *entities*; this is about *time*.

  `[INFERRED]` **P30's relatedness ordering may make it likelier**, which is worth stating
  plainly rather than defending. Before ordering, two reports of one story arrived scattered
  and were summarised separately; now they sit adjacent and get merged, which is the intended
  behaviour and also the condition for this failure. The readability fix and this defect share
  a cause.

  **Addressed 2026-08-26 by giving the model the information it never had**, on the operator's
  instruction to add a time signal so newer news is favoured.

  `[VERIFIED]` The root cause was simpler than any of the options first listed: `build_prompt`
  sent **title and summary only**. There was no timestamp, no ordering hint, nothing. The model
  was not ignoring recency, it was never given any. Each item now carries a relative age, and
  `NOTES_PROMPT` says to state a shared event as the newest item does.

  `[VERIFIED]` On the real batch the signal is unambiguous: the CBS report reads `[3d ago]` and
  the ESPN one `[just now]`, three days apart.

  `[INFERRED]` Relative age rather than a timestamp, because the question is "which of these is
  later" and an age asks it directly, while an ISO timestamp turns it into a subtraction that a
  7B model does badly. Under an hour reads "just now" so a flurry of reports on one story does
  not collapse to "0h" and become indistinguishable again.

  `[UNKNOWN]` **Whether it works.** This is a prompt change, and `TASKS.md` P6 records one that
  was measured to move nothing. The difference is that this adds *information* rather than
  *instruction*, but that is an argument, not a measurement. Watch the next few runs where a
  batch carries two stages of one story.

  **The Harden clause has an explanation, from the operator 2026-08-26.** *"James Harden
  returned to the Cleveland Cavaliers **after a brief stint away**"* traces to the source
  headline saying Harden *"returns to Cavaliers"*. `[INFERRED]` So the model is elaborating on
  the word "returns" rather than inventing an event, and Harden had in fact signed a new
  contract. That reclassifies it: not a fabrication, but unsupported colour added to a true
  statement, which no entity check can see and which is a much smaller problem than a wrong
  tense on a completed transaction.

---

- [x] **P41. Windows Task Scheduler is an option but nothing makes it usable.** Closed
  2026-08-26 on the operator's request, commits `1e2d680`, `6533396`, `61d2312`.
  `[VERIFIED]` The trigger for this was a real missed brief. No 08:00 delivery on 2026-08-26;
  `/var/log/syslog` showed cron logging 3 to 7 entries every hour up to 00:00 and then
  **nothing from 01:00 to 08:00**, including the system's own ten-minute jobs. The host slept,
  WSL was suspended, and cron does not run a job it missed.
  `[VERIFIED]` **`uptime` is not evidence of wakefulness in WSL2** and it misled this
  investigation. It reported 8h27m of continuous uptime across the window in which nothing ran,
  because the counter keeps going while the VM is paused. `docs/SCHEDULING.md` now carries the
  syslog-gap check instead.

  **What shipped.** `scripts/schedule_windows.py` prints the registration command with both
  path forms derived. `[INFERRED]` The two forms are the actual trap: `C:\...` for Windows and
  `/mnt/c/...` for WSL, and a task with one of them wrong registers cleanly and then fails
  every run, silently and on a schedule. It prints rather than registers, because registering
  needs Administrator and changes the machine.

  `[VERIFIED]` Two settings the hand-written block lacked, both checked through PowerShell
  rather than assumed:
  - `-RepetitionDuration ([TimeSpan]::MaxValue)`. Omitting it leaves `Duration` empty with
    `StopAtDurationEnd: True`, and `[UNKNOWN]` whether Windows reads that as "forever" or "stop
    at the default". Stating it produces `P99999999DT23H59M59S` and removes the question.
  - `-StartWhenAvailable`, so a run missed while the machine was off happens late rather than
    not at all. That is the entire difference from cron, rather than merely running elsewhere.

  `[VERIFIED]` The emitted quoting was executed end to end, not eyeballed: `powershell.exe`
  invoking `wsl.exe -e bash -c "cd '...' && ./.venv/bin/python main.py --help"` reached
  `main.py` and printed its usage.

  `[INFERRED]` **This does not start v0.4.0 early.** That milestone's dependency on ADR-014 is
  about *intervals* — running more often means more upstream fetches — and a different trigger
  at the same 8-hour cadence changes no fetch behaviour. The scheduler half is independent of
  ADR-014; the interval half is not, and is still waiting.

  `[VERIFIED]` Mutation-tested four ways. Two survived the first attempt because `replace(...,
  1)` hit the **docstring** mention rather than the template, so the command was unchanged and
  the tests correctly passed. Applying is not the same as applying where intended; the second
  campaign asserted the emitted command actually changed.

---

- [ ] **P42. Interval becomes a bounded choice, and the brief's size scales with it.**
  Open, specified by the operator 2026-08-26. **Belongs to v0.4.0 and v1.0.0; not started.**
  8 hours stays the standard until then.

  `[VERIFIED]` **The bounds are measured, not guessed.** Across 13 scheduled runs at 8 hours,
  new articles surviving deduplication were min 10, median 23, max 81 — about **3.9 an hour**
  in the offseason. At 30 minutes most runs would deliver nothing at all, since `main.py`
  already logs "nothing new to report" and sends no message. Roughly 2 hours to 2 days is the
  usable band. `[UNKNOWN]` These are offseason rates and should be re-measured in season.

  `[VERIFIED]` **Scaling the output limit alone will not work**, which is the finding worth
  keeping. `DEFAULT_MAX_ARTICLES = 12` caps what reaches the summariser and **8 of 22 logged
  runs hit exactly 12**, so the cap already binds at 8 hours. At 2 days it would discard about
  175 of 187 articles and still produce a twelve-story brief. A longer interval would lose
  more news rather than deliver more.

  `[INFERRED]` Three quantities move together and should be derived from one interval setting
  rather than tuned apart: the story cap, `DEFAULT_SUMMARY_CHARS` (1024), and the chunk count,
  since `summarize.py` splits above `CHUNK_SIZE = 5`. `[VERIFIED]` Run time scales too — the
  2026-08-26 00:00 run took **10m36s** for 12 stories in 3 chunks, so a 2-day brief may
  approach a timeout and that needs measuring before a ceiling is promised.

  `[INFERRED]` Deriving all three from the interval preserves PRD D1: the run still defines
  the window, and nothing gains a second source of truth about how much news a brief covers.

  Recorded in `docs/PRD.md` D6 with requirements R7 and R8, and in `ROADMAP.md` under v0.4.0
  and v1.0.0.


- [x] **P43. Three tests drove the real `main` straight into the live games API.** Found
  2026-08-26 when a pre-commit `make check` failed on a 429 from `api.balldontlie.io`, with a
  traceback about a source the test was not testing. **Fixed — `40d417d`.**
  `[VERIFIED]` `tests/test_db.py` calls `main.main()` four times and stubbed the games adapter
  zero times. Three of the four therefore fetched games for real: `test_a_dry_run_does_not_purge`,
  `test_a_poll_stores_without_delivering` and `test_a_default_run_still_polls_and_delivers_in_one_pass`.
  The fourth passes `--no-poll`, which already contacts nothing, which is the whole point of
  ADR-014.
  `[VERIFIED]` **Blocking the network proves nothing here, so the calls were counted instead.**
  Every adapter catches its own failure and returns `[]` (`CLAUDE.md` §5 rule 6), so a refused
  call is indistinguishable from a quiet source: all 31 tests passed with `requests.get`
  raising. A counting plugin separated "did not need the network" from "asked and was refused".
  - Proof — before: `test_a_dry_run_does_not_purge: 1 call -> https://api.balldontlie.io/v1/games`,
    and the same for the other two. After: **none**. 31 passed both times.
  - Proof — `make check` → **411 passed, 1 xfailed**, exit=0, and the suite dropped from ~16s
    to 7.8s because three tests no longer wait on an upstream.
  `[INFERRED]` The fix clears `BALL_DONT_LIE_API_KEY` rather than stubbing the adapter, so the
  real skip path (`settings.can_fetch_games`) still runs. None of the three assert anything
  about games; they are about the poll/deliver seam.
  `[UNKNOWN]` Whether the 429 also explains the failure seen in that same run — the poll-only
  test's captured output showed a brief being printed, which cannot happen past
  `if args.poll_only: return 0`. **Not reproduced in six consecutive green runs.** Do not
  record a cause for it until it is seen again; `SESSION.md` §11 lists concluding from one run
  as this project's repeat mistake.
  - **What to watch:** if it recurs, capture the failing run's `main.py` state before anything
    else. `CLAUDE.md` §8 keeps live sources behind `@pytest.mark.network`; the general lesson
    is that a test driving the real `main` reaches everything the real `main` reaches, which is
    the same leak `EVIDENCE_PATH` was pointed at temporary storage to close.

---

- [x] **P43. A test passed locally and broke CI because it read the filesystem.** Found and
  fixed 2026-08-26 by the release gate, commits `13e0665` and `59eea85`.
  `[VERIFIED]` `test_the_generated_schedule_follows_the_configured_interval` drove
  `scripts/schedule_windows.main`, which resolves the **real project path**. Here that is
  `/mnt/c/DSC/...` and translates to a Windows path; on a CI runner it is
  `/home/runner/work/SportWire/SportWire`, which has none, so the command correctly refused and
  returned 1. **The code was right in both places and the test only worked in one.**
  Fixed by extracting `resolve_interval`, so config resolution is testable without a
  filesystem, and asserting the emitted command against an explicit path.

  `[VERIFIED]` **The release gate worked.** `release.yml` runs `make check` before publishing,
  so no GitHub release was created for the red commit. That guard was written because "a tag on
  a red commit is a claim, published under a version number, that something works", and this is
  the first time it has actually caught one.

  `[INFERRED]` **Third of this shape in a week, and the pattern is worth naming.** P37 was four
  tests reading the wall clock, which rotted after six days. P42's wiring tests first measured
  grouping and then per-source capping rather than what they claimed. This one read the
  filesystem. In each case the code was correct and the test depended on something about the
  machine it ran on. The common fix is the same: give the test the input explicitly rather than
  letting it discover one.

---

- [ ] **P44. Judge the brief's writing with a second model pass.** Open, proposed by the
  operator 2026-08-26. **Not built, and the cost is smaller than the last time this was
  considered.**

  The idea: after a summary survives validation, ask a model whether it reads well, and use
  that to steer the writing rather than the facts.

  `[VERIFIED]` **This is not the option rejected under P5.** That one was a second-pass check
  of **every sentence against the source notes**, rejected because it "doubles an already 5 to
  9 minute run". A style judge is **one call on a finished paragraph**, against a chunked
  summarisation that already makes 3 or 4. Measured across 13 dated runs, summarisation takes
  0.3 to 10.9 minutes, median 3.9, so one more call is a fraction rather than a doubling.

  `[INFERRED]` **Style is a better fit for a model judge than facts are**, which is the real
  argument. ADR-012 measured that every local model tested fabricates names and figures, so a
  model is the wrong tool for checking truth. Style has no ground truth to fabricate against:
  asking "does this read like a news brief or like a list" is a judgement, and a judgement is
  what a model can actually give.

  `[VERIFIED]` There is already a specific defect it might catch. `processing/summarize.py`
  records that a preamble appears despite an explicit instruction against it, and
  `validate.py` counts preambles without rejecting for them, on the grounds that a preamble is
  "a style problem, not a truth problem". Nothing currently acts on that count.

  `[UNKNOWN]` Whether it changes anything. `[VERIFIED]` A prompt change of a similar shape was
  measured for names and moved nothing (3/6 against 3/6), and P6 is the standing warning about
  mechanisms that read as protection and cannot be shown to work. Before building: count how
  many delivered briefs have a style defect worth catching, using the preamble flag already in
  the log. If the answer is few, this is decoration.

  `[INFERRED]` It should never gate delivery. A brief that is factually sound but reads poorly
  must still arrive; the judge's output belongs in the log, or at most as a retry hint, on the
  same reasoning that made the P5 claim marker advisory rather than a rejection.

- [ ] **P45. International league coverage is accepted for now, to be tightened later.**
  Open, operator decision 2026-08-26: *"I'm fine with news from international leagues. However,
  we'll tighten that later on."*
  `[INFERRED]` Recorded so it is a decision rather than an oversight. The feeds are
  NBA-scoped, so EuroLeague, NBL and FIBA items arrive only when a US outlet covers them,
  which is roughly the right filter by accident.
  `[VERIFIED]` It is not hypothetical: a captured batch carried *"On February 25, 2024, at the
  Ariake Coliseum, Japan defeated China 76-73 during Window 1 of the FIBA qualifiers"*, which
  the retrospective rule dropped for being about the past rather than for being international.
  `[UNKNOWN]` What tightening should mean. `[INFERRED]` Once ADR-015's league attribution
  exists, "NBA" versus "international basketball" is the same routing problem as NBA versus
  NFL, so this should reuse that mechanism rather than become its own filter.

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


- [ ] **P46. Only one Reddit feed can be fetched per run, which blocks r/nfl.** Open, found
  2026-08-26 while adding the NFL feeds for v0.5.0.

  `[VERIFIED]` r/nfl works fine on its own: `RssNewsAdapter('r/nfl', ...)` returned 25
  articles with `last_error=None` after a quiet period. It fails whenever r/nba was fetched
  shortly before it, in the same run:

  ```
  0.5s  ESPN          17 articles  err=None
  1.7s  CBS Sports    36 articles  err=None
  3.2s  r/nba         25 articles  err=None
  3.7s  r/nfl          0 articles  err=HTTPError   (429 Too Many Requests)
  ```

  `[VERIFIED]` Spacing does not fix it. The same pair was retried with a 5 second gap and
  again with a 30 second gap, from a rested state both times, and the second request failed
  identically. So this is not a politeness delay problem, it is a per-IP budget measured over
  minutes. Adding a sleep between requests would cost every run time and buy nothing.

  `[VERIFIED]` Separately, the User-Agent matters more than expected. `curl` sending a
  spoofed `Mozilla/5.0` gets HTTP 403 from both subreddits, while the adapter's declared
  `SportWire/0.1 (+github.com/AlphaNerdFx/SportWire)` gets 200. Reddit is rejecting the
  pretend browser and accepting the honest bot, which is the opposite of the usual guess and
  is worth not undoing by "fixing" the User-Agent later.

  **Decision for now: ship NFL with the three editorial feeds and no community feed.** They
  return 113 articles between them, which is not short of material. `[INFERRED]` Alternating
  the two subreddits across runs would work but adds stored state and halves community
  coverage for each league, which is a lot of machinery for a feed that is a supplement.

  Resolve by: authenticating to Reddit. `[INFERRED]` An OAuth client gets a much larger
  request budget than anonymous access, which would let both subreddits be fetched in one
  run. Free, official, and no terms problem, so it fits C2 and C3. This is the same fix
  already suggested for general rate-limit headroom, now with a concrete thing it unblocks.

- [x] **P47. An ordinary word at the end of a name could ground the whole name.** Closed
  2026-08-26, found by a test written for something else.

  Adding NFL teams to `test_a_team_is_never_exempt_from_grounding` failed on
  `New England Patriots`. The cause was not the new football vocabulary. It was the
  either-end grounding rule from P25: a name is grounded when either its first or last word
  appears in the sources, and "new" appears in almost any batch of English.

  `[VERIFIED]` Against the source headline "LeBron tests new talent with YouTube golf page",
  which names no team at all:

  ```
  before:  New England Patriots  let through
           New York Knicks       let through
           New Orleans Pelicans  let through
           Kansas City Chiefs    refused
  after:   7 of 7 refused
  ```

  So this predates the football feeds. It could not show up earlier because no team in the
  31-name list began with an ordinary English word, and the basketball teams that do
  (`New York Knicks`, `New Orleans Pelicans`) were never in it.

  **Fix:** an end may only identify a name when the sources do not also write that word in
  lower case. That is the same evidence `_index_source_names` already uses to decide a
  headline's capitalisation is not proof of an entity, so no new mechanism was added, an
  existing one was applied in a second place.

  `[VERIFIED]` Cost measured before shipping, over 327 articles from the live feeds plus the
  recorded evidence, holding 399 distinct proper names the sources wrote themselves:
  **0 of 399 verdicts changed.** Every real name stays grounded, because a real name either
  appears verbatim or has a non-ordinary end. The rule only bites on names whose *only*
  claim to grounding was an ordinary word.

  `[INFERRED]` Worth noting how this was found. The test was written to check that the new
  NFL vocabulary had not opened a hole. It had not, and it found an older and wider one
  instead. The complement test earns its place here.

- [x] **P48. A possessive headline welded a team to a player and then refuted the team.**
  Closed 2026-08-26, found by the first football brief falling back to a headline list.

  `[VERIFIED]` The run at 21:06 rejected all three attempts:

  ```
  attempt 1 rejected (invented names: Cincinnati Bengals)
  attempt 2 rejected (invented names: Cincinnati Bengals, Minnesota Vikings)
  attempt 3 rejected (invented names: Cincinnati Bengals, Minnesota Vikings, Carolina Panthers)
  ```

  All three teams are named by the sources. The cause was ESPN's house style:

  ```
  Vikings' Jeshaun Jones suspended three games for violating NFL substance abuse policy
  Panthers' Canales backs Young, defers on deal
  ```

  The apostrophe is not trailing punctuation, so the capitalised run walked straight through
  it and indexed one name, `{jeshaun, jones, vikings}`. The refutation rule then read that as
  an entity keyed on "vikings" that disagrees with `Minnesota Vikings` about everything else,
  and refused the real team.

  **Fix:** a possessive ends the name it follows, exactly as a comma already did. The player
  after it survives as a name of their own, so nothing is lost from the index.

  `[INFERRED]` This reads as a football bug and is not one. The construction is just as
  common in basketball writing. What differs is that a basketball team usually appears
  somewhere else in the batch in a plain form, and one agreeing same-key name is enough to
  acquit. "Vikings" appeared twice in that batch and both were possessive.

  `[VERIFIED]` Measured before shipping, over 350 articles from the live feeds and the
  recorded evidence:

  - Full team names against their own league's batch: NFL **16/18 accepted before, 17/18
    after**, the gain being `Minnesota Vikings`. NBA unchanged at 6/8.
  - The 398 names the sources write themselves: **0 changed**, in either direction. Those are
    already grounded verbatim, so the rule only reaches expanded forms, which is the
    population it was written for.

  `Cincinnati Bengals`, the first name in that log, was fixed separately by adding "qb" to
  the competition vocabulary: the batch carried "Bengals QB Joe Burrow" and indexed
  `{bengals, qb}` as an entity.

- [ ] **P49. "North Carolina" refutes "Carolina Panthers".** Open, found 2026-08-26 while
  measuring P48.

  `[VERIFIED]` After the possessive fix, one of eighteen NFL teams is still refused:

  ```
  index['carolina'] = [{'carolina', 'north'}]
  ```

  Nothing is wrong with that index entry. "North Carolina" is a real proper name, it is two
  words like `Carolina Panthers`, so the P20 length rule permits it to refute, and it is the
  only name keyed on "carolina" so there is nothing to acquit.

  `[INFERRED]` This is the key-sharing weakness recorded in P24 rather than a new defect: two
  unrelated entities share an identifying word and the rule cannot tell them apart. What is
  new is a case where the collision is between a place and a team named after that place,
  which will keep happening. Carolina, Washington, and the state names generally.

  Resolve by: deciding whether a source name may refute a summary name when the two share
  only a *place* word. `[UNKNOWN]` Whether that can be decided without a list of places,
  which would be another hardcoded vocabulary and needs the same argument P23 had. Do not
  build it before measuring how many names it would actually change.

- [x] **P50. An honour standing beside a team refuted the team.** Closed 2026-08-26, found
  by re-running the football brief after P48 and watching it fall back again.

  `[VERIFIED]` The batch of twelve leads named the Bengals four times and Cincinnati once,
  and the summary was refused on all three attempts for `Cincinnati Bengals`:

  ```
  index['bengals'] = [{'all-pro', 'bengals'}]
  ```

  from "Ja'Marr Chase injury scare: Bengals All-Pro goes down awkwardly in practice". One
  entry, keyed on "bengals", disagreeing with `Cincinnati Bengals` about everything else, and
  nothing else keyed there to acquit it.

  Two things were wrong and both are fixed:

  1. `all-pro` was not in `_COMPETITION_VOCABULARY`, although `all-star`, `all-nba`,
     `all-defensive` and `all-rookie` all were. It is the football member of that set.
  2. More importantly, the index dropped only *ordinary* words from a name, never competition
     vocabulary. So even after adding it, "Bengals All-Pro" would still have been indexed as
     an entity. Grounding has always treated a structural term as identifying nobody; the
     index now agrees with it.

  `[VERIFIED]` Measured over 373 articles from the live feeds and the recorded evidence, 304
  real two-word names and 500 generated blends:

  - Real names grounded: **304/304 before, 304/304 after.** No change, and none expected:
    those names appear verbatim.
  - Blends refused: **461/500 before, 452/500 after.**

  That second number is the honest cost and it looks worse than it is. `[VERIFIED]` All
  eleven blends that stopped being refused have a competition term as one half:

  ```
  AFC Ten     Bryce QB    Great NFL   NBC NFL    NFL Bartelstein
  Penn North  Zamir NFL   The Forecast   Agent Forecast
  Christmas Athletic   Guggenheim NBA
  ```

  `[INFERRED]` None of those is the failure this rule exists to catch. That failure is
  `Jayson Brown`, a person fused from two real players, and it involves no structural term at
  all. The generator that produced these pairs any first word with any last word, so it
  manufactures combinations a summariser would never write. What the measurement really shows
  is that the index was catching junk built from league words, and stopped.

  `[INFERRED]` The trade is also asymmetric in the way that matters here. A false accusation
  costs the whole brief its prose, which is the outcome the operator asked never to see
  again. A missed blend costs one wrong name inside a paragraph that is otherwise delivered.
