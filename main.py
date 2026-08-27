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
from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import NamedTuple

from config.settings import Settings, SettingsError, brief_size_for
from delivery.base import DeliveryChannel
from delivery.brief import build_messages
from delivery.stdout import StdoutChannel
from delivery.telegram import TelegramChannel
from ingestion.nba_games import BallDontLieGamesAdapter
from ingestion.rss_news import DEFAULT_LEAGUE, FEED_LEAGUES, FEEDS, RssNewsAdapter
from models.schemas import GameData, NewsArticle, SeriesContext
from processing.cluster import group_related, limit_per_source, order_by_relatedness
from processing.dedup import deduplicate_articles, deduplicate_games
from processing.highlights import find_notable_games
from processing.newsworthy import MAX_ARTICLE_AGE_HOURS, drop_non_news
from processing.openrouter import OpenRouterSummarizer
from processing.priority import sort_by_priority
from processing.summarize import (
    EscalatingSummarizer,
    OllamaSummarizer,
    Summarizer,
)
from processing.validate import unsupported_sentences
from storage.db import SeenStore
from storage.evidence import record_batch

logger = logging.getLogger("sportwire")

# How early a brief may be considered due. `[INFERRED]` Without it, a trigger running every
# half hour delivers at 8h00 the first day, 8h20 the next and so on, because each brief is
# measured from the previous delivery rather than from a fixed clock. Five minutes is smaller
# than any interval offered and large enough to stop the drift.
DUE_TOLERANCE_HOURS = 5 / 60


def fetch_news(feed_names: Iterable[str]) -> tuple[list[NewsArticle], list[str]]:
    """Every configured feed in one list, plus the names of the ones that failed.

    Each adapter swallows its own failures, so one dead outlet shortens the brief rather than
    ending the run. But a failure and a quiet feed both return [], so the adapter is asked
    which happened rather than the count being used to guess.

    `[VERIFIED]` 2026-08-18: Reddit answered HTTP 500 for the whole 00:00 run. The brief lost
    25 of its 87 articles and said nothing, because nothing distinguished that from a slow
    news morning. Second observed case, after CBS timed out on 2026-08-15.

    Pulled out of `main` on 2026-08-18 for one reason, recorded because it is the only thing
    that justifies moving code out of the pipeline: a mutation deleting the failure collection
    entirely left all 315 tests green. Inline, this branch could not be tested without the
    network.
    """
    articles: list[NewsArticle] = []
    failed: list[str] = []
    for source_name in feed_names:
        adapter = RssNewsAdapter(source_name)
        fetched = adapter.fetch()
        logger.info("  %s: %d articles", source_name, len(fetched))
        if adapter.last_error:
            failed.append(source_name)
        articles.extend(fetched)
    return articles, failed


def brief_is_due(elapsed_hours: float | None, interval_hours: int) -> bool:
    """Whether enough time has passed since the last delivered brief.

    `[VERIFIED]` 2026-08-27, and the operator confirmed the cause: *"pc was idle so no
    message"*. Cron fires `0 */8 * * *` only if the machine happens to be awake at that exact
    minute, and this one suspends. Both the 08:00 and the 16:00 slots were slept through in a
    single day, so no brief arrived at all: syslog shows cron silent 03:28 to 10:55 and again
    15:25 to 16:25.

    With `--if-due` the scheduler can run often and this decides, so any wake-up after the
    brief became due delivers it. `[INFERRED]` That is the standard shape for a machine that
    sleeps, and it needs no cooperation from Windows, unlike the Task Scheduler route in
    `docs/SCHEDULING.md`, which solves the same problem the other way.

    A tolerance, because a scheduler firing every half hour would otherwise drift the brief
    later by up to that much on every cycle, and eight hours would slowly become nine.
    """
    if elapsed_hours is None:
        return True
    return elapsed_hours >= interval_hours - DUE_TOLERANCE_HOURS


def forget_window(dedup_window_hours: int) -> int:
    """How long a delivered article stays remembered, never less than it stays newsworthy.

    **The floor is the whole function.** `[VERIFIED]` GitHub issue #10 measured what happens
    without it: at an 8-hour window, 3 of 17 ESPN items were older than the window and still
    being published, so each one looked new again and was re-delivered every cycle.

    `[VERIFIED]` Anything delivered longer ago than `MAX_ARTICLE_AGE_HOURS` was published at
    least that long ago too, so `drop_non_news` removes it before dedup is ever consulted.
    That is what makes forgetting it harmless, and it stops being true the moment the window
    drops below that limit.

    Named rather than inline because a mutation deleting the floor left all 371 tests green.
    That is the fourth pipeline-wiring mutant of the week (TASKS.md P36).
    """
    return max(dedup_window_hours, MAX_ARTICLE_AGE_HOURS)


def build_story_groups(articles: list[NewsArticle]) -> list[list[NewsArticle]]:
    """Turn ranked articles into the ordered list of stories the brief shows.

    Three steps whose **order matters**, which is the reason they live in one named function
    rather than three lines inside `main`:

    1. **Group** articles covering one story, so a widely-reported event takes one slot rather
       than seven. `[VERIFIED]` 2026-08-08: a single Kawhi Leonard story produced seven r/nba
       posts in one capture. Nothing is dropped — grouping is a view, and every article in a
       group is still recorded as delivered.
    2. **Cap** how many stories a community feed may lead. `[VERIFIED]` r/nba posts dozens of
       items a day regardless of how much news there is, and title-pattern filtering could not
       separate its reporting from its chatter. A story it shares with an outlet is
       unaffected: those merged in step 1, and the outlet leads them.
    3. **Order** by relatedness, after the cap. `[VERIFIED]` The cap keeps the highest-ranked
       stories, so reordering first would change which ones those are.

    Extracted 2026-08-18 for the same reason `fetch_news` was: a mutation deleting step 3
    entirely left all 341 tests green, because nothing could reach these lines without the
    network. That is the third pipeline-wiring mutant to survive in one day.
    """
    return order_by_relatedness(limit_per_source(group_related(articles)))


class Brief(NamedTuple):
    """One league's assembled brief, plus what must be recorded once it is delivered.

    `[INFERRED]` The two article lists are not the same thing and the difference matters:
    `messages` is what gets sent, while `fresh_articles` and `fresh_games` are what must be
    marked as seen, and only after a send succeeds. Returning them together keeps that
    ordering rule in the caller, where the delivery result is known.
    """

    messages: list[str]
    fresh_articles: list[NewsArticle]
    fresh_games: list[GameData]


def assemble_brief(
    articles: list[NewsArticle],
    games: list[GameData],
    *,
    store: SeenStore,
    settings: Settings,
    failed_sources: list[str],
    no_summary: bool,
    covering_hours: float,
    vocabulary: list[NewsArticle] | None = None,
    league: str | None = None,
) -> Brief:
    """Turn one batch of articles into the messages for one brief.

    Everything from dedup to formatting, with no delivery and no early exits, so it can be
    called once per league (ADR-015). `[INFERRED]` Pulled out of `main` unchanged rather than
    rewritten, because a behaviour change hidden inside a move is the hardest kind to find
    later. Sends nothing and records nothing as seen, so calling it twice is safe.

    `vocabulary` is the wider sample the validator learns ordinary English from, and it is
    deliberately not the same list as `articles`. `[VERIFIED]` TASKS.md P32: a twelve-story
    batch is too small a sample, and splitting the run by league makes each batch smaller
    still, so the sample stays the whole run while the stories stay one sport.
    """
    if vocabulary is None:
        vocabulary = articles
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

    story_groups = build_story_groups(fresh_articles)

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

    # Only what the brief would actually show. `[VERIFIED]` 2026-08-08: summarising
    # everything fetched meant 16 chunks and 17 model calls, exceeding the timeout and
    # falling back to the headline list anyway.
    #
    # Computed here rather than inside the branch below because the recorded batch is
    # these leads whether or not a summary was attempted, and a run with `--no-summary`
    # is exactly the kind that is worth being able to replay.
    # Both derived from the chosen interval, never set apart (PRD D6, TASKS.md P42).
    #
    # `[VERIFIED]` Scaling only the character limit would not work: the story cap binds on
    # 8 of 22 logged runs at 8 hours, so a longer interval would discard more news and
    # still write twelve stories. `[INFERRED]` At the default 8 hours these are exactly
    # today's values, so nothing changes unless the interval does.
    # Sized by the period this brief actually covers, not by the configured interval.
    # `[VERIFIED]` 2026-08-27: the machine slept through both scheduled runs, so the next
    # brief spanned sixteen hours and was still sized for eight, twelve stories. Everything
    # past the cap is recorded as delivered whether or not it was shown, so the extra stories
    # are not held over, they are gone. `brief_size_for` already bounds the growth, so a very
    # long gap cannot produce an unreadable brief.
    max_stories, summary_chars = brief_size_for(round(covering_hours))
    to_summarise = [group[0] for group in story_groups[:max_stories]]

    if story_groups and not no_summary:
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
        elif settings.escalates_model:
            # Small model first, the big one only when the validator refuses what it wrote.
            # `[VERIFIED]` 2026-08-27: 7.4 GB of RAM under WSL2 against a 4.4 GB model is
            # what made the desktop unusable during a run. TASKS.md P55.
            summarizer = EscalatingSummarizer(
                first=OllamaSummarizer(model=settings.ollama_first_model),
                then=OllamaSummarizer(model=settings.ollama_model),
            )
        else:
            summarizer = OllamaSummarizer(model=settings.ollama_model)
        logger.info(
            "summarising %d stories via %s",
            len(to_summarise),
            summarizer.summarizer_name,
        )
        # Everything fetched this run is handed over as the vocabulary sample, while
        # the summary is still validated against `to_summarise` alone.
        #
        # `[VERIFIED]` TASKS.md P32: a twelve-story batch is too small a sample of
        # English. On 2026-08-18 16:00 it never wrote "reacts" or "fire" in lower case,
        # so "Raptors Reacts:" and "Fire Adam Silver" were indexed as entities and
        # refuted the Raptors and the commissioner. Across 258 articles both words are
        # plainly ordinary.
        try:
            news_summary = summarizer.summarise(
                to_summarise, max_chars=summary_chars, vocabulary_sample=articles
            )
        finally:
            # Hand the model back as soon as this league is written, rather than leaving it
            # resident while the brief is formatted and sent. `[VERIFIED]` 2026-08-27: on a
            # machine with 5.3 GB free and a 4.4 GB model, that residency is what the
            # operator felt as the desktop stalling. In a `finally` because a summarizer that
            # raised is exactly the one still holding memory.
            summarizer.release()

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
        failed_sources=failed_sources,
        max_articles=max_stories,
        league=league,
    )

    # Keep the batch before anything else can go wrong with it. `[VERIFIED]` TASKS.md
    # P38 and P39: this week the reproduction evidence was destroyed twice, once by /tmp
    # being cleared on shutdown and once by a purge bug, and both times the numbers
    # measured against it stopped being reproducible. Recording is best-effort and never
    # raises, because losing a brief to protect its evidence would be an absurd trade.
    record_batch(
        to_summarise,
        summary=news_summary,
        unsupported_claims=unsupported_claims,
        failed_sources=failed_sources,
        directory=settings.evidence_path,
        label=league,
    )
    return Brief(
        messages=messages, fresh_articles=fresh_articles, fresh_games=fresh_games
    )


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
    if args.no_poll:
        # balldontlie is a source like any other, and this flag means no source is contacted.
        games = []
    elif not settings.can_fetch_games:
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

    # `--no-poll` must contact nothing at all, which means skipping the fetch itself rather
    # than discarding its result. `[INFERRED]` A flag that promises not to touch a source and
    # then touches it is worse than no flag, because it is the one that gets scheduled often.
    # Asked before anything is fetched, so a scheduler that runs often costs nothing on the
    # wake-ups where no brief is due.
    with SeenStore(settings.database_path) as store:
        elapsed_hours = store.hours_since_last_delivery()

    if args.if_due and not brief_is_due(elapsed_hours, settings.poll_interval_hours):
        logger.info(
            "not due: %.1fh since the last brief, interval is %dh",
            elapsed_hours or 0.0,
            settings.poll_interval_hours,
        )
        return 0

    # What this brief covers: the real gap when there was one, the configured interval
    # otherwise. Never less than the interval, so a run triggered early is not shortchanged.
    covering_hours = max(float(settings.poll_interval_hours), elapsed_hours or 0.0)

    if args.no_poll:
        articles, failed_sources = [], []
    else:
        articles, failed_sources = fetch_news(FEEDS)

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
        # Forget what is too old to come back. The floor is the point: purging inside the
        # window during which a feed still lists an item makes it look new again, and
        # `[VERIFIED]` GitHub issue #10 measured that at an 8-hour window, 3 of 17 ESPN items
        # were older than the window and still being published, so they were re-delivered
        # every cycle. Anything older than `MAX_ARTICLE_AGE_HOURS` is dropped as non-news
        # before dedup is consulted at all, so forgetting it cannot resurrect it.
        #
        # Never on a dry run. `[VERIFIED]` 2026-08-25 this shipped without that guard and a
        # `--dry-run` deleted six days of dedup state while logging "nothing sent, nothing
        # recorded". A dry run that mutates the database is worse than none, because its
        # whole purpose is inspecting the pipeline without consequences.
        if not args.dry_run:
            forget_after = forget_window(settings.dedup_window_hours)
            purged = store.purge_delivered_before(forget_after)
            if purged:
                logger.info(
                    "forgot %d articles delivered over %dh ago", purged, forget_after
                )

        # ADR-014, the seam between polling and delivering.
        #
        # The **poll** writes what was just fetched. The **brief** then reads a window out of
        # the store rather than using the in-memory list, so the two can run at different
        # rates: `--no-poll` assembles a brief without touching a single upstream source.
        #
        # `[VERIFIED]` That matters because otherwise requests scale with how often people
        # want news, and `ingestion/rss_news.py` has recorded since 2026-08-09 that Reddit
        # returns 429 to three requests in two seconds.
        #
        # `[INFERRED]` Behaviour at today's one-brief-per-8-hours is unchanged: the poll runs
        # immediately before the read, so the window contains what was just fetched plus
        # anything earlier that has not yet been delivered. Dedup then removes what was sent.
        if not args.dry_run and not args.no_poll:
            stored = store.record_fetched(articles)
            logger.info(
                "polled %d articles, %d new to the store", len(articles), stored
            )

        if args.poll_only:
            logger.info("poll only: nothing assembled, nothing sent")
            return 0

        # Read the window rather than trust the fetch. On a dry run nothing was written, so
        # fall back to what is in hand rather than reporting on an empty store.
        if not args.dry_run and not args.no_poll:
            articles = store.fetched_since(settings.dedup_window_hours)
        elif args.no_poll:
            articles = store.fetched_since(settings.dedup_window_hours)
            logger.info("no poll: assembled from %d stored articles", len(articles))

        # One brief per league (ADR-015). Grouped from the single window read rather than
        # queried per league, so the poll, `--no-poll` and `--dry-run` paths all see one
        # batch and cannot disagree about what the window held.
        #
        # `[INFERRED]` This is the whole leakage defence. Nothing downstream tells the sports
        # apart, and the summarizer is stateless between calls, so keeping them in separate
        # batches is what stops one brief describing both.
        leagues = sorted({article.league for article in articles})
        logger.info(
            "assembling %d brief(s): %s", len(leagues), ", ".join(leagues) or "none"
        )

        messages: list[str] = []
        fresh_articles: list[NewsArticle] = []
        fresh_games: list[GameData] = []

        for league in leagues:
            brief = assemble_brief(
                [article for article in articles if article.league == league],
                # Game data is basketball only: balldontlie is the sole games adapter and
                # `GameData` carries no league because it has never needed one.
                games if league == "NBA" else [],
                store=store,
                settings=settings,
                # Only the feeds for this league, so an NFL outage is not reported in the
                # basketball brief, where the reader can do nothing with it.
                failed_sources=[
                    name
                    for name in failed_sources
                    if FEED_LEAGUES.get(name, DEFAULT_LEAGUE) == league
                ],
                no_summary=args.no_summary,
                covering_hours=covering_hours,
                vocabulary=articles,
                league=league,
            )
            messages.extend(brief.messages)
            fresh_articles.extend(brief.fresh_articles)
            fresh_games.extend(brief.fresh_games)

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
        "--poll-only",
        action="store_true",
        help=(
            "fetch and store, then stop. For running ingestion on its own schedule, "
            "independent of how often a brief is wanted (ADR-014)"
        ),
    )
    parser.add_argument(
        "--no-poll",
        action="store_true",
        help=(
            "assemble a brief from what is already stored, without contacting any source. "
            "The other half of --poll-only"
        ),
    )
    parser.add_argument(
        "--if-due",
        action="store_true",
        help=(
            "do nothing unless a brief is actually due. Lets the scheduler run often and "
            "leaves the timing to this program, so a machine that was asleep at the exact "
            "minute still gets its brief on the next wake-up"
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
