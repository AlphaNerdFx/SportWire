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
| R1 | Brief delivered automatically on a schedule, without manual invocation | **Not built** — `TASKS.md` M8 |
| R2 | News section is a written summary rather than a list of headlines | **Not built** — M7 |
| R3 | Configuration read from one module rather than `os.getenv` in `main.py` | **Not built** — M2 |
| R4 | Structured logging of what was fetched, dropped and sent | Partial — `main.py` logs; not configurable |
| R5 | A second news source, proving the adapter boundary holds | **Not built** — M5/M6 |
| R6 | NFL coverage | `[UNKNOWN]` — **decision needed, see §7 D3** |

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

1. Runs unattended on a schedule for **14 consecutive days** without manual intervention.
2. Zero duplicate stories delivered across those 14 days.
3. No run crashes; source failures degrade visibly in the log instead.
4. The operator reads the brief instead of opening a sports app. **This is the real test** —
   an unread brief is a failed product regardless of uptime.
5. `[UNKNOWN]` Whether the operator can explain the implementation. `TASKS.md` H13 attempt 1
   scored 2 of 8. `CLAUDE.md` §1 ranks this **above** shipping, so v1.0.0 is arguably not
   reachable until it passes.

## 7. Open decisions blocking v1.0.0 scope

**These are for the operator. Each one causes rework if built around wrongly.**

### D1 — Delivery cadence
How often does a brief arrive? `.env.example` says `POLL_INTERVAL_HOURS=8`; the operator has
also described "the last six hours." These must become one number.
*Affects:* R1 scheduling, M7's prompt ("summarise the last N hours"), and how empty a brief
is on a quiet cycle.

### D2 — Deduplication window
`.env.example` says `DEDUP_WINDOW_HOURS=48`, but `storage/db.py` currently remembers items
**forever**, deliberately: `[VERIFIED]` ESPN's feed reaches back roughly three days, so a
48-hour window would re-send items that are still listed.
*Decision needed:* keep "remember forever", or introduce a window and accept the duplicates?
*Note:* D1 and D2 are **separate knobs** that the original documents conflated.

### D3 — Is NFL in v1.0.0?
The project is named for both sports. `TASKS.md` L1 defers NFL behind "NBA path stable across
several real runs."
*Affects:* whether v1.0.0 is weeks or days away. `[INFERRED]` The adapter boundary means NFL
is additive rather than invasive — but it is still a new source, new fixtures, new tests.

### D4 — What "phone port" means
`SESSION.md` §9 Q8 records this as undefined. Candidates: cron on the operator's PC (already
possible), Termux on Android, or a hosted trigger. Each is a different amount of work and N1
forbids the third.

### D5 — Summarizer input richness
`[VERIFIED]` RSS gives a title and a one-to-two sentence description. Full article text would
require fetching article pages, which is the C3 scraping exposure ADR-009 exists to avoid.
*Decision:* accept description-only input for M7, or reopen the sourcing question?

## 8. Release plan

| Release | Contents | Gate |
|---|---|---|
| **v0.1** ✅ | F1–F8. Manual invocation. | Delivered to a phone 2026-08-05 |
| **v0.2** | R2 (summarizer), R3 (settings module) | D1, D5 answered |
| **v0.3** | R1 (scheduling), R4 (logging) | D1 answered |
| **v0.4** | R5 (second source, proves M6) | — |
| **v1.0.0** | All of the above + §6 criteria met | D1–D4 answered; H13 passed |
| **post-1.0** | NFL (if D3 says so), RAG query interface, non-technical setup (L13), semantic dedup if ADR-005 fires | Triggers in `TASKS.md` |

## 9. Known limitations carried into v1.0.0

Recorded in `SESSION.md` §8b; repeated here because a PRD that hides them is marketing.

- **L-1** `--date` affects games only; news is always current. SportWire cannot reconstruct a
  past day.
- **L-2** No individual player statistics. No free documented source exists (ADR-010).
- **L-3** Live and scheduled game payload shapes are unobserved — every captured game reads
  `Final`, because it is the offseason. Resolve after 2026-09-30.
