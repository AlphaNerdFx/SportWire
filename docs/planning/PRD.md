# SportWire — Product Requirements Document

**Version:** 0.1 (draft)
**Date:** 2026-08-06
**Status:** `[UNKNOWN]` sections marked below require operator decisions before v1.0.0 scope
is fixed. Per `CLAUDE.md` §0, unanswered questions are left explicitly unanswered rather
than filled with plausible prose.

---

## 1. Problem

Following the NBA across multiple outlets means checking several apps and websites daily and
reading the same story several times under different headlines. Existing sports apps optimise
for engagement — push notifications per event, autoplay video, ranked feeds — rather than for
"tell me what happened and let me get on with my day."

## 2. Product

A local-first aggregator that pulls NBA game data and news on a schedule, removes what it has
already reported, identifies what was notable, and delivers a short brief to the operator's
phone via Telegram.

**Non-goals for v1.0.0**, stated so scope creep is visible when it happens:

- Not a live score ticker. It reports on a schedule, not per-event.
- Not a chatbot. Delivery is one-way; there is no query interface (deferred, `TASKS.md` L9).
- Not a hosted service. It runs on one machine, for one recipient (`SESSION.md` §9 Q9).
- Not a historical archive. `[VERIFIED]` News cannot be fetched for a past date — RSS has no
  date query (`SESSION.md` §8b L-1).

## 3. Users

| User | Description | Status |
|---|---|---|
| **Primary** | The operator. Single recipient, runs it on his own machine. | v1.0.0 |
| **Secondary** | Developers who clone the repo and run their own instance with their own keys. | v1.0.0 — drives the "must work from any IP" and "no paid tier" constraints |
| **Tertiary** | Non-technical users who want a brief without editing `.env`. | **Deferred** — `TASKS.md` L13 |

## 4. Current capabilities (v0.1, working and verified)

`[VERIFIED]` 2026-08-05, delivered to a real phone:

| # | Capability | Evidence |
|---|---|---|
| F1 | Fetch NBA games for a date | balldontlie.io, ADR-003 |
| F2 | Fetch NBA news | ESPN public RSS, ADR-009 |
| F3 | Suppress already-delivered items across runs | SQLite seen-store; a repeat run sends nothing |
| F4 | Collapse near-identical headlines within a run | `SequenceMatcher` ≥ 0.85 |
| F5 | Identify notable games | comeback, overtime, closest finish, largest margin, highest scoring |
| F6 | Deliver a three-message brief | scores → notable → news, one notification |
| F7 | Preview without sending | `--dry-run` |
| F8 | Degrade rather than crash on a dead source | enforced in `ingestion/base.py` |

## 5. Requirements for v1.0.0

### Functional

| ID | Requirement | Status |
|---|---|---|
| R1 | Brief delivered automatically on a schedule, without manual invocation | ~~Not built~~ **Built.** `[VERIFIED]` 2026-09-24: cron every 30 minutes with `--if-due`, or Windows Task Scheduler; 23 accumulated days delivered (`scripts/soak_report.py`) |
| R2 | News section is a written summary rather than a list of headlines | ~~Built, then disabled, ADR-012; dropped from v1.0.0 scope.~~ **On by default since 2026-08-10**, validated against the sources, falling back to headlines when no draft passes (ADR-012, ADR-016). `[VERIFIED]` Prose in 72% of NBA and 83% of NFL briefs by 2026-09-23. `--no-summary` turns it off |
| R3 | Configuration read from one module rather than `os.getenv` in `main.py` | ~~Not built~~ **Built**: `config/settings.py` |
| R4 | Structured logging of what was fetched, dropped and sent | ~~Partial~~ **Built**: dated log lines for every stage, level set by `LOG_LEVEL` or `--log-level` |
| R5 | A second news source, proving the adapter boundary holds | ~~Not built~~ **Built**: 7 feeds through one adapter class |
| R6 | NFL coverage | ~~Decision needed~~ **Built, and in v1.0.0 scope** (§7 D3, `v0.5.0`). The NFL community feed is after v1.0.0 (`TASKS.md` P46) |
| R7 | The operator picks the delivery interval from ~~a bounded set of choices~~ **8, 12 or 24 hours** | **Built** 2026-09-24 (§7 D6, `TASKS.md` P42) |
| R8 | The summary's length scales with the interval, so a longer gap yields a longer brief | **Built**: story count, summary length, per-outlet cap and repeat window all scale (§7 D6) |

### Non-functional

| ID | Requirement | Source |
|---|---|---|
| N1 | Runs on one Windows machine via WSL2, Python 3.10. No cloud, no containers. | C1 |
| N2 | No paid API tiers or recurring costs | C2, ADR-010 |
| N3 | Publishable as open source; no ToS-violating access | C3, ADR-009 |
| N4 | A dead source shortens the brief; it never crashes the run | `CLAUDE.md` §5.6 |
| N5 | Anyone cloning the repo can run it with their own free keys | C3 |
| N6 | Every factual claim in documentation carries an evidence tag | `CLAUDE.md` §0 |

## 6. Success criteria for v1.0.0

`[INFERRED]` — proposed, not yet agreed:

1. Runs unattended on a schedule for **14 accumulated days** without manual intervention.
   ~~consecutive~~ **Changed 2026-09-04 at the operator's instruction.** A shut-down PC reset
   the count, and the PC being off says nothing about whether the software runs unattended.
   Days on which the machine never ran do not count for the gate and do not count against it;
   a run that executed and failed does. `[VERIFIED]` 2026-09-23: **23 of 14**, met.
2. Zero duplicate stories delivered across those 14 days. ~~`[VERIFIED]` Currently unmet: the
   same story is redelivered as new articles about it arrive (`TASKS.md` P68).~~ P68 fixed that
   across briefs on 2026-09-04. `[VERIFIED]` **Still unmet, for a different reason, 2026-09-24:**
   one brief can carry the same story several times (six Kawhi Leonard extension articles on
   09-23), because grouping failed to merge them (`TASKS.md` P70), and repeat suppression
   judged against stories that were never shown (P71).
3. No run crashes; source failures degrade visibly in the log instead.
4. The operator reads the brief instead of opening a sports app. **This is the real test** —
   an unread brief is a failed product regardless of uptime.
5. `[UNKNOWN]` Whether the operator can explain the implementation. `TASKS.md` H13 attempt 1
   scored 2 of 8. `CLAUDE.md` §1 ranks this **above** shipping, so v1.0.0 is arguably not
   reachable until it passes.

## 7. Scope decisions — **RESOLVED 2026-08-06**

### D1 — Delivery cadence and summary window → **the run defines the window**
Poll every 8 hours. The summarizer covers **whatever survived deduplication**, which is by
definition everything new since the last run.

`[VERIFIED]` The operator initially proposed a fixed 6-hour summary window against an 8-hour
poll. Measured against the live feed, 6 of 17 items were older than 6 hours — so that pairing
creates a **2-hour blind spot** where an article is new, survives dedup, and is then silently
excluded from the summary. Letting the run define the window removes the failure mode instead
of tuning it, and stays correct if the cadence is ever changed.

### D6 — Interval is a bounded choice, and output scales with it → **decided 2026-08-26**

Operator decision: 8 hours stays the standard for now; at v1.0.0 the operator picks from a
**set** of intervals rather than editing a cron line, bounded roughly between **2 hours and 2
days**, and the model's output limit moves with the choice.

**Why bounded, with the measurements behind the bounds.** `[VERIFIED]` Across 13 scheduled
runs at 8 hours, new articles surviving deduplication were **min 10, median 23, max 81**,
which is roughly **3.9 new articles per hour** in the offseason. Extrapolating that rate:

| interval | expected new articles | why it sits inside or outside the bounds |
|---|---|---|
| 30 min | ~2 | Most runs would deliver nothing. `main.py` already logs "nothing new to report" and sends no message, so the brief becomes noise or silence |
| **2 hours** | ~8 | The floor. Enough for a brief most of the time, and still under the 12-story cap |
| **8 hours** | ~23 | Today's standard |
| 24 hours | ~94 | Well past the cap; most news is discarded |
| **2 days** | ~187 | The ceiling, and already lossy — see below |

`[UNKNOWN]` These are offseason rates. In season the volume will be higher and the bounds
should be re-measured rather than assumed to hold.

**A longer interval does not currently produce a fuller brief, and this is the part that
needs building.** `[VERIFIED]` `DEFAULT_MAX_ARTICLES = 12` caps the stories that reach the
summariser, and **8 of 22 logged runs hit exactly 12** — the cap already binds regularly at 8
hours. At 2 days it would discard roughly 175 of 187 articles. So scaling the *output token
limit* alone is not enough: **the story cap has to scale too**, or a longer interval simply
loses more news while producing the same twelve-story summary.

`[INFERRED]` Three quantities move together and should be derived from one interval setting
rather than tuned separately: the story cap (`DEFAULT_MAX_ARTICLES`), the output limit
(`DEFAULT_SUMMARY_CHARS`, currently 1024), and probably the chunk count, since
`processing/summarize.py` already splits above `CHUNK_SIZE = 5` and a 40-story brief would be
8 chunks and 9 model calls. `[VERIFIED]` The 2026-08-26 00:00 run took **10 minutes 36
seconds** for 12 stories in 3 chunks, so run time scales with this too and a 2-day brief may
approach a timeout.

`[INFERRED]` Deriving all three from the interval keeps D1 true: the run still defines the
window, and nothing gains a second source of truth about how much news a brief covers.

**Decided 2026-09-24: the choice is 8, 12 or 24 hours**, not the 2-hour-to-2-day band above.
The operator picked the three; they were then checked against the pipeline before building.

| Check | Finding | Verdict |
|---|---|---|
| News supply | `[VERIFIED]` 8.63 articles an hour arrived over the last 7 days across both leagues (`SeenStore.arrivals_per_hour`), and a brief at 8 hours groups a median 37.5 stories (minimum 10) from the log | Enough to fill 12, 15 or 21 stories |
| Story count and length | `brief_size_for`: 12 stories / 1024 characters at 8h, 15 / 1280 at 12h, 21 / 1792 at 24h | Unchanged at 8h |
| Per-outlet cap | `[VERIFIED]` A fixed cap of 4 per outlet limits NFL, with 3 feeds, to 12 stories at any interval, and NBA to 15 | **Did not hold.** The cap now scales by the same ratio: 4, 5, 7 (r/nba 3, 4, 5) |
| Repeat window | `[INFERRED]` A fixed 24-hour memory misses the previous brief at a 24-hour interval, which arrives 24 to 24.5 hours earlier | **Did not hold.** Now `max(24, 2 x interval)`: 24, 24, 48 |
| Message length | 1792 characters is under Telegram's 4096; headline fallbacks are split on blank lines | Holds |
| Model time | `[VERIFIED]` Summarising 12 or 13 stories took a median 28 s, 90th percentile 214 s, maximum 420 s since 09-08. `[INFERRED]` 21 stories means 5 note chunks instead of 3 | Holds, well inside a 30-minute cron gap; re-measure once a 24h brief runs |

`[UNKNOWN]` In-season NBA volume. The rate above includes the NFL season but not the NBA's,
which starts in October.

### D2 — Deduplication window → **168 hours (7 days)**
`[VERIFIED]` 2026-08-06, live measurement of ESPN's feed (17 items, oldest **99.1 hours** old):

| Window | Items older than the window but still listed → **re-sent every run** |
|---|---|
| 8h | **3 of 17** |
| 48h | 2 of 17 |
| **168h** | **0 of 17** |

The window controls how long *we remember*, not how long ESPN publishes. A short window makes
duplicates **worse**: forget an item still sitting in the feed and it looks new again on every
cycle. An 8-hour window at three runs a day would re-deliver a stale article roughly a dozen
times. 168h measures zero duplicates while still bounding database growth.

~~`[UNKNOWN]` Purging is not yet implemented.~~ **Implemented** (issue #10, closed 2026-08-25):
every run purges delivered, polled and story-name rows older than the window.

### D3: Sport scope → ~~**NBA only for v1.0.0**~~ **NBA and NFL for v1.0.0** (2026-09-24)
~~Expand to the four major US leagues (NFL, MLB, NHL) *after* 1.0.~~ NFL was built on 2026-08-26
(`v0.5.0`). On 2026-08-17 the operator widened v1.0.0 to all four leagues; on 2026-09-24 he
narrowed it back to NBA and NFL, with MLB as `v1.1.0` and NHL as `v1.2.0` (`ROADMAP.md`). `[INFERRED]` The adapter
boundary makes each additional sport additive rather than invasive, but each still needs a
source, fixtures and tests. Ships v1.0.0 in days rather than weeks.

### D4 — Scheduling and phone delivery → **cron first, Termux wrapper after**
A cron entry invoking `main.py` on the operator's machine is v1.0.0. A Termux-based Android
wrapper follows, motivated by accessibility for non-technical users (L13).

`[Likely]` Constraint on the messaging ambition, recorded before it becomes a plan: **Android
does not permit automated WhatsApp sending from a local app.** WhatsApp exposes no local send
API; a `wa.me` intent opens the app with text prefilled but still requires a manual tap. Full
automation needs either the paid Business API (recurring cost, ADR-002) or an unofficial
bridge (ToS violation, ban risk). The genuinely local equivalents that work are **Termux
notifications** (free, no ToS issue) and `termux-sms-send` (works, but carrier-billed per
message). Any of these would sit behind the existing `DeliveryChannel` interface.

A *hosted* service was also raised; it contradicts N1/C1 and would need a superseding ADR.

### D5 — Summarizer input → **news descriptions only**
Title plus the RSS description. No article body: fetching article pages is the C3 scraping
exposure ADR-009 exists to avoid. Game scores are excluded from the summary because, in the
operator's words, they are self-explanatory — they already have their own message.

## 8. Release plan

| Release | Contents | Gate |
|---|---|---|
| **v0.1** ✅ | F1–F8. Manual invocation. | Delivered to a phone 2026-08-05 |
| **v0.2** | ~~R2 (summarizer)~~ disabled per ADR-012; R3 (settings module) | — |
| **v0.3** | R1 (scheduling), R4 (logging) | D1 answered |
| **v0.4** | R5 (second source, proves M6) | — |
| **v1.0.0** | All of the above + §6 criteria met, for NBA and NFL, running from a fresh clone | D1 to D6 answered; H13 passed; `ROADMAP.md` conditions |
| **post-1.0** | ~~NFL (if D3 says so)~~ MLB (`v1.1.0`), NHL (`v1.2.0`), the NFL community feed (P46), RAG query interface, non-technical setup (L13), semantic dedup if ADR-005 fires | Triggers in `TASKS.md` |

## 9. Known limitations carried into v1.0.0

Recorded in `SESSION.md` §8b; repeated here because a PRD that hides them is marketing.

- **L-1** `--date` affects games only; news is always current. SportWire cannot reconstruct a
  past day.
- **L-2** No individual player statistics. No free documented source exists (ADR-010).
- **L-3** Live and scheduled game payload shapes are unobserved — every captured game reads
  `Final`, because it is the offseason. Resolve after 2026-09-30.
