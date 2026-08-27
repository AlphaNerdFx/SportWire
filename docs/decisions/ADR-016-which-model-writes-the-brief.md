# ADR-016 — Which model writes the brief, and what happens when it will not

**Date:** 2026-08-27
**Status:** accepted, built and running

## Surface

The brief is written by the smallest model that can do the job, and if that model will not
produce something trustworthy, a bigger one is asked instead. The reader never sees the
difference except that briefs arrive faster and the computer stays usable while they do.

## Thorough

### What changed

`[VERIFIED]` Until 2026-08-27 one model wrote every brief, `mistral:7b`, chosen in ADR-012 for
resisting fabrication. There are now up to three rungs, tried in order and stopping at the
first whose output survives validation:

```
OpenRouter (hosted, only if a key is set)   1 attempt
llama3.2:3b  (2.0 GB, local)                2 attempts
mistral:7b   (4.4 GB, local)                the remainder
```

### Why

`[VERIFIED]` The operator reported that a run *"spent like 8 minutes processing to just get
proses"* and that the *"whole PC goes down to halt"*. The measurements behind that:

```
WSL2 memory      7.4 GB total, 5.3 GB free, 656 MB of swap already in use
mistral:7b       4.4 GB          llama3.2:3b   2.0 GB
```

`[INFERRED]` A 4.4 GB model against 5.3 GB of free memory is the whole explanation. Nothing
about the code was slow; the machine was swapping. And most briefs do not need a 7B model: the
task is compressing a few kilobytes of headlines, not reasoning.

### The alternatives, and why not them

- **Switch to the small model outright.** Simplest, and it gambles quality on every brief.
  `[VERIFIED]` Rejected on evidence the same day: given a football batch, `llama3.2:3b`
  produced Bill Belichick, Tom Brady and the Tampa Bay Buccaneers, none of which appears in
  the batch and all of which are several seasons stale.
- **Keep the big model and accept the stall.** What the operator complained about.
- **Run both and compare.** Twice the memory, on a machine that does not have it.

### What makes the ladder safe rather than a gamble

`[INFERRED]` This is the part worth understanding, and it is the reason the decision is
defensible at all. The ladder does not trust the small model; it trusts the **validator**.
Output from `llama3.2:3b` is accepted only if it survives exactly the check `mistral:7b`
output would face, so the worst case is the behaviour the project already had, plus the time
spent on a rung that failed.

`[INFERRED]` A ladder without an honest acceptance test would simply be a quality cut with
extra steps.

### Each rung prepares its own notes

`[INFERRED]` Deliberate, and it costs model calls. A fabrication can enter when the notes are
extracted just as easily as when the paragraph is written, so handing the big model the small
model's notes would upgrade the writing while preserving the mistake.

### The hosted rung fails differently, and that shaped it

`[VERIFIED]` 2026-08-27, minutes after the operator added an OpenRouter key, every call
returned `429 ... upstream_provider_shared_pool`: the free model's shared pool at the provider
was throttled. Nothing was wrong with the key.

`[VERIFIED]` The original wiring chose hosted **instead of** local, so both briefs fell back to
headline lists while a working local model sat idle. `[INFERRED]` That is backwards. Falling
back to a worse model is better than falling back to no prose, and the hosted rung gets one
attempt rather than several because a rate limit is not cured by asking again a second later.

## Deep

### The pattern

This is **graceful degradation**, and specifically a fallback chain: a sequence of providers
of decreasing preference behind one interface, where failure at one rung is a normal event
rather than an error. The same shape appears in DNS resolvers, CDN origin fallback, and in
this repository already: `CLAUDE.md` §5.6 says every external call returns an empty list on
failure so a dead source degrades the brief without crashing the run.

`[INFERRED]` What makes a fallback chain work, and what makes it dangerous, is the same thing:
the **acceptance test** at each rung. A chain whose test is "did it return anything" degrades
silently into whatever the worst rung produces. A chain whose test is "is this trustworthy"
degrades in quality only as far as the test allows. Here the test is `validate_summary`, and
it is why the rungs can be ordered by cost rather than by trust.

### Composition rather than a flag

`EscalatingSummarizer` wraps two `Summarizer`s and is itself a `Summarizer`, so the three-rung
chain is two two-rung chains nested. `[INFERRED]` That is the **decorator** shape, and the
practical benefit is that "which model" and "what to do when a model fails" stay separate
decisions: the hosted rung knows nothing about Ollama, and the ladder knows nothing about
HTTP status codes. Adding a fourth rung is a constructor argument, not a new branch.

### Why memory is a design input at all

`[INFERRED]` On a laptop, an inference model is not like a library: it is a large resident
allocation whose size is a first-class constraint, and it competes with the desktop the
operator is using. That makes "how big is the model" an architectural question rather than a
tuning detail, in the same way that choosing SQLite over Postgres was (`CLAUDE.md` §5.5). The
ladder exists because 2.0 GB fits comfortably in 5.3 GB and 4.4 GB does not.

## Consequences

`[VERIFIED]` Measured on 2026-08-27:

- A full two-league run with prose went from 183 to 490 seconds to **51 seconds**, with the
  big model never loaded.
- Free memory during a run stayed above **5.2 GB**, against swapping before.
- With the hosted rung throttled, both briefs still delivered prose on the first local attempt.

`[UNKNOWN]` How often the small model's output is rejected and the ladder escalates. One
football batch escalated and one did not, which is not a rate. `scripts/soak_report.py` counts
the outcome per league and the answer needs runs from a settled version.

`[UNKNOWN]` Whether the hosted rung is better than either local model. It has not produced a
single accepted summary yet, so nothing is known about its writing or its fabrication rate.
