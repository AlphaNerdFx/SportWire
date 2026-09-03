# Decisions

> Moved out of the GitHub wiki on 2026-09-03. It now sits in the folder it
> indexes, so an ADR cannot be added without this list being in the same diff.

Every architectural choice is recorded as an ADR in
[`docs/decisions/`](.), with
the evidence behind it and the condition that would reverse it.

This page is an index. **The ADRs themselves are authoritative.**

---

## Recorded decisions

| ADR | Decision | The evidence in one line |
|---|---|---|
| 001 | Rebuild rather than salvage the prototype | Nine concerns implemented 2–3 times over; the delivery layer had never executed |
| 002 | Telegram, not WhatsApp | WhatsApp Business API bills every message with no free tier; unofficial bridges risk a permanent ban |
| [003](ADR-003-nba-data-source.md) | balldontlie for game data | `cdn.nba.com` returned **HTTP 403** from two independent networks, contradicting a `[VERIFIED]` claim carried over from an earlier session |
| 004 | SQLite, not Postgres | Tens of rows per run. Also: requiring a database *server* would block anyone cloning the repo |
| 005 | No embeddings yet | Deferred until a real near-duplicate pair exists that lexical matching misses |
| 006 | Human writes interfaces, agent writes bodies | Later reversed by the operator; consequences recorded in ADR-011 |
| 007 | Three-layer explanations at decision points only | Per-change essays would exhaust context faster than the coding |
| 008 | Evidence tagging is mandatory | The fabricated handoff was this project's most expensive failure |
| [009](ADR-009-nba-news-source.md) | ESPN's public RSS for news | A published feed is an invitation to consume; scraping the same site is not |
| [010](ADR-010-no-player-stats.md) | Team-level "notable games" only | No free documented source for player box scores exists |
| [011](ADR-011-slice-1-retrospective.md) | Retrospective on building v0.1 | What actually went wrong and why |
| [012](ADR-012-summarisation.md) | LLM summarisation ships **enabled, behind a validator** | Four models tested; every one fabricated facts, so output is checked against its sources and falls back to headlines |
| [013](ADR-013-openclaw-stays-external.md) | External assistants may orchestrate SportWire, never be a dependency | OpenClaw reaches WhatsApp via Baileys — the exact mechanism ADR-002 rejected |
| [014](ADR-014-fetch-cadence-independent-of-delivery.md) | Fetch cadence is independent of delivery cadence | Polling often and sending rarely are different needs; tying them made one hostage to the other |
| [015](ADR-015-one-brief-per-league.md) | One brief per league, each on its own schedule | Football and basketball in one message meant one league's quiet day diluted the other's news |
| [016](ADR-016-which-model-writes-the-brief.md) | Which model writes the brief, and what happens when it will not | A small model writes first and a larger one is the fallback; a two-league run went from 183-490s to 51s |

---

## Three findings worth reading even if you skip the rest

### Verified evidence expires

`CLAUDE.md` carried a `[VERIFIED]` claim that `cdn.nba.com` "works from anywhere". Retested
live, it returned **HTTP 403** from Akamai — from a sandbox *and* from a residential
connection. The tag had been carried forward from earlier research and restated as fact.

The whole NBA data source had to be replaced. A `[VERIFIED]` tag from a previous session is
now treated as `[Likely]`, not `[Certain]`.

### Fluency is uncorrelated with truth

Given 15 real articles, `gemma3:4b` ignored them entirely and produced fluent, wholly
fabricated NBA news — a Gabe Vincent signing, an Anthony Davis injury return, a Celtics
trade. None of it happened. `mistral:7b`, the best of four models tested, scored perfectly on
one input and then renamed Dillon Brooks to "Devin Booker" on the next.

~~Summarisation therefore ships off.~~ **Corrected 2026-08-14.** That held until
2026-08-10, when ADR-012 reversed it. Summarisation now ships **on**, because the output is
checked against its sources before it can be sent and falls back to the headline list when it
fails. Fluency is still uncorrelated with truth; what changed is that nothing has to trust it.

`[VERIFIED]` No invented *name* has reached a phone. `[VERIFIED]` A false *claim* has — the
check grounds entities, not relationships, so a sentence built entirely from real sourced
names can still assert something no source said. One was delivered on 2026-08-13. Open.

### Rules enforced by mechanism beat rules enforced by memory

The evaluation above concluded, in writing, that single-run testing cannot establish
confidence at this model size. Two commits later a model was adopted on the strength of a
single run — the exact error just documented.

What caught it was a scripted check comparing capitalised names in the output against names
present in the source. Not the rule. The mechanism.

The same principle appears throughout: the virtualenv holds only permitted packages so an
unauthorised import fails at import time, and the failure policy lives in a base-class method
adapters never write.

**This page was itself an instance of the failure.** `[VERIFIED]` For four days it stated that
summarisation ships disabled, after that decision had been reversed, and linked to an ADR
filename that no longer existed. The Home page's own rule — *"this wiki navigates, it does not
duplicate"* — is exactly the kind of rule held in memory, and it did not hold. `make check`
now fails when any documentation link points at a file that does not exist, and CI runs it
daily, so a wiki edit cannot quietly outlive the repository it describes.
