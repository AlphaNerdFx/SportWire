# Changelog

What changed in each released version, one entry per tag, newest first.

`[VERIFIED]` Every line below is the opening claim of that version's own release notes, read
with `git tag -l <version> -n99`, with dates from `git log -1 --format=%ad --date=short <tag>`.
Nothing here is a summary written from memory. The full notes stay in the tag and on the
GitHub release page; this file is the index to them.

New entries go under Unreleased as the work lands, and move under a version heading when the
tag is cut. See `CLAUDE.md` §9.

## Unreleased

- A player whose name ends in `Jr.` or `Sr.` is no longer accused of being invented when the
  brief writes about something of his. Three briefs in six days lost an attempt to it (P66).
- The basketball brief no longer carries hockey, baseball or college stories, and the football
  brief no longer carries hockey. The feeds are scoped by web address, not by content, so one
  of them had been delivering an NHL contract to a basketball reader (P35).
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
