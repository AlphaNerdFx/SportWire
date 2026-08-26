"""Behaviour tests for the only component that remembers anything between runs.

`storage/db.py` decides what the operator has already been sent. A bug here is invisible in
a single run and obvious across two: either a story arrives twice, or it never arrives at
all. `[VERIFIED]` GitHub issue #15 named this module as untested, and it stayed that way
while nine others gained tests.

Every test uses a real SQLite file in `tmp_path`, never a mock and never `:memory:` shared
across connections. The schema is created by `SeenStore` itself, so these also assert that
`CREATE TABLE IF NOT EXISTS` actually produces a usable database from nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from models.schemas import GameData, NewsArticle
from storage.db import SeenStore

GameFactory = Callable[..., GameData]
ArticleFactory = Callable[..., NewsArticle]


@pytest.fixture
def store(tmp_path: Path) -> SeenStore:
    """A real store on disk, thrown away with the test."""
    return SeenStore(tmp_path / "test.db")


def test_a_fresh_database_remembers_nothing(store: SeenStore) -> None:
    """The first run must start empty rather than raising on a missing schema."""
    assert store.seen_article_ids() == set()
    assert store.seen_game_hashes() == set()


def test_a_recorded_article_is_remembered(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The whole point of the module: what was delivered must not be delivered again."""
    article = make_article("Cavs deal Schroder for Hornets' Mann")

    assert store.record_articles([article]) == 1
    assert store.seen_article_ids() == {article.article_id}


def test_recording_the_same_article_twice_is_not_an_error(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`INSERT OR IGNORE` is load-bearing, not defensive.

    A run that fails after recording some articles must be safe to repeat, and the second
    attempt will hand over items the first already stored. Raising there would turn a partial
    failure into a permanently stuck pipeline.
    """
    article = make_article("Cavs deal Schroder for Hornets' Mann")
    store.record_articles([article])

    assert store.record_articles([article]) == 0
    assert store.seen_article_ids() == {article.article_id}


def test_recording_nothing_is_not_an_error(store: SeenStore) -> None:
    """An empty brief still completes a run, so the store must accept an empty batch."""
    assert store.record_articles([]) == 0
    assert store.record_games([]) == 0


def test_state_is_visible_to_a_second_store_on_the_same_file(
    tmp_path: Path, make_article: ArticleFactory
) -> None:
    """The real usage: one process writes, the next process reads.

    `[INFERRED]` Testing through a single open connection would pass even if nothing were
    committed, which is exactly the bug that would make every run re-send yesterday's brief.
    """
    path = tmp_path / "across-runs.db"
    article = make_article("Cavs deal Schroder for Hornets' Mann")

    with SeenStore(path) as first:
        first.record_articles([article])

    with SeenStore(path) as second:
        assert second.seen_article_ids() == {article.article_id}


def _played_on(game: GameData, days_ago: int) -> GameData:
    """The same fixture, moved back in time.

    `make_game` pins `start_time` so `state_hash` stays reproducible, but `head_to_head`
    counts only meetings played *before* the game being asked about. Without distinct dates
    every test would compare a game against itself and see nothing.
    """
    return game.model_copy(
        update={"start_time": game.start_time - timedelta(days=days_ago)}
    )


def test_a_recorded_game_state_is_remembered(
    store: SeenStore, make_game: GameFactory
) -> None:
    """Games dedup on state, not identity, so the hash is what gets stored."""
    game = make_game()

    assert store.record_games([game]) == 1
    assert store.seen_game_hashes() == {game.state_hash}


def test_the_same_game_at_a_new_score_is_a_new_state(
    store: SeenStore, make_game: GameFactory
) -> None:
    """`[VERIFIED]` This is the behaviour `state_hash` exists for: a game reported at half
    time and again as final is one game and two states, and both must be recorded so the
    second report is not silently swallowed as a duplicate.
    """
    at_half = make_game(home_score=55, away_score=51, status="In Progress", period=2)
    at_final = make_game(home_score=110, away_score=104)

    store.record_games([at_half])

    assert store.record_games([at_final]) == 1
    assert len(store.seen_game_hashes()) == 2


def test_head_to_head_is_zero_for_a_season_never_seen(
    store: SeenStore, make_game: GameFactory
) -> None:
    """Zeros are the honest answer, not an error.

    This instance only knows what it has itself recorded, so a brief early in a season, or on
    a fresh install, has no series history to show.
    """
    assert store.head_to_head(make_game()) == (0, 0, 0)


def test_head_to_head_counts_a_previous_meeting_to_the_winner(
    store: SeenStore, make_game: GameFactory
) -> None:
    """The core arithmetic, with the winner decided by score rather than by which side is home."""
    earlier = _played_on(
        make_game(home_score=120, away_score=99, game_id=1), days_ago=7
    )
    tonight = make_game(game_id=2)

    store.record_games([earlier])

    assert store.head_to_head(tonight) == (1, 0, 1)


def test_the_same_rivalry_at_the_other_venue_still_counts(
    store: SeenStore, make_game: GameFactory
) -> None:
    """`[INFERRED]` A fixture played at the other arena is the same rivalry, so wins are
    attributed by team name in either arrangement. Getting this wrong would halve every
    series record and nobody would notice.
    """
    away_leg = _played_on(
        make_game(
            home="Golden State Warriors",
            away="Los Angeles Lakers",
            home_score=115,
            away_score=100,
            game_id=1,
        ),
        days_ago=7,
    )
    tonight = make_game(game_id=2)

    store.record_games([away_leg])

    # The Warriors won that one, and tonight they are the away side.
    assert store.head_to_head(tonight) == (0, 1, 1)


def test_a_game_still_in_progress_is_not_counted_as_a_result(
    store: SeenStore, make_game: GameFactory
) -> None:
    """`[INFERRED]` A head-to-head record built from half-time scores would be wrong in a way
    nobody would think to check, so only finished games become results.
    """
    unfinished = _played_on(
        make_game(home_score=55, away_score=51, status="In Progress", game_id=1),
        days_ago=7,
    )
    tonight = make_game(game_id=2)

    store.record_games([unfinished])

    assert store.head_to_head(tonight) == (0, 0, 0)


def test_tonight_is_not_counted_in_its_own_history(
    store: SeenStore, make_game: GameFactory
) -> None:
    """The record must describe how the series stood *beforehand*.

    Recording a game and then asking about it is the ordinary sequence in a run, so this is
    the case most likely to be hit and least likely to be noticed.
    """
    tonight = make_game()

    store.record_games([tonight])

    assert store.head_to_head(tonight) == (0, 0, 0)


def test_an_old_delivery_is_forgotten(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The store must not grow forever. GitHub issue #10."""
    article = make_article("Cavs deal Schroder for Hornets' Mann")
    store.record_articles([article])

    assert store.purge_delivered_before(hours=0) == 1
    assert store.seen_article_ids() == set()


def test_a_recent_delivery_survives_a_purge(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The expensive direction, and the one the issue warns about.

    `[VERIFIED]` Forgetting an article a feed is still publishing makes it look new again on
    the next run. At an 8-hour window, 3 of 17 ESPN items were older than the window and
    still listed, so they were re-delivered every cycle.
    """
    article = make_article("Cavs deal Schroder for Hornets' Mann")
    store.record_articles([article])

    assert store.purge_delivered_before(hours=168) == 0
    assert store.seen_article_ids() == {article.article_id}


def test_purging_keeps_the_series_history(
    store: SeenStore, make_game: GameFactory
) -> None:
    """`game_results` is what `head_to_head` reads, and it is meant to accumulate.

    `[INFERRED]` Purging it would make the brief worse the longer SportWire runs, which is
    the opposite of what that table exists for.
    """
    earlier = _played_on(
        make_game(home_score=120, away_score=99, game_id=1), days_ago=7
    )
    store.record_games([earlier])

    store.purge_delivered_before(hours=0)

    assert store.head_to_head(make_game(game_id=2)) == (1, 0, 1)


@pytest.mark.parametrize("configured", [1, 8, 24, 167, 168, 500])
def test_the_pipeline_never_forgets_faster_than_it_filters(configured: int) -> None:
    """The floor that makes purging safe at all, asserted against the real function.

    `[VERIFIED]` An article delivered longer ago than `MAX_ARTICLE_AGE_HOURS` was published
    at least that long ago too, so `drop_non_news` removes it before dedup is ever consulted.
    That is what makes forgetting it harmless, and it stops being true the moment the window
    drops below that limit.

    ~~An earlier version of this test computed `max()` itself and asserted the result.~~
    **That asserted nothing**: a mutation deleting the floor from `main` left all 371 tests
    green, because the test never called the code. Rewritten to call `forget_window`.
    """
    from main import forget_window
    from processing.newsworthy import MAX_ARTICLE_AGE_HOURS

    assert forget_window(configured) >= MAX_ARTICLE_AGE_HOURS


def test_a_generous_window_is_honoured_rather_than_clamped() -> None:
    """The floor raises a short window; it must not lower a long one.

    `[INFERRED]` Someone who sets a fortnight wants a fortnight, and quietly shortening it
    would re-send stories that are still in the feed on a slow news week.
    """
    from main import forget_window

    assert forget_window(500) == 500


@pytest.fixture
def no_upstream_games(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop a test that drives the real `main` from calling the live games API.

    `[VERIFIED]` 2026-08-26: without this, `make check` reached `api.balldontlie.io` and a
    run failed when it answered **HTTP 429**, with a traceback that had nothing to do with
    the code under test. `CLAUDE.md` §8 keeps live sources behind `@pytest.mark.network` and
    out of the default run; these tests drove them anyway, because they exercise `main` end
    to end and `main` fetches games.

    Clearing the key uses the real skip path (`settings.can_fetch_games` is then False)
    rather than stubbing the adapter, so the test still runs production code. `[INFERRED]`
    None of these tests assert anything about games — they are about the poll/deliver seam —
    so removing games removes noise, not coverage.

    Same class of leak as `EVIDENCE_PATH` above: driving the real `main` reaches whatever the
    real `main` reaches, and every such resource has to be pointed somewhere harmless.
    """
    monkeypatch.setenv("BALL_DONT_LIE_API_KEY", "")


def test_a_dry_run_does_not_purge(
    tmp_path: Path,
    make_article: ArticleFactory,
    monkeypatch: pytest.MonkeyPatch,
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-25 this shipped broken and cost six days of dedup state.

    The purge sits inside the store block, which runs long before the `--dry-run` early
    return, so a dry run deleted rows while logging "dry run: nothing sent, nothing recorded".
    A dry run that mutates the database is worse than no dry run at all, because its entire
    purpose is inspecting the pipeline without consequences.

    Asserted against `main` rather than the store, because the store is right either way: it
    purges when told to, and the bug was in who told it.
    """
    import main

    path = tmp_path / "dry.db"
    stale = make_article("A story delivered long ago")

    with SeenStore(path) as store:
        store.record_articles([stale])
        # Backdate it well past any window, so a purge would certainly remove it.
        store._connection.execute(
            "UPDATE seen_articles SET seen_at = ?", ("2020-01-01T00:00:00+00:00",)
        )
        store._connection.commit()

    monkeypatch.setenv("DATABASE_PATH", str(path))
    # Point the evidence directory at the temporary tree too. `[VERIFIED]` 2026-08-25 without
    # this the test wrote into the repository's own `evidence/`, because it drives the real
    # `main`. A test that leaves files in the project tree is how a fixture quietly becomes
    # production data.
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "fetch_news", lambda feeds: ([], []))
    main.main(["--dry-run", "--no-summary"])

    with SeenStore(path) as after:
        assert after.seen_article_ids() == {stale.article_id}, (
            "a dry run must not forget anything"
        )


# --- ADR-014: fetching and delivering run at different rates ---------------------------------


def test_a_fetched_article_comes_back_whole(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The point of ADR-014: a brief is assembled from here, so nothing may be lost in transit.

    Every field the pipeline reads has to survive the round trip, and it comes back as a real
    `NewsArticle` so nothing above the store learns a row shape.
    """
    article = make_article(
        "Cavs deal Schroder for Hornets' Mann",
        summary="Cleveland moved the guard on Tuesday.",
        source="ESPN",
        author="Shams Charania",
    )

    assert store.record_fetched([article]) == 1
    [restored] = store.fetched_since(hours=1)

    assert restored.article_id == article.article_id
    assert restored.title == article.title
    assert restored.summary == article.summary
    assert restored.source == article.source
    assert restored.author == article.author
    assert restored.published_at == article.published_at


def test_a_second_poll_does_not_refresh_the_fetch_time(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[INFERRED]` The behaviour a window query depends on, and the easy thing to get wrong.

    Feeds list an item for days, so it arrives in poll after poll. If each poll updated
    `fetched_at`, a week-old story would look new forever and never leave the window.
    """
    article = make_article("Cavs deal Schroder for Hornets' Mann")
    store.record_fetched([article])

    assert store.record_fetched([article]) == 0
    assert len(store.fetched_since(hours=1)) == 1


def test_only_the_window_is_returned(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """A brief covers a period, not the whole archive.

    Backdated directly, because `fetched_at` is set by the store rather than passed in — which
    is itself the design: it records when *this process* saw the item.
    """
    recent = make_article("Fetched just now")
    old = make_article("Fetched last week")
    store.record_fetched([recent, old])
    store._connection.execute(
        "UPDATE fetched_articles SET fetched_at = ? WHERE article_id = ?",
        ("2026-08-01T00:00:00+00:00", old.article_id),
    )
    store._connection.commit()

    titles = [a.title for a in store.fetched_since(hours=24)]

    assert titles == ["Fetched just now"]


def test_fetching_is_not_delivering(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """Two questions, two tables. `[INFERRED]` Collapsing them would make an article that has
    been fetched but not yet sent indistinguishable from one already delivered, which is
    exactly the state ADR-014 creates and depends on.
    """
    article = make_article("Cavs deal Schroder for Hornets' Mann")

    store.record_fetched([article])

    assert store.seen_article_ids() == set(), "fetching must not mark it delivered"
    assert len(store.fetched_since(hours=1)) == 1


def test_an_empty_poll_is_not_an_error(store: SeenStore) -> None:
    """A source can legitimately return nothing, and a poll that found nothing still finishes."""
    assert store.record_fetched([]) == 0
    assert store.fetched_since(hours=24) == []


def _fresh(title: str, source: str = "ESPN") -> NewsArticle:
    """An article that is new against the **real** clock.

    `make_article` dates items from `conftest.NOW`, which is fixed at 2026-08-13 so that age
    is arithmetic rather than a race (P37). These tests drive the real `main`, which reads the
    real clock, so a fixture-dated article is a fortnight old and `drop_non_news` discards it
    before the store ever sees it.

    `[INFERRED]` Both conventions are right for their own callers. What matters is not mixing
    them: use the fixture clock when testing a function that accepts one, and a real timestamp
    when driving the pipeline end to end.
    """
    return NewsArticle(
        article_id=f"fresh-{abs(hash(title))}",
        title=title,
        url="https://example.com/story",
        summary="",
        source=source,
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


def test_a_poll_stores_without_delivering(
    tmp_path: Path,
    make_article: ArticleFactory,
    monkeypatch: pytest.MonkeyPatch,
    no_upstream_games: None,
) -> None:
    """ADR-014's write half, driven through the real `main`.

    `--poll-only` exists so ingestion can run on a schedule that suits the sources rather than
    one that suits the reader. It must store what it found and send nothing.
    """
    import main

    path = tmp_path / "poll.db"
    fetched = [_fresh("Cavs deal Schroder for Hornets' Mann")]
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "fetch_news", lambda feeds: (fetched, []))

    # `--no-summary` is not incidental. `[VERIFIED]` 2026-08-26: without it, a mutation that
    # removed the poll-only guard did not fail this test, it made it **hang** for ten minutes
    # calling Ollama. A test that drives the whole pipeline must be unable to reach a model or
    # a network, or a mutation campaign becomes a timeout instead of a result.
    assert main.main(["--poll-only", "--channel", "stdout", "--no-summary"]) == 0

    with SeenStore(path) as store:
        assert len(store.fetched_since(hours=1)) == 1
        assert store.seen_article_ids() == set(), (
            "a poll must not mark anything delivered"
        )


def test_a_brief_can_be_assembled_without_contacting_any_source(
    tmp_path: Path, make_article: ArticleFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-014's read half, and the reason the whole decision exists.

    `[VERIFIED]` Otherwise upstream requests scale with how often people want news, and
    `ingestion/rss_news.py` has recorded since 2026-08-09 that Reddit returns 429 to three
    requests in two seconds.

    `fetch_news` is replaced with something that fails loudly rather than returning empty,
    because a flag that promises not to touch a source and then touches it is worse than no
    flag: it is the one that gets scheduled often.
    """
    import main

    path = tmp_path / "brief.db"
    with SeenStore(path) as store:
        store.record_fetched([_fresh("Cavs deal Schroder for Hornets' Mann")])

    def explode(feeds: object) -> None:
        raise AssertionError("--no-poll contacted a source")

    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "fetch_news", explode)

    assert main.main(["--no-poll", "--channel", "stdout", "--no-summary"]) == 0


def test_a_default_run_still_polls_and_delivers_in_one_pass(
    tmp_path: Path,
    make_article: ArticleFactory,
    monkeypatch: pytest.MonkeyPatch,
    no_upstream_games: None,
) -> None:
    """`[INFERRED]` The seam must not change behaviour at today's one brief per 8 hours.

    Splitting a pipeline is exactly the kind of change that works in its new modes and quietly
    breaks the old one, so the unflagged path is asserted rather than assumed.
    """
    import main

    path = tmp_path / "both.db"
    fetched = [_fresh("Cavs deal Schroder for Hornets' Mann")]
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "fetch_news", lambda feeds: (fetched, []))

    assert main.main(["--channel", "stdout", "--no-summary"]) == 0

    with SeenStore(path) as store:
        assert len(store.fetched_since(hours=1)) == 1, "stored"
        assert store.seen_article_ids(), "and delivered"


def _backdate(store: SeenStore, article_id: str, hours_ago: float) -> None:
    """Move one row's fetch time. `fetched_at` is set by the store, which is the design."""
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    store._connection.execute(
        "UPDATE fetched_articles SET fetched_at = ? WHERE article_id = ?",
        (when, article_id),
    )
    store._connection.commit()


def test_the_arrival_rate_is_measured_over_the_span_actually_observed(
    store: SeenStore,
) -> None:
    """The number a bounded interval choice should be built on (PRD D6, TASKS.md P42).

    Ten articles across ten hours is one an hour, and it must stay one an hour when asked
    about a week. `[INFERRED]` Dividing by the requested window instead would report 0.06 and
    make every interval look viable, which is the opposite of useful.
    """
    articles = [_fresh(f"Story {index}") for index in range(10)]
    store.record_fetched(articles)
    for index, article in enumerate(articles):
        _backdate(store, article.article_id, hours_ago=index)

    assert store.arrivals_per_hour(over_hours=168) == pytest.approx(10 / 9, rel=0.01)


def test_an_empty_store_reports_no_rate_rather_than_guessing(store: SeenStore) -> None:
    """Zero is the honest answer before polling has run, and it is what a fresh clone sees."""
    assert store.arrivals_per_hour() == 0.0


def test_a_single_article_is_not_a_rate(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """One observation has no span, so it cannot say how often anything arrives.

    `[INFERRED]` Returning a large number here would be worse than returning nothing: the
    first poll would suggest news arrives constantly and unlock every short interval.
    """
    store.record_fetched([_fresh("The only story so far")])

    assert store.arrivals_per_hour() == 0.0


def test_history_outside_the_window_does_not_dilute_the_rate(store: SeenStore) -> None:
    """Asking about the last day must not average in a quiet fortnight."""
    recent = [_fresh(f"Recent {index}") for index in range(4)]
    ancient = _fresh("From long ago")
    store.record_fetched([*recent, ancient])
    for index, article in enumerate(recent):
        _backdate(store, article.article_id, hours_ago=index)
    _backdate(store, ancient.article_id, hours_ago=500)

    # Four articles across three hours, and the old one is outside the window entirely.
    assert store.arrivals_per_hour(over_hours=24) == pytest.approx(4 / 3, rel=0.01)
