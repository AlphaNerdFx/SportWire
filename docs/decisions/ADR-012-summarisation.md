# ADR-012 — LLM summarisation ships disabled

**Date:** 2026-08-06
**Status:** accepted

## Surface
The brief was going to replace its list of headlines with a written paragraph produced by an
AI model running on the operator's own machine. Every model tested made things up — inventing
players, contract figures and people who were not in the news — so the feature ships switched
off and the headline list stays.

## Thorough

**What was built.** A `Summarizer` interface with an Ollama implementation (the third use of
the same boundary as `SourceAdapter` and `DeliveryChannel`), map-reduce chunking, and
`processing/priority.py` to order articles before they reach the model. All of it works and
all of it is kept.

**What was measured.** Four models, same fixture, same prompts, scored on stories missed and
names invented:

| Model | Size | Missed | Invented | Time |
|---|---|---|---|---|
| `llama3.2:3b` | 2.0 GB | 1–5 of 11 | 0–2 | 10–42s |
| `qwen2.5:3b` | 1.9 GB | 11 of 11 | 0 | 8s |
| `gemma3:4b` | 3.3 GB | 11 of 11 | 5 | 234s |
| `mistral:7b` | 4.4 GB | 0 | 0 | 337s |

`[VERIFIED]` `qwen2.5:3b` produced 187 characters asserting *"There were no significant roster
or on-court developments reported today"* — on a day a superstar changed teams.

`[VERIFIED]` `gemma3:4b` ignored the supplied articles completely and wrote fluent, entirely
fabricated NBA news: a Gabe Vincent signing, an Anthony Davis injury return, a Celtics–Pacers
trade, a LeBron watch endorsement. None of it appears in the feed. **This is the exact failure
mode of the fabricated handoff document that caused this repository to be rebuilt** — plausible
prose with nothing behind it.

**Why the winner was still rejected.** `mistral:7b` scored 0 missed / 0 invented and was
adopted. Run once more against **17 live articles** instead of the 15-article fixture, it:

| Wrote | Source says |
|---|---|
| "Devin Booker secured a three-year, $73M extension with the Suns" | "Suns keeping **Brooks** on 3-year, $73M extension" |
| "Malik Monk agreed to a one-year, **$3.3M** deal with the Nuggets" | "**Walker** returning to NBA with 1-year Nuggets deal" — no figure given |
| "**Steve Nash's right-hand man, Leon Rose**, is departing…" | "Knicks executive **Rosas** leaving team" |
| "**9** different champions in the last **8** years" | "**eight** different champions in **eight** years" |

Three fabricated people and an invented dollar figure. `[INFERRED]` The clean run was a
property of that input, not of the model.

**Amendment, 2026-08-07 — the substitutions are systematic, not random.** The operator
observed that "Booker" is a real Suns player and asked whether the model might be correcting
against real-world news. It cannot: `mistral:7b` runs locally with no network access and
static weights frozen at its training cutoff, and the Brooks signing postdates that cutoff.

But the observation identified the real pattern. Every substitution replaced a **less famous
name with a more famous one from the same organisation**:

| Source | Model wrote | Who that is |
|---|---|---|
| Brooks (Suns) | **Devin Booker** | The Suns' franchise star |
| Gersson Rosas (Knicks executive) | **Leon Rose** | The Knicks' actual president |
| — | **Steve Nash** | Real, famous, NBA-adjacent |

`[INFERRED]` During generation the model weighs `P(token | context)`. Its training strongly
associates "Suns" with Booker; the prompt said Brooks; **the prior beat the context.**

This inverts the property a news brief needs. The more obscure the subject — and therefore
the more genuinely newsworthy — the more likely a famous name overwrites it. Routine stories
about stars survive; the stories you could not have guessed are exactly the ones corrupted.

`[INFERRED]` It also explains why prompt engineering failed to help: the instruction competes
against the weights rather than configuring them.

**Decision: summarisation is gated behind `main.py --summary` and off by default.** The
default path makes no model call. The headline list is never wrong; a paragraph that renames
Dillon Brooks to Devin Booker is worse than no paragraph.

**Alternatives rejected:**
- **A hosted frontier model.** Would almost certainly fix accuracy. Rejected on **C2**
  (recurring cost) and **L13** (an API key is another setup step). Note for the record that
  open-sourcing alone does *not* preclude this — an optional user-supplied key keeps the code
  open. The objection is cost, not licensing.
- **A one-line LLM opener over the headline list.** Rejected by the operator as superfluous —
  it adds a sentence of atmosphere over facts that are already listed underneath.
- **Fine-tuning.** Would need hand-written training data, a GPU, and produces a model *larger*
  on disk than the one it replaces. It also does not address fabrication at this parameter
  count.

## Deep

**The generalisable lesson is about what counts as evidence.** The 3B evaluation concluded, in
writing, that *"failures differ between runs of the same model, so single-run testing cannot
establish confidence at this size."* Two commits later, `mistral:7b` was declared clean and
wired into the pipeline **on the strength of a single run** — the precise error that had just
been documented. It was caught only because a dry-run was inspected line by line before
sending.

Writing a lesson down does not install it. The defence that actually worked was mechanical:
a scripted check comparing capitalised names in the output against names present in the
source. `[INFERRED]` That is the same principle as the clean virtual environment and the
`_fetch`/`fetch` split — **a rule enforced by a mechanism beats a rule enforced by memory**,
including the memory of whoever wrote the rule.

Second lesson: **fluency is uncorrelated with truth, and a summariser inherits none of its
source's authority.** The headline list is trustworthy because it is a transformation with no
degrees of freedom — the words shown are the words published. The moment a model rewrites
them, every fact needs independent verification, and at this model size verification fails
often enough to make the feature negative-value.

## Follow-up, 2026-08-08 — measured pass rate: **0 of 3**

A validator was built (`processing/validate.py`) that checks every proper name and figure in
a generated summary against the source articles, so fabrication fails closed to the headline
list rather than reaching a phone. `[VERIFIED]` It correctly rejects every failure recorded
above, and correctly passes grounded summaries including ones carrying real figures.

The remaining question was whether fabrication is *occasional* — in which case retrying a
rejected summary would land a good one — or *constant*. Measured over three attempts on the
same 12 live articles with `mistral:7b`:

| Attempt | Result | Time | Detail |
|---|---|---|---|
| 1 | **no output** | 647s | exceeded the 600s timeout |
| 2 | **rejected** | 236s | invented "Dallas Mavericks" |
| 3 | **rejected** | 14s | invented "Al Horford's departure from the Celtics and his arrival in Philadelphia" — a whole transaction |

`[INFERRED]` Retry is therefore not a fix: at a 0/3 pass rate it costs twenty minutes to
arrive at the same headline list. Attempt 3 is the clearest evidence — it did not slip a name,
it invented a trade. Runtime also varied by a factor of 46 for identical work.

`[VERIFIED]` Coverage was measured at the same time, and the constraint is upstream:

| Source | Items | Title avg | Descriptions | Desc avg |
|---|---|---|---|---|
| ESPN | 15 | 57 | 15/15 | 140 chars |
| CBS Sports | 36 | 98 | 36/36 | 94 chars |
| r/nba | 25 | 154 | 13/25 | **653** chars |

Editorial outlets syndicate roughly one sentence. Reddit carries five times more. Richer input
would require fetching article pages, which is the C3 exposure ADR-009 exists to avoid — so
this is as much text as the summariser will ever get from published feeds.

**The feature stays built, gated, and off.** The validator makes it safe; the pass rate makes
it useless. Both facts are worth keeping, because the validator is the reusable part.

## Reversed, 2026-08-10 — summarisation is now on by default

**The reversal condition below was met, and by a route neither obvious nor anticipated: the
input changed, not the model.**

Re-measured on the same `mistral:7b`, five attempts over twelve stories:

| Attempt | Result | Time |
|---|---|---|
| 1 | no output | 668s (cold load exceeded the timeout) |
| 2 | **pass** | 490s |
| 3 | **pass** | 16s |
| 4 | rejected — invented "Jimmy Butler" | 16s |
| 5 | **pass** | 19s |

**3 of 5, against 0 of 3 previously.** Nothing about the model changed. What changed was
what it was given: retrospectives and highlight clips are now filtered
(`processing/newsworthy.py`), stale items are dropped by an age guard, stories covered by
several outlets are merged (`processing/cluster.py`), and no source may lead more than four.
The model receives twelve coherent current stories instead of a mix including 2017 highlight
clips and week-old articles. `[INFERRED]` **Less noise in, less invention out** — which was
not something the earlier evaluation predicted or looked for.

**Retry is now worth doing, and only because the check is mechanical.** At a 0/3 rate it
merely burned time. Retrying *without* validation would only produce a different fabrication.

> **Amended 2026-08-13.** This paragraph originally read "at 3/5 a second attempt reaches
> roughly 84% and a third roughly 94%." `[VERIFIED]` That compounding does not hold. The
> 00:00 run on 2026-08-13 failed all three attempts and invented **the same name** on each
> one. The arithmetic assumes independent failures; a model completing a training prior fails
> identically every time. `[UNKNOWN]` The real rate — count it over the soak (`TASKS.md` P4)
> rather than projecting it from one sitting. The 84% figure should not be requoted.

`[VERIFIED]` The safety property is unchanged and is what makes this defensible: the
summarizer validates its own output and returns `None` when nothing passes, so the worst case
is the headline list. A fabrication still cannot reach a phone.

`[VERIFIED]` First production run with it enabled passed on attempt one — 1,060 characters,
every name traceable to a source article.

`[VERIFIED]` Runtime is bimodal rather than variable: 16–19s warm, 490–668s cold, because
Ollama unloads the model when idle. The first call of each cron run pays that load; retries
are cheap.

**Still true, and worth keeping in view:** one attempt in five invents something. The
validator catches it, but the underlying model is no more reliable than it was — the system
around it is.

## Reversal condition

Re-enable by default when a locally-runnable model passes the name-invention check across
**at least five separate runs on live data**, not one. Reversal on the hosted option requires
C2 being relaxed, which is the operator's call and would need its own ADR.
