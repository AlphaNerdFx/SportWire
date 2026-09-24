# Changelog

What changed in each released version, one entry per tag, newest first.

`[VERIFIED]` Every line below is the opening claim of that version's own release notes, read
with `git tag -l <version> -n99`, with dates from `git log -1 --format=%ad --date=short <tag>`.
Nothing here is a summary written from memory. The full notes stay in the tag and on the
GitHub release page; this file is the index to them.

New entries go under Unreleased as the work lands, and move under a version heading when the
tag is cut. See `CLAUDE.md` §9.

## Unreleased

- A brief is now due every 8, 12 or 24 hours, your choice, and nothing else is accepted. A
  longer interval gives a longer brief: the story count, each outlet's share and how long a
  delivered story is remembered all grow with it, so a 24-hour NFL brief can carry 21 stories
  instead of stopping at 12 (P42).
- A follow-up to a story you were never shown is no longer dropped as a repeat. Only the
  stories actually in a brief count as delivered; before, three in four of the stories the
  repeat check remembered had never reached you (P71).
- Two reports of the same story in one brief now merge more often: the 49ers are recognised
  as the Niners, "Giants' Jaxson Dart" as Jaxson Dart, and a headline's opening word is no
  longer taken for a name. The day's biggest story can still appear more than once (P70).
- Three kinds of real name are no longer refused as invented: one cut by an ellipsis, one
  written with a position ("QB Darnold") and one inside a hyphenated word ("Carter-like").
  An audit of every refusal since 09-05 found about three in four were real inventions (P72).
- The README and getting-started guide now work from a fresh clone on a stock Ubuntu: the
  right Python path, both Ollama models, and keys marked optional for a dry run (P73).
- v1.0.0 covers the NBA and the NFL. Baseball and hockey move to v1.1.0 and v1.2.0, and the
  football community feed comes after v1.0.0.
- A player whose name ends in `Jr.` or `Sr.` is no longer accused of being invented when the
  brief writes about something of his. Three briefs in six days lost an attempt to it (P66).
- The basketball brief no longer carries hockey, baseball or college stories, and the football
  brief no longer carries hockey. The feeds are scoped by web address, not by content, so one
  of them had been delivering an NHL contract to a basketball reader (P35).
- Betting cards, forecasts written as "Predicting", counterfactual "what if" pieces, career
  timelines and untagged highlight posts no longer reach the brief. Found by reading fifteen
  delivered headlines rather than by a test: eight of them were not news (P69).
- A money figure in the brief is now checked as a number rather than as a run of digits.
  Nearly a quarter of invented figures used to pass because their digits happened to appear
  somewhere in the batch, and one-digit figures passed four times in five (P31).
- The same story is no longer delivered again on the next run. A story that develops still
  gets through: the test is whether the new article names anyone the story was not delivered
  with before (P68).
- A player named after his position in a headline, as in "Broncos WR Mims", is no longer
  mistaken for a different person and refused. Football headlines are written this way
  constantly (P67).
- Rankings and predictions are dropped whichever way the headline words them. The old rule
  matched three exact phrases and missed most of the class, so a fifth of what it was meant to
  catch was still reaching the summarizer and inviting it to invent (P56).

## v0.5.12 - 2026-08-28

- The store of polled articles is cleaned up, having previously grown for as long as the
  program ran.

## v0.5.11 - 2026-08-27

- A post about a player visiting a maternity ward no longer ranks alongside a max contract.

## v0.5.10 - 2026-08-27

- Setting a hosted API key used to replace the local model rather than sit in front of it,
  which turned a throttled provider into a brief with no writing in it at all.

## v0.5.9 - 2026-08-27

- A standing worry about the test suite settled by measuring it rather than acting on it.

## v0.5.8 - 2026-08-27

- You can now read a brief beside the sentences the checker doubted about it.

## v0.5.7 - 2026-08-27

- Two faults the operator spotted in a delivered brief, both fixed.

## v0.5.6 - 2026-08-27

- The brief now survives a laptop that goes to sleep, which the day before it did not.

## v0.5.5 - 2026-08-27

- There is now a way to count how often the brief keeps its written summary instead of falling
  back to a list of headlines.

## v0.5.4 - 2026-08-27

- Rankings, mock drafts and forecasts no longer reach the summarizer, because they were the
  main thing making it invent players.

## v0.5.3 - 2026-08-27

- Fixes a bug shipped a few hours earlier in v0.5.2, before anyone could run into it.

## v0.5.2 - 2026-08-27

- A run used to make the whole machine unusable for several minutes. It now finishes in under a
  minute and leaves more than 5 GB of memory free while it works.

## v0.5.1 - 2026-08-27

- Football briefs were being written by a model that had been told it was writing about
  basketball. Fixed, along with three false accusations that were costing those briefs.

## v0.5.0 - 2026-08-26

- Football arrives, and it gets its own brief rather than sharing the basketball one.

## v0.4.0 - 2026-08-26

- You choose how often the brief arrives, and what schedules it.

## v0.3.0 - 2026-08-26

- Fetching and delivering are now separate operations.

## v0.2.0 - 2026-08-26

- The first milestone this project actually finished.

## v0.1.5 - 2026-08-18

- A false claim between two real names is marked in the brief rather than hidden.

## v0.1.4 - 2026-08-17

- A dry run of the real pipeline passes on the first attempt.

## v0.1.3 - 2026-08-17

- Two false accusations are gone, and both were costing whole briefs.

## v0.1.2 - 2026-08-17

- The sport's own vocabulary stops failing briefs.

## v0.1.1 - 2026-08-16

- The validator stops accusing the model of things it did not do.

## v0.1.0 - 2026-08-14

- First tagged pre-release.

## pre-release-legacy-frozen - 2026-08-03

- The frozen legacy prototype. No working product, tests and scaffolding only. Kept as the
  `legacy` branch for reference and never extended.
