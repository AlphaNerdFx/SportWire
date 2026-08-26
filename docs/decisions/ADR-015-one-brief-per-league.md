# ADR-015 — One brief per league, each on its own schedule

**Date:** 2026-08-26
**Status:** proposed

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
