# OPERATING_RULES.md — How the Agent Works on This Project

**Scope:** agent *workflow discipline* only.

This file deliberately does **not** restate:
- **Tone and advisor stance** → `SYSTEM_INSTRUCTIONS.md`. Follow it in every reply.
- **Project constraints C1–C6, architecture, commands, dependencies** → `CLAUDE.md`.
- **Task order and proof requirements** → `TASKS.md`.

One fact, one home. `CLAUDE.md` §5 rule 1 says "one concern, one module"; that applies to
governance documents too. If a rule here ever contradicts `CLAUDE.md`, `CLAUDE.md` wins and
this file is wrong — say so instead of silently picking one.

Every rule below exists because of a **specific, verified failure in this repository**, cited
inline. None of it is generic advice.

---

## 0. Who writes what

**The agent writes the code, the tests and the documentation. The operator does not.**

`[VERIFIED]` 2026-08-05 this replaced ADR-006, which had specified the inverse — the human
writing signatures, docstrings and test assertions, the agent writing only the bodies. The
operator reversed it explicitly: *"You'll write the code not me."* ADR-011 §7 records the
reversal and its consequences.

What follows from that, and what does **not**:

- **The agent never instructs the operator to write code.** Not as a task, not as a remedy,
  not as an exercise. If the agent believes something would be better understood by writing
  it, it may say so **once**, as an option, and then drop it.
- **The agent explains as it goes.** A concept the operator has not shown familiarity with is
  taught at the point it first appears, before the code that uses it — briefly, grounded in
  this codebase rather than in the abstract.
- **The operator reviews and questions.** He decides what is correct, especially for anything
  user-facing: message content, formatting, what counts as notable, what gets cut.
- **Understanding is still required, and is still ranked above shipping** (`CLAUDE.md` §1). It
  is demonstrated by *explaining*, not by authoring. See §10.

`[INFERRED]` The failure mode this guards against is the agent quietly reintroducing the old
contract because the learning goal makes it tempting. It has already happened once: after the
reversal, the agent proposed that the operator rewrite `processing/dedup.py` as a remedy for a
failed knowledge check. That was the superseded contract returning under another name.

---

## 1. Two tagging systems. Do not mix them.

| Where | Tags | Meaning |
|---|---|---|
| **Written into any file** (docs, commits, comments, docstrings) | `[VERIFIED]` / `[INFERRED]` / `[UNKNOWN]` | `CLAUDE.md` §0 evidence rule. Permanent record. |
| **Spoken in conversation** | `[Certain]` / `[Likely]` / `[Guessing]` | `SYSTEM_INSTRUCTIONS.md` rule 2. Live confidence. |

`[UNKNOWN]` and `[Guessing]` are acceptable, expected answers. Filling a gap with plausible
prose is the single failure that cost this project weeks.

## 2. Evidence expires. Re-verify, do not inherit.

`[VERIFIED]` **2026-08-04:** `CLAUDE.md` carried a `[VERIFIED]` claim that `cdn.nba.com`
"works from anywhere." Tested live this session: **HTTP 403** from Akamai, from the agent
sandbox *and* from the operator's own residential machine. The tag had been carried forward
from a prior session's research and restated as fact without retest. It was wrong, and the
whole NBA data source (ADR-003) had to be replaced.

Therefore:

- A `[VERIFIED]` tag written in a **previous session** is `[Likely]`, not `[Certain]`.
- Before building on any external service, **hit it in this session** and paste the status code.
- When a re-test contradicts a recorded claim, **correct the document in place with a dated
  strikethrough** — never silently delete the old claim. The correction history is evidence.

## 3. Read the file before you change it.

Do not infer what code does from its name, and do not infer what a document says from its
title. `[VERIFIED]` `HANDOFF.md` described a folder tree, a failure history, and completed
milestones that did not exist on disk. `[VERIFIED]` 17 files in the legacy repo are
**zero bytes**, including `run_pipeline.py` — the file its own architecture called the
entrypoint. A plausible filename is not evidence of content.

If you have not read it in **this session**, read it before editing it.

## 4. Never weaken a test to make it pass.

The agent writes both the code and the tests (see §0). That removes the independent check a
separate test author would provide, which makes this rule stricter rather than looser: the
cheapest path to "passing" is quietly lowering the bar, and nobody else is watching for it.

Snapshot tests exist for exactly this reason. The operator approves real output once; any
later change that alters it fails and shows the diff. **A snapshot is re-approved only after
the operator has seen the diff and agreed it is correct.**

- Do not edit a test to make it pass **unless you have confirmed the test itself encodes a
  wrong assumption** — and say so explicitly before touching it.
- A failure means either the code is wrong or the test's assumption changed. **Determine
  which before editing either one.**
- `[VERIFIED]` The legacy repo had 12 test files and zero working features.
  `test_ingestion_setup.py` passed in 3.32s — too fast for network or DB I/O — so it asserted
  imports resolve and nothing more. **Test count is not health.** Assert on behaviour with
  real-shaped data.

## 5. Duplicate-check before creating anything.

`[VERIFIED]` The legacy repo implemented nine concerns two or three times over — four
`NewsArticle` definitions (one of them inside `tests/conftest.py` itself), two orchestrators,
two normalizers, two DB layers, two entrypoints. Python raises no error when four modules
define the same class, so the drift was **silent and cumulative**.

Before creating any file or class:
```bash
grep -rn "class <Name>\|def <name>" --include="*.py" .
```
State the result before writing. Agents fail by accretion, not by exception.

## 6. One concern per change.

If you notice a second problem while fixing the first, **name it and ask**. Do not fix three
things and present them as one diff.

Since 2026-08-17 the commit rule is stricter than "one logical change": it is **one commit per
file**, with the whole message capped at 256 characters. See `CLAUDE.md` §9, which owns it.

## 7. Scope tripwires — stop and split.

Stop and propose splitting the work when a task would:
- touch **more than four files**, or
- create **more than one new module**, or
- add a dependency (see §8).

`CLAUDE.md` §6 requires one function or one file per turn. These are the concrete thresholds
for that rule.

## 8. Dependencies are guilty until proven necessary.

`[VERIFIED]` **2026-08-04:** the legacy `.venv` was **5.6 GB, 151 packages** — `torch`,
`sentence-transformers`, `alembic`, `asyncpg`, `pgvector`, `SQLAlchemy` — i.e. the entire
*deferred* column of `CLAUDE.md` §11, installed before anything in the *required* column had
ever been proven to run.

- Install only what the current slice needs, when it needs it.
- Every deferred package in `CLAUDE.md` §11 has a written trigger condition. **Cite the
  trigger** before installing it, or do not install it.
- Never add a dependency without stating what it does and what it replaces.
- A clean environment is an enforcement mechanism: an unauthorized import should fail loudly
  at import time, not succeed silently.

## 9. Plan, then report what actually happened.

- At the start of a multi-step task, state the plan as a numbered list **before** executing.
- After each step, report **the actual outcome, not the intended one.**
- After any code change: run the relevant tests, **paste the real output**, diagnose any
  failure before fixing it, then state what changed and what it means downstream.
- Flag anything noticed but not addressed.

**"Should work" is not a status.** Do not present work as complete before its test passes.

## 10. What "done" means here.

A task is done when **all three** hold:

1. A test asserting its **behaviour** passes, and the real output is pasted into `TASKS.md`.
2. The **operator can explain what it does and why**, unaided. `CLAUDE.md` §1 ranks this above
   shipping.
3. No `[UNKNOWN]` remains in the claim being made about it.

**When (2) fails, the remedy is explanation, not rewriting.** ADR-006's original remedy —
delete the code and regenerate it — assumed the operator had written the interfaces, so a
failure to explain implied the implementation was too clever. That assumption no longer holds
(§0): deleting agent-written code produces more agent-written code he also has not read.

So instead:

- The agent walks through the specific thing that was not understood, in this codebase's
  terms, using a concrete example rather than an abstraction.
- If the explanation does not land, that is a signal the **code** is too clever, not that the
  operator is at fault. Simplify the code and explain again.
- Re-check later, on the same point. Understanding that survives a gap is understanding;
  understanding measured immediately after an explanation is recall.

**The agent does not set the operator homework.** No "try rewriting this", no exercises, no
tasks conditional on his authoring code.

## 11. Context discipline (constraint C6).

Pro-tier usage and context are finite. Read the specific files a task needs and let the rest
go. Say so when context grows large and suggest splitting the work. Routine implementation
gets a one-line rationale; **only architectural decision points get the three-layer
explanation**, written to `docs/decisions/ADR-NNN-<slug>.md` (ADR-007) — surface, thorough,
deep. Not in chat, where it scrolls away unread.

## 12. Ask, do not assume, on anything outward-facing or irreversible.

Stop and ask before: creating a file, adding a dependency, deleting or overwriting anything,
pushing to a remote, or sending a message to a real person's device. Approval for one such
action does not extend to the next one.

When a decision has more than one defensible answer, **present the options with the tradeoff
and a recommendation** — do not pick silently.
