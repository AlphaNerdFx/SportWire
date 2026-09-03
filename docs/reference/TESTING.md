# Testing

> Moved out of the GitHub wiki on 2026-09-03.

`[VERIFIED]` **560 passing tests and 1 declared expected failure**, run by `make check` — the
same command CI runs, so a green badge and a green terminal mean the same thing. The wiki copy
of this page said 126, which was true when it was written and had not been true for weeks. That
is the drift this move is meant to stop: the count now sits beside the suite it counts.

```bash
make check   # ruff format --check, ruff check, pytest, documentation links
```

This page explains the *method*, because in this project the method turned out to matter more
than the count.

---

## Test count is not health

`[VERIFIED]` The abandoned prototype had **12 test files and zero working features**. Its
`test_ingestion_setup.py` passed in 3.32 seconds — too fast for network or database I/O —
because all it asserted was that imports resolve.

So the rule here is: **every test asserts behaviour with real-shaped data.** Fixtures in
[`tests/fixtures/`](../../tests/fixtures) are
real payloads captured once from live sources. Adapters are tested against those, never
against the network, so the suite cannot fail because ESPN was slow.

---

## Every test is mutation-tested

A test that has never been seen to fail is indistinguishable from a test that asserts nothing.
So each one is checked by **putting the bug back** and confirming the suite notices.

`[VERIFIED]` 2026-08-13, writing the `processing/` suite, this caught **five tests that
asserted nothing** — none of which had been spotted by reading them:

| Test | Why it was hollow |
|---|---|
| sentence-splitting in the validator | Passed with sentence splitting disabled |
| stopword trimming in the validator | Passed with the trim disabled |
| "a common name does not group" | Shared only *one* name, so a different rule held it up |
| fingerprint widening in the clusterer | Nothing covered that line at all |
| paragraph preservation in the summariser | The *mutation* silently failed to apply and reported green |

`[INFERRED]` The pattern is consistent and worth stating plainly: **a test written from the
same reasoning as the code inherits the code's blind spots.** Only trying to break it exposes
that. Two of those five diagnoses turned out to be real defects in the code.

The last row is its own lesson. A mutation that does not apply looks *exactly* like a mutation
the suite survived, so every mutation script now asserts the source actually changed before
running the tests.

---

## What is covered

| Area | State |
|---|---|
| `processing/` | `[VERIFIED]` Every live module has behaviour tests: newsworthy, dedup, priority, cluster, highlights, validate, summarize |
| Brief rendering | `[VERIFIED]` Snapshot tests — approved output becomes the assertion |
| `storage/`, `config/`, RSS parsers, Telegram splitter | `[UNKNOWN]` Not yet covered |
| Live in-season game payloads | `[UNKNOWN]` The season has not started; every captured game reads `Final` |

---

## Snapshot tests, and why they are not weakened

The brief's rendered output is stored in
[`tests/snapshots/`](../../tests/snapshots). Any
change that alters what would be delivered fails the suite and prints the diff.

The value is in what a diff shows that reading output cannot: **what disappeared.**
`[VERIFIED]` A run once delivered two messages instead of three and looked entirely normal.

A snapshot is re-recorded **only after a human has read the diff and agreed it is correct**.
Updating one to make a test pass is the same mistake as deleting the assertion.

---

## Documentation is tested too

`make check` fails when any documentation link points at a file that does not exist.

`[VERIFIED]` This exists because of a real failure. When ADR-012 was reversed on 2026-08-10 the
ADR file was renamed, and three documents kept linking to the old name: `README.md`,
`SECURITY.md`, and the wiki's Decisions page. All three also still *described* the superseded
decision. Nothing noticed for four days, because nothing looked.

`[VERIFIED]` **The wiki was the reason two of those three went unnoticed, and it is gone.**
2026-09-03 its pages moved into this folder, so documentation is now reviewed in the same
commit as the code it describes and one checker covers all of it. The check used to clone a
second repository and CI ran it daily to catch browser edits there; neither is needed now.

---

## Where the bugs actually came from

`[VERIFIED]` Eleven bugs were found by **reading delivered output**, none by a test. Six more
(P5–P10) were found by **writing tests**, none by reading output.

`[INFERRED]` Two different nets, catching two different classes of bug. Neither replaces the
other, and the project needs both.

Full detail in
[`SESSION.md`](../sessions/SESSION.md) §8 and
[`TASKS.md`](../planning/TASKS.md).
