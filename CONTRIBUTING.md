# Contributing to SportWire

Contributions are welcome. This project has unusual documentation conventions, and they are
not decorative — a previous version of it was built against a fabricated handoff document and
had to be discarded. Please read this before opening a pull request.

## The evidence rule

**Every factual claim in a document, commit message, comment or docstring carries a tag.**

| Tag | Meaning |
|---|---|
| `[VERIFIED]` | You ran a command in this session and saw the output. Include the command. |
| `[INFERRED]` | Strong reasoning from evidence you can point at. State the evidence. |
| `[UNKNOWN]` | You do not know. **This is an acceptable and expected answer.** |

If you cannot support a claim, write `[UNKNOWN] — resolve by running: <command>`. Do not fill
the gap with plausible prose. That specific failure cost this project weeks.

**Tags expire.** A `[VERIFIED]` claim from six months ago is `[INFERRED]` today — external
services change. `cdn.nba.com` was documented as working "from anywhere" and turned out to
return HTTP 403 from every network we tried. If you build on a recorded claim about an
external service, re-test it and say so.

## Before you write code

```bash
make install     # creates .venv, installs everything
make check       # what CI runs: ruff + pytest
```

`make check` passing locally means CI will pass — the workflow runs that exact target rather
than duplicating the commands.

## Rules that are enforced, not suggested

**One concern, one module.** Before creating a file or class, check it does not already
exist:

```bash
grep -rn "class <Name>\|def <name>" --include="*.py" .
```

The prototype this replaced had four `NewsArticle` definitions, two orchestrators and two
entrypoints. Python raises no error when several modules define the same class, so the drift
was silent and cumulative.

**Adapters convert; the pipeline never learns source shapes.** A new source is one class
implementing `NewsSourceAdapter` or `GameSourceAdapter`. If adding one requires changing
anything outside `main.py`'s source list, the boundary is wrong — say so in the PR rather than
working around it.

**Every external call degrades, never crashes.** Implement `_fetch()`; never override
`fetch()`. The base class owns the try/except so it cannot be forgotten.

**Tests assert behaviour on real-shaped data.** Fixtures in `tests/fixtures/` are real
payloads captured once from live sources. Adapters are tested against those, never the live
network. A test that only asserts imports resolve proves nothing — the prototype had twelve
test files and zero working features.

**Never weaken a test to make it pass.** If a test fails, either the code is wrong or the test
encoded an assumption that changed. Work out which before editing either. If you change a
snapshot, include the diff in your PR description and explain why the new output is correct.

## Adding a news source

This is the easiest useful contribution:

1. Add an entry to `FEEDS` in `ingestion/rss_news.py`
2. Capture a real payload into `tests/fixtures/`
3. Confirm it parses and that ids do not collide with existing sources

`[VERIFIED]` CBS Sports needed exactly that and no new parsing code — RSS is a specification,
and both feeds use identical element names.

**Check the source publishes a feed before writing a scraper.** A published RSS feed is an
invitation to consume it. Scraping the same site's HTML is a licensing and terms-of-service
exposure, and this repository will not accept it.

## Commits

```
<type>: <imperative summary>
```

`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`. One logical change per commit.

Commit bodies here are longer than usual on purpose — they record *why*, and what evidence
supported it. Look at `git log` for the house style.

## Architectural changes

Anything that changes a boundary, adds a dependency, or reverses a recorded decision needs an
ADR in `docs/decisions/`. Use `TEMPLATE.md`: surface, thorough, deep, and a **reversal
condition** — what evidence would justify undoing this.

If your change contradicts an existing ADR, say so explicitly and argue why the original
reasoning no longer holds. Do not silently reverse a deliberate choice.

## Dependencies

The virtualenv contains five packages and that is deliberate. `CLAUDE.md` §11 lists deferred
packages each with a trigger condition; cite the trigger, or do not add the dependency.

`[VERIFIED]` The prototype's environment was 5.6 GB and 151 packages — including PyTorch —
before anything in the required column had been proven to run.

## What gets rejected

- Code that violates a source's terms of service, or requires bypassing bot protection
- A dependency without a stated trigger and what it replaces
- Documentation asserting a feature works before it has run
- A second module for something that already exists
- Snapshot updates without a reviewed diff
