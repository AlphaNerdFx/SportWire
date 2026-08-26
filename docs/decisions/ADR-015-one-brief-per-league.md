# ADR-015 — One brief per league, each on its own schedule

**Date:** 2026-08-26
**Status:** accepted, and built on 2026-08-26 except for the per-league schedule

## Surface

Each sport gets its own brief on its own timetable, so basketball news in season does not
arrive at the same rhythm as football news in the off-season, and a quiet week in one sport
never pads itself with another.

## Thorough

### The decision

`[VERIFIED]` Operator decision 2026-08-26, chosen over one sectioned brief and over mixing
leagues as today: **a league is a separate brief with a separate interval.** NBA every 8
hours and NFL every 24 is a legitimate configuration, and so is following only one.

### Where a league comes from

**From the feed, never from the text.** `[VERIFIED]` The feed URLs are already league-scoped:
`espn.com/espn/rss/nba/news`, `cbssports.com/rss/headlines/nba/`, `sports.yahoo.com/nba/rss/`,
`reddit.com/r/nba/.rss`. The source knows what it is, which is the same reasoning that puts
`source_name` on an adapter rather than inferring the outlet from an article's wording.

`[VERIFIED]` Classifying by content was measured and is not needed. Across 128 live articles
from those four feeds, **1 (0.8%)** reads as another sport, a CBS item pairing an NFL contract
story with a list. `[INFERRED]` A content classifier would be a permanent source of
misattribution, in exchange for catching one item in 128 that feed attribution already handles
by putting it in the NBA brief where its feed said it belonged.

### Why this also fixes cross-sport leakage in the summary

`[VERIFIED]` Operator's point 2026-08-26: a separate model pass per sport prevents one league
bleeding into another's brief. That falls out of this decision rather than needing anything
extra, and the reason is worth stating exactly.

`[VERIFIED]` The summariser is **stateless between calls**. `processing/summarize.py` posts to
Ollama with `options` and a prompt and no `context` field, so nothing carries from one call to
the next. `[VERIFIED]` That was measured independently when the concurrency hypothesis for
fabrication was tested and disproved.

~~`[INFERRED]` So cross-sport leakage can only enter through the **input batch**, never through
model memory. A per-league brief summarises a per-league batch, which means the model is never
shown two sports at once and cannot blend them.~~ **Half right, corrected the same day.**

`[VERIFIED]` The batch half holds: the model is never shown two sports at once, and nothing
carries between calls. What that argument missed is that the model does not need the batch in
order to name a basketball team. The first football brief that kept its prose said "Ashton
Jeanty of the Timberwolves", and "Timberwolves" appears **0 times** in those twelve football
articles. Jeanty is a running back. The team came from the model's own weights, and the
validator did not catch it because a lone capitalised word is never treated as a name.

`[INFERRED]` Splitting the briefs makes this more visible rather than less. A mixed brief
would have carried the same sentence and it would have looked less obviously wrong. So the
decision is still right, and the claim attached to it was too strong.

`[VERIFIED]` Closed the same day. The validator now checks a team standing on its own against
the sources, using a list of the 62 NBA and NFL nicknames. It is narrow on purpose: checking
every lone capitalised word would have flagged "Elsewhere", "Lastly" and "Meanwhile" in both
briefs of one run to catch a single wrong team, while checking only known teams flagged 0 of
258 real titles that name one. `TASKS.md` P51 has the rest, including what it will not do for
a league it has not been told about.

The part that does survive: no separate process, model or instance is required. A second
Ollama instance would cost memory and would not have prevented this, because the wrong team
came from weights that both instances would share.

### What this costs, stated before it is built

`[VERIFIED]` **Model time multiplies.** The 2026-08-26 00:00 run took 10 minutes 36 seconds
for 12 stories in 3 chunks. Four leagues on similar volume is roughly 40 minutes of local
inference per cycle, and `[VERIFIED]` runs already overlap the schedule when they are slow: on
2026-08-15 a run took 19 minutes against an 8-hour interval, which was fine, but four leagues
at 2-hour intervals would not be.

`[INFERRED]` Two things bound it rather than one. Per-league intervals mean an off-season sport
can sit at 24 or 48 hours, which is the point of the decision; and `POLL_INTERVAL_CHOICES`
already refuses the combinations most likely to overrun.

`[UNKNOWN]` Whether a slow league can delay a fast one. Today a run is a single process, so a
40-minute NFL summarisation would push the NBA brief late. That needs measuring before four
leagues are live, not assumed away.

### Alternatives considered

**(a) One brief, sections per league.** One message, one interval, sections omitted when a
league is quiet.
*Rejected by the operator.* `[INFERRED]` It is the cheaper design and the honest note is that
it would have avoided the cost above entirely, but it forces one interval across sports whose
news rates differ by an order of magnitude between season and off-season.

**(b) Leagues mixed, ranked together, as today.**
*Rejected.* `[VERIFIED]` This is the current behaviour and it already misbehaves: a quiet NBA
day let an NFL contract story reach story 12 of 12 in the brief (TASKS.md P35).

**(c) Attribute by content rather than by feed.**
*Rejected on measurement*, see above. Kept as a note because it will be proposed again the
first time a league-scoped feed carries a stray item.

### What this rules out

`[INFERRED]` A single `POLL_INTERVAL_HOURS` no longer describes the system. It becomes
per-league, and the settings that derive from it — story cap and summary length (PRD D6) —
become per-league with it. Anything reading a global interval is now reading the wrong thing.

## Deep

The underlying idea is **partitioning a workload by a key that already exists in the data**,
rather than by one inferred after the fact. The league is not a property SportWire computes; it
is a property of the feed it subscribed to, carried along and never recovered later.

The same shape appears as the partition key in a distributed log, the shard key in a database,
and the routing key on a message queue. In each case the rule is identical: pick a key the
producer already knows, because a key derived downstream can disagree with itself, and every
disagreement becomes a row in the wrong place that nothing detects.

`[VERIFIED]` This project has already paid for the alternative once, in a smaller way. The
validator spent a week inferring which entity a name referred to and produced six false
accusations doing it; the fix each time was to carry better information forward rather than to
infer harder.

## Reversal condition

`[UNKNOWN]` If per-league summarisation proves too slow on this machine — four leagues failing
to finish inside the shortest configured interval — the answer is (a), one sectioned brief with
one summarisation pass, not more tuning. Measure total run time across four leagues before
committing to the fourth.


## What was actually built, 2026-08-26

`[VERIFIED]` The split, end to end. `python main.py --dry-run --no-summary` produced two
messages, 54 basketball articles and 112 football ones, and a word count over each found no
term from one sport in the other's brief. The pieces:

- `NewsArticle.league`, stamped by the adapter from `FEED_LEAGUES` rather than guessed from
  the text.
- A `league` column on `fetched_articles`, added to existing databases by `ALTER TABLE`.
  This is the migration this decision's predecessor said would eventually be needed.
- `assemble_brief` in `main.py`, called once per league, with delivery left outside it so
  nothing is recorded as sent until every brief is built.
- A heading per league, because both briefs arrive within seconds and "NEWS" twice tells the
  reader nothing.
- Failed sources reported only in their own league's brief. An NFL outage in the basketball
  brief is a fact the reader can do nothing with.
- One evidence file per league, labelled, since both are written inside the same second.

Two things are deliberately *not* per league yet:

**The schedule.** Both briefs are still built by one run on one interval. Splitting them
needs the bounded interval choice from P42, which is v1.0.0 work. `[INFERRED]` Nothing built
here blocks it: the loop already assembles each league independently, so a per-league
schedule becomes a question of which leagues a given run handles.

**The vocabulary sample.** The validator still learns ordinary English from the whole run,
both sports together. `[VERIFIED]` That is on purpose and it is the opposite of the leakage
rule: P32 records that a twelve-story batch is too small a sample of English, and splitting
by league makes each batch smaller still. The sample teaches the validator which lower-case
words are ordinary; it never reaches the model, so it cannot leak a sport into a brief.
