# SESSION.md — Current Working State

**Last updated:** 2026-08-14
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
| **Version** | `[VERIFIED]` **v0.1.0**, tagged 2026-08-14, published as a pre-release |
| **Repo** | Public, MIT, CI green. `[VERIFIED]` 17 issues: 15 open, #6 and #14 closed |
| **Wiki** | `[VERIFIED]` 6 pages. Its links are checked by `make check`; it had drifted for 4 days before that existed |
| **Tests** | `[VERIFIED]` **181 passed, 1 xfailed** (2026-08-14 `make check`). See §8 |
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
make check     # ruff + pytest + documentation links, exactly what CI runs
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
| 005 | Semantic dedup declined **on evidence**: ~~612 pairs, max 0.439~~ → **540 pairs, max 0.425** (corrected 2026-08-13, P8: the original was measured live and does not reproduce from the committed fixtures; the decision is unchanged and slightly stronger) | no |
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

  tail -40 logs/sportwire.log      # runs are DATED from 2026-08-13 onward
  make check                        # expect 126 passed, 1 xfailed
  git log --oneline -12

Three things to check in that log specifically, all new since 2026-08-13:

1. Does "grouping skipped" appear? That is the P9 warning. If it fires in
   production, the cluster threshold question becomes real and there is finally
   data to settle it with. If it never fires, say so — that is also an answer.
2. Count validation outcomes across the DATED runs only. That resolves P4. The
   measured floor is 11% (2 of 19 attempts) but it mixes code versions. Do not
   restate 84% under any circumstances.
3. Did any run produce a 12-story summary? That is the untested case for P2 —
   the paragraph prompt has only ever been observed on a 7-story, 2-chunk run.

Ask me for the latest delivered brief. The log records that a summary passed,
never its shape, and P2 and P5 both need the text that lands on my phone.

One decision is waiting, in TASKS.md. Do not pick it silently:
- P5: validate.py grounds entities, not claims. A sentence built entirely from
  real names can assert a false relationship and pass — one did, on attempt 1,
  and reached my phone ("...end of playoff runs for ... Kawhi Leonard", who is
  active). Four options written out; (c), an entity-pair co-occurrence check,
  is the recommendation. It is recorded as an xfail in tests/test_validate.py,
  so it flips to XPASS the moment it is fixed.

Then, the remaining #15 work — everything left on SESSION.md §8's original list
that is NOT in processing/: storage/db.py, config/settings.py, both RSS parsers,
and the Telegram message splitter.

**Mutation-test everything you write.** Put the bug back and confirm the suite
notices. That caught five tests of mine that asserted nothing, and two of those
diagnoses became real defects (P6, P9). Commit before mutating — a `git checkout`
restore once wiped an uncommitted fix. And assert the mutation actually applied;
one silently did not and reported "20 passed", which looks exactly like the
suite surviving it.

Do not add features unless I ask.
```

---

## 11. What to resist

`[INFERRED]` Patterns this project has repeatedly fallen into, worth naming:

- **Concluding from one run.** Done twice, wrongly both times — a model declared clean on one
  sample, then a validator blamed on the model when the bug was mine. `[VERIFIED]` The "84%"
  pass rate is the same mistake a third time: one sitting of 3/5, restated as fact in several
  places, against a measured floor of 11%.
- **Trusting a green test.** `[VERIFIED]` 2026-08-13: five tests written that session asserted
  nothing, and review caught none of them — only mutation did. A test written from the same
  reasoning as the code inherits the code's blind spots. Worse, one *mutation* silently failed
  to apply and reported a green run, which is indistinguishable from the suite surviving it.
- **Fixing the same symptom twice from different directions.** `[VERIFIED]` Two commits a day
  apart both fixed "a correct summary was rejected", and the second made the first dead code
  (P6). Neither had reason to look at the other. Ask what already handles this.
- **Adding a category without checking what it displaces.** `[VERIFIED]` Three highlight
  categories added in the M band silently removed "Biggest win" from the brief, because the
  new category claimed the game first and the old one was not reassigned (P10).
- **Filtering by cleverer patterns.** Title-based classification of Reddit hit a hard limit;
  a blacklist missed untagged chatter and a whitelist dropped the biggest story. Bounding
  volume worked where classification could not.
- **Adding a source without measuring freshness.** The Athletic looks like a news feed and is
  an archive — 100 items, oldest 17 days, one within 48 hours.
- **Believing a green run means a working feature.** Nine bugs say otherwise.
