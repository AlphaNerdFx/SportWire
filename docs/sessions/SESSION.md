# SESSION.md — Current Working State

**Last updated:** 2026-09-24
**Repository:** https://github.com/AlphaNerdFx/SportWire (public)
**Next session should begin with:** §10.

> **Where the documents live changed on 2026-09-03.** Everything except `README.md`,
> `CLAUDE.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md` and `CHANGELOG.md` now
> sits under `docs/`, and the GitHub wiki was retired into it. `docs/README.md` is the index
> and `CLAUDE.md` §9 has the map. This file is `docs/sessions/SESSION.md`.

> **Evidence tags:** `[VERIFIED]` = a command was run and its output seen. `[INFERRED]` =
> reasoned from stated evidence. `[UNKNOWN]` = not known; do not guess. `CLAUDE.md` §0.
>
> **Tags expire.** A `[VERIFIED]` claim from a previous session is `[Likely]` today —
> external services change. `OPERATING_RULES.md` §2. This has already cost this project one
> full data source: `cdn.nba.com` was documented as working "from anywhere" and returns 403
> from every network tried.

---

## 1. Project Overview

| Field | Value |
|---|---|
| **Name** | SportWire, an NBA and NFL news brief delivered to Telegram |
| **Stage** | **Working and running unattended.** A brief is due every 8, 12 or 24 hours (default 8), one per league since 2026-08-26. v1.0.0 is NBA and NFL (decided 2026-09-24). |
| **Version** | `[VERIFIED]` 2026-09-24: **v0.5.12** is the latest tag. `git tag --sort=-v:refname` |
| **Repo** | Public, MIT, CI green. `[VERIFIED]` 7 issues open, `gh issue list` |
| **Wiki** | Retired into `docs/` on 2026-09-03; one signpost page remains |
| **Tests** | `[VERIFIED]` **466 passed, 1 xfailed** (2026-08-26 `make check`, exit 0). See §8 |
| **Runtime** | `[VERIFIED]` WSL2 Ubuntu, Python 3.10.12, `.venv` (68 MB, 21 packages) |
| **Sources** | Basketball: ESPN, CBS Sports, Yahoo Sports, r/nba. Football: ESPN, CBS Sports, Yahoo Sports. Games: balldontlie, basketball only |
| **Delivery** | Telegram `@sportwire_news_bot`. One brief per league, only the first message rings the phone |

---

## 2. What exists and works

`[VERIFIED]` All of the following has run in production, unattended, on a schedule:

| Module | Job |
|---|---|
| `config/settings.py` | The only place `.env` is read. Paths anchored to `PROJECT_ROOT`, not the cwd. |
| `models/schemas.py` | `GameData`, `NewsArticle`, `GameHighlight`, `SeriesContext`. All frozen. |
| `ingestion/base.py` | Two source ABCs. `fetch()` owns the try/except so adapters cannot skip it. |
| `ingestion/rss_news.py` | One adapter, **seven feeds across two leagues**. Reads **both** RSS 2.0 and Atom. |
| `ingestion/nba_games.py` | balldontlie games, per-period scores, team ids as a side channel. |
| `processing/newsworthy.py` | **The only module that removes articles.** Age, content tags, retrospective phrases, rankings and guesses, and since 2026-09-03 a story about another sport (P35). |
| `processing/dedup.py` | Exact id across runs; near-identical titles within a run; and since P68 a retelling of a story shown in the last 24 hours (48 at a 24-hour interval) is dropped unless it names someone new. |
| `processing/priority.py` | Sorts high/medium/low, with tonight's teams as a within-tier tiebreaker. |
| `processing/cluster.py` | Groups articles covering one story, using `names.py`'s scanner since 2026-09-24 (P70, partly fixed); caps stories per source, scaled with the interval (P42). |
| `processing/highlights.py` | Comeback, overtime, closest finish, wire-to-wire, biggest quarter, second-half takeover. |
| `processing/summarize.py` | `Summarizer` ABC + Ollama, map-reduce chunking, validated retry. |
| `processing/validate.py` | Checks every name and figure against sources. **Fails closed.** Ends a scanned source name at a team or a position (P67). |
| `processing/names.py` | The shared name vocabulary: the scanner, team nicknames by league, positions, and the sports this project does not cover. |
| `processing/openrouter.py` | Hosted summarizer, dormant until a key exists. |
| `storage/db.py` | Seen-ids, game results, local head-to-head. |
| `delivery/` | `DeliveryChannel` ABC, Telegram, stdout, three-message formatting. |
| `main.py` | The single entrypoint. The only file naming a concrete class. |

---

## 3. How it is operated

~~Cron, every 8 hours~~ `[VERIFIED]` 2026-09-24, `crontab -l`: cron wakes the program every 30
minutes and `--if-due` sends only when `POLL_INTERVAL_HOURS` (8, 12 or 24) has passed since the
last brief, so a sleeping PC delays a brief instead of losing it (P58):

```cron
*/30 * * * * cd "/mnt/c/DSC/.../SportWire" && ./.venv/bin/python main.py --if-due >> ".../logs/sportwire.log" 2>&1
```

Logs live in `logs/` (gitignored) rather than `/tmp`, which WSL clears on restart.

```bash
make dry-run   # fetch and print, send nothing, record nothing
make run       # fetch and send now
make check     # ruff + pytest + documentation links, exactly what CI runs
```

`[Likely]` The one fragility: WSL cron stops if the WSL instance shuts down. If briefs stop
with no error, check `service cron status` first. `docs/reference/SCHEDULING.md` §Option B has a
Windows Task Scheduler command that survives reboots.

---

## 4. The working agreement (changed mid-project — read this)

`[VERIFIED]` ADR-006 originally specified that the human writes signatures, docstrings and
test assertions while the agent writes only bodies. **The operator reversed this on
2026-08-05:** *"You'll write the code not me."*

`OPERATING_RULES.md` §0 now governs:

- **The agent writes the code, tests and documentation. The operator does not.**
- **The agent never sets the operator code to write** — not as a task, remedy or exercise.
  `[VERIFIED]` This has already been violated once: after the reversal, the agent proposed
  the operator rewrite `processing/dedup.py` as a remedy for a failed knowledge check. That
  was the superseded contract returning under another name.
- **The agent explains as it goes**, at the point a concept first appears.
- **Understanding is still required and still ranked above shipping** (`CLAUDE.md` §1). It is
  demonstrated by explaining, not authoring.
- When an explanation does not land, that is evidence the **code** is too clever. Simplify
  it; do not retest the operator.

---

## 5. Decisions

~~`[VERIFIED]` **Only six ADRs exist as files:** 003, 009, 010, 011, 012, 013.~~ **Stale, and
corrected 2026-08-27.** `[VERIFIED]` `ls docs/decisions/` now lists **nine**: 003, 009, 010,
011, 012, 013, 014, 015, 016. Decisions 001–008 were taken on 2026-08-03 and recorded **in
this table only** — the numbering implies files that were never written. Either backfill them
or stop citing them as documents; do not assume a reader can open one.

`[INFERRED]` The stale count is worth leaving visible rather than quietly editing. A
`[VERIFIED]` claim with a command beside it went false because three ADRs were added and this
line was not re-run, which is exactly the decay `OPERATING_RULES.md` §2 warns about: a tag
records when something was checked, not that it stays true.

| ADR | Decision | File? |
|---|---|---|
| 001 | Fork clean rather than salvage the prototype | no |
| 002 | Telegram, not WhatsApp — no per-message cost, no ban risk | no |
| 003 | balldontlie for games; `cdn.nba.com` is dead (403 from every network) | **yes** |
| 004 | SQLite. Reaffirmed against a Postgres proposal — open-sourcing *strengthens* the case | no |
| 005 | Semantic dedup declined **on evidence**: ~~612 pairs, max 0.439~~ → **540 pairs, max 0.425** (corrected 2026-08-13, P8: the original was measured live and does not reproduce from the committed fixtures; the decision is unchanged and slightly stronger) | no |
| 006 | **Superseded.** Human writes interfaces, agent writes bodies — reversed 2026-08-05 (§4) | no |
| 009 | ESPN RSS for news — a published feed is an invitation; scraping is not | **yes** |
| 010 | No individual player statistics. Every free source blocked, paywalled or ToS-barred | **yes** |
| 011 | Slice 1 retrospective | **yes** |
| 012 | Summarisation: off → **on**, with a validator and retry | **yes** |
| 013 | OpenClaw may orchestrate SportWire externally, but must never be a dependency | **yes** |
| 014 | Fetching runs on its own cadence, independent of when briefs are delivered | **yes** |
| 015 | One brief per league, each on its own schedule | **yes** |
| 016 | The smallest model that survives validation writes the brief; bigger ones are the fallback | **yes** |

---

## 6. Where the summarizer actually stands

This consumed most of 2026-08-06 to 08-12 and the state is nuanced.

**On, by default, using `mistral:7b` locally.** Every summary is checked by
`processing/validate.py` before it can be delivered; a failed check falls back to the
headline list.

~~`[VERIFIED]` **No fabrication has ever reached the phone.**~~ **Corrected 2026-08-13.**
~~`[VERIFIED]` **No invented _name_ has reached the phone. A false _claim_ has.**~~
**Corrected again 2026-08-14 — this claim has now been wrong twice, each time narrowed
rather than abandoned.** `[VERIFIED]` **An invented name has reached the phone.** The 16:00
brief that day delivered *"January will see Giannis Antetokounmpo and Jayson Brown
reunions"*, on attempt 1. There is no Jayson Brown: the model fused Jayson Tatum and Jaylen
Brown, and last-word grounding accepted the result on "Brown". `[VERIFIED]` The old rule
caught **0 of 5,442** such blends measured on the committed fixtures — the claim was never
true, it was merely never tested. Fixed in `f1a38a6`; see TASKS.md P12.

`[INFERRED]` **The pattern worth keeping is the retraction itself.** Both corrections took
the form "the strong claim was wrong, here is a narrower one" — and the narrower one failed
within a day. A third narrowing is available ("no invented name reaches the phone *when the
name is not camelCase*", per P13) and should be resisted; the honest statement is that the
validator's coverage is **measured**, not complete.

The 08:00
brief that day passed validation on attempt 1 asserting that Westbrook's retirement "marked
the end of playoff runs for basketball greats like Kobe Bryant, Tim Duncan, Dirk Nowitzki, and
Kawhi Leonard" — and Kawhi Leonard is active. Every name in that sentence is grounded, which
is exactly why it passed. See P5 below; the original claim was true of the failure class the
validator was built for and false of the one nobody had looked for.

**What made it work was cleaning the input, not changing the model.** `[VERIFIED]` The same
`mistral:7b` went from 0/3 to 3/5 on validation after retrospectives were filtered, stale
articles dropped, duplicate coverage merged and sources capped.

**Two of my own bugs looked like model failures and were not:**

- `[VERIFIED]` The validator required *every* word of a name to appear in the sources, so it
  rejected "New York Knicks" whenever a source wrote "Knicks". Three correct summaries were
  thrown away. Grounding now accepts the **last** word — the identifying one.
- `[VERIFIED]` `" ".join(text.split())` collapsed newlines, so a multi-paragraph summary
  arrived as one block and the prompt looked ignored.

**Genuine model failures that remain:** `[VERIFIED]` `mistral:7b` invented "Joe Dumars" on
three consecutive attempts from a Pistons story — pattern-completing from training priors.
**Retry assumes independent failures and cannot help when the error repeats identically.**

### `[VERIFIED]` 2026-08-13, from `logs/sportwire.log` — read this before quoting a pass rate

Counted across the whole log: **8 summarisation runs. 2 delivered a validated summary, 5 fell
back after 3 rejections each, 1 errored.** Per attempt that is **2 accepted / 19 ≈ 11%**.

**Treat that as a floor, not the rate.** `[VERIFIED]` The count mixes code versions and cannot
be cleaned: at least one logged run predates the current summariser, its traceback naming the
pre-rename directory `NBA and NFL News and Games Assistant`.

`[VERIFIED]` **The reason it cannot be segmented was a defect in the log itself** — `main.py`
recorded `%H:%M:%S` with **no date**, and with 8-hour runs plus cron gaps whenever WSL sleeps,
two `08:00:17` lines could be one day apart or four. Fixed in `ec7bc3c`; an honest count starts
from the next run.

1. **The "~84%" figure is not supported by any reading of this log.** It came from 3/5 on one
   sitting. The measured floor is 11% — a factor of eight out. `[UNKNOWN]` The real rate.
   Re-count after ~2 weeks of dated logs; do not restate 84%.
2. `[VERIFIED]` **The identical-repeat failure mode is confirmed, not a one-off.** "Ayo
   Dosunmu" was invented on all three attempts. `[Likely]` Dosunmu, Cockburn and Frazier were
   Illinois teammates — the model is emitting a **co-occurrence cluster** from training, so
   one hallucinated name drags in its associates. `[INFERRED]` Retry cannot fix this by
   construction: it assumes independent failures.
3. `[VERIFIED]` **It is slow.** The failed run spent **19 minutes** on three attempts before
   falling back; the successful one took 12. Roughly 5–9 minutes per attempt on 12 stories.
   `[INFERRED]` This is why the interactive dry-run kept exceeding the command timeout — the
   timeout was not the bug, the runtime is simply longer than an interactive command allows.

### `[VERIFIED]` 2026-08-13, resolved with the operator — the paragraph prompt works

The operator supplied both delivered briefs. The commit clock is what makes them readable:
`71b2fa9` landed at **14:43**, so the 08:00 brief ran on the *old* prompt and only the 16:00
brief tests the change.

- **08:00, old prompt.** One unbroken block. Westbrook's retirement, then Jalen Duren, then
  Lakers ownership, then **back** to Westbrook for the Michael B. Jordan narration and
  LeBron's "HELLUVA CAREER BRODIE!!" — the reactions separated from the event by two
  unrelated subjects. The exact failure the prompt was written to fix.
- **16:00, new prompt.** Two paragraphs. ¶1 is Westbrook: retirement, the LeBron/Giannis
  tributes, the triple-double record — **the reaction sits with the event.** ¶2 is everything
  else. Both criteria met.

`[UNKNOWN]` **Whether it holds.** n=1, and §11 records concluding from one run as a mistake
made twice already. The 16:00 input was also smaller — 7 stories over 2 chunks against the
08:00 run's 12 over 3 — so the structural risk (notes arriving in chunk order, related items
far apart) is **untested at 3 chunks under the new prompt.** The next 12-story run is the
real test; if grouping breaks there, order notes by subject before the reduce step.

### `[VERIFIED]` 2026-08-13 — the validator's blind spot, and it reached the phone

The 08:00 brief passed validation **on attempt 1** carrying: *"His retirement marked the end
of playoff runs for basketball greats like Kobe Bryant, Tim Duncan, Dirk Nowitzki, and Kawhi
Leonard."* `[INFERRED]` Kawhi Leonard is active — the same run's feed carried his Raptors
trade story.

Every name is real and appears in the sources, so `validate.py` passes it. The 16:00 run shows
the same shape from the other side: attempt 2 was rejected for `Los Angeles Clippers-approved`
and attempt 3 was accepted saying *"team-approved beat writers"* — **the model rephrased
around the validator rather than becoming correct.**

`[INFERRED]` **The validator catches invented entities and is blind to false relationships
between real ones.** A different failure class from Joe Dumars / Ayo Dosunmu, which grounding
and retry were both built for. `[UNKNOWN]` How often it happens — nothing detects it, so it
has never been counted. Open as **P5**, recorded as an xfail in `tests/test_validate.py` so it
flips to XPASS when fixed.

---

## 7. Known limitations

| # | Limitation |
|---|---|
| L-1 | `--date` affects games only. RSS has no date query, so SportWire cannot reconstruct a past day. |
| L-2 | No individual player statistics (ADR-010). |
| L-3 | `[UNKNOWN]` Live and scheduled game payload shapes. Every game ever captured reads `Final` — it has been the offseason throughout. **Resolve after 2026-09-30.** |
| L-4 | Head-to-head only knows games this instance has delivered. Empty early in a season. |
| L-5 | Reddit contributes chatter that title-pattern filtering provably cannot separate from news. Capped at 3 stories rather than classified. |
| L-6 | **The same story is redelivered as new articles about it arrive** (P68). Dedup matches an article id, never a story, so four consecutive briefs carried the NBA's Clippers ruling. Reported by the operator on 2026-09-04 by reading briefs. **This is what blocks issue #1**, whose gate requires zero duplicate stories as well as the days. |
| L-7 | The entity-pair check flags a sentence whose names never co-occur. Read against sources on 2026-09-04: 6 of 9 flags were real errors, 2 were on entirely correct sentences, and three real errors went unflagged. It stays in the log and the evidence file, never in the brief (P5). |

---

## 8. Testing — issue #15, largely resolved 2026-08-13

~~**`processing/` has almost no tests.**~~ **`processing/` is now covered.**

`[VERIFIED]` 2026-08-13, `make check`: **126 passed, 1 xfailed**, up from 3 tests at the
start of that session. Seven of eight `processing/` modules have behaviour tests; the eighth,
`openrouter.py`, is dormant until an API key exists.

| Module | Tests | Recorded bugs locked in |
|---|---|---|
| `summarize.py` | 20 | 2 |
| `highlights.py` | 17 | 0 |
| `cluster.py` | 16 | 0 |
| `priority.py` | 14 | 3 |
| `newsworthy.py` | 13 | 5 |
| `dedup.py` | 11 | 0 — H13 Q1/Q3/Q7 answers instead |
| `validate.py` | 11 | 4, plus one xfail for P5 |

**`[VERIFIED]` Still uncovered, all from this section's original list:** `storage/db.py`,
`config/settings.py`, both RSS parsers, the Telegram message splitter.

### The method matters more than the count — read this before adding tests

`[VERIFIED]` **Every module was mutation-tested**: the bug was put back and the suite required
to notice. This caught **five tests that asserted nothing**, none of which review had spotted:

- `validate.py` — the sentence-splitting and stopword tests both passed with their mechanism
  disabled; the generous last-word grounding rescued the broken cases.
- `cluster.py` — the "a common name does not group" test shared only *one* common name, so
  `MIN_SHARED_NAMES` held it up and it passed with the frequency ceiling removed entirely.
  Nothing covered fingerprint-widening at all.
- `summarize.py` — one mutation silently **failed to apply** (shell escaping) and reported
  "20 passed", which looks identical to the suite surviving it.

`[INFERRED]` **A test written from the same reasoning as the code inherits the code's blind
spots.** Only trying to break it exposes that. Two of the five diagnoses turned into real
defects (P6, P9). Always assert the mutation actually applied before trusting a green run.

`[VERIFIED]` Three `highlights.py` tests were wrong on the first run while the *code* was
right — each constructed game accidentally qualified for an earlier category that claimed it.
`[INFERRED]` With eight categories and a precedence order, building a game that exercises
exactly one is genuinely hard, which is an argument for the tests rather than against them.

### What testing found — P5 to P10

`[VERIFIED]` Six findings, **none of which any test or review had caught before**, and two of
them user-facing. Full detail and options in `TASKS.md`.

| # | Finding | State |
|---|---|---|
| P5 | `validate.py` grounds **entities, not claims** — a false relationship between real names passes, and one reached the phone | **open**, recorded as an xfail |
| P6 | `_drop_leading_stopword` could not change any verdict; superseded a day after it landed | fixed (doc) |
| P7 | `priority.py`'s word-boundary comment claimed a protection it does not deliver | fixed (doc) |
| P8 | ADR-005's "612 pairs / 0.439" does not reproduce; the fixtures give 540 / 0.425 | fixed (doc) |
| P9 | `group_related` **silently merged nothing below 25 articles** | fixed — now warns |
| P10 | a claimed superlative left its category **empty**, losing brief lines | fixed — reassigns |

`[VERIFIED]` **Nine real bugs were found in six days, every one by reading live output** —
never by a test:

| Bug | Module |
|---|---|
| "tonight" tier ranked a child-support story first | priority |
| `Warriors'` failed to match `warriors` | priority |
| A current story dropped for citing "2015" | newsworthy |
| `U+2060` before `[Highlight]` defeated the tag match | newsworthy |
| "On this day" retrospectives reached a brief | newsworthy |
| Ujiri/Russell retrospectives past the year window | newsworthy |
| `In Detroit` flagged as an invented name | validate |
| Every-word grounding rejected `New York Knicks` | validate |
| Retry gave up on the first HTTP 500 | summarize |
| **A Westbrook retirement report dropped for citing his 2008 debut** | newsworthy |
| **The drop log recorded no reason and truncated the title at 80 chars** | newsworthy |

**Eleven, and the tenth was the ninth returning.** `[VERIFIED]` 2026-08-13: r/nba's
`[Charania] After 18 NBA seasons, Russell Westbrook has retired…` was filtered out. Rule 2
fired on any past year outside quotes, and a retirement report naturally cites the career
start. **The same rule, the same class, the second time** — it had already been narrowed once
after dropping a current Ballmer story for citing 2015.

`[VERIFIED]` The brief still covered the retirement, because ESPN and CBS carried it under
titles with no year. `[INFERRED]` **That was luck, not resilience** — a Reddit-only story
would have vanished silently.

`[VERIFIED]` **Resolved 2026-08-13 (P3, commit `06110ab`): Rule 2 was deleted**, not narrowed
a second time. `[INFERRED]` The class was unfixable by narrowing because that rule read a
*number* while the others read a *phrase* — a year is evidence of what a piece mentions, never
of what it is about, and retirement, contract, draft and anniversary reporting all cite years.
The accepted cost is one recorded true positive (an Ujiri/Leonard 2019 retrospective) now
reaching the brief; it is asserted in the test suite so the trade stays visible.

`[VERIFIED]` **All eleven are now locked in by tests, and each was a two-line test as
predicted.** `[INFERRED]` The list's real lesson held: every one was found by reading output,
and P5–P10 above were found by writing tests — two different nets catching two different
classes of bug. Neither replaces the other.

---

## 9. Open questions

1. ~~Dedup window~~ **168h** (PRD D2). Must exceed the feed's reach, not the poll interval.
2. ~~Cadence~~ **8h**; the run defines the summary window (PRD D1).
3. ~~NBA scope~~ ~~**NBA only for v1.0.0**~~ **Overtaken by events:** football shipped
   2026-08-26 (ADR-015) and gets its own brief.
4. ~~Local vs hosted LLM~~ **Local first**; hosted built and dormant.
5. ~~Legacy git history~~ Resolved — no secrets, published.
6. ~~Scraping legality~~ Resolved — ESPN publishes RSS (ADR-009).
7. ~~`storage/` salvage~~ Moot; rebuilt.
8. ~~Phone port~~ **cron now, Termux wrapper later** (PRD D4).
9. ~~Multi-user~~ **Single-user per instance.**
10. **Non-technical setup** — deferred, issue #11.
11. **`[UNKNOWN]` Is the brief actually read?** The PRD's real success criterion, and still
    untested. The operator has called it *"better on the eyes, unsure if more useful."*
12. **How should a developing story be reported the second time?** Open, and it is P68's real
    question rather than a technical one. The operator drew the line himself on 2026-09-04:
    the Clippers punishment repeating across four briefs is wrong, the Gillian Zucker
    revelation inside that story is right. So the rule wanted is *report developments, not
    the same facts again*, which is harder than suppressing a repeat.
13. ~~Does the 14-day gate need consecutive days?~~ **No, changed 2026-09-04.** They
    accumulate. A shut-down PC used to reset the count, and the PC being off says nothing
    about whether the software runs unattended. Issue #1 and the PRD both say so now.
14. ~~How far should v1.0.0 reach?~~ **NBA and NFL, running from a fresh clone** (operator,
    2026-09-24). MLB is v1.1.0, NHL v1.2.0, the NFL community feed (P46) after v1.0.0.
15. ~~Which intervals?~~ **8, 12 or 24 hours** (operator, 2026-09-24), checked analytically
    in PRD D6; the per-outlet cap and the repeat window now scale with it (P42).
16. **Should P70's grouping change stay?** `[VERIFIED]` It merged 23 correct, 5 borderline and
    9 wrong new groups out of 37, and it does not yet fix the day's biggest story. It is on
    `main` and running; `git revert` of its five commits restores the old grouping.

---

## 10. Exact first prompt for the next session

Paste verbatim:

```
Read CLAUDE.md, then docs/process/OPERATING_RULES.md, docs/sessions/SESSION.md,
docs/sessions/HANDOVER.md and docs/planning/TASKS.md before doing anything.

Note especially:
- CLAUDE.md §0: tag every factual claim. [UNKNOWN] is an acceptable answer.
- CLAUDE.md §9: 256 characters maximum per commit message, one commit per file.
- CLAUDE.md §13: delegate independent work to Sonnet subagents, at most two or three
  at once, each in its own worktree; you review and bring commits onto main.
- CLAUDE.md §14: work silently and give the full reasoning once, at the end.
- OPERATING_RULES.md §2: [VERIFIED] tags from earlier sessions are [Likely].

First, tell me the current state without changing anything:

  make check                                   # expect 609 passed, 1 xfailed
  .venv/bin/python scripts/soak_report.py      # per-league prose rate, the gate count
  git log --oneline -15
  tail -40 logs/sportwire.log

Then read the last delivered brief of each league against its own sources:

  .venv/bin/python scripts/soak_report.py --audit

Where the work is, in order (v1.0.0 = NBA and NFL, from a fresh clone):

- P70, the zero-duplicates clause of the gate. The day's biggest story still splits
  into several groups, because all its names are common. TASKS.md P70 has the next
  step and the measurement to repeat.
- P72's open false alarms, if measurement says they matter.
- The week-long duplicate audit, repeated on briefs delivered after 2026-09-24.
- Issue #2 (H13): the operator's explanation check, last attempted 2026-08-05. His
  practice drills and their saved grades are in the SportWire Inside Out artifact.
- Before tagging v1.0.0: repeat P73's fresh-clone check.
```
