# SportWire — NBA/NFL News & Games Retrieval Assistant

Aggregates NBA and NFL news from multiple sources, deduplicates stories, summarises them and
delivers a periodic brief to a Telegram chat. Game data is basketball only so far.

**Status: running unattended, two leagues.** `[VERIFIED]` 2026-08-05 a real brief reached a
phone via Telegram, and a repeat run correctly sent nothing because deduplication remembered
it. `[VERIFIED]` 2026-08-26 each sport gets its own brief: a run produced two messages, 54
basketball articles and 112 football ones, with neither sport appearing in the other's brief.
See [`ADR-015`](docs/decisions/ADR-015-one-brief-per-league.md).

A prior prototype is frozen for reference on the `legacy` branch. It never completed a single
end-to-end run; [`docs/history/AUDIT.md`](docs/history/AUDIT.md) records the forensic findings that led to this rebuild, and
[`ADR-011`](docs/decisions/ADR-011-slice-1-retrospective.md) records what building the replacement
actually taught.

## Quick start

Needs Python 3.10 or newer with its `venv` module (on Ubuntu, `sudo apt install python3-venv`).
Use `.venv/bin/python` rather than a bare `python`, which does not exist on a stock Ubuntu.

```bash
git clone https://github.com/AlphaNerdFx/SportWire.git && cd SportWire
make install                # create .venv and install dependencies
cp .env.example .env        # keys are optional for a dry run; see below
make dry-run                # fetch and print a brief, sending and recording nothing
make run                    # fetch and send
make check                  # what CI runs: lint, tests, documentation links
.venv/bin/python scripts/soak_report.py           # how often briefs keep their prose, per league
.venv/bin/python scripts/soak_report.py --audit   # the latest brief beside its sources and doubts
```

`[VERIFIED]` 2026-09-24, from a fresh clone of `08d6c98` with an empty `.env`: `make install`
and `make check` passed, and `main.py --dry-run`, run from `/tmp`, fetched 196 articles and
printed a brief for each league.

Keys, all free: a [balldontlie.io](https://www.balldontlie.io/) key adds NBA scores (news needs
no key), and a Telegram bot token and chat id from [@BotFather](https://t.me/botfather) are
needed only to send. See `.env.example` and
[`docs/reference/GETTING_STARTED.md`](docs/reference/GETTING_STARTED.md).

A brief is due every 8, 12 or 24 hours (`POLL_INTERVAL_HOURS`, default 8); a longer interval
gives a longer brief. To run it unattended, see
[`docs/reference/SCHEDULING.md`](docs/reference/SCHEDULING.md): cron and Windows Task
Scheduler are both documented.

### Local summarisation

> ~~`[VERIFIED]` **Disabled by default, and you probably want to leave it that way.**~~
> **Corrected 2026-08-14.** This described the decision as it stood before 2026-08-10, when
> [ADR-012](docs/decisions/ADR-012-summarisation.md) reversed it. The ADR and the code were
> updated; this file, `SECURITY.md` and the wiki were not, and the stale link to the ADR's old
> filename is what eventually exposed it. `make check` now fails on a broken documentation
> link so the same drift cannot repeat silently.

`[VERIFIED]` **Enabled by default**, using local Ollama models. Requires Ollama installed and
both default models pulled: `llama3.2:3b` writes most briefs and `mistral:7b` is loaded only
when the first one's draft fails the checks. Without Ollama the run degrades to the headline
list rather than failing.

```bash
# On a clean Ubuntu, Ollama's install script needs zstd first — it fails without it
# and the error does not say so.
sudo apt install zstd
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
ollama pull mistral:7b

.venv/bin/python main.py --dry-run              # summarised
.venv/bin/python main.py --dry-run --no-summary # headline list only
```

**Every summary is checked against its sources before it can be sent.**
`processing/validate.py` rejects any proper name or figure that appears nowhere in the source
articles, retries, and falls back to the plain headline list if nothing passes — it fails
closed. `[VERIFIED]` No invented *name* has ever reached a phone.

Two limits you should know before relying on it:

- `[VERIFIED]` **The pass rate**, measured 2026-09-23 with `scripts/soak_report.py` and
  `scripts/accuracy_report.py`: prose reached 72% of NBA briefs and 83% of NFL briefs; since
  09-08, 52.9% of individual drafts were rejected. ~~2 accepted of 19 attempts~~ was an early,
  mixed-version floor (`TASKS.md` P4).
- `[VERIFIED]` **The validator grounds entities, not claims.** A sentence built entirely from
  real names can still assert a false relationship between them and pass. `[VERIFIED]` On
  2026-09-23 a brief said the Steelers were "exploring trade options" for Joey Porter Jr.; the
  source was a writer's list of mock trades. See `TASKS.md` P5; this is open.

`[INFERRED]` The headline list is never wrong; a generated paragraph can be. If that trade is
not one you want, run with `--no-summary`.

## Project documents

**[`docs/`](docs/README.md) is the index.** Everything below lives there, sorted by what it
is. The GitHub wiki was retired into it on 2026-09-03, so documentation now changes in the
same commit as the code it describes.

- [`CLAUDE.md`](CLAUDE.md) — operating rules and constraints for this repo (start here)
- [`docs/reference/GETTING_STARTED.md`](docs/reference/GETTING_STARTED.md) — clone to first brief
- [`docs/reference/WALKTHROUGH.md`](docs/reference/WALKTHROUGH.md) — one story from a feed to a phone
- [`docs/reference/ARCHITECTURE.md`](docs/reference/ARCHITECTURE.md) — target system shape
- [`docs/reference/TESTING.md`](docs/reference/TESTING.md) — how this project tests, and why the method matters more than the count
- [`docs/reference/INTERNALS.md`](docs/reference/INTERNALS.md) — every non-trivial function and why it is shaped that way
- [`docs/planning/ROADMAP.md`](docs/planning/ROADMAP.md) — what each version number means
- [`docs/planning/TASKS.md`](docs/planning/TASKS.md) — the task queue, with proof required per completed item
- [`docs/sessions/SESSION.md`](docs/sessions/SESSION.md) — current working state, decisions made, open questions
- [`docs/history/AUDIT.md`](docs/history/AUDIT.md) — forensic audit of the legacy prototype
- [`docs/decisions/`](docs/decisions/README.md) — architecture decision records (ADRs)

## License

MIT — see `LICENSE`.
