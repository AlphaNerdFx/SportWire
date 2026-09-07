# HANDOVER

Written 2026-09-07. Everything below was checked by running a command in this session. Where a
number came from an earlier session it says so and was re-run. Tags follow `CLAUDE.md` §0.

> **This file lives in `docs/sessions/`, not at the repository root.** The `handover` skill says
> root; the documents were moved under `docs/` on 2026-09-03 at the operator's instruction and
> `CLAUDE.md` §9 carries the map. Writing it to root would contradict that map, so the skill was
> not followed to the letter and this note is the reason.

---

## STATE

`[VERIFIED]` `git branch --show-current`, `git log -1`, `git status --short`, `git stash list`:

| | |
|---|---|
| Branch | `main` |
| Last commit | `289ff61abe4a5ba06df290e012c414f0df57907c` |
| Subject | `docs: record the P69 replay, and that it is the training set` |
| Unpushed | **0** |
| Working tree | **clean** |
| Stashes | **0** |
| Version | `0.5.12` |

---

## THE ONE THING TO READ FIRST

`[VERIFIED]` **The accuracy work in this session cost prose delivery, which is the opposite of
what the operator asked for.** Measured over the recorded briefs:

```
2026-08-28 to 09-04, before the figure and filter changes   prose 36 of 44   82%
2026-09-05 to 09-07, after                                  prose  9 of 14   64%
```

`[VERIFIED]` The rejection rate rose with it: 47.3% of attempts rejected as inventing something
before, **62.1%** after. Of 18 rejections since 09-05, 13 name something and **5 a figure** —
figures barely featured before P31 tightened that check.

`[INFERRED]` Some of this is the tightening working as intended: P31 proved the old figure rule
waved through 22.8% of invented numbers, so summaries that used to pass on a coincidence now
fail honestly. But the operator said plainly on 2026-09-04: *"go with what was proven best that
maximizes LLM output and not just headlines. I'll take the hallucination at this point."* A
64% prose rate is movement away from that.

`[UNKNOWN]` How much of the drop is the validator and how much is the machine. `[VERIFIED]` The
same window carries **24 Ollama read timeouts** and 9 runs where the local model exhausted its
attempts, so at least some fallbacks are a slow model rather than a strict check. **This is not
separated yet and it must be before anything is tuned.** See OPEN DECISIONS 1.

---

## DONE THIS SESSION

`[VERIFIED]` From `git log`. Grouped by what they were for.

**The v1.0.0 gate changed shape and its day count is now met**
- `013bd3b` and the commits under it — the 14-day criterion became **accumulated** rather than
  consecutive, in GitHub issue #1, `PRD.md` and `soak_report.py`. A shut-down PC used to reset
  the count and says nothing about whether the software runs unattended.
- `[VERIFIED]` `python scripts/soak_report.py` now reads **14 of 14**.

**P68, the repeated-story bug the operator found by reading briefs** (`50a199c` … `f3643a9`)
- The NBA's Clippers ruling reached four consecutive briefs. Dedup matched an article id, so a
  fresh report of yesterday's news passed every time.
- Fixed by remembering what a delivered story was about and dropping a retelling that names
  nobody new. `[VERIFIED]` It has fired **11 times in live runs** since.

**P31, figures grounded by digit soup** (`32d830d` and its neighbours)
- The old rule stripped punctuation from the whole batch and asked whether a figure's digits
  appeared anywhere in it. `[VERIFIED]` 22.8% of invented figures passed, 81% of one-digit ones.
  Comparing values instead: **0.2%**, with three corrections across 51 delivered briefs.

**P69, the filter's blind spots, found by hand audit** (`635269c`, `289ff61`)
- `[VERIFIED]` 15 delivered headlines read one by one: **8 were not news**. Six rules shipped,
  dropping 18 of 494 surviving titles, none of them real stories.
- Three candidates measured and **rejected** because each also took real reporting; the tests
  now pin that boundary.

**The metrics the operator asked for** (`aa73fb2`)
- `scripts/accuracy_report.py` and `docs/reference/METRICS.md`.

**P16, P17, P3, P7, P35, P36, P66, P67 closed** with their measurements recorded.

**The wiki was retired into `docs/`** and the documents reorganised (`d526893` … `fa95363`),
including a single signpost page left on the wiki.

---

## IN PROGRESS

`[VERIFIED]` **Nothing is half-finished.** Tree clean, everything pushed, `make check` green.

`[VERIFIED]` **A `/loop` was running and is not scheduled any more.** The last iteration ended
with a report rather than a `ScheduleWakeup`, so no wakeup is pending and nothing will fire on
its own. Restart it with `/loop` if that is wanted.

**Exact next step, and it is a measurement rather than code:** separate the prose-rate drop into
its two causes. Run

```bash
awk '$1>="2026-09-05"' logs/sportwire.log | grep -c "Read timed out"
awk '$1>="2026-09-05"' logs/sportwire.log | grep -oE "attempt . rejected \(.*\)"
```

and count how many of the 9 fallbacks since 09-05 followed a timeout versus a rejection. Only
then decide whether the figure check needs loosening, because tuning a validator against a
number that is really about a slow Ollama would be the wrong fix to the wrong problem.

---

## JOBS

`[VERIFIED]` **No background job of mine is still running.**

`[VERIFIED]` **None of them followed this skill's prescribed pattern, and that is the same gap
the last handover recorded.** The skill specifies
`nohup <cmd> > logs/<name>-$(date +%s).log 2>&1 & echo $!`. I used the harness's own
backgrounding, which writes to a session-scoped scratchpad and reports no PID, so **those log
paths will not exist for the next reader.**

| Command | PID | Log path | Started | Expected runtime | How to check |
|---|---|---|---|---|---|
| ~~`make check` (×12, before each commit batch)~~ | not captured | scratchpad, **now gone** | 2026-09-03 to 09-07 | 10–100 s each | finished; all exit 0, last one 579 passed |
| ~~`gh run watch` (×6, CI after each push)~~ | not captured | scratchpad, **now gone** | 2026-09-03 to 09-05 | 25–40 s each | finished; every run green |
| ~~measurement scripts (blends, figures, repeats, relevance)~~ | not captured | scratchpad, **now gone** | 2026-09-04/05 | seconds each | finished; every number is quoted in `TASKS.md` P31, P68, P69 |

`[VERIFIED]` **Cron is running and is not mine.** The last line of `logs/sportwire.log` is
`2026-09-07 19:01:13 not due: 0.1h since the last brief`, and 62 delivery lines are recorded.

---

## OPEN DECISIONS

**1. The prose rate fell to 64% and the operator asked for the opposite. What gives?**
`[VERIFIED]` 82% → 64%, alongside 24 Ollama read timeouts in the same window.
- (a) **Separate the causes first, decide after.** No change until the timeout share is known.
- (b) Loosen the figure check to warn rather than reject. `[INFERRED]` Gets prose back and
  reinstates part of what P31 measured as a 22.8% false-acquittal rate.
- (c) Raise the attempt ceiling so a slow or unlucky model gets more tries, at the cost of run
  time, which P55 was fought to bring down.
- (d) Accept 64% as the price of a validator that now works.
**Recommendation: (a).** It is one command and everything else is guessing until it is run.

**2. The v1.0.0 gate's day count is met. Is the gate met?**
`[VERIFIED]` 14 of 14 days. `[VERIFIED]` The duplicate-stories clause was the blocker and P68
addressed it on 09-04; the suppression has fired 11 times since. `[UNKNOWN]` Whether any
duplicate slipped through after it, which nothing has checked.
**Recommendation: audit the last week's briefs for a repeated story before closing issue #1.**
Closing a gate on an unverified clause is the shape this project exists to avoid.

**3. `P54` lost its baseline.** `[INFERRED]` It was waiting on soak data from a settled version,
and the summarizer's inputs changed twice this week (P69's filter, P68's suppression). The
partial count it was accumulating is no longer comparable.
**Recommendation: restate P54's window as starting 2026-09-05 and let it run.**

---

## CHECK STATUS

`[VERIFIED]` Run bare, immediately before writing this file:

```
make check            exit=0
579 passed, 1 xfailed
```

`[VERIFIED]` The single `xfail` is deliberate and is not broken:

> `tests/test_validate.py::test_false_relationship_between_grounded_names_is_caught` —
> `TASKS.md` P5. The validator grounds entities, not claims, so a sentence of real names can
> assert something false and pass. The operator chose marking over rejecting, so the test now
> describes a road not taken and flips to XPASS if that is ever revisited.

`[VERIFIED]` Current readings:

```
python scripts/soak_report.py       14 of 14 days; NBA and NFL both delivering
python scripts/accuracy_report.py --since 2026-09-05
                                    62.1% of attempts rejected as inventing something
                                    72.3% of fetched articles survive the news filter
```

`[VERIFIED]` The hand-audit calibration in `docs/reference/METRICS.md` is **7 of 15 (47%)** on
2026-09-05, and the 70% beside it is the same sample replayed through rules written from it,
which is the training set grading itself. **A fresh sample on a new seed is owed** and is the
only thing that can say whether 47% moved.

---

## STASHES

`[VERIFIED]` **None.** `git stash list` is empty. The 95 entries the previous handover recorded
were dropped on 2026-09-03 on the operator's instruction, after checking that all 95 touched
only files still in the tree and that the one non-mutation entry held nothing unique. They
remain recoverable as unreachable objects until roughly 2026-12-02.
