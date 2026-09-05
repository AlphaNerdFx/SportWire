# Metrics

Two questions this project kept answering with impressions, and how each is measured now.

```bash
python scripts/accuracy_report.py --since 2026-08-28   # both numbers
python scripts/accuracy_report.py --sample 15 --seed 5 # the hand audit that anchors them
```

`[VERIFIED]` Written 2026-09-05 at the operator's request: *"establishing a reliable metric for
accuracy. A metric for measuring how much the model hallucinates along with another model that
measures how much news retrieval is relevant to actual news as compared to old meta posts or
highlights etc."*

---

## The limit that comes first

Both automatic numbers are **the pipeline judging itself**. Fabrication counts what
`processing/validate.py` caught; relevance counts what `processing/newsworthy.py` dropped. A
rule blind to a class of junk is blind to it twice: once when filtering, once when reporting on
its own filtering.

`[INFERRED]` So the automatic numbers track **movement between versions**, and only a hand
audit says where the level actually is. Both calibrations below were done by reading, and both
found the automatic number optimistic.

---

## Metric 1 — Fabrication

**What it counts.** Every summarisation attempt in `logs/sportwire.log`, and how many were
rejected for naming a person, team or figure the sources never wrote.

`[VERIFIED]` 2026-08-28 to 2026-09-05:

| | |
|---|---|
| attempts | 74 |
| rejected as inventing something | **35 (47.3%)** |
| accepted on the first try | 30 (40.5%) |
| briefs that never passed, so fell back to headlines | 17 |
| hosted provider errored before writing | 48 |

That last row is not fabrication and is reported separately on purpose. `[VERIFIED]` 48 of the
80 "no attempt passed validation" lines are OpenRouter returning HTTP 429 before producing a
word. An earlier version of this instrument counted them as failures and overstated the rate by
more than half.

**What it cannot count.** `[VERIFIED]` 2026-09-04, four delivered briefs read against their
sources: the entity-pair check flagged 9 sentences, **6 were real errors and 2 were on entirely
correct sentences**, while **3 further errors were never flagged at all**. Those three were each
made inside a single clause, where there is no second entity to contradict:

```
"The team's search for a new big man comes after Cam Whitmore was waived by the Cavaliers."
"Dexter Lawrence is promising a strong preseason performance."
"The NFL's decision to keep four quarterbacks..."
```

So the delivered-error estimate carries two constants, both from that audit: flags are right
about **two thirds** of the time, and there are at least **0.75 unflagged errors per brief**.

---

## Metric 2 — Retrieval relevance

**What it counts.** Every article the feeds handed over, against what the news filter removed.

`[VERIFIED]` 2026-08-28 to 2026-09-05:

| | |
|---|---|
| articles the feeds handed over | 4,470 |
| survived the news filter | **3,275 (73.3%)** |
| removed as not news | 1,195 (26.7%) |
| of which stale beyond the age window | 781 (65%) |
| of which rankings, mock drafts and predictions | 258 (22%) |
| of which clips, charts and meme posts | 71 (6%) |

The denominator is the fetch count, not what reached a brief. `[VERIFIED]` An earlier version
divided by dropped plus delivered and read 26.1%, which measured nothing: what reaches a brief
is also cut by deduplication, grouping and the story cap, none of which is a judgement about
relevance.

### The calibration, and it is the number that matters

`[VERIFIED]` 2026-09-05, 15 delivered articles drawn at random (`--sample 15 --seed 5`) and read
one by one. **7 of 15 are genuinely news.**

| Verdict | Headline |
|---|---|
| news | `[Wachtell Report] Clippers CCO Scott Sonnenberg, in internal texts…` |
| news | `John Lynch reveals what 49ers must do to earn blockbuster trade` |
| news | `Pablo Torre says there's no way Kawhi Leonard didn't know…` |
| news | `'I love the eyes on me.' Giants' Cam Skattebo back after brutal injury` |
| news | `NBA Offseason News/Trade/Free Agent Rumors 2026: Curry has extension options…` |
| news | `…Thanasis Antetokounmpo returns to…` |
| news | `McVay: Atwell trade not about possible Nacua ban` |
| **not** | `NFL waiver wire order for 2026: Where all 32 teams **rank**…` |
| **not** | `Knicks Domino Effects: **What if** Jalen Brunson stayed in Dallas?` |
| **not** | `What happened to Ben Simmons? Complete **career timeline**` |
| **not** | `Hey, **remember** Joe Smith? The Clippers certainly do…` |
| **not** | `**Best bets** to make or miss the NFL playoffs` |
| **not** | `**Predicting** last-place finisher for each NFL division in 2026` |
| **not** | `Wemby **highlights** from today's game` |
| **not** | `As a lawyer, I just want to tip my hat to the league and Wachtell…` |

`[INFERRED]` **47% against an automatic 73.3%**, and the gap is not noise. Every one of the eight
misses names a class the filter already has a rule for and words the rule does not list:
`rank` where it lists "ranking", `Predicting` where it lists "prediction", an untagged
`highlights` post where the rule matches only a `[Highlight]` tag. See `TASKS.md` P69.

---

## The protocol

Run the audit when a filter or validator rule changes, and at least every 14 days.

1. `python scripts/accuracy_report.py --sample 15 --seed <a new one>`
2. Read each headline against the batch it came from. Mark news or not news. A piece reporting
   a real event with opinion attached is **news**; a piece whose subject is a list, a
   prediction, a counterfactual or a clip is **not**.
3. Record the fraction, the seed and the date here, so two readings can be compared.
4. Where a miss names a word the rules nearly have, add it to the task rather than the rule
   directly: widening a keyword list has produced invisible false negatives twice in this
   project (`TASKS.md` P3).

| Date | Sample | Seed | News | Automatic figure |
|---|---|---|---|---|
| 2026-09-05 | 15 | 5 | **7 (47%)** | 73.3% |

`[UNKNOWN]` Whether 15 is a large enough sample. It is what one sitting of careful reading
costs, and two readings a fortnight apart will say more than one larger one.
