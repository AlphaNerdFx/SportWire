# HANDOVER

Written 2026-09-25. Everything below was checked by a command run in this session. Tags follow
`CLAUDE.md` §0. This file lives in `docs/sessions/`, not the repository root, because
`CLAUDE.md` §9 maps it there; the `handover` skill's "root" predates that move.

---

## STATE

`[VERIFIED]` `git branch --show-current`, `git log -1`, `git status --short`, `git fetch` then
`git log origin/main..HEAD`, `git stash list`, `git worktree list`, `gh run list`:

| | |
|---|---|
| Branch | `main` |
| Last commit | `d5ca41629da7179527729e609b69997d57089256` |
| Subject | `docs: mark the push and issue updates done in HANDOVER` |
| Unpushed | **0**. CI run `36030476508` green |
| Working tree | clean |
| Stashes | 0 |
| Worktrees | `main` only |
| Version | `v0.5.12` is the latest tag |
| Live system | cron runs `main.py --if-due` from this tree; last log line `2026-09-25 02:30:08 not due: 7.0h since the last brief, interval is 8h` |

---

## THE ONE THING TO READ FIRST

`[VERIFIED]` **The only engineering blocker left for v1.0.0 is duplicate stories inside one
brief.** The day's biggest stories still split into several groups because all their names are
too common to anchor a match. A replay of 20 real runs through the old and new grouping code
cut duplicate leads from about 28 to about 16 (`[INFERRED]`, hand count), but Karl-Anthony
Towns (5 leads) and Kawhi Leonard (5 leads) still repeat. `TASKS.md` P70 has the fix and the
measurement to repeat. Everything else before v1.0.0 is an audit, a decision, or the operator.

---

## DONE THIS SESSION (2026-09-23 to 09-25)

Operator decisions, 2026-09-24: v1.0.0 is NBA and NFL from a fresh clone; intervals are 8, 12
or 24 hours; r/nfl (P46) after v1.0.0; `CLAUDE.md` §13 subagent policy and §14 silent output.

**Code**
- P42 intervals: `2b6d954`, `ce0eb57`, tests `7182d51` `aafc08c` `185ec88`, comment `06b247a`.
  Per-outlet cap and repeat window now scale with the interval; 8 hours unchanged.
- P71 repeat suppression remembers only shown stories: `a2c0b1a`, test `9a1d000`, `9d53ea4`,
  `057ae3f`. `[VERIFIED]` Before, 76% of remembered stories had never been shown.
- P72 three validator false alarms fixed (ellipsis, position tag, hyphen): `d776e8d`, `b8a2a98`.
- P70 one name scanner for grouping: `410b9eb`, `81f35cc`, tests `eb54222` `f4a8e40` `cb798c1`.
  Partly fixes P70.
- `acdca67` Windows task names both leagues. Earlier, pushed on 09-23: dead code removed
  (`e90c28b`, `dcbee2c`, `09176d2`, `08d6c98`), `graphify-out/` ignored (`39f2521`).

**Documents**: ROADMAP `85786a2`; PRD `43973ff`; README `ffac91c`; GETTING_STARTED `21c4893`;
SCHEDULING `dd60251`; `.env.example` `a7bc028`; TASKS `4fa6197` `b507f33` `6f35cf0`;
CHANGELOG `bf88002` `ae09944`; CLAUDE.md `655b3bc` `9183386`; INTERNALS `5a0caa1`; METRICS
`6ddec05`; SESSION `61c2995`; HANDOVER `2af7eb9` `d5ca416`.

**GitHub**: `[VERIFIED]` issue #8 body corrected (struck "NBA only", MLB v1.1.0, NHL v1.2.0,
r/nfl after v1.0.0) plus a comment; issue #1 has a gate-status comment.

**Outside the repository**: the SportWire Playbook and SportWire Inside Out artifacts (the
second saves graded drills to its `attempts` collection), and two skills,
`~/.claude/skills/inside-out-course/` and `~/.claude/skills/inside-out-architecture/`.

---

## IN PROGRESS

`[VERIFIED]` Nothing is half-written. The exact next step is P70's second half, in
`processing/cluster.py`:

1. Count a full name and its own surname as one entity, and let a shared full person name plus
   one more shared name join a group regardless of rarity.
2. Stop a group's name set growing by union, so one roundup headline cannot chain two stories.
3. Pass the batch's ordinary words into `drop_repeated_stories` so headline openers ("Did")
   stop counting as new names there too.
4. Re-run both measurements: the replay (20 runs since 09-17, rebuilt from `fetched_articles`
   minus `seen_articles` at each run's start, old code at `08d6c98` vs new) and the hand review
   of new merges. Require Kawhi Leonard and Karl-Anthony Towns in one group each, no loss of
   the fixed cases, and fewer than 9 wrong merges.

---

## JOBS

`[VERIFIED]` No background job is running. None used the skill's `nohup` pattern.

| Command | PID | Log path | Started | Expected runtime | How to check |
|---|---|---|---|---|---|
| ~~fresh clone of `08d6c98`: install, check, dry run from /tmp~~ | n/a | session scratchpad | 09-24 09:32 | 2 min | finished: 579 passed, exit 0 |
| ~~fresh clone of `cb798c1`: same~~ | n/a | session scratchpad | 09-24 18:59 | 3 min | finished: 609 passed, exit 0 |
| ~~5 Sonnet subagents (P42, P70, P72 twice, P71)~~ | n/a | session transcripts | 09-24 | varied | all integrated; worktrees removed |
| ~~grouping replay, old vs new code, 20 runs~~ | n/a | session scratchpad | 09-25 | 2 min | finished: about 28 to about 16 duplicate leads |

---

## OPEN DECISIONS

What remains before v1.0.0, in the suggested order:

1. **Zero duplicates** (issue #1): P70 second half above, then a fresh stretch of briefs audited
   by hand. Engineering, then calendar days.
2. **The validator condition** ("no known false-accusation bug"). `[VERIFIED]` P72 left five
   open classes. (a) Fix the city-for-team class and accept the rest as documented limits, or
   (b) reword the condition to recurring bugs only. Recommendation: (a).
3. **Thin briefs.** `[VERIFIED]` On 09-24 at 19:30 the per-outlet cap discarded 32 NFL stories
   because one outlet had most of the new news, and capped stories are recorded as seen (P58).
   (a) Relax the cap when other outlets have nothing new, (b) hold capped stories over to the
   next brief, (c) leave it. Recommendation: decide before the duplicate audit, since it changes
   what the audit sees.
4. **No-crash clause**: `[UNKNOWN]` never audited. One scripted pass over the log.
5. **Issue #2 (H13)**: the operator's explanation check, last 2 of 8 on 08-05. The operator's.
6. **PRD criterion 4**: whether the brief is actually read. Only the operator can answer.
7. **At release**: publish the measured pass rate in the notes, repeat the fresh-clone check
   (P73), bump `pyproject.toml`, move CHANGELOG's Unreleased entries, tag.

Outside anyone's control: issue #5 waits for the NBA season in October.

---

## CHECK STATUS

`[VERIFIED]` Run bare, immediately before writing this file:

```
make check    exit=0
609 passed, 1 xfailed
All documentation links resolve.
```

The `xfail` is deliberate: `tests/test_validate.py::test_false_relationship_between_grounded_names_is_caught`
documents that the validator checks names, not claims (P5).

---

## STASHES

`[VERIFIED]` None. `git stash list` is empty.
