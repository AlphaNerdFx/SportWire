# ADR-014 — Fetch cadence is independent of delivery cadence

**Date:** 2026-08-15
**Status:** proposed

## Surface

SportWire will collect news on its own fixed timetable and keep what it finds, so that
however often you ask for a brief — and however many people eventually ask — it never has to
go back and pester the news sources again.

## Thorough

### The problem this prevents

The operator's stated goal is to let a user choose how often they receive a brief. The
obvious implementation is to run the pipeline on that schedule: the brief is due, so fetch,
dedup, summarise, send. **That design makes source requests a function of users and their
chosen intervals**, which is the one thing a free upstream will not tolerate.

`[VERIFIED]` This is not speculative for Reddit. `ingestion/rss_news.py` already records it
from 2026-08-09: *"Reddit rate-limits aggressively — three requests in ~2s returned two HTTP
429s. One fetch per run is fine; never retry in a loop."* `[VERIFIED]` 2026-08-15 it was hit
again from this repository — five `r/nba` fetches over a few minutes, run as measurement
probes for TASKS.md P19, returned `429 Client Error: Too Many Requests`.

`[INFERRED]` Under the obvious design, ten users on hourly briefs is 240 requests a day to
each source, and worse than the total is the shape: schedules land on the hour, so the
requests arrive as a burst rather than spread out. `[VERIFIED]` The current pipeline is
nowhere near this — one fetch per source per 8-hour run — so this ADR is about the design
that the interval feature would otherwise force, not about a defect in what runs today.

`[VERIFIED]` The failure would also be quiet. `ingestion/base.py:47` catches every exception
from `_fetch` and returns `[]`, by the deliberate rule that a dead source degrades the brief
rather than crashing the run (`CLAUDE.md` §5 rule 6). A rate-limited source therefore drops
out of a brief with a log line and no other signal.

### The decision

**Ingestion cadence and delivery cadence become separate concerns.**

- A **poll** fetches every source on a fixed schedule chosen to suit the sources, and writes
  what it finds to SQLite.
- A **brief** is assembled by reading that store over a time window, and sends nothing
  upstream.

Source requests then scale with the number of *sources*, which is a number this project
controls, and not with users, intervals, or retries — none of which it controls.

### What this rules out, deliberately

`[INFERRED]` The routes that "circumvent" a rate limit rather than respect it — rotating IPs
or proxies, spoofing the `User-Agent` to look like a browser, or splitting requests across
accounts — are excluded by C3. They put ToS-violating code in a repository whose whole point
is to be publishable, and a reviewer would find them immediately.

### Alternatives considered

**(a) Cache the raw feed response with a minimum refetch interval.** Refuse to refetch a
source within N minutes and reuse the last payload. Simplest possible change: no schema
work, no migration.
*Rejected as insufficient rather than wrong* — it is a strict subset of this decision. It
bounds request *rate*, but the cache holds one payload per source, so a brief can never
cover a window longer than the feed's own depth, and two users with different intervals still
get whatever the last fetch happened to contain.

**(b) Authenticate with a free Reddit OAuth application.** Legitimate, not evasive, and still
free (C2).
*Rejected as an answer to this question, not on its merits* — it raises the ceiling without
changing the shape, so the same design still walks into the same wall with more users. It
also adds a credential and a signup step for anyone cloning the repo (C3 friction). It stays
available if polling alone proves insufficient.

**(c) Do nothing until the interval feature is actually built.** Defensible under
`CLAUDE.md` §6's "do not generate a whole subsystem so it's ready."
*Rejected on sequencing* — the storage shape is the expensive part to change later, and the
interval feature is the operator's stated next goal. `[INFERRED]` The cost of deciding now is
one table; the cost of deciding after a delivery scheduler exists is a rewrite of it.

### The tradeoff being accepted

`[VERIFIED]` `storage/db.py` states in its own docstring: *"Only identifiers are stored, never
article text or scores. The store answers exactly one question — 'have I sent this already?'
— and storing more than that would invite this module to grow into a second source of truth
about content."* **This decision contradicts that sentence, and the sentence will be amended
rather than quietly left standing.**

`[VERIFIED]` The precedent is already in the same file. `game_results` (line 43) keeps
content, and its comment justifies the exception in exactly these terms: *"asking balldontlie
for a season series costs one request per fixture and its free tier returns 429 from about
the sixth… Every result needed is already passing through this process; writing it down turns
a rate-limited network call into a local query."* That is this argument, applied to games
eight days earlier.

`[INFERRED]` The real risk the original sentence guards against is duplication of truth — two
modules disagreeing about what an article is. That is contained by `CLAUDE.md` §5 rule 2:
`models/schemas.py` remains the only definition of `NewsArticle`, and the store persists and
returns *that* type rather than inventing a row shape the rest of the pipeline must learn.

`[VERIFIED]` The cache lives in `SeenStore` rather than a new module, decided by the operator
2026-08-15. A second module opening the same SQLite file is the duplication `CLAUDE.md` §5
rule 1 names as why the legacy repo failed — it contains *two DB connection layers*.

`[VERIFIED]` **No migration is required.** `storage/db.py:69` runs `executescript(_SCHEMA)` on
every connect and every statement is `CREATE TABLE IF NOT EXISTS`, so a new table appears on
the next run and existing rows are untouched. A migration is only needed when a table that
already exists has to change shape, because then the file on disk and the code disagree and
something must reconcile them. This change is deliberately the first kind.

## Deep

The underlying idea is **decoupling producer and consumer rates through a buffer**, and it is
one of the oldest results in systems design: when two processes must run at different speeds,
you do not make one wait for the other — you put storage between them and let each run at the
rate that suits it.

The same shape appears as the **bounded buffer** in concurrent programming, as a **message
queue** between services, as the page cache between a CPU and a disk, and as every CDN ever
built. In each case the buffer converts a *coupling* problem into a *capacity* problem, which
is the trade being made here: SportWire will hold more on disk in order to ask upstream less.

The specific variant is **cache-aside read-through with a write-behind refresh** — briefs read
only from the store, and a separate process is responsible for keeping the store current.
Its characteristic weakness is **staleness**: a brief can only be as fresh as the last poll,
so the poll interval sets a floor on how current any brief can be, no matter how often it is
requested. `[INFERRED]` For an 8-hour news brief that floor is irrelevant; for a live score
ticker it would be disqualifying, which is why `GameData` is not in scope here.

There is also a **rate-limiting** concept worth naming, because it explains why "just retry"
is not a fix. Upstream limits are typically a *token bucket*: a bucket refills at a fixed rate
and each request spends a token, so a burst is tolerated only until the bucket empties.
Retrying immediately on a 429 spends tokens that do not exist and extends the penalty, which
is why `ingestion/rss_news.py` says *never retry in a loop* — and why the correct response to
a 429 is to wait for the interval the server names in `Retry-After`.

## Reversal condition

Undo or revisit this if any of these turn out to be true:

- **The interval feature is abandoned.** If briefs stay on one fixed schedule for one user,
  the pipeline already satisfies every rate limit and the store is unnecessary complexity.
- **Staleness becomes the complaint.** If the operator wants briefs materially fresher than
  the poll interval, the buffer is in the wrong place and a fetch-on-demand path with a short
  cache is the better shape after all — alternative (a), promoted.
- **Storage growth stops being trivial.** `[UNKNOWN]` The disk cost of retaining article text
  has not been measured. Resolve by checking `sportwire.db` size after a week of polling. If
  it grows in a way that matters, this needs a retention window — which `SeenStore`
  deliberately does not have today, for reasons its own docstring gives.
- **A source forbids caching its content.** `[UNKNOWN]` Not checked per feed. Consuming a
  published feed is using the interface as intended (ADR-009), but retention is a separate
  question from retrieval, and a terms change could make storing article text a C3 problem
  even where fetching it is fine.
