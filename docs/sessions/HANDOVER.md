# HANDOVER

Written 2026-09-24. Everything below was checked by a command run in this session. Tags follow
`CLAUDE.md` §0. This file lives in `docs/sessions/`, not the repository root, because
`CLAUDE.md` §9 maps it there; the `handover` skill's "root" predates that move.

---

## STATE

`[VERIFIED]` `git branch --show-current`, `git log -1`, `git status --short`,
`git log origin/main..HEAD`, `git stash list`, `git worktree list`:

| | |
|---|---|
| Branch | `main` |
| Last commit | `61c2995eeddf45dc47fcc822532d9b1163f7ed14` |
| Subject | `docs: bring SESSION.md to 2026-09-24: scope, intervals, cron, P70 decision, next prompt` |
| Unpushed | ~~33 commits~~ **0**: pushed 2026-09-25 on the operator's instruction, CI run `36030219430` green. Issues #1 and #8 updated the same day |
| Working tree | clean |
| Stashes | 0 |
| Worktrees | main only. The four subagent worktrees were removed after checking each was clean and every commit subject was on `main` |
| Version | `v0.5.12` is the latest tag |

`[INFERRED]` cron runs `main.py --if-due` from this working tree, so everything on `main` is
already live on the operator's machine even though it is not pushed.

---

## THE ONE THING TO READ FIRST

`[VERIFIED]` **The v1.0.0 zero-duplicates clause is still unmet, and the grouping change that
went in today is a partial fix with a known cost.** On a reconstruction of the 09-23 NBA run,
the Kawhi Leonard extension still splits into 8 groups, because every one of its names is too
common to anchor a match. The same change merged 37 new groups across the recorded batches:
23 correct, 5 borderline, **9 wrong**. It is on `main` and live. OPEN DECISIONS 1.

---

## DONE THIS SESSION

Decisions by the operator, 2026-09-24: v1.0.0 is NBA and NFL; intervals are 8, 12 or 24 hours;
the NFL Reddit feed (P46) waits until after v1.0.0; a fresh clone must run; `CLAUDE.md` §13
(subagent delegation) and §14 (work silently, full reasoning at the end).

**Code** (all `[VERIFIED]` by `make check` after each integration):
- P42, intervals: `2b6d954` choices become 8/12/24 with a scaled per-outlet cap and repeat
  window; `ce0eb57` wires them into `assemble_brief`; tests `7182d51`, `aafc08c`, `185ec88`;
  comment `06b247a`. At 8 hours nothing changes; at 24 hours an NFL brief can carry 21 stories.
- P71, repeat suppression only remembers stories actually shown: `a2c0b1a`, test `9a1d000`,
  comments `9d53ea4`, `057ae3f`. Before, 76% of remembered stories had never been shown.
- P72, three validator false alarms fixed (ellipsis, position tag, hyphen): `d776e8d`, tests
  `b8a2a98`. Audit: about 70 of 95 rejections genuine, every figure rejection genuine.
- P70, one name scanner for grouping: `410b9eb`, `81f35cc`, tests `eb54222`, `f4a8e40`,
  `cb798c1`. Partly fixed, see above.
- `acdca67` Windows task description names both leagues.

**Documents**: ROADMAP `85786a2` (scope, v1.0.0 current, MLB v1.1.0, NHL v1.2.0, multi-user
renumbered v1.4.0); PRD `43973ff` (requirements marked built, D3, D6 analysis table); README
`ffac91c`, GETTING_STARTED `21c4893`, SCHEDULING `dd60251`, `.env.example` `a7bc028` (fresh
clone: venv python, both Ollama models, optional keys, what reads `POLL_INTERVAL_HOURS`);
TASKS `4fa6197`, `b507f33` (P42 closed, P46 deferred, P70 to P73 recorded); CHANGELOG
`bf88002`, `ae09944`; CLAUDE.md `655b3bc`, `9183386`; INTERNALS `5a0caa1`; METRICS `6ddec05`;
SESSION `61c2995`.

**Earlier the same day, already pushed** (`08d6c98` is on `origin/main`): `graphify-out/`
ignored `39f2521`; dead code deleted, 208 lines (`e90c28b`, `dcbee2c`, `09176d2`, `08d6c98`).

**Outside the repository**: two teaching artifacts for the operator (SportWire Playbook and
SportWire Inside Out, the second with graded drills saved to its `attempts` collection), and
two reusable skills at `~/.claude/skills/inside-out-course/` and
`~/.claude/skills/inside-out-architecture/`.

---

## IN PROGRESS

`[VERIFIED]` Nothing is half-written; the tree is clean. The next step is **P70's second
half**, and it is a measurement plus a change:

1. In `processing/cluster.py`, count a full name and its own surname as one entity, and let a
   shared full person name plus one more shared name join a group regardless of rarity.
2. Stop a group's name set growing by union, or cap it, so one roundup headline cannot chain
   two stories ("...Jaxson Dart, Caleb Williams...").
3. Re-run the measurement the subagent used (120 evidence batches; reconstruction of the
   09-23 runs from `fetched_articles` minus `seen_articles`; hand review of every new merge)
   and require: Kawhi Leonard in one group, the 23 correct merges kept, fewer than 9 wrong.
4. Pass the batch's ordinary words through `drop_repeated_stories` so "Did Todd Monken" is
   fixed for repeat suppression too.

---

## JOBS

`[VERIFIED]` No background job is running. None used the skill's `nohup` pattern: they were
harness-backgrounded commands and Sonnet subagents, whose logs lived in session scratch space.

| Command | PID | Log path | Started | Expected runtime | How to check |
|---|---|---|---|---|---|
| ~~fresh clone of `08d6c98`: install, check, dry-run from /tmp~~ | n/a | scratchpad | 09:32 | 2 min | finished: 579 passed, dry run exit 0 |
| ~~fresh clone of `cb798c1`: same~~ | n/a | scratchpad | 18:59 | 3 min | finished: 609 passed, dry run exit 0 (Ollama 500 handled by escalation) |
| ~~5 Sonnet subagents (P42, P70, P72, P71, P72 relaunch)~~ | n/a | session transcripts | 09:31 to 18:51 | varied | all finished and integrated; three were cut off twice by the usage limit and resumed |

---

## OPEN DECISIONS

**1. Keep P70's grouping change on `main`?**
- (a) Keep it, and do the second half next. Fewer duplicate leads (1,091 to 1,059 stories on
  the recorded batches), 9 wrong merges live meanwhile.
- (b) Revert its five commits (`git revert cb798c1 f4a8e40 eb54222 81f35cc 410b9eb`) until the
  second half is measured.
**Recommendation: (a).** The wrong merges fold a story under another rather than duplicating
it, and the old code duplicated the day's biggest stories every day.

~~**2. Push the 33 commits?**~~ Done 2026-09-25.

~~**3. Update GitHub issues #1 and #8**~~ Done 2026-09-25: #8's body corrected and commented, #1 has a gate status table.

**4. City aliases for the validator** (Los Angeles for the Clippers, and so on), P72's largest
open false-alarm class. Needs data in `processing/names.py` and a measurement first.

---

## CHECK STATUS

`[VERIFIED]` Run bare, immediately before writing this file:

```
make check    exit=0
609 passed, 1 xfailed
All documentation links resolve.
```

The one `xfail` is deliberate: `tests/test_validate.py::test_false_relationship_between_grounded_names_is_caught`
documents that the validator checks names, not claims (P5). `[VERIFIED]` The 09-23 NFL brief
shows it live: "the Steelers are exploring trade options" came from a list of mock trades and
passed.

---

## STASHES

`[VERIFIED]` None. `git stash list` is empty.
