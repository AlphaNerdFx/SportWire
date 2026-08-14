---
name: commit
description: Verify then commit safely — bare make check, mutation-verify new tests, stage narrowly
---

Every step below exists because it was skipped once in this repository and cost something.

1. **Survey before touching anything.** Run `git status` and `git diff --stat`.
   **Never discard uncommitted work.** If something must be undone, use
   `git stash push -m "<reason>"` and tell the user the stash name — `git checkout --`,
   `git restore` and `git reset --hard` are blocked by a PreToolUse hook precisely because a
   `git checkout --` once wiped an uncommitted fix mid-session.

2. **Run `make check` BARE**, or as
   `make check > /tmp/out.log 2>&1; echo "exit=$?"; tail -60 /tmp/out.log`.
   **Never pipe it into `tail`/`head`/`grep`** — the pipeline returns the *last* command's
   status, so a failing check reports success. `[VERIFIED]` That masking put two commits onto
   a red tree in a single session. Print the exit code. **If it is non-zero, STOP and report.**

3. **Mutation-verify every test added in this change.** For each new test: introduce a
   plausible bug in the function it targets (invert a condition, off-by-one, return a constant),
   re-run *only that test*, and confirm it **FAILS**. Then restore.
   - Assert the mutation actually applied (`assert s != before`) before running pytest. A
     mutation that silently fails to apply reports green, which is indistinguishable from the
     suite surviving it.
   - Commit first, or stash the mutation — never restore it with a destructive git verb.
   - **List any test that still passed under mutation and rewrite it.** `[VERIFIED]` Five tests
     written in one session asserted nothing, and review caught none of them.

4. **Stage narrowly.** Name the files this change touches. Avoid `git add -A`, which has
   swept up unrelated edits here before (a stray newline in `CLAUDE.md`).

5. **Write the message for the *why*.** Conventional prefix (`feat:`, `fix:`, `test:`,
   `docs:`, `refactor:`, `chore:`), imperative summary, one logical change per commit. Tag
   factual claims `[VERIFIED]` / `[INFERRED]` / `[UNKNOWN]` per `CLAUDE.md` §0, and state the
   evidence — a command that was run, a measurement that was taken.

6. **Report the real outcome**, including anything noticed but not fixed. "Should work" is not
   a status.
