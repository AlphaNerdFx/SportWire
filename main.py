"""SportWire — the single entrypoint. Fetch, deduplicate, format, deliver.

`CLAUDE.md` §5 rule 3: one entrypoint, no secondary runners. The legacy prototype had two
(`run_pipeline.py` and `ingestion/run_ingestion.py`), both empty.

This module is the only place that reads configuration and the only place that knows which
concrete adapters and channel are in use. Everything below it depends on interfaces, which
is why adding a source (task M6) should not require editing anything here except one line
of the source list.

Run it:
    python main.py --dry-run        print the brief, send nothing
    python main.py                  send it
    python main.py --date 2026-01-15    fetch a specific day's GAMES rather than today's

`[VERIFIED]` Known limitation: `--date` affects games only. RSS is a feed of what is
published at this moment and the format has no date parameter, so historical headlines
cannot be requested from ESPN at all. Running with `--date` therefore pairs that day's
scores with today's news. Harmless for the intended daily use, but it means this is not a
tool for reconstructing a past day — see `SESSION.md` known limitations.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone

from dotenv import load_dotenv

from delivery.brief import build_messages
from delivery.telegram import TelegramChannel
from ingestion.espn_news import ESPNNewsAdapter
from ingestion.nba_games import BallDontLieGamesAdapter
from processing.dedup import deduplicate_articles, deduplicate_games
from processing.highlights import find_notable_games
from processing.priority import sort_by_priority
from processing.summarize import DEFAULT_MODEL, OllamaSummarizer
from storage.db import SeenStore

logger = logging.getLogger("sportwire")


def main(argv: list[str] | None = None) -> int:
    """Run one pipeline pass. Returns a process exit code."""
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    load_dotenv()

    target_date = _parse_date(args.date)

    # --- fetch -----------------------------------------------------------------
    # Both adapters swallow their own failures and return [], so one dead source
    # shortens the brief rather than ending the run.
    games_key = os.getenv("BALL_DONT_LIE_API_KEY", "")
    if not games_key:
        logger.warning("BALL_DONT_LIE_API_KEY is not set; skipping games")
        games = []
    else:
        games = BallDontLieGamesAdapter(
            api_key=games_key, target_date=target_date
        ).fetch()

    # `--date` reaches the games adapter only. An RSS feed is a document of what is
    # published *now* — the format has no date query, so historical headlines cannot be
    # requested from ESPN at all. Saying so out loud, because a brief that mixes January's
    # scores with today's news is confusing unless you know why.
    if target_date is not None:
        logger.warning(
            "--date %s applies to games only; ESPN RSS always returns current news",
            target_date.isoformat(),
        )

    articles = ESPNNewsAdapter().fetch()
    logger.info("fetched %d games, %d articles", len(games), len(articles))

    # --- deduplicate -----------------------------------------------------------
    database_path = os.getenv("DATABASE_PATH", "sportwire.db")
    with SeenStore(database_path) as store:
        fresh_games = deduplicate_games(games, store.seen_game_hashes())
        fresh_articles = deduplicate_articles(articles, store.seen_article_ids())
        logger.info(
            "after dedup: %d games, %d articles (%d and %d already sent)",
            len(fresh_games),
            len(fresh_articles),
            len(games) - len(fresh_games),
            len(articles) - len(fresh_articles),
        )

        # --- summarise -----------------------------------------------------------
        # Sorted first so the most important news reaches the model first; it will not
        # reliably reorder on instruction (see processing/priority.py).
        fresh_articles = sort_by_priority(fresh_articles)

        # Off by default. `[VERIFIED]` 2026-08-06 every local model tested fabricated
        # facts on live data — mistral:7b, the best of them, renamed Dillon Brooks to
        # "Devin Booker", invented a "$3.3M" figure, and turned "Knicks executive Rosas"
        # into "Steve Nash's right-hand man, Leon Rose". The headline list is never wrong,
        # so it stays the default until a model earns the swap.
        news_summary: str | None = None
        if fresh_articles and args.summary:
            summarizer = OllamaSummarizer(
                model=os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
            )
            logger.info(
                "summarising %d articles via %s",
                len(fresh_articles),
                summarizer.summarizer_name,
            )
            news_summary = summarizer.summarise(fresh_articles)
            if news_summary is None:
                logger.warning("no summary produced; falling back to the headline list")

        # --- format ------------------------------------------------------------
        messages = build_messages(
            fresh_games,
            find_notable_games(fresh_games),
            fresh_articles,
            news_summary=news_summary,
        )

        if not messages:
            logger.info("nothing new to report")
            return 0

        # --- deliver -----------------------------------------------------------
        if args.dry_run:
            _print_messages(messages)
            logger.info("dry run: nothing sent, nothing recorded")
            return 0

        channel = _build_channel()
        if channel is None:
            return 1

        # Only the first message rings the phone; the rest arrive silently so a
        # three-part brief is one notification rather than three.
        delivered = 0
        for index, message in enumerate(messages):
            if channel.send(message, silent=index > 0):
                delivered += 1

        if delivered == 0:
            logger.error("no messages delivered; not recording anything as sent")
            return 1

        # Recorded only after delivery succeeded. Recording first would mean a failed
        # send silently loses those items forever, because the next run would consider
        # them already delivered.
        store.record_games(fresh_games)
        store.record_articles(fresh_articles)
        logger.info("delivered %d/%d messages", delivered, len(messages))

    return 0


def _build_channel() -> TelegramChannel | None:
    """Construct the delivery channel from the environment, or None if unconfigured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.error(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env to send. "
            "Use --dry-run to preview without sending."
        )
        return None
    return TelegramChannel(bot_token=token, chat_id=chat_id)


def _print_messages(messages: list[str]) -> None:
    """Print each message the way it would arrive, for --dry-run."""
    for index, message in enumerate(messages, start=1):
        print(f"\n--- message {index} of {len(messages)} ({len(message)} chars) ---")
        print(message)
    print()


def _parse_date(raw: str | None) -> date | None:
    """Parse --date, or return None to mean today."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).date()
    except ValueError:
        logger.error("--date must be YYYY-MM-DD, got %r", raw)
        raise SystemExit(2) from None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and deliver an NBA brief.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the brief instead of sending it; records nothing as seen",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help=(
            "fetch GAMES for a specific date instead of today. Does not affect news: "
            "RSS has no date query, so ESPN always returns current headlines"
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help=(
            "EXPERIMENTAL: replace the headline list with an LLM-written paragraph. "
            "Off by default because every local model tested fabricated player names and "
            "figures on live data — see processing/summarize.py"
        ),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="logging level (default: INFO)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
