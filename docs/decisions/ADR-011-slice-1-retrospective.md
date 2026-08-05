# ADR-011 — What building slice 1 actually taught

**Date:** 2026-08-05
**Status:** accepted (retrospective; task H12)

## Surface
Slice 1 works: a real brief reaches a real phone. Along the way, several things the project
"knew" turned out to be wrong, and the ones that mattered were caught by measuring rather
than by reasoning.

## Thorough

### 1. Recorded evidence expires

`[VERIFIED]` `CLAUDE.md` carried a `[VERIFIED]` claim that `cdn.nba.com` "works from
anywhere." On live retest it returned **HTTP 403** from Akamai — from the agent's sandbox
*and* from the operator's own residential machine. The tag had been carried forward from an
earlier session's research and restated as fact.

The whole NBA data source had to be replaced (ADR-003 rewritten). The evidence rule in
`CLAUDE.md` §0 stopped fabrication but did not stop **staleness**, which is a different
failure. `OPERATING_RULES.md` §2 now encodes the fix: a `[VERIFIED]` tag from a previous
session is `[Likely]`, not `[Certain]`.

### 2. Measurement beat reasoning, repeatedly

Every one of these was a confident, sensible assumption that real data contradicted:

| Assumption | Reality |
|---|---|
| `pubDate` identifies an RSS item | `[VERIFIED]` 6 distinct timestamps across 15 items; 7 stories share one second |
| RSS items arrive newest-first | `[VERIFIED]` they do not — item 11 was newer than items 1–10 |
| Every article has an author | `[VERIFIED]` absent on 2 of 15; a required `str` would have crashed on first run |
| An open JSON endpoint requires no bypass | `[VERIFIED]` ESPN's internal API returns 403 to any self-identifying client, 5/5 |
| Summer League needs filtering out | `[VERIFIED]` balldontlie returns nothing for Summer League dates — no filter needed |
| A "notable games" threshold is easy to pick | First attempt flagged **5 of 9 games** and labelled two different games "largest margin" |

`[INFERRED]` The general rule: **the shape and behaviour of external data is an empirical
question, not a design question.** Not one of these was discoverable by thinking harder.

### 3. Enforce rules structurally, not editorially

Three rules that were previously prose became mechanisms, and the difference is that a
mechanism cannot be forgotten:

- **Dependency discipline** — the legacy `.venv` was `[VERIFIED]` **5.6 GB / 151 packages**,
  containing the entire *deferred* column of `CLAUDE.md` §11 before anything in the *required*
  column had run. Rebuilt at **68 MB / 21 packages**; `import torch` now raises rather than
  silently succeeding.
- **Failure policy** — `CLAUDE.md` §5 rule 6 ("a dead source degrades, never crashes") is
  enforced by subclasses implementing `_fetch()` while the base class owns `fetch()`. An
  adapter author cannot opt out, because they never write the method containing the policy.
- **Ordering of record-then-send** — items are recorded as delivered *after* delivery
  succeeds. Recording first would silently lose items forever on a failed send.

### 4. The same boundary answered three different questions

`SourceAdapter` (inputs), `DeliveryChannel` (outputs), and the planned `Summarizer` (M7) are
the same shape: an abstract interface, concrete implementations, and a pipeline that depends
only on the abstraction. `[INFERRED]` A pattern reused three times for unrelated problems is
evidence the boundary is real rather than decorative. Task M6 remains the actual exam.

### 5. Features were declined on evidence, not deferred on principle

Two capabilities were dropped with measurements attached rather than vague "later" notes:

- **Semantic dedup (ADR-005)** — the closest real title pair scored 0.550 while two entirely
  unrelated stories scored 0.438, an 0.11 margin from one example. And the "duplicate" pair
  was not duplicate: the second article carried a different person's comments, so collapsing
  it would have deleted information.
- **Player box scores (ADR-010)** — every free source tested and failed; the paid tier is
  $9.99/month for a dissatisfaction nobody has experienced yet, since it is the offseason and
  no in-season brief has ever been delivered.

### 6. Tests and real usage catch different bugs — neither substitutes for the other

Two defects appeared within an hour of the first real send:

- **Real usage found what tests would not.** `--date 2026-01-15` delivered January's
  scoreboard with today's news. Correct behaviour (RSS has no date query), misleading flag.
  No unit test would have flagged it; using it did, immediately.
- **Tests would have found what usage could not.** A run delivered two messages instead of
  three. From the phone this was indistinguishable from a crash, a splitter bug, or silent
  data loss. The answer came from the database timestamps: two runs 44 seconds apart, with
  dedup correctly suppressing already-sent news.

`[INFERRED]` The operator's position had been that correctness "can only be verified by
content that shows on the Telegram bot." The second case disproves it directly — the output
looked fine and revealed nothing. **Silent omission is invisible from the output by
definition.**

### 7. The learning contract was reversed, and that is the largest open risk

ADR-006 specified that the human writes signatures, docstrings and test assertions, and the
agent writes only the bodies. Partway through slice 1 the operator instructed: *"You'll write
the code not me."*

`[VERIFIED]` All ten application files were written by the agent. The reversal was recorded
rather than performed silently, and H13 remains open precisely because of it — the operator
has since stated he does not understand the system.

`[INFERRED]` This is the project's primary goal at risk, not a process footnote:
`CLAUDE.md` §1 ranks "the operator can explain it" **above** "it ships." A working system he
cannot defend is defined by this repo as a failure, not a success. The mitigation that
remains is H13 itself, which cannot be delegated.

## Deep

The connecting idea across items 1, 2 and 6 is that **confidence and correctness are
independent variables**, and this project keeps finding new places where they diverge:

- A *fabricated* handoff was fluent and wrong — the failure that started the rebuild.
- A *verified* claim was accurate when written and wrong when reused.
- A *reasonable* schema assumption was defensible and wrong against real payloads.
- A *correct* output looked identical to a broken one.

Each needs a different defence: evidence tagging for the first, re-verification for the
second, fixtures for the third, and instrumentation for the fourth. `[INFERRED]` No single
discipline covers all four, which is why the repo now carries an evidence rule, a
re-verification rule, a fixtures rule, and structured logging — and why "I looked at it and
it seemed fine" is never sufficient for any of them.

## Reversal condition

If H13 is passed and the operator can explain all ten files, item 7 downgrades from an open
risk to a recorded process deviation. If it is not passed, ADR-006's remedy applies as
written: the files he cannot explain are deleted and regenerated with a different approach.
