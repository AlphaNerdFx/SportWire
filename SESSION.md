# SESSION.md — Current Working State

**Last updated:** 2026-08-13
**Repository:** https://github.com/AlphaNerdFx/SportWire (public)
**Next session should begin with:** §10.

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
| **Name** | SportWire — NBA news and game-data brief, delivered to Telegram |
| **Stage** | **Working and running unattended.** Cron delivers every 8 hours. |
| **Repo** | Public, MIT, CI green. `[VERIFIED]` 15 issues: 13 open, #6 and #14 closed |
| **Runtime** | `[VERIFIED]` WSL2 Ubuntu, Python 3.10.12, `.venv` (68 MB, 21 packages) |
| **Sources** | ESPN, CBS Sports, Yahoo Sports, r/nba (news); balldontlie (games) |
| **Delivery** | Telegram `@sportwire_news_bot`, three messages, one notification |

---

## 2. What exists and works

`[VERIFIED]` All of the following has run in production, unattended, on a schedule:

| Module | Job |
|---|---|
| `config/settings.py` | The only place `.env` is read. Paths anchored to `PROJECT_ROOT`, not the cwd. |
| `models/schemas.py` | `GameData`, `NewsArticle`, `GameHighlight`, `SeriesContext`. All frozen. |
| `ingestion/base.py` | Two source ABCs. `fetch()` owns the try/except so adapters cannot skip it. |
| `ingestion/rss_news.py` | One adapter, four feeds. Reads **both** RSS 2.0 and Atom. |
| `ingestion/nba_games.py` | balldontlie games, per-period scores, team ids as a side channel. |
| `processing/newsworthy.py` | **The only module that removes articles.** Age, content tags, retrospective phrases. |
| `processing/dedup.py` | Pass 1 exact id across runs; pass 2 near-identical titles within a run. |
| `processing/priority.py` | Sorts high/medium/low, with tonight's teams as a within-tier tiebreaker. |
| `processing/cluster.py` | Groups articles covering one story; caps stories per source. |
| `processing/highlights.py` | Comeback, overtime, closest finish, wire-to-wire, biggest quarter, second-half takeover. |
| `processing/summarize.py` | `Summarizer` ABC + Ollama, map-reduce chunking, validated retry. |
| `processing/validate.py` | Checks every name and figure against sources. **Fails closed.** |
| `processing/openrouter.py` | Hosted summarizer, dormant until a key exists. |
| `storage/db.py` | Seen-ids, game results, local head-to-head. |
| `delivery/` | `DeliveryChannel` ABC, Telegram, stdout, three-message formatting. |
| `main.py` | The single entrypoint. The only file naming a concrete class. |

---

## 3. How it is operated

`[VERIFIED]` Cron, every 8 hours, surviving terminal closes and running unattended for days:

```cron
0 */8 * * * cd "/mnt/c/DSC/.../SportWire" && ./.venv/bin/python main.py >> ".../logs/sportwire.log" 2>&1
```

Logs live in `logs/` (gitignored) rather than `/tmp`, which WSL clears on restart.

```bash
make dry-run   # fetch and print, send nothing, record nothing
make run       # fetch and send now
make check     # ruff + pytest, exactly what CI runs
```

`[Likely]` The one fragility: WSL cron stops if the WSL instance shuts down. If briefs stop
with no error, check `service cron status` first. `docs/SCHEDULING.md` §Option B has a
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

`[VERIFIED]` **Only six ADRs exist as files:** 003, 009, 010, 011, 012, 013
(`ls docs/decisions/`). Decisions 001–008 were taken on 2026-08-03 and recorded **in this
table only** — the numbering implies files that were never written. Either backfill them or
stop citing them as documents; do not assume a reader can open one.

| ADR | Decision | File? |
|---|---|---|
| 001 | Fork clean rather than salvage the prototype | no |
| 002 | Telegram, not WhatsApp — no per-message cost, no ban risk | no |
| 003 | balldontlie for games; `cdn.nba.com` is dead (403 from every network) | **yes** |
| 004 | SQLite. Reaffirmed against a Postgres proposal — open-sourcing *strengthens* the case | no |
| 005 | Semantic dedup declined **on evidence**: 612 real cross-source pairs, max similarity 0.439 | no |
| 006 | **Superseded.** Human writes interfaces, agent writes bodies — reversed 2026-08-05 (§4) | no |
| 009 | ESPN RSS for news — a published feed is an invitation; scraping is not | **yes** |
| 010 | No individual player statistics. Every free source blocked, paywalled or ToS-barred | **yes** |
| 011 | Slice 1 retrospective | **yes** |
| 012 | Summarisation: off → **on**, with a validator and retry | **yes** |
| 013 | OpenClaw may orchestrate SportWire externally, but must never be a dependency | **yes** |

---

## 6. Where the summarizer actually stands

This consumed most of 2026-08-06 to 08-12 and the state is nuanced.

**On, by default, using `mistral:7b` locally.** Every summary is checked by
`processing/validate.py` before it can be delivered; a failed check falls back to the
headline list. `[VERIFIED]` **No fabrication has ever reached the phone.**

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

Two consecutive scheduled runs, and they disagree:

| Run | Result |
|---|---|
| **00:00** | **0 of 3.** `invented names: Ayo Dosunmu, Kofi Cockburn, Dallas` → `Ayo Dosunmu` → `Ayo Dosunmu, Trent Frazier, Dallas`. Fell back to headlines. |
| **08:00** | **Passed.** No rejection logged, delivered. |

Three things follow, and the third is the one that matters:

1. **The "~84%" figure quoted elsewhere is not supported.** It came from 3/5 on one sitting.
   Two runs later the observed rate is 1/2 and the confidence interval on either number is
   far too wide to quote. `[UNKNOWN]` The real rate. Count over the soak; do not restate 84%.
2. `[VERIFIED]` **The identical-repeat failure mode is confirmed, not a one-off.** "Ayo
   Dosunmu" was invented on all three attempts. `[Likely]` Dosunmu, Cockburn and Frazier were
   Illinois teammates — the model is emitting a **co-occurrence cluster** from training, so
   one hallucinated name drags in its associates. `[INFERRED]` Retry cannot fix this by
   construction: it assumes independent failures.
3. `[VERIFIED]` **It is slow.** The failed run spent **19 minutes** on three attempts before
   falling back; the successful one took 12. Roughly 5–9 minutes per attempt on 12 stories.
   `[INFERRED]` This is why the interactive dry-run kept exceeding the command timeout — the
   timeout was not the bug, the runtime is simply longer than an interactive command allows.

`[UNKNOWN]` Whether the paragraph/grouping prompt works. `[VERIFIED]` The 08:00 run on
2026-08-13 produced a validated summary, so the change did not break delivery — **but the
log records only that it passed, not its shape.** Judging paragraphs and subject grouping
needs the delivered text, which lives on the operator's phone. **Ask him.**

---

## 7. Known limitations

| # | Limitation |
|---|---|
| L-1 | `--date` affects games only. RSS has no date query, so SportWire cannot reconstruct a past day. |
| L-2 | No individual player statistics (ADR-010). |
| L-3 | `[UNKNOWN]` Live and scheduled game payload shapes. Every game ever captured reads `Final` — it has been the offseason throughout. **Resolve after 2026-09-30.** |
| L-4 | Head-to-head only knows games this instance has delivered. Empty early in a season. |
| L-5 | Reddit contributes chatter that title-pattern filtering provably cannot separate from news. Capped at 3 stories rather than classified. |

---

## 8. The most important open problem

**`processing/` has almost no tests. Issue #15.**

`[VERIFIED]` **19 source modules. One test file. Three test functions, all three testing
rendering** (`tests/test_brief_snapshot.py`). Nothing covers `dedup`, `cluster`,
`newsworthy`, `priority`, `validate`, `highlights`, `storage/db`, `settings`, either RSS
parser, or the Telegram message splitter.

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

**Eleven now, and the tenth is the ninth returning.** `[VERIFIED]` 2026-08-13: r/nba's
`[Charania] After 18 NBA seasons, Russell Westbrook has retired…` was filtered out. Rule 2
fires on any past year outside quotes, and a retirement report naturally cites the career
start. **This is the same rule, the same class, and the second time** — it was already
narrowed once after dropping a current Ballmer story for citing 2015.

`[VERIFIED]` The brief still covered the retirement, because ESPN and CBS carried it under
titles with no year. `[INFERRED]` **That is luck, not resilience** — a Reddit-only story
would have vanished silently, which is precisely the failure class this filter's own
docstring says it exists to prevent.

`[VERIFIED]` **Fixed the diagnosis, not the rule.** `drop_non_news` now logs which rule
fired and the offending text, and the full title. The rule itself has more than one
defensible fix — drop it, require two past years, require the year early in the title, or
exempt retirement and contract contexts — so per `CLAUDE.md` §6 it is **not** picked
silently. Decide it with the operator.

`[INFERRED]` Every one of the eleven would have been a two-line test, and every one can
silently return. This is the single highest-value work remaining.

---

## 9. Open questions

1. ~~Dedup window~~ **168h** (PRD D2). Must exceed the feed's reach, not the poll interval.
2. ~~Cadence~~ **8h**; the run defines the summary window (PRD D1).
3. ~~NBA scope~~ **NBA only for v1.0.0**; other US leagues after (PRD D3).
4. ~~Local vs hosted LLM~~ **Local first**; hosted built and dormant.
5. ~~Legacy git history~~ Resolved — no secrets, published.
6. ~~Scraping legality~~ Resolved — ESPN publishes RSS (ADR-009).
7. ~~`storage/` salvage~~ Moot; rebuilt.
8. ~~Phone port~~ **cron now, Termux wrapper later** (PRD D4).
9. ~~Multi-user~~ **Single-user per instance.**
10. **Non-technical setup** — deferred, issue #11.
11. **`[UNKNOWN]` Is the brief actually read?** The PRD's real success criterion, and still
    untested. The operator has called it *"better on the eyes, unsure if more useful."*

---

## 10. Exact first prompt for the next session

Paste verbatim:

```
Read CLAUDE.md, OPERATING_RULES.md, SESSION.md and TASKS.md before doing anything.

Note especially:
- OPERATING_RULES.md §0: you write the code, tests and documentation. Never set me
  code to write, not as a task or a remedy. Explain as you go.
- OPERATING_RULES.md §2: [VERIFIED] tags from previous sessions are [Likely], not
  [Certain]. Re-test any external service before building on it.
- CLAUDE.md §0: tag every factual claim. [UNKNOWN] is an acceptable answer.

First, tell me the current state without changing anything:

  tail -40 logs/sportwire.log      # did cron run, did the summary pass validation
  make check                        # ruff + pytest
  git log --oneline -10

Then ask me one question you cannot answer from the logs: the 08:00 brief on
2026-08-13 passed validation, but the log records only that it passed, not its
shape. Ask whether it arrived as 2-3 paragraphs and whether a reaction sat in the
same paragraph as the event it reacts to. That resolves TASKS.md P2.

Two decisions are waiting for me, both in TASKS.md. Do not pick either silently:
- P3: newsworthy.py Rule 2 dropped a Westbrook retirement report for citing his
  2008 debut. Second false positive from that rule. Four options are written out.
- P4: the summariser's pass rate is unknown. The old "84%" came from one sitting
  of 3/5; the very next runs went 0/3 then pass. Count it, don't project it.

Then: issue #15 is the highest-value work remaining. Eleven real bugs were found
by reading output, none by a test, and every one can silently return. The most
recent one is the ninth returning in a new form.

Do not add features until #15 is addressed unless I ask.
```

---

## 11. What to resist

`[INFERRED]` Patterns this project has repeatedly fallen into, worth naming:

- **Concluding from one run.** Done twice, wrongly both times — a model declared clean on one
  sample, then a validator blamed on the model when the bug was mine.
- **Filtering by cleverer patterns.** Title-based classification of Reddit hit a hard limit;
  a blacklist missed untagged chatter and a whitelist dropped the biggest story. Bounding
  volume worked where classification could not.
- **Adding a source without measuring freshness.** The Athletic looks like a news feed and is
  an archive — 100 items, oldest 17 days, one within 48 hours.
- **Believing a green run means a working feature.** Nine bugs say otherwise.
