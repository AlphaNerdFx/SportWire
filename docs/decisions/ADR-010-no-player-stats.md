# ADR-010 — Notable events use team-level data only; no player box scores

**Date:** 2026-08-05
**Status:** accepted

## Surface
The "notable events" message reports things like comebacks, overtime and blowouts, using
team scores. It does not say "player X scored 40 points," because there is no way to get
that for free without using data the provider does not publish for outside use.

## Thorough

The operator's spec for message 2 was "remarkable individual/team performances." Team
performances are delivered. Individual performances are not, and this ADR records why.

**Every free source was tested live on 2026-08-05:**

| Source | Player box scores | Verdict |
|---|---|---|
| balldontlie free tier | `[VERIFIED]` HTTP 401 on `/v1/stats` and `/v1/box_scores/live` | Not available |
| balldontlie All-Star tier | `[GUESSING]` presumably yes — the pricing page lists tiers, not a feature matrix | **$9.99/month, recurring** — violates C2 without approval |
| TheSportsDB free | `[VERIFIED]` HTTP 404 on `eventstats.php` | Not available |
| `stats.nba.com` | `[VERIFIED]` times out (curl exit 28) from a datacenter IP | Works only from the operator's own connection, so anyone cloning the repo gets nothing — violates C3 |
| ESPN internal JSON (`site.api.espn.com`) | `[VERIFIED]` yes — returns per-game leaders | See below |
| Basketball Reference / StatMuse | `[INFERRED]` no public API; scraping only | Sports Reference prohibits bots and rate-limits aggressively — violates C3 |

**On ESPN's internal endpoint specifically.** An earlier draft of this decision argued it
was acceptable because, unlike `stats.nba.com`, it required no bypass. **That argument was
withdrawn when it was actually tested:**

| User-Agent | Result |
|---|---|
| `SportWire/0.1 (+https://github.com/sportwire)` | `[VERIFIED]` **403 × 5** |
| `Mozilla/5.0 … Chrome/124 …` | `[VERIFIED]` **403 × 5** |
| `python-requests/2.34.2` (library default) | `[VERIFIED]` 200 × 10 |

The endpoint *does* filter, and it only serves clients that decline to identify themselves.
The same self-identifying User-Agent gets `[VERIFIED]` HTTP 200 three times out of three
from ESPN's **published RSS feed**. One interface accepts named third parties by design;
the other refuses them. That is the provider indicating which one is intended for us.

**Decision: message 2 uses team-level data only** — comebacks (derived from per-period
scores), overtime, closest finish, largest margin, highest combined score. The operator
declined the paid tier explicitly on 2026-08-05: *"I won't purchase any subscription for
this open-source project."*

**Tradeoff accepted:** no "40 points, 12 rebounds" lines. `[INFERRED]` Mitigated by the
news feed itself — when an individual performance is genuinely remarkable, ESPN writes an
article about it, and message 3 delivers that. The operator raised this argument first.

## Deep

The generalisable lesson is about **when to buy your way out of a constraint.** The
$9.99/month option was available at any point and would have removed the problem
immediately. It was declined not only on cost but on timing: as of this decision it is the
NBA offseason, no in-season brief has ever been delivered, and therefore **nobody has yet
experienced the dissatisfaction the purchase would fix.**

`ARCHITECTURE.md` §10 records the legacy prototype's fatal version of this error —
"optimising for a scale you have not reached costs the scale you have" — where weeks went
into pgvector, asyncpg and Alembic while no story ever reached a phone. Paying for data to
solve an unobserved problem is the same mistake with a credit card attached.

The second lesson is narrower and worth keeping: **an API's access rules are evidence about
its intended audience.** A published feed that serves a self-identifying client, next to an
internal endpoint that 403s the same client, is not an ambiguous situation requiring a legal
opinion. The 403 *is* the answer.

## Reversal condition

Revisit after the season starts (2026-09-30) and the brief has run daily for roughly two
weeks. If the operator can point to specific briefs that felt thin without box-score lines,
that is real evidence and the $9.99 tier becomes a defensible purchase — **after**
confirming All-Star actually includes `/v1/stats`, which is currently `[GUESSING]`.
Reversal on ESPN's internal endpoint requires it serving a self-identifying client, which
would change what the provider is signalling.
