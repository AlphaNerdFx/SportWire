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

## Reversal condition

Re-enable by default when a locally-runnable model passes the name-invention check across
**at least five separate runs on live data**, not one. Reversal on the hosted option requires
C2 being relaxed, which is the operator's call and would need its own ADR.
