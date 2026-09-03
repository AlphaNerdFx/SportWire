# Getting started

> Moved out of the GitHub wiki on 2026-09-03 so it lives with the code it describes.

Runs on Linux, macOS, or Windows via WSL2. Python 3.10 or newer.

## 1. Get the code and dependencies

```bash
git clone https://github.com/AlphaNerdFx/SportWire.git
cd SportWire
make install
```

`make install` creates `.venv` and installs five packages. No Docker, no database server,
nothing global.

## 2. Get two free credentials

**balldontlie** — sign up at [balldontlie.io](https://www.balldontlie.io/) for a free API
key. Games only; the news feeds need no key.

**Telegram bot** — message [@BotFather](https://t.me/botfather), send `/newbot`, follow the
prompts, and keep the token. Then find your chat id: send your new bot any message, open
`https://api.telegram.org/bot<TOKEN>/getUpdates`, and read `chat.id` from the response.

## 3. Configure

```bash
cp .env.example .env
```

Fill in three values:

```
BALL_DONT_LIE_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

`.env` is gitignored. Nothing else is required — every other setting has a working default.

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

Three messages arrive, with one notification. Run it again immediately and **nothing is
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

**The brief seems short** — it caps at 12 articles, ranked by importance, and says
`+ N more, ranked lower` at the end. Change `DEFAULT_MAX_ARTICLES` in `delivery/brief.py`.
