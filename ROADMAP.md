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

### `v0.2.0` — the brief can be trusted **(done 2026-08-26)**

`[VERIFIED]` All three conditions met. P5 closed as marked-not-rejected, P21 closed with the
abbreviation table, P4 counted at 31% overall and 50% since the fixes. The 2026-08-26 00:00
run delivered prose on attempt 1.

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

### `v0.3.0` — fetch stops depending on delivery **(done 2026-08-26)**

`[VERIFIED]` Both halves built and exercised end to end. `--poll-only` fetched 98 articles,
stored them and sent nothing; `--no-poll` then assembled and delivered a brief while contacting
**no source at all**, not even the games API. Upstream requests now happen in one place, the
poll, and a brief can be assembled any number of times without adding one.

`[VERIFIED]` The folded-in defect is also closed: a source that fails is named in the brief
rather than vanishing with only a log line.

`[INFERRED]` Behaviour at today's one brief per 8 hours is unchanged, which is deliberate. The
default run still polls and delivers in one pass, and a test asserts that unflagged path
specifically, because splitting a pipeline is exactly the change that works in its new modes
and quietly breaks the old one.

**Done when the number of upstream requests depends on the number of sources, not on how often
anyone asks for a brief.**

Implements **ADR-014**, currently *proposed*. `[VERIFIED]` The constraint is real: Reddit
returned HTTP 429 to this repository's own measurement probes on 2026-08-15, and
`ingestion/rss_news.py` has recorded the limit since 2026-08-09.

Also folds in the small independent defect found alongside it: a rate-limited or timed-out
source currently returns an empty list and vanishes from the brief with only a log line.
`[VERIFIED]` CBS did exactly that at 16:00, contributing 0 articles after a read timeout.

### → `v0.4.0` — the operator chooses the interval **and the scheduler** **(current)**

**Done when both the delivery schedule and the thing that triggers it are configuration, not a
cron line someone edited by hand.**

**The interval is a bounded choice, not a free number** (operator decision 2026-08-26, PRD D6).
Roughly 2 hours to 2 days, and the model's output limit moves with it. `[VERIFIED]` The bounds
come from measurement: 13 runs at 8 hours produced a median of 23 new articles, about 3.9 an
hour, so 30 minutes would usually deliver nothing while 2 days would swamp the cap.

Depends on `v0.3.0` and cannot be started before it — an interval feature built on
fetch-per-brief is the design ADR-014 exists to prevent. Resolves the `[UNKNOWN]` in §2 about
scheduling by making it explicit rather than discovered.

The scheduler half was added on 2026-08-17 at the operator's request, and it is a real choice
rather than a preference, because the two options fail in opposite directions.

`[VERIFIED]` Today the trigger is `0 */8 * * *` in WSL's crontab. Cron inside WSL only runs
while WSL is running, which is why `TASKS.md` P4 records that runs are skipped while the
machine sleeps and warns against inferring a rate from elapsed days.

**Observed directly on 2026-08-26**, which turns that from an inference into a measurement.
The operator reported no brief at 08:00. `[VERIFIED]` From `/var/log/syslog`, cron logged
between 3 and 7 entries every hour from 2026-08-25 14:00 through 2026-08-26 00:00, including
the 00:00 SportWire run, and then **nothing at all for hours 01:00 to 08:00**. Even the
system's own every-ten-minutes jobs stopped. The host slept, WSL was suspended with it, and
cron does not run a job it missed.

`[VERIFIED]` **`uptime` is not evidence here and it misled this investigation for a minute.**
It reported 8 hours 27 minutes of continuous uptime across the very window in which nothing
ran, because WSL2 keeps counting while the VM is paused. The gap in syslog is the evidence;
uptime is not.

`[INFERRED]` This is the case the table below exists for, and it is now concrete rather than
hypothetical: an operator who closes the lid loses every brief until the machine is next
awake at a scheduled minute, with no error and no trace in the application log.

So the operator picks, and the two answers are for two different wants:

| what you want | what schedules it |
|---|---|
| Delivery that does not stop, including while WSL is down or the machine has just woken | An OS level scheduler outside WSL: Windows Task Scheduler, or `launchd` on macOS, or a systemd timer on Linux, or something running on a phone |
| Control over when the instance is alive, so shutting it down really does stop it | Cron inside WSL, as now |

`[INFERRED]` This is the same adapter boundary the project already uses three times, for
ingestion sources, delivery channels and summarisers: one interface, several implementations,
and the pipeline never learns which one it got. A scheduler is a fourth instance of it, so the
work is a small module plus documentation rather than a new architecture.

`[UNKNOWN]` What the mobile option actually is. Naming it now would be filling a gap with
plausible prose. It needs its own investigation, and `TASKS.md` L10 already holds the phone
port as deferred pending a concrete definition.

### `v0.5.0` — NFL

Promoted from after the line to before it on 2026-08-17, see the note under `v1.0.0`.
`[VERIFIED]` `TASKS.md` records the L1 trigger as already fired, so this is held back by
sequencing rather than by its own condition.

### `v0.6.0` — MLB and NHL

The remaining two of the four major American leagues. Grouped into one milestone because the
work is the same shape twice and the second one should cost much less than the first.

`[UNKNOWN]` The data sources. Nothing has been researched for either league, and ADR-003 is the
precedent for how much that research matters: the NBA answer took two reversals and a
contradicted `[VERIFIED]` claim before it settled on balldontlie. Do not assume an equivalent
exists for MLB or NHL until someone has made the request and seen the response.

`[VERIFIED]` A concrete cost this milestone inherits, which is easy to miss: two of the lists
shipped on 2026-08-17 are NBA only. `_COMPETITION_VOCABULARY` in `processing/validate.py` holds
conferences, divisions and honours; `_TEAM_NAME_GROUPS` holds ten groups of NBA team names.
Four leagues means four of each, or one structure keyed by league. `processing/priority.py` team
keywords are NBA only in the same way.

### `v0.7.0` — delivery beyond Telegram, through OpenClaw

**Done when the operator can receive the brief on a channel other than Telegram without this
repository containing a line of channel specific code.**

Added 2026-08-17 at the operator's request. `[VERIFIED]` OpenClaw is real, MIT licensed,
self hosted and local first, and it carries channels for Discord, Google Chat, iMessage,
Matrix, Microsoft Teams, Signal, Slack, Telegram, WhatsApp and Zalo. That fits C1, C2 and C3
on its face: no API fees, nothing to sign up for, open source.

**The design that makes it work, and it matters.** SportWire delivers *to OpenClaw*, and
OpenClaw decides which messaging app that becomes. The channel choice therefore lives in the
operator's own OpenClaw configuration, outside this tree. `[INFERRED]` That is what keeps C3
intact: this repository stays publishable because it contains no bridge, no reverse engineered
protocol and no credentials, only one more `DeliveryChannel` implementation pointing at a local
process the operator runs.

`[VERIFIED]` **Two corrections to the request, both researched on 2026-08-17 rather than
assumed.**

- **WhatsApp through OpenClaw does not avoid the WhatsApp problem, it repackages it.** The
  channel uses Baileys, an unofficial WhatsApp Web client that links a real personal number by
  QR code. That is the same category `CLAUDE.md` §4 records as a ToS violation with a permanent
  ban risk, and independent write ups say to pair a number you would not mind losing and that
  Baileys clients still get banned in 2026 on usage that looks clean. Nothing here changes
  ADR-002's reasoning; what changes is that the risk now sits in a process outside this repo,
  and taking it is the operator's informed call rather than something the code decides.
- **Facebook Messenger is not supported.** It appears nowhere in OpenClaw's documentation or
  README. `[UNKNOWN]` Whether any free and publishable route to Messenger exists. Treat it as
  unresearched, not as available.

`[INFERRED]` The channels that are both free and low risk here are Signal, Discord, Slack and
Matrix, since none of them requires impersonating a web client. Those are the ones worth
demonstrating first, and a working second channel is what proves the boundary regardless of
which one it is.

Adopting this needs an ADR amending ADR-002, written when the work starts rather than now.
`[UNKNOWN]` Whether OpenClaw is stable enough to depend on. It appeared in late 2025 and moves
quickly, so pin a version and record which one was tested.

### `v1.0.0` — the line

~~**A trustworthy single-user NBA brief.**~~ **Widened 2026-08-17 at the operator's request:**
*"4 major-american sport integration before v1.0.0"* and *"Integration with Windows task
scheduling or other before v1.0.0"*. Recorded as a move rather than a quiet rewrite, per §5.

**A trustworthy single-user brief across the four major American leagues.** Specifically, all
of:

1. Briefs for NBA, NFL, MLB and NHL arrive on schedule, unattended, from a scheduler this
   repository documents, with the operator's choice of scheduler honoured (`v0.4.0`).
   The operator also picks the **interval** from a bounded set, and the brief's length scales
   with it (PRD D6, R7 and R8, decided 2026-08-26). `[VERIFIED]` Scaling the output limit alone
   is not enough: `DEFAULT_MAX_ARTICLES = 12` already binds on 8 of 22 logged runs at 8 hours,
   so a 2-day interval would discard roughly 175 of 187 articles unless the story cap scales
   too.
2. The summarisation pass rate is a **measured** number, published in the release notes.
3. No known false-accusation bug in `processing/validate.py`. `[VERIFIED]` Six were fixed
   between 2026-08-15 and 2026-08-17, so this condition is doing real work.
4. `make check` green, and the README sufficient to run it.

~~`[INFERRED]` This is deliberately narrower than `CLAUDE.md` §1, which names NBA **and** NFL.
The reasoning is goal ranking: §1 ranks *ship a working system* first, and a measured, reliable
one-league brief is a working system, while two unmeasured leagues is twice the surface with
the same unknown. NFL is the first thing after the line, not part of it.~~

**Superseded 2026-08-17, and the reasoning it replaced is worth keeping visible.** The old line
argued that one measured league beats four unmeasured ones. That argument is not wrong, and the
operator has decided anyway, which is his call. What it means in practice is that condition 2
now has to hold across four leagues rather than one, so the honest risk is that `v1.0.0`
arrives much later rather than that it arrives worse. `[INFERRED]` The way to keep it from
arriving worse is that each league ships as its own milestone with its own measurement, which
is why `v0.5.0` and `v0.6.0` are separate rather than one "add three leagues" step.

`[INFERRED]` OpenClaw at `v0.7.0` sits before the line but is not one of its conditions.
Delivery already works through Telegram, so a second channel is a widening of the product
rather than a requirement for calling it finished, and it depends on an outside project whose
stability is unknown. If it slips, the line should not slip with it.

### After 1.0, in this order

- **`v1.1.0` — multi-user routing (L8).** Only meaningful once `v0.3.0` and `v0.4.0` exist.
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

`[VERIFIED]` Two entered on 2026-08-17 by the operator's decision rather than by a trigger, and
both are named above: L1, NFL, became `v0.5.0`, and L6, WhatsApp delivery, is partly answered by
`v0.7.0`. L6 stays open regardless, because its trigger was the operator accepting a recurring
per message cost through an official provider, and the OpenClaw route is a different thing: free,
unofficial, and carrying a ban risk instead of a bill.

---

## 5. Keeping this file honest

- **One milestone is marked `(current)`.** If two ever are, that is the bug.
- **A milestone is done when its `TASKS.md` items are checked with proof**, not when it feels
  finished — `CLAUDE.md` §6 forbids marking a task complete without pasting the output.
- **Move the line rather than redefine it.** If `v1.0.0`'s conditions turn out to be wrong,
  change them here in place with a dated note, the way `SESSION.md` and `TASKS.md` record
  retractions. Do not quietly drop a condition that became inconvenient.
- ~~`[VERIFIED]` **`TASKS.md` checkboxes have drifted** and should not be counted
  mechanically: P9 is still `- [ ]` although P19's rarity floor removed the condition it
  describes, and P13's body records it resolved while its box is unchecked.~~ **Reconciled
  2026-08-16**; both are now `- [x]` with the closing evidence in their entries. The warning
  stands as a habit though: a box is only as true as the last person to edit it, so check an
  entry's body before counting its box.
