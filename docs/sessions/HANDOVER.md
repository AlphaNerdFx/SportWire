# HANDOVER

Written 2026-08-28. Everything below was checked by running a command in this session, not
recalled. Tags follow `CLAUDE.md` §0.

**Patched 2026-09-03 and 2026-09-04**, in three places: open decisions 1 and 4, and the
STASHES section, because
the 95 stashes they describe were dropped that day and a `[VERIFIED]` claim about something that
no longer exists is the failure this file was written to avoid. Everything else is untouched and
is a snapshot of 2026-08-28, so STATE and IN PROGRESS are older than the repository.

> `[INFERRED]` This file is the one the project's own history warns about: the previous
> handover described a system that did not exist. Nothing here is carried forward from an
> earlier session without re-checking, and where I do not know, it says so.

---

## STATE

`[VERIFIED]` `git branch --show-current`, `git log -1`, `git status --short`:

| | |
|---|---|
| Branch | `main` |
| Last commit | `500c088e850f25ce4ad0e8331a8889a517f25e85` |
| Subject | `docs: close P10, verified on the fixture` |
| Unpushed | **0** (`git log origin/main..HEAD` is empty) |
| Working tree | **clean** |
| Version | `0.5.11` (`pyproject.toml`) |

`[VERIFIED]` Twelve releases were cut and published this session, `v0.5.0` through `v0.5.11`,
all with CI and Release green on GitHub.

---

## DONE THIS SESSION

`[VERIFIED]` 79 commits since the `v0.5.0` tag. Grouped by what they were for.

**NFL, and one brief per league (ADR-015)**
- `20456f9` `85e13d2` and others — the league is carried from the feed, stored beside the
  article, and each sport gets its own brief, heading, evidence file and failed-source list.
- Three football feeds added after checking each live rather than assuming them from the
  basketball URLs.

**Validator defects, each measured against live feeds before shipping**
- `be8934b` P47 — an ordinary word at a name's end grounded the whole name. 0 of 399 real
  names changed.
- `518a7a1` P48 — `Vikings' Jeshaun Jones` welded a team to a player and then refuted the
  team. NFL teams accepted 17/18 → 18/18.
- `5508755` P50 — `Bengals All-Pro` did the same. Blends 461/500 → 452/500, and all 11 lost
  are junk built from league words.
- `390f799` P52 — the same weld without an apostrophe, `Giants WR Calvin Austin III`.
- `20456f9` P51 — a team standing alone is now checked. 0 false flags across 258 titles.

**Cost and the machine (ADR-016, `d15afd5`)**
- `a68f816` `1eeba43` P55 — notes extracted once instead of per retry, a small model writing
  first, the model handed back when the run ends, generation bounded. A two-league run with
  prose went from 183–490 s to **51 s**, with `mistral:7b` never loaded.
- `1d41576` P55 — the token ceiling was fixed at the default while the real limit scales with
  the interval, so 24h and 48h briefs would have been cut off mid-sentence.
- `d0523e8` P63 — a hosted key meant hosted *instead of* local, so a throttled provider
  produced headline lists while a working local model sat idle.

**Scheduling (`5986c8a`, P58)**
- Cron slept through both slots on 2026-08-27 and no brief arrived all day. `--if-due` moves
  the decision into the program; the crontab now wakes it every 30 minutes.
- A brief after a gap is sized by the period it actually covers, not the configured interval.

**Content quality**
- `0342f44` P56 — rankings, mock drafts and forecasts dropped before summarising.
- `66ee4c1` P60 — reader polls dropped; one had turned two players into "fans".
- `85e13d2` P59 — five headlines about one signing became one story instead of four.
- `800ab75` P7 — a birth is no longer ranked as a signing.

**Instruments**
- `261648a` P57 — `scripts/soak_report.py` counts prose-versus-fallback per league.
- `2509eb8` P62 — `--audit` shows a brief beside its sources and the sentences the checker
  doubted.
- `eb01157` P36 — measured `main.py` at **82.1%** reached instead of restructuring it.

**Process, at the operator's instruction**
- `55081eb` — write the test *after* the change is checked, then switch off the exact
  mechanism it names and confirm it fails. A test that survives is rewritten, not
  supplemented. Four tests in one day had passed for the wrong reason.
- `18c8020` P64 — the suite no longer reads the operator's `.env`.

---

## IN PROGRESS

`[VERIFIED]` **Nothing is half-finished.** The tree is clean, everything is pushed, and the
last task closed (`P10`) was verified against the committed fixture before being ticked.

`[INFERRED]` The next useful step is not code. **P54 and P56 both say "resolve by counting
acceptances per league across the soak", and the soak has only just started producing data
from a settled version.** The instrument exists (`python scripts/soak_report.py`); what it
needs is runs, not changes. Changing the summarizer now would contaminate the measurement
again, which is what happened all through 2026-08-26 and 27.

**Exact next step:** after several more scheduled runs, run `scripts/soak_report.py` and read
the per-league numbers. Only then decide whether P54 (invented team affiliations) and P56
(rankings inviting invention) actually improved anything.

---

## JOBS

`[VERIFIED]` **No background job is still running** (`ps` shows no `main.py`).

`[VERIFIED]` **These did not follow this skill's prescribed pattern and that is a real gap.**
The skill specifies `nohup <cmd> > logs/<name>-$(date +%s).log 2>&1 & echo $!`. I used the
harness's own backgrounding instead, which writes to a session-scoped scratchpad directory and
reports no PID. `[INFERRED]` The consequence matters for a handover: **those log paths will not
exist for the next reader**, because the scratchpad is deleted with the session. Anything worth
keeping from them was copied into `TASKS.md` or a tag message at the time.

| Command | PID | Log path | Started | Expected runtime | How to check |
|---|---|---|---|---|---|
| ~~`main.py --dry-run` (×11, timing and output checks)~~ | not captured | scratchpad, **now gone** | 2026-08-26/27 | 1–23 min each | finished; results recorded in `TASKS.md` P55, P56, P58, P63 |
| ~~full-suite trace for `main.py` reach~~ | not captured | scratchpad, **now gone** | 2026-08-27 | ~22 s | finished; **82.1%**, recorded in `TASKS.md` P36 |
| ~~OpenRouter reachability probe~~ | not captured | scratchpad, **now gone** | 2026-08-27 | seconds | finished; HTTP 429, recorded in `TASKS.md` P63 |
| ~~release publication watchers (×6)~~ | not captured | scratchpad, **now gone** | 2026-08-27 | up to 25 min | finished; all releases published and green |
| ~~scheduled-run watcher~~ | not captured | scratchpad, **now gone** | 2026-08-28 01:18 | ~13 min | finished; the 01:31 run delivered 2/2 |

---

## OPEN DECISIONS

**1. ~~Should the doubted-sentence marker return to the brief?~~ Settled 2026-09-04: no,
option (a).** The operator chose it on 2026-09-03 and the measurement landed the next day and
agrees: reading four delivered briefs against their sources, 2 of 9 flags were on entirely
correct sentences, so a marker would doubt correct reporting about once in four. Recall is
worse than precision, and three unflagged errors show why. Full reading in `TASKS.md` P5.

The original question, kept for the record:
`[VERIFIED]` The entity-pair check flagged exactly one sentence in each of two delivered
briefs, and both were the errors the operator found by reading. The flags go to the log and
the evidence file only, because the operator asked on 2026-08-26 for the warning to be removed
from the brief.
- (a) Leave it hidden; read it with `scripts/soak_report.py --audit`.
- (b) Mark only sentences whose entities never co-occur. Rarer than the old warning: about one
  sentence per brief.
- (c) Reject such sentences outright. `[INFERRED]` Risks the headline lists the operator has
  said repeatedly he does not want.
**Recommendation: (a) for now, revisit once the soak shows how often it fires.**

**2. Cron with `--if-due`, or Windows Task Scheduler?**
`[VERIFIED]` The cron form works: the machine slept 21:30 to 01:08 and the brief was delivered
at 01:31, late rather than lost. Task Scheduler solves the same problem with
`-StartWhenAvailable` and is already written in `scripts/schedule_windows.py`.
**Recommendation: keep cron. It is now proven on this machine and needs nothing from Windows.**

**3. Keep the OpenRouter key?**
`[VERIFIED]` Every call returns HTTP 429, `upstream_provider_shared_pool` — the free model's
shared pool, not the key. Each run therefore spends one futile request per league before
falling back to local.
`[UNKNOWN]` Whether the hosted model is any better than the local one. **It has not produced a
single accepted summary**, so nothing is known about its writing or its fabrication rate.
**Recommendation: keep it. The cost is two failed requests per run and the fallback is
proven; if the pool frees up, the soak will show whether it is worth anything.**

**4. ~~95 stashes.~~ Settled 2026-09-03: all 95 dropped, on the operator's instruction.**
`[VERIFIED]` `git stash list` now returns nothing. See STASHES below for what was checked
first and how to get them back.

---

## CHECK STATUS

`[VERIFIED]` Run bare, this session, immediately before writing this file:

```
make check            exit=0
544 passed, 1 xfailed
```

`[VERIFIED]` The single `xfail` is deliberate and is not a broken test:

> `tests/test_validate.py::test_false_relationship_between_grounded_names_is_caught` —
> TASKS.md P5, open and undecided: the validator grounds entities, not claims. Every name in
> it appears in the sources, so a false relationship between real names passes. It asserts
> what the validator *should* do, so it flips to XPASS the day P5 is fixed.

`[VERIFIED]` Current soak reading, `python scripts/soak_report.py`:

```
NBA           10 of 13  (76.9%)   fell back 3
NFL            7 of 12  (58.3%)   fell back 5
unlabelled     3 of 14  (21.4%)   fell back 11
```

**Do not quote those as the rate.** `[VERIFIED]` Twelve releases landed across two days, so
those batches come from twelve versions of the validator and three different models.
`unlabelled` is the shape from before briefs were split by league and is not comparable to the
rows above it. `[INFERRED]` The instrument is sound; the reading is not yet.

---

## STASHES

~~`[VERIFIED]` **95 entries**, from `git stash list`.~~ **Emptied 2026-09-03**, on the
operator's instruction. `[VERIFIED]` `git stash list` returns nothing and `make check` is
still green afterwards: exit 0, 547 passed, 1 xfailed.

`[VERIFIED]` What was checked before they went, rather than assuming the earlier reading:

- All 95 touched only files that still exist. None created a file living nowhere else.
- The whole set was 1264 diff lines across 95 stashes, about 13 lines each, which is the shape
  of a one-line deliberate bug rather than work.
- 94 were mutation scaffolding. The 95th, `pre-autonomous-checkpoint` from 2026-08-14, held
  four untracked files: `.claude/settings.json`, both skill files, and
  `tests/test_check_links.py`. All four are tracked now, three byte-identical to the stashed
  copies, and the fourth is an older copy of the commit skill from before the 2026-08-17
  rules. Nothing unique, so it went with the rest.

`[VERIFIED]` They are recoverable. Dropped stash commits are unreachable rather than deleted:
`git fsck --unreachable --no-reflogs` lists them, and git does not garbage-collect unreachable
objects for 90 days by default, so until roughly **2026-12-02**.
