# ADR-009 — NBA news via the ESPN public RSS feed

**Date:** 2026-08-04
**Status:** accepted

## Surface
NBA headlines will come from ESPN's own public news feed — the same thing a podcast app or
news reader subscribes to. We read it the way it was meant to be read, rather than copying
text off ESPN's web pages.

## Thorough

**The problem.** `CLAUDE.md` §4 flagged that scraping ESPN or HoopsHype in a public repo is a
licensing and ToS exposure, not merely a technical one, and required checking for an official
feed *before* any scraper is written. `SESSION.md` open question 6 recorded this as
unresearched. This ADR closes it.

**What was tested live, 2026-08-04:**

| Candidate | Result | Disposition |
|---|---|---|
| `espn.com/espn/rss/nba/news` | `[VERIFIED]` HTTP 200, 9,282 bytes, 15 items | **Chosen** |
| `reddit.com/r/nba/.rss` | `[VERIFIED]` HTTP 200, 54,500 bytes, Atom | Deferred — see below |
| `news.google.com/rss/search?q=NBA` | `[VERIFIED]` HTTP 200, 132,240 bytes | Rejected — aggregator; links out to third parties, inherits their terms rather than resolving them |
| `cbssports.com/rss/headlines/nba/` | `[VERIFIED]` HTTP 200, 35,701 bytes | Viable fallback; messier XML |
| `sports.yahoo.com/nba/rss.xml` | `[VERIFIED]` HTTP 301 redirect | Rejected — dead at the documented path |

**Why ESPN over Reddit.** Operator's reasoning, recorded: r/nba is user-generated and
noise-heavy, which degrades the quality of any downstream summarization step (M7). ESPN's feed
is editorial — every item is a published article with an author and a headline written to be
read. Reddit remains a candidate for *later* addition (see Reversal condition), specifically
because adding a second source is the test of whether the adapter boundary works (task M6).

**Measured limits, not assumed ones:**

- `[VERIFIED]` `<ttl>30</ttl>` — ESPN's stated polite refresh interval is 30 minutes. The
  planned `POLL_INTERVAL_HOURS=8` is well inside it. No rate-limit exposure.
- `[VERIFIED]` 15 items spanning 2026-08-01 14:08 EST → 2026-08-04 18:44 EST — a ~3.2 day
  coverage window.
- `[INFERRED]` **That window will shrink substantially in-season.** August is the NBA
  offseason; a quiet news cycle is why 15 items reach back three days. During the season, with
  games nightly, ESPN plausibly publishes 15 NBA stories in far less than 8 hours — at which
  point an 8-hour poll would silently drop every story older than the 15th item. **Mitigation:
  poll every 2–4 hours.** The feed is 9 KB and dedup is a hash lookup, so the cost is
  negligible and the failure mode (silent story loss) is invisible if it happens.

**Tradeoff accepted:** a single-outlet feed carries ESPN's editorial selection bias, and 15
items is a shallow buffer. Both are acceptable for v1 and both are fixed by adding a second
source later — which is planned work (M5/M6), not a workaround.

## Deep

**The concept: a published feed is a sanctioned interface; a scraped page is not.**

Scraping infers structure from a page whose author never agreed to keep that structure stable,
and whose terms typically forbid the copying. Publishing RSS is the opposite: the publisher
emits a machine-readable document *for the purpose of being consumed by programs they do not
control*, and advertises its own refresh cadence via `<ttl>`. Consuming it is using the
interface as intended. This is the same principle as ADR-002 (Telegram's official Bot API over
an unofficial WhatsApp bridge) and ADR-003 (a documented third-party API over an undocumented
endpoint that happened to return 200). Three separate decisions, one rule: **prefer the
interface whose provider knows you are using it.**

**The second concept: never assume identity or ordering in an external feed — measure it.**

Three assumptions any competent developer would make about this feed are false, and all three
were caught by measuring rather than reasoning:

1. `[VERIFIED]` **`pubDate` does not identify an item.** Only 6 unique timestamps across 15
   items; seven stories share a single second. Using it as a key silently collapses stories.
2. `[VERIFIED]` **Items are not in chronological order.** Item 11 (Aug 4 18:44) is newer than
   items 1–10, and the last four run Aug 1, Aug 1, Aug 2, Aug 2. Any "take the newest N" logic
   built on feed position is wrong.
3. `[VERIFIED]` **`guid` is the identity key** — `US-EN-49531647`, `isPermaLink="false"`,
   matching the article ID inside the link. 15/15 unique.

`[VERIFIED]` Additionally, `<dc:creator>` is present on only 13 of 15 items, so the author
field is optional in practice even though it "obviously" should always exist.

The general lesson, and the reason `CLAUDE.md` §8 mandates fixtures: **the shape of external
data is an empirical question, not a design question.** Every one of these four facts would
have produced a plausible-looking schema that broke or silently corrupted output on real data.
This is the same failure class as the fabricated `HANDOFF.md` — confident structure asserted
without observation.

## Reversal condition

- If ESPN's editorial bias or 15-item depth proves limiting, **add** a second source rather
  than replacing this one — CBS Sports RSS is the verified fallback, and r/nba is the
  higher-volume option if noise proves tolerable after M7's summarization step exists to filter
  it. Adding a source without changing the orchestrator is task M6 and is the explicit test of
  the adapter boundary.
- If ESPN moves or discontinues the feed (HTTP 404/301 at the recorded path), fall back to CBS
  Sports and record a new ADR — do not silently substitute.
