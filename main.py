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
import sys
from datetime import date, datetime, timezone

from config.settings import Settings, SettingsError
from delivery.base import DeliveryChannel
from delivery.brief import DEFAULT_MAX_ARTICLES, build_messages
from delivery.stdout import StdoutChannel
from delivery.telegram import TelegramChannel
from ingestion.nba_games import BallDontLieGamesAdapter
from ingestion.rss_news import FEEDS, RssNewsAdapter
from models.schemas import NewsArticle, SeriesContext
from processing.cluster import group_related, limit_per_source
from processing.dedup import deduplicate_articles, deduplicate_games
from processing.highlights import find_notable_games
from processing.newsworthy import drop_non_news
from processing.openrouter import OpenRouterSummarizer
from processing.priority import sort_by_priority
from processing.summarize import OllamaSummarizer, Summarizer
from processing.validate import unsupported_sentences
from storage.db import SeenStore

logger = logging.getLogger("sportwire")


def main(argv: list[str] | None = None) -> int:
    """Run one pipeline pass. Returns a process exit code."""
    args = _parse_args(argv)

    try:
        settings = Settings.from_env()
    except SettingsError as error:
        # Configuration problems are the user's to fix, not stack traces to decipher.
        logging.basicConfig(level="INFO", format="%(message)s")
        logger.error("configuration error: %s", error)
        return 2

    logging.basicConfig(
        level=args.log_level or settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        # The date is here because the log is the only record of the soak, and a
        # time alone cannot be attributed to a run or a code version. `[VERIFIED]`
        # 2026-08-13: counting the summariser's pass rate (TASKS.md P4) over 483
        # lines was impossible for exactly this reason -- runs are 8h apart, cron
        # skips whenever WSL sleeps, so consecutive `08:00:17` lines could be one
        # day apart or four, and at least one logged run predated the current
        # summariser entirely (its traceback names the pre-rename directory).
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    target_date = _parse_date(args.date)

    # --- fetch -----------------------------------------------------------------
    # Both adapters swallow their own failures and return [], so one dead source
    # shortens the brief rather than ending the run.
    if not settings.can_fetch_games:
        logger.warning("BALL_DONT_LIE_API_KEY is not set; skipping games")
        games = []
    else:
        games = BallDontLieGamesAdapter(
            api_key=settings.balldontlie_api_key, target_date=target_date
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

    # Every configured feed, in one list. Each adapter swallows its own failures, so one
    # dead outlet shortens the brief rather than ending the run.
    articles: list[NewsArticle] = []
    for source_name in FEEDS:
        fetched = RssNewsAdapter(source_name).fetch()
        logger.info("  %s: %d articles", source_name, len(fetched))
        articles.extend(fetched)

    # Remove items that are not reporting at all — highlight clips, retrospectives,
    # discussion threads. `[VERIFIED]` A community feed carries these alongside news and
    # their post timestamps say nothing about when the event happened: one live capture
    # included a 2017 highlight posted that morning. Editorial feeds are unaffected.
    #
    # This runs before dedup so nothing downstream spends effort on items that will never
    # be shown, and before the seen-store so a rejected item is not recorded as delivered.
    articles = drop_non_news(articles)

    logger.info("fetched %d games, %d articles", len(games), len(articles))

    # --- deduplicate -----------------------------------------------------------
    with SeenStore(settings.database_path) as store:
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
        # Games are passed in so articles naming a team that played rank first. That is what
        # makes a high-volume community feed usable: tonight's fixtures are an exact filter
        # the pipeline already has, at no extra cost.
        fresh_articles = sort_by_priority(fresh_articles, fresh_games)

        # Group articles covering one story, so a widely-reported event takes one slot
        # rather than seven. `[VERIFIED]` 2026-08-08: a single Kawhi Leonard story produced
        # seven r/nba posts in one capture. Nothing is dropped here — grouping is a view,
        # and every article in a group is still recorded as delivered.
        story_groups = group_related(fresh_articles)

        # Bound how many stories a community feed may lead. `[VERIFIED]` r/nba posts
        # dozens of items a day regardless of how much news there is, and title-pattern
        # filtering could not separate its reporting from its chatter. A story it shares
        # with an outlet is unaffected: those merged above, and the outlet leads them.
        story_groups = limit_per_source(story_groups)

        # On by default since 2026-08-10. It was off while validation passed 0/3; what
        # changed is the input, not the model — filtering retrospectives and capping per
        # source leaves twelve coherent current stories.
        #
        # `[UNKNOWN]` The pass rate. An earlier comment here claimed ~84% from a single
        # sitting of 3/5; `[VERIFIED]` 2026-08-13 the 00:00 run then failed all three
        # attempts and the 08:00 run passed. Two runs is not a rate either. Do not quote a
        # number until the soak has counted enough of them.
        #
        # The summarizer validates its own output and returns None when nothing passes, so
        # a fabrication can never reach a phone: the worst case is the headline list.
        news_summary: str | None = None
        unsupported_claims: list[str] = []
        if story_groups and not args.no_summary:
            # Only what the brief would actually show. `[VERIFIED]` 2026-08-08: summarising
            # everything fetched meant 16 chunks and 17 model calls, exceeding the timeout
            # and falling back to the headline list anyway.
            to_summarise = [group[0] for group in story_groups[:DEFAULT_MAX_ARTICLES]]

            # Hosted when a key is configured, local otherwise. `[VERIFIED]` local 7B
            # fabrication repeats identically across attempts -- "Joe Dumars" invented three
            # times from one Pistons story -- so retry cannot rescue it and parameter count
            # is the only remaining lever (ADR-012).
            summarizer: Summarizer
            if settings.prefers_hosted_summariser:
                summarizer = OpenRouterSummarizer(
                    api_key=settings.openrouter_api_key,
                    model=settings.openrouter_model,
                )
            else:
                summarizer = OllamaSummarizer(model=settings.ollama_model)
            logger.info(
                "summarising %d stories via %s",
                len(to_summarise),
                summarizer.summarizer_name,
            )
            news_summary = summarizer.summarise(to_summarise)

            if news_summary is None:
                logger.info("using the headline list")
            else:
                # Claims the sources cannot have reported, marked rather than removed.
                #
                # `[VERIFIED]` 2026-08-18: the 00:00 brief said Damian Lillard had been traded
                # from Portland to the Pelicans. He had not; the batch says he is back with
                # Portland. Every name in the sentence is real and in the batch, so the
                # summarizer's own validation grounds them all and the brief was delivered.
                #
                # This runs *after* acceptance and never changes it. `[VERIFIED]` The operator
                # chose marking over rejecting, because rejecting that sentence would have
                # rejected all three attempts and delivered a headline list. TASKS.md P5.
                unsupported_claims = unsupported_sentences(news_summary, to_summarise)
                if unsupported_claims:
                    logger.warning(
                        "%d sentence(s) name entities that never share a source article: %s",
                        len(unsupported_claims),
                        " | ".join(unsupported_claims),
                    )

        # --- format ------------------------------------------------------------
        # Head-to-head comes from what this instance has already recorded, not the API.
        # `[VERIFIED]` 2026-08-08: the network version cost one request per fixture and
        # balldontlie's free tier returned 429 from the sixth, so a nine-game slate got
        # context for four. Every result needed already passes through this process, so the
        # local answer costs nothing, cannot be rate-limited, and improves the longer
        # SportWire runs. It is empty for a season this instance has not seen — which is the
        # honest answer rather than a guess.
        series = {}
        for game in fresh_games:
            home_wins, away_wins, meetings = store.head_to_head(game)
            if meetings:
                series[game.game_id] = SeriesContext(
                    game_id=game.game_id,
                    meeting_number=meetings + 1,
                    home_team_prior_wins=home_wins,
                    away_team_prior_wins=away_wins,
                )

        if fresh_games:
            logger.info(
                "season-series context for %d of %d games (from local history)",
                len(series),
                len(fresh_games),
            )

        messages = build_messages(
            fresh_games,
            find_notable_games(fresh_games),
            story_groups,
            news_summary=news_summary,
            series=series,
            unsupported_claims=unsupported_claims,
        )

        if not messages:
            logger.info("nothing new to report")
            return 0

        # --- deliver -----------------------------------------------------------
        if args.dry_run:
            _print_messages(messages)
            logger.info("dry run: nothing sent, nothing recorded")
            return 0

        channel: DeliveryChannel
        if args.channel == "stdout":
            # Unlike --dry-run, this records delivery: an external relay must not re-send
            # the same stories on every run (ADR-013).
            channel = StdoutChannel()
        else:
            try:
                settings.require_delivery()
            except SettingsError as error:
                logger.error("%s", error)
                return 1

            channel = TelegramChannel(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )

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
        "--channel",
        choices=("telegram", "stdout"),
        default="telegram",
        help=(
            "where to deliver. 'stdout' prints the brief AND records it as delivered, so an "
            "external relay can forward it without re-sending stories; unlike --dry-run, "
            "which records nothing"
        ),
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help=(
            "skip the LLM summary and send the headline list. Useful when Ollama is "
            "unavailable, or to compare the two forms"
        ),
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="override LOG_LEVEL from .env for this run",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
