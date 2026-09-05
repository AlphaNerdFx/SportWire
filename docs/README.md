# SportWire documentation

A local-first NBA and NFL news brief, delivered to Telegram on a schedule. Runs on one
machine, uses only free sources, and records every architectural decision with the evidence
behind it.

> Moved out of the GitHub wiki on 2026-09-03. The wiki said of itself *"this wiki navigates,
> it does not duplicate"*, which was the right instinct in the wrong place: it was a second
> repository, editable in a browser, that nothing but a nightly CI job ever checked. Its
> pages are now here, reviewed in the same commit as the code they describe.

---

## Start here

| If you want to… | Go to |
|---|---|
| Run it yourself | [Getting started](reference/GETTING_STARTED.md) |
| Follow one story through the system | [Walkthrough](reference/WALKTHROUGH.md) |
| Read the target shape | [`ARCHITECTURE.md`](reference/ARCHITECTURE.md) |
| Know why something was built that way | [Decisions](decisions/README.md) |
| Run it unattended | [`SCHEDULING.md`](reference/SCHEDULING.md) |
| See how it is tested | [Testing](reference/TESTING.md) |
| Know how accurate it is | [Metrics](reference/METRICS.md) |
| Read the current state | [`SESSION.md`](sessions/SESSION.md) |
| Find the next task | [`TASKS.md`](planning/TASKS.md) |
| Contribute | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |

## What it does

Every run fetches games and news for each league, discards anything already delivered, works
out which games were notable, and sends a brief per league:

1. **Scores** — every game with its final result
2. **Notable** — comeback, overtime, close finish, wire to wire, second-half takeover, big
   quarter, big win, high scoring
3. **News** — a summarised paragraph, or the headline list if the summary fails its check

Empty sections are omitted. Outside the season there are no games, so for much of the year the
brief is news only.

## Current state

`[VERIFIED]` 2026-09-03, by running the commands named.

| | |
|---|---|
| **Working** | Games (balldontlie), news from seven feeds across two leagues, deduplication across runs, story grouping, notable-game detection, LLM summarisation behind a validator, Telegram delivery, scheduling by cron |
| **Leagues** | NBA and NFL, one brief each (ADR-015). The wiki said NFL was "not built, post-1.0"; it shipped on 2026-08-26 |
| **Tested** | `make check` → **560 passed, 1 xfailed** |
| **Delivering** | `python scripts/soak_report.py` → NBA 23 of 31 briefs kept their prose, NFL 23 of 30. The rest fell back to headline lists |
| **Known broken** | The validator grounds *entities*, not *claims*. A sentence of real names can assert something false and pass, which is the declared xfail and `TASKS.md` P5. One reached a phone on 2026-08-13 and another on 2026-09-02 |
| **Not built** | Feedback capture, individual player statistics, leagues beyond these two |

## Known limitations

Real, documented, and deliberately not hidden:

- **`--date` affects games only.** RSS has no date parameter, so historical headlines cannot
  be fetched. SportWire cannot reconstruct a past day.
- **No individual player statistics.** No free, documented source exists — every option is
  paywalled, blocked from datacenter IPs, or refuses self-identifying clients
  ([ADR-010](decisions/ADR-010-no-player-stats.md)).
- **Live game payloads are unobserved.** Every captured game reads `Final`, because it has
  been the offseason throughout development. The in-season path has therefore never executed,
  which is the main reason this is versioned `0.x`. Resolves after 2026-09-30.
- **The summariser's pass rate is now measured but young.** The numbers above come from one
  settled version over several days. An earlier "~84%" came from a single sitting and is not
  supported.

## Where everything lives

| Directory | Holds |
|---|---|
| [`decisions/`](decisions/README.md) | ADRs, and the template for a new one |
| [`planning/`](planning/TASKS.md) | `TASKS.md`, `ROADMAP.md`, `PRD.md` |
| [`process/`](process/OPERATING_RULES.md) | `OPERATING_RULES.md`, `SYSTEM_INSTRUCTIONS.md` |
| [`sessions/`](sessions/SESSION.md) | `SESSION.md`, `HANDOVER.md` |
| [`reference/`](reference/ARCHITECTURE.md) | `ARCHITECTURE.md`, `WALKTHROUGH.md`, `TESTING.md`, `GETTING_STARTED.md`, `INTERNALS.md`, `SCHEDULING.md`, `METRICS.md` |
| [`history/`](history/AUDIT.md) | `AUDIT.md` |

`README.md`, `CLAUDE.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md` and
`CHANGELOG.md` stay at the repository root, where a visitor and GitHub both look for them.

## Why the documentation is like this

An earlier version of this project was built against a handoff document written by an LLM that
described folder structures, failure histories and completed milestones **that did not exist**.
It read perfectly. Weeks of work went into a system that had never once run end to end.

Everything here therefore carries an evidence tag — `[VERIFIED]`, `[INFERRED]` or `[UNKNOWN]`
— and `[UNKNOWN]` is an acceptable answer. See [`CLAUDE.md`](../CLAUDE.md) for the rule and
[`AUDIT.md`](history/AUDIT.md) for the audit that established what the old code actually did.
