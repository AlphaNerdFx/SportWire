# ROADMAP

**What this document is for.** Development on this project has been reactive — a brief arrives,
something in it looks wrong, and the next two hours go wherever that leads. That found real
bugs, but it is not a direction. This file exists so there is exactly one answer to "what are
we doing next", and so a version number means something.

**Development is linear.** One milestone is current. The others are an *order*, not a schedule,
and nothing below the current one is started early. If something urgent appears, it either
becomes the current milestone or it waits — it does not run alongside.

**What this file does not own.** `TASKS.md` owns the items and the proof they are done;
`SESSION.md` owns what is true right now. This file owns only **order and version meaning**. A
task written out in full in both places will drift, and the drift will be invisible — the same
failure `CLAUDE.md` §5 rule 1 describes for code. Items are referenced here by id, never copied.

---

## 1. Versioning

`[VERIFIED]` These conventions already exist and are enforced; they are recorded here rather
than invented. Source: `TASKS.md` §RELEASES, `.github/workflows/release.yml`.

- Tags are `vMAJOR.MINOR.PATCH`.
- A tag is **annotated** (`git tag -a -F <file>`), and its message **becomes the GitHub Release
  notes**. One source of truth, not two.
- `version` in `pyproject.toml` must match the tag. `release.yml` refuses to publish otherwise.
- Pushing a `v*` tag runs `make check` first and publishes only if it passes. `[INFERRED]` A
  tag on a red commit is a claim, published under a version number, that something works.

**What the numbers mean here, while below 1.0:**

| | meaning |
|---|---|
| `MAJOR` = 0 | Pre-release. The brief works but its reliability is not yet measured. |
| `MINOR` | One milestone from §3 completed. This is the number that moves. |
| `PATCH` | A fix to a released milestone that does not complete the next one. |

`[INFERRED]` Every 0.x release is marked **pre-release** on GitHub, as `v0.1.0` was. A release
that hides its limits is the failure this repository was founded on, so the notes state what is
unproven as well as what works.

---

## 2. Where this is now

`[VERIFIED]` **`v0.1.0`**, tagged 2026-08-14 and marked pre-release. Tags present:
`v0.1.0`, `pre-release-legacy-frozen`.

`[VERIFIED]` 2026-08-15, what genuinely works: the pipeline fetches four feeds, drops non-news,
deduplicates across runs, ranks, groups related coverage, caps per source, summarises through a
local model, validates that summary against its sources, and delivers to Telegram. It ran
unattended twice on 2026-08-15 (08:00 and 16:00) and `delivered 1/1 messages` both times.
`make check` → **235 passed, 1 xfailed**.

`[VERIFIED]` What is not yet true, and is the reason §3 is ordered as it is:

- **The 16:00 brief arrived as a bare headline list.** All three summarisation attempts were
  rejected. Two of the six rejected names were validator defects, since fixed (P19, P20); at
  least two were the model genuinely inventing teams.
- `[UNKNOWN]` **The summariser's pass rate.** This is P4, and it is formally unknown — do not
  quote a number for it. Attempt-1 successes were invisible in the log until `4c7c4ed`.
- `[UNKNOWN]` **What schedules the unattended runs.** They happen, but the crontab entry is
  commented out and carries a Windows path, and no systemd timer or Windows task was found.
  Resolve by asking the operator, then `crontab -l` immediately after.
- `[VERIFIED]` **`main` is 31 commits ahead of `origin/main`.** Everything since `1cecc5a`
  exists only on the operator's machine.

---

## 3. The order

### → `v0.2.0` — the brief can be trusted **(current)**

**Done when a delivered brief is prose, and the rate at which it is not is a measured number.**

`[VERIFIED]` This is first because it is the defect the operator actually experiences: the
headline fallback reached the phone on 2026-08-15, and nobody can say how often that happens.
Everything later inherits this — a scheduling feature that delivers an untrustworthy brief more
often is worse than no feature.

- **P4** — establish the pass rate over a real soak. Countable for the first time since
  `4c7c4ed`.
- **P21** — `Madison Square Garden` refused where the sources say only `MSG`.
- **P5** — the validator grounds entities, not claims. Live in the suite as the one xfail, so
  it flips to XPASS when fixed.

`[UNKNOWN]` Whether P4's measurement will show the model is good enough at all. `[INFERRED]` If
it does not, the honest outcome is an ADR on model choice (ADR-012 territory), not more
validator tuning — the validator is already three fixes deep this week.

### `v0.3.0` — fetch stops depending on delivery

**Done when the number of upstream requests depends on the number of sources, not on how often
anyone asks for a brief.**

Implements **ADR-014**, currently *proposed*. `[VERIFIED]` The constraint is real: Reddit
returned HTTP 429 to this repository's own measurement probes on 2026-08-15, and
`ingestion/rss_news.py` has recorded the limit since 2026-08-09.

Also folds in the small independent defect found alongside it: a rate-limited or timed-out
source currently returns an empty list and vanishes from the brief with only a log line.
`[VERIFIED]` CBS did exactly that at 16:00, contributing 0 articles after a read timeout.

### `v0.4.0` — the operator chooses the interval

**Done when the delivery schedule is configuration, not a cron line.**

Depends on `v0.3.0` and cannot be started before it — an interval feature built on
fetch-per-brief is the design ADR-014 exists to prevent. Resolves the `[UNKNOWN]` in §2 about
scheduling by making it explicit rather than discovered.

### `v1.0.0` — the line

**A trustworthy single-user NBA brief.** Specifically, all of:

1. The NBA brief arrives on schedule, unattended, from a scheduler this repository documents.
2. The summarisation pass rate is a **measured** number, published in the release notes.
3. No known false-accusation bug in `processing/validate.py`. `[VERIFIED]` Three were fixed on
   2026-08-15 alone, so this condition is doing real work.
4. `make check` green, and the README sufficient to run it.

`[INFERRED]` This is deliberately narrower than `CLAUDE.md` §1, which names NBA **and** NFL.
The reasoning is goal ranking: §1 ranks *ship a working system* first, and a measured, reliable
one-league brief is a working system, while two unmeasured leagues is twice the surface with
the same unknown. NFL is the first thing after the line, not part of it.

### After 1.0, in this order

- **`v1.1.0` — NFL (L1).** `[VERIFIED]` `TASKS.md` records the L1 trigger as already fired, so
  this is held back by sequencing rather than by its own condition.
- **`v1.2.0` — multi-user routing (L8).** Only meaningful once `v0.3.0` and `v0.4.0` exist.
- **`v2.0.0`** — reserved for a change that breaks how the operator runs it. Nothing currently
  planned qualifies.

---

## 4. Not scheduled

`TASKS.md` §LOW holds thirteen deferred items, each with a **trigger condition** — semantic
dedup, Postgres, async ingestion, WhatsApp delivery, Docker, a query interface. They are not
listed here, and that is deliberate: a roadmap that lists everything is a wish list, and this
project has already been damaged once by a document describing work that was not happening.

**An L-item enters this roadmap only when its trigger has fired**, and then it takes a version
number of its own rather than riding along inside another milestone.

---

## 5. Keeping this file honest

- **One milestone is marked `(current)`.** If two ever are, that is the bug.
- **A milestone is done when its `TASKS.md` items are checked with proof**, not when it feels
  finished — `CLAUDE.md` §6 forbids marking a task complete without pasting the output.
- **Move the line rather than redefine it.** If `v1.0.0`'s conditions turn out to be wrong,
  change them here in place with a dated note, the way `SESSION.md` and `TASKS.md` record
  retractions. Do not quietly drop a condition that became inconvenient.
- `[VERIFIED]` **`TASKS.md` checkboxes have drifted** and should not be counted mechanically:
  P9 is still `- [ ]` although P19's rarity floor removed the condition it describes, and
  P13's body records it resolved while its box is unchecked. Reconcile before using the open
  count as evidence of anything.
