# Getting started

> Moved out of the GitHub wiki on 2026-09-03 so it lives with the code it describes.

Runs on Linux, macOS, or Windows via WSL2. Python 3.10 or newer, with its `venv` module (on
Ubuntu: `sudo apt install python3-venv`). Commands below use `.venv/bin/python`, because a
stock Ubuntu has `python3` but no `python`.

`[VERIFIED]` 2026-09-24 these steps were followed on a fresh clone of `08d6c98` with an empty
`.env`: install and `make check` passed, and a dry run from `/tmp` printed a brief per league.

## 1. Get the code and dependencies

```bash
git clone https://github.com/AlphaNerdFx/SportWire.git
cd SportWire
make install
```

`make install` creates `.venv` and installs five packages. No Docker, no database server,
nothing global.

## 2. Get two free credentials (optional for a dry run)

Neither is needed to see a brief: with an empty `.env`, `make dry-run` fetches the news
feeds and prints the result. balldontlie adds NBA scores; Telegram is needed only to send.

**balldontlie** — sign up at [balldontlie.io](https://www.balldontlie.io/) for a free API
key. Games only; the news feeds need no key.

**Telegram bot** — message [@BotFather](https://t.me/botfather), send `/newbot`, follow the
prompts, and keep the token. Then find your chat id: send your new bot any message, open
`https://api.telegram.org/bot<TOKEN>/getUpdates`, and read `chat.id` from the response.

## 3. Configure

```bash
cp .env.example .env
```

Fill in the values you have:

```
BALL_DONT_LIE_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

`.env` is gitignored. Nothing else is required; every other setting has a working default.

**How often a brief goes out:** `POLL_INTERVAL_HOURS` is 8, 12 or 24 (default 8). Anything
else is refused with a message saying so. A longer interval gives a longer brief with more
stories, rather than the same brief with more news discarded.

## 3b. Install the local summariser (optional)

The news section is a short written summary by default, from local Ollama models. Without
Ollama the brief falls back to a headline list, so this step is optional:

```bash
sudo apt install zstd            # Ollama's installer needs it on a clean Ubuntu
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b          # writes most briefs
ollama pull mistral:7b           # loaded only when the first model's draft fails the checks
```

## 4. See it work without sending anything

```bash
make dry-run
```

This fetches live data, deduplicates, formats, and **prints** the brief. Nothing is sent and
nothing is recorded, so you can run it as often as you like.

## 5. Send it

```bash
make run
```

One brief per league arrives (NBA and NFL), each as one to three messages: scores, notable
games and news, with the empty sections left out. Only the first message makes a sound. Run it again immediately and **nothing is
sent** — everything has been delivered already. That is deduplication working, not a bug.

To see a full brief with games during the offseason, use a past in-season date:

```bash
./.venv/bin/python main.py --dry-run --date 2026-01-15
```

Note this affects **games only**. News is always current — RSS has no date parameter.

## 6. Run it unattended

See [`docs/SCHEDULING.md`](../../docs/reference/SCHEDULING.md)
for cron and Windows Task Scheduler, both with working commands.

Before trusting a schedule, run it the way the scheduler will — from a different directory:

```bash
cd /tmp && /path/to/SportWire/.venv/bin/python /path/to/SportWire/main.py --dry-run
```

If that prints a brief, the scheduled run will work.

---

## Troubleshooting

**"configuration error: …"** — a value in `.env` is malformed. The message names the setting
and what was wrong with it.

**Telegram credentials rejected** — confirm you have messaged your bot at least once. A bot
cannot start a conversation; the chat must exist first.

**No games** — expected outside the NBA season. The scoreboard and notable sections are
omitted and you get news only.

**Nothing sent at all** — everything currently in the feeds has already been delivered. Check
the log: `after dedup: 0 games, 0 articles`. To start over, delete `sportwire.db`.

**The brief seems short**: at 8 hours it carries 12 stories, ranked by importance, and says
`+ N more, ranked lower` at the end. ~~Change `DEFAULT_MAX_ARTICLES` in `delivery/brief.py`.~~
That constant no longer decides it (corrected 2026-09-24); set `POLL_INTERVAL_HOURS` to 12 or
24 for 15 or 21 stories.

**Every summary attempt fails with a model error**: the model named in `OLLAMA_FIRST_MODEL`
or `OLLAMA_MODEL` is not pulled. Run `ollama list` and pull the missing one.
