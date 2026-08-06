# SportWire — NBA/NFL News & Games Retrieval Assistant

Aggregates NBA and NFL news and game data from multiple sources, deduplicates stories, and
delivers a periodic brief to a Telegram chat.

**Status: slice 1 working.** `[VERIFIED]` 2026-08-05 — a real three-message brief (scores,
notable events, news) was delivered to a phone via Telegram, and a repeat run correctly sent
nothing because deduplication remembered it.

A prior prototype is frozen for reference on the `legacy` branch. It never completed a single
end-to-end run; `docs/AUDIT.md` records the forensic findings that led to this rebuild, and
`docs/decisions/ADR-011-slice-1-retrospective.md` records what building the replacement
actually taught.

## Quick start

```bash
make install                # create .venv and install dependencies
cp .env.example .env        # then fill in your own keys
make dry-run                # fetch and print a brief, sending nothing
make run                    # fetch and send
make check                  # what CI runs: lint + tests
```

Requires a free [balldontlie.io](https://www.balldontlie.io/) API key and a Telegram bot
token from [@BotFather](https://t.me/botfather). See `.env.example`.

To run it unattended every 8 hours, see [`docs/SCHEDULING.md`](docs/SCHEDULING.md) — cron and
Windows Task Scheduler are both documented.

### Optional: local summarisation

`[VERIFIED]` **Disabled by default, and you probably want to leave it that way.** Every local
model tested fabricated player names and contract figures on real data — see
[ADR-012](docs/decisions/ADR-012-summarisation-off-by-default.md). The headline list is never
wrong; a generated paragraph is not. To experiment anyway:

```bash
# On a clean Ubuntu, Ollama's install script needs zstd first — it fails without it
# and the error does not say so.
sudo apt install zstd
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral:7b

python main.py --dry-run --summary
```

## Project documents

- `CLAUDE.md` — operating rules and constraints for this repo (start here)
- `SESSION.md` — current working state, decisions made, open questions
- `TASKS.md` — the task queue, in priority order, with proof required per completed item
- `ARCHITECTURE.md` — target system shape
- `docs/AUDIT.md` — forensic audit of the legacy prototype
- `docs/decisions/` — architecture decision records (ADRs)

## License

MIT — see `LICENSE`.
