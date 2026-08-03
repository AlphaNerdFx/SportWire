# ADR-003 — NBA game data via balldontlie.io (supersedes the prior `cdn.nba.com` decision)

**Date:** 2026-08-03
**Status:** accepted

## Surface
The plan was to pull live NBA scores from a free NBA.com data feed. That feed turned out to
be blocked for everyone, not just us, so we're switching to a different free provider,
`balldontlie.io`, that is built for outside developers to use.

## Thorough
The original decision (recorded in `SESSION.md` §5 as the prior ADR-003) was to use
`cdn.nba.com`'s live JSON endpoints — undocumented but believed unprotected, based on the
prior session's research. That belief was carried into `CLAUDE.md` §4 as a `[VERIFIED]` fact
without being re-tested this session.

It was re-tested today, twice: once from the coding agent's sandboxed shell, once from the
operator's own residential machine with no sandbox. Both attempts, on two different
`cdn.nba.com` paths, returned HTTP 403 from Akamai's edge (`errors.edgesuite.net`). The
identical result from two different network positions rules out "sandbox has a bad IP" as
the explanation — the endpoint itself is now protected, or was never actually unprotected and
the earlier claim was itself unverified prose (see `docs/AUDIT.md` for the pattern of
fabricated/unverified claims already found once in this project).

Three alternatives were live-tested before deciding:

| Source | Result | Note |
|---|---|---|
| `stats.nba.com` | Connection hangs from the sandbox (consistent with the still-standing datacenter-IP-block finding) | Not retested residentially; even if it worked for the operator, using it would make the repo unusable for anyone who clones it (violates C3) |
| `site.api.espn.com` (undocumented JSON) | `[VERIFIED]` HTTP 200, real data, zero setup | Rejected: same undocumented/ToS-grayness category as the ESPN-scraping caution already in `CLAUDE.md` §4 — swapping one unofficial endpoint for another doesn't fix the underlying risk |
| `api.balldontlie.io` | `[VERIFIED]` HTTP 401 without a key — but it is a **documented API intended for third-party use**, with a free tier requiring only signup | **Chosen** |

**Decision: `balldontlie.io` becomes the critical-path NBA game-data source.** It is the only
candidate that is both free and actually meant to be used by outside code, which is what C2
(free/open-source) and C3 (publishable, no ToS violations) actually require — not just "any
endpoint that happens to return 200 today."

**Tradeoff:** requires the operator to sign up and manage a free API key (a new piece of
config `cdn.nba.com` wouldn't have needed), and the provider could add rate limits or a paid
tier later — it has changed its access model before (anonymous access existed previously and
was removed). Accepted: a documented API changing its terms with notice is a fundamentally
different risk than an undocumented endpoint disappearing or blocking us with no warning.

## Deep
This is the same lesson as ADR-002 (Telegram over WhatsApp) applied a second time: **prefer
the boring, documented, intended-for-you interface over the clever unofficial one**, even
when the unofficial one works today. Undocumented APIs and reverse-engineered endpoints are
an implicit contract with no SLA — the provider owes you nothing and can change behavior
without notice, which is exactly what appears to have happened here between the prior
session's research and today. This also generalizes to why `[VERIFIED]` tags must be
re-earned per session, not inherited: external systems are not static, and evidence has a
shelf life.

## Reversal condition
If `balldontlie.io` introduces a paid tier with no usable free quota, or its data proves
insufficient (e.g. missing live in-progress game state), re-open this ADR and evaluate
`site.api.espn.com` as a fallback with an explicit, documented ToS-risk acceptance — not a
silent substitution.
