---
name: handover
description: Write HANDOVER.md so the next session resumes losslessly
---

Write or overwrite `HANDOVER.md` at the repository root with the sections below.

**Record only what you have verified this session.** Tag every factual claim `[VERIFIED]`,
`[INFERRED]` or `[UNKNOWN]` per `CLAUDE.md` §0. `[UNKNOWN]` is an acceptable answer; inventing
plausible detail is the failure that cost this project weeks, and a handover document is
exactly where it happened last time. Do not carry a claim forward from an earlier session
without re-checking it — a `[VERIFIED]` tag from a previous session is `[Likely]`, not
`[Certain]`.

## Required sections

**STATE** — branch, last commit SHA and subject, whether it is pushed, and a `git status`
summary. Run the commands; do not recall them.

**DONE THIS SESSION** — bullets, each with its commit SHA. What changed and why.

**IN PROGRESS** — what is half-finished and **the exact next step**, specific enough to act on
without rereading the transcript. If nothing is in progress, say so plainly.

**JOBS** — every backgrounded command, one row each:

| Command | PID | Log path | Started | Expected runtime | How to check |
|---|---|---|---|---|---|

Background work is launched as
`nohup <cmd> > logs/<name>-$(date +%s).log 2>&1 & echo $!`, and its row is appended here
**immediately**, not at the end of the session. If a job has finished, record its outcome and
strike the row rather than deleting it.

**OPEN DECISIONS** — anything waiting on the operator. State the options and the recommendation;
do not pre-empt the choice.

**CHECK STATUS** — the real result of `make check`, run bare or with the exit code echoed, plus
any known-broken or `xfail` tests and why. Never write "passing" without having just run it.

**STASHES** — any `git stash` entries created, with their names and what is in them, so nothing
recoverable is left unlabelled.

## Finally

Verify every link you write resolves (`make check` covers this). Then tell the operator the
file is written and name the single most important thing in it.
