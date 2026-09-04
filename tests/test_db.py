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

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config.settings import brief_size_for
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


def _fresh(title: str, source: str = "ESPN", league: str = "NBA") -> NewsArticle:
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
        league=league,
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


_DISTINCT_TITLES = [
    "Hawks sign Kobe Bufkin to an extension",
    "Celtics waive Luke Kornet before camp",
    "Nets trade Cam Thomas to the Pistons",
    "Hornets hire Tomas Satoransky as an assistant",
    "Bulls extend Ayo Dosunmu for two years",
    "Cavaliers name Sam Merrill a starter",
    "Mavericks release Dwight Powell",
    "Nuggets add Julian Strawther to the rotation",
    "Pistons promote Jaden Ivey to captain",
    "Warriors re-sign Gui Santos",
    "Rockets decline Jock Landale's option",
    "Pacers reward Andrew Nembhard with a deal",
    "Clippers waive Kobe Brown",
    "Grizzlies extend Santi Aldama",
    "Heat sign Nikola Jovic long term",
    "Bucks add Andre Jackson to the roster",
    "Wolves keep Josh Minott another season",
    "Pelicans move Trey Murphy to the bench",
    "Knicks bring back Precious Achiuwa",
    "Magic reward Anthony Black with minutes",
]


def _distinct_batch(count: int) -> list[NewsArticle]:
    """Articles that neither group together nor hit the per-source cap.

    Two things had to be right before this test could measure what it claims:

    `[VERIFIED]` A first attempt used "Story number 0..19", and `group_related` correctly
    merged all twenty into one story, because they share the rare name "Story".

    `[VERIFIED]` A second attempt made them all ESPN, and `limit_per_source` correctly capped
    them at 4. Spreading across the four real sources raises the ceiling to 15 stories, which
    is enough for the 12-story default to be the binding limit rather than the source cap.
    """
    sources = ["ESPN", "CBS Sports", "Yahoo Sports", "r/nba"]
    return [
        _fresh(title, source=sources[index % len(sources)])
        for index, title in enumerate(_DISTINCT_TITLES[:count])
    ]


def test_the_interval_decides_how_many_stories_a_brief_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`[VERIFIED]` P36: pipeline wiring in `main` is invisible to the suite unless a test
    drives it, and three mutations deleting a whole step have already passed unnoticed.

    Asserted on the observable consequence: the same twenty stories produce a short brief at
    the two-hour interval and a longer one at two days.
    """
    import main

    fetched = _distinct_batch(20)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "iv.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "fetch_news", lambda feeds: (fetched, []))

    def stories_at(interval: str) -> int:
        monkeypatch.setenv("POLL_INTERVAL_HOURS", interval)
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / f"iv{interval}.db"))
        capsys.readouterr()
        main.main(["--channel", "stdout", "--no-summary"])
        return capsys.readouterr().out.count("—")

    assert stories_at("2") < stories_at("48"), (
        "a longer interval must carry more stories"
    )


def test_the_default_interval_leaves_the_brief_exactly_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property that makes the whole change safe: 8 hours changes nothing.

    `[INFERRED]` A scaling rule that quietly altered today's brief would be a behaviour change
    disguised as a feature, and the operator asked for 8 hours to stay the standard.
    """
    import main
    from delivery.brief import DEFAULT_MAX_ARTICLES

    fetched = _distinct_batch(20)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "default.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.delenv("POLL_INTERVAL_HOURS", raising=False)
    monkeypatch.setattr(main, "fetch_news", lambda feeds: (fetched, []))

    capsys.readouterr()
    main.main(["--channel", "stdout", "--no-summary"])

    assert capsys.readouterr().out.count("—") == DEFAULT_MAX_ARTICLES


# --- ADR-015: one brief per league ----------------------------------------------------------


def test_the_league_survives_the_round_trip(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[VERIFIED]` The prerequisite for ADR-015, and the thing a default silently hides.

    `NewsArticle.league` defaults to "NBA", so a store that dropped the column entirely would
    still return "NBA" for an NBA article and look correct. Recording an NFL one is what
    actually proves the value is written and read rather than re-defaulted on the way out.
    """
    football = make_article("Mahomes signs an extension", league="NFL")

    store.record_fetched([football])
    [restored] = store.fetched_since(hours=1)

    assert restored.league == "NFL"


def test_asking_for_one_league_excludes_the_other(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The whole leakage defence in ADR-015: the batch never contains both sports.

    Nothing downstream tells the sports apart, so if this filter is wrong the summarizer is
    handed a mixed batch and blends them, which is the failure the decision exists to prevent.
    """
    store.record_fetched(
        [
            make_article("Mahomes signs an extension", league="NFL"),
            make_article("Doncic drops 40 on the Clippers", league="NBA"),
        ]
    )

    basketball = store.fetched_since(hours=1, league="NBA")
    football = store.fetched_since(hours=1, league="NFL")

    assert [article.title for article in basketball] == [
        "Doncic drops 40 on the Clippers"
    ]
    assert [article.title for article in football] == ["Mahomes signs an extension"]
    assert len(store.fetched_since(hours=1)) == 2, (
        "no league asked for means all of them"
    )


def test_an_existing_database_gains_the_league_column(tmp_path: Path) -> None:
    """`[VERIFIED]` The migration. ADR-014 said this case would need one, and here it is.

    Builds the pre-league table by hand, because that is what is sitting on the operator's
    disk. `CREATE TABLE IF NOT EXISTS` is a no-op against it, so without the `ALTER TABLE`
    every read of the new column raises `no such column` and the brief stops being delivered.
    """
    import sqlite3

    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE fetched_articles (
            article_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
            summary TEXT NOT NULL, source TEXT NOT NULL, author TEXT,
            published_at TEXT NOT NULL, fetched_at TEXT NOT NULL
        );
        INSERT INTO fetched_articles VALUES
            ('kept', 'A story recorded before leagues existed', 'https://example.com', '',
             'ESPN', NULL, '2026-08-26T00:00:00+00:00', '2026-08-26T00:00:00+00:00');
        """
    )
    connection.commit()
    connection.close()

    with SeenStore(path) as store:
        [restored] = store.fetched_since(hours=24 * 365 * 100)

    assert restored.title == "A story recorded before leagues existed", (
        "the migration must not drop the rows it is migrating"
    )
    assert restored.league == "NBA", (
        "everything recorded before NFL existed was basketball"
    )


def test_each_league_gets_its_own_brief(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """ADR-015 driven through the real `main`, which is the only place the split happens.

    `[VERIFIED]` TASKS.md P36: wiring in `main` is invisible to the rest of the suite, so
    every unit below here can pass while the pipeline still hands the summarizer one mixed
    batch. The assertion that matters is not the message count, it is that no message
    contains both sports.
    """
    import main

    fetched = [
        _fresh("Doncic drops 40 on the Clippers", source="ESPN", league="NBA"),
        _fresh(
            "Celtics waive a training camp guard", source="CBS Sports", league="NBA"
        ),
        _fresh("Mahomes signs a contract extension", source="ESPN NFL", league="NFL"),
        _fresh(
            "Packers release a veteran lineman", source="CBS Sports NFL", league="NFL"
        ),
    ]
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "leagues.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "fetch_news", lambda feeds: (fetched, []))

    assert main.main(["--dry-run", "--no-summary"]) == 0

    printed = capsys.readouterr().out
    messages = re.split(r"--- message \d+ of \d+ [^\n]*---", printed)[1:]

    assert len(messages) == 2, f"expected one brief per league, got {len(messages)}"
    for message in messages:
        basketball = "Doncic" in message or "Celtics" in message
        football = "Mahomes" in message or "Packers" in message
        assert basketball != football, f"a brief mixed the two sports:\n{message}"


def test_each_league_records_its_own_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-26: the label reached `record_batch` but never reached `main`.

    The edit that was supposed to pass the league through silently failed to apply, and two
    runs recorded `label=None` before anyone looked at a filename. Nothing failed, because
    the filenames were seconds apart and neither overwrote the other, and no test drove
    `main` as far as the evidence directory. TASKS.md P36 is the standing version of this.
    """
    import main

    evidence = tmp_path / "evidence"
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "labels.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(evidence))
    monkeypatch.setattr(
        main,
        "fetch_news",
        lambda feeds: (
            [
                _fresh("Doncic drops 40 on the Clippers", source="ESPN", league="NBA"),
                _fresh("Mahomes signs an extension", source="ESPN NFL", league="NFL"),
            ],
            [],
        ),
    )

    assert main.main(["--dry-run", "--no-summary"]) == 0
    capsys.readouterr()

    recorded = sorted(path.name for path in evidence.glob("*.json"))

    assert len(recorded) == 2, f"one batch per league, got {recorded}"
    assert any(name.endswith("-nba.json") for name in recorded), recorded
    assert any(name.endswith("-nfl.json") for name in recorded), recorded


def test_the_model_is_released_even_when_summarising_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-27, written because a mutation demanded it.

    Turning the `finally` in `main` into an `else` left all 487 tests green: nothing drove
    `main` far enough to notice that a summarizer which raised was never asked to hand its
    memory back. That is the worst case for holding a 4.4 GB model on a machine with 5.3 GB
    free, because the run that failed is the one still holding it. TASKS.md P36.
    """
    import main
    from processing.summarize import OllamaSummarizer

    released: list[str] = []

    class Exploding(OllamaSummarizer):
        def summarise(self, *args: object, **kwargs: object) -> str | None:
            raise RuntimeError("ollama fell over mid-brief")

        def release(self) -> None:
            released.append(self._model)

    # One model, so `main` takes the plain branch rather than building a ladder.
    monkeypatch.setenv("OLLAMA_MODEL", "mistral:7b")
    monkeypatch.setenv("OLLAMA_FIRST_MODEL", "mistral:7b")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "release.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "OllamaSummarizer", Exploding)
    monkeypatch.setattr(
        main,
        "fetch_news",
        lambda feeds: ([_fresh("Doncic drops 40 on the Clippers", source="ESPN")], []),
    )

    with pytest.raises(RuntimeError):
        main.main(["--dry-run"])
    capsys.readouterr()

    assert released == ["mistral:7b"], (
        "a summarizer that raised is exactly the one still holding the model"
    )


# --- P58: a machine that sleeps through its own schedule ------------------------------------


def test_nothing_delivered_yet_reports_no_gap(store: SeenStore) -> None:
    """`[INFERRED]` A fresh install has never delivered, which is not a gap of zero hours.

    None and 0.0 would send `brief_is_due` opposite ways, so the distinction is the whole
    point: a first run is always due.
    """
    assert store.hours_since_last_delivery() is None


def test_the_gap_is_measured_from_the_last_delivery(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[VERIFIED]` 2026-08-27: the real store read 16.5 hours after both runs were slept
    through, against a configured interval of 8.
    """
    store.record_articles([make_article("Doncic drops 40")])
    store._connection.execute(
        "UPDATE seen_articles SET seen_at = ?",
        ((datetime.now(timezone.utc) - timedelta(hours=9)).isoformat(),),
    )
    store._connection.commit()

    gap = store.hours_since_last_delivery()

    assert gap is not None
    assert 8.9 < gap < 9.1, gap


def test_a_dry_run_does_not_look_like_a_delivery(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[INFERRED]` The gap is read from `seen_articles`, written only after a send succeeds.

    If a dry run counted, inspecting the pipeline would postpone the next real brief, which is
    the same class of mistake as P39 where a dry run purged the store.
    """
    store.record_fetched([make_article("Doncic drops 40")])

    assert store.hours_since_last_delivery() is None, (
        "polling is not delivering; only a successful send counts"
    )


def test_a_clock_that_went_backwards_does_not_shrink_the_brief(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[INFERRED]` A negative gap would size the brief below its own interval.

    Worth guarding rather than assuming: this machine suspends and resumes constantly, which
    is exactly where clocks jump.
    """
    store.record_articles([make_article("Doncic drops 40")])
    store._connection.execute(
        "UPDATE seen_articles SET seen_at = ?",
        ((datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),),
    )
    store._connection.commit()

    assert store.hours_since_last_delivery() == 0.0


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (None, True),
        (0.0, False),
        (7.0, False),
        (7.95, True),
        (8.0, True),
        (16.5, True),
    ],
)
def test_whether_a_brief_is_due(elapsed: float | None, expected: bool) -> None:
    """`[VERIFIED]` 7.95 is the tolerance case and it is why the tolerance exists.

    A trigger running every half hour measures each brief from the previous delivery, so
    without slack the eight hour brief lands at 8h00, then 8h20, then 8h40, drifting later
    every cycle. Five minutes early stops that and is smaller than any offered interval.
    """
    import main

    assert main.brief_is_due(elapsed, 8) is expected


def test_a_run_that_is_not_due_touches_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-27: cron slept through both slots and no brief arrived all day.

    `--if-due` exists so the scheduler can run often and this program decides, which means the
    cheap path has to be genuinely cheap. Asserted by making `fetch_news` fail the test if it
    is called at all: a wake-up that is not due must not touch a single source.
    """
    import main

    path = tmp_path / "due.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))

    with SeenStore(path) as store:
        store.record_articles([_fresh("Doncic drops 40 on the Clippers")])

    def must_not_run(feeds: object) -> None:
        raise AssertionError("a run that is not due must not contact any source")

    monkeypatch.setattr(main, "fetch_news", must_not_run)

    assert main.main(["--if-due", "--dry-run", "--no-summary"]) == 0


def test_a_brief_after_a_missed_run_is_allowed_to_be_longer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-27: the gap was 16.5 hours and the brief was sized for 8.

    Everything past the story cap is recorded as delivered whether or not it was shown, so
    the surplus is not held over for next time, it is gone. A brief covering twice its usual
    period therefore has to be allowed to carry more, or sleeping through a run silently costs
    the reader stories. TASKS.md P36: this is wiring in `main`, invisible to every unit below.
    """
    import main

    path = tmp_path / "long.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))

    # Delivered a day ago, so the next brief covers 24 hours rather than the configured 8.
    with SeenStore(path) as store:
        store.record_articles([_fresh("An old story already sent")])
        store._connection.execute(
            "UPDATE seen_articles SET seen_at = ?",
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
        )
        store._connection.commit()

    # Unrelated on purpose. `[VERIFIED]` Titles sharing a phrase cluster into one story, so
    # a first attempt at this test showed exactly 1 and proved nothing about the cap.
    subjects = [
        "Warriors sign Niang",
        "Pelicans reach deal with Mathurin",
        "Curry extension talks open",
        "Kuminga joins the Wolves",
        "Bucks waive a camp guard",
        "Heat trade for a wing",
        "Knicks hire an assistant",
        "Nuggets pick up an option",
        "Spurs recall a rookie",
        "Magic extend their centre",
        "Kings part with a forward",
        "Suns add a shooter",
        "Raptors promote a coach",
        "Jazz claim a guard",
        "Hornets release a veteran",
        "Pacers sign a big",
        "Pistons agree a buyout",
        "Wizards add depth",
        "Blazers move a pick",
        "Grizzlies convert a contract",
    ]
    many = [
        _fresh(title, source=f"Source {index}") for index, title in enumerate(subjects)
    ]
    monkeypatch.setattr(main, "fetch_news", lambda feeds: (many, []))

    assert main.main(["--dry-run", "--no-summary"]) == 0
    printed = capsys.readouterr().out

    shown = sum(1 for subject in subjects if subject in printed)
    at_eight_hours, _ = brief_size_for(8)

    assert shown > at_eight_hours, (
        f"a 24 hour brief showed {shown} stories, no more than the {at_eight_hours} "
        "allowed for 8 hours, so the missed run cost the reader news"
    )


# --- P36: wiring in main that no test reached ------------------------------------------------


def test_main_builds_the_model_ladder_when_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-27: measured reach of `main.py` was 82.1%, and this branch was in
    the missing 17.9% on the day it was written.

    Deleting the whole `elif settings.escalates_model` arm left 533 tests green, so nothing
    checked that the small model is ever chosen first. That is P36's pattern exactly: the
    decision sits inline in `main`, where the units below it cannot see it.
    """
    import main

    built: list[tuple[str, str]] = []

    class FakeLadder:
        def __init__(self, first: object, then: object) -> None:
            built.append((getattr(first, "model", "?"), getattr(then, "model", "?")))

        def summarise(self, *args: object, **kwargs: object) -> str | None:
            return None

        def release(self) -> None:
            return None

        @property
        def summarizer_name(self) -> str:
            return "fake ladder"

    class FakeOllama:
        def __init__(self, model: str) -> None:
            self.model = model

    # Cleared explicitly. `[VERIFIED]` 2026-08-27 this test broke the moment the operator put
    # a real OpenRouter key in `.env`, because `Settings.from_env` reads that file and a
    # hosted key changes which summarizer `main` builds. A test that passes or fails on the
    # contents of one machine's `.env` is the P37 fault in a new place.
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OLLAMA_FIRST_MODEL", "llama3.2:3b")
    monkeypatch.setenv("OLLAMA_MODEL", "mistral:7b")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "ladder.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "EscalatingSummarizer", FakeLadder)
    monkeypatch.setattr(main, "OllamaSummarizer", FakeOllama)
    monkeypatch.setattr(
        main,
        "fetch_news",
        lambda feeds: ([_fresh("Doncic drops 40 on the Clippers")], []),
    )

    assert main.main(["--dry-run"]) == 0
    capsys.readouterr()

    assert built == [("llama3.2:3b", "mistral:7b")], (
        f"the small model must be tried first and the capable one second, got {built}"
    )


def test_main_checks_the_accepted_summary_for_unsupported_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-27: this call was also in the unreached 17.9% of `main.py`.

    It is the check that flagged both errors the operator found by reading a delivered brief,
    one sentence in each of two briefs, and it is what `--audit` reads back. Deleting the call
    left the suite green, so nothing noticed if the pipeline simply stopped looking.

    Asserted on the recorded evidence rather than the log, because that is where the result is
    kept and where anything downstream reads it from.
    """
    import main
    from storage.evidence import load_batch

    evidence = tmp_path / "evidence"
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "claims.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(evidence))
    monkeypatch.setenv("OLLAMA_FIRST_MODEL", "one-model")
    monkeypatch.setenv("OLLAMA_MODEL", "one-model")

    class Summarizer:
        def __init__(self, model: str) -> None:
            self.model = model

        @property
        def summarizer_name(self) -> str:
            return "stub"

        def release(self) -> None:
            return None

        def summarise(self, *args: object, **kwargs: object) -> str:
            # Both names are in the batch, but never in the same article, which is exactly
            # the shape the pair check exists to notice. Full names on purpose: the check
            # treats a lone capitalised word as no entity at all, which a first draft of this
            # test did not know and discovered by failing.
            return "Luka Doncic and Patrick Mahomes met on Tuesday."

    monkeypatch.setattr(main, "OllamaSummarizer", Summarizer)
    monkeypatch.setattr(
        main,
        "fetch_news",
        lambda feeds: (
            [
                _fresh("Luka Doncic drops 40 on the Clippers", source="ESPN"),
                _fresh("Patrick Mahomes signs an extension", source="CBS Sports"),
            ],
            [],
        ),
    )

    assert main.main(["--dry-run"]) == 0
    capsys.readouterr()

    recorded = sorted(evidence.glob("*.json"))
    assert recorded, "the run should have recorded a batch"
    payload = json.loads(recorded[0].read_text())

    assert payload["unsupported_claims"], (
        "a sentence whose names never share an article must be recorded as unsupported"
    )
    assert load_batch(recorded[0]), "the batch must still round trip"


def test_a_hosted_key_still_falls_back_to_the_local_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_upstream_games: None,
) -> None:
    """`[VERIFIED]` 2026-08-27: the operator set an OpenRouter key and every call returned 429.

    The free model shares an upstream pool at the provider and that pool was throttled, which
    has nothing to do with the key. Before this, configuring a hosted model meant hosted
    *instead of* local, so a throttled pool delivered a headline list while a working local
    model sat idle on the same machine.

    `[INFERRED]` Falling back to a worse model beats falling back to no prose, and the brief
    the operator asked never to see again is the headline list.
    """
    import main

    chain: list[str] = []

    class Recorder:
        def __init__(self, *args: object, **kwargs: object) -> None:
            chain.append(type(self).__name__)

    class FakeHosted(Recorder):
        pass

    class FakeLocal(Recorder):
        def __init__(self, model: str) -> None:
            super().__init__()
            self.model = model

    built: list[tuple[object, object]] = []

    class FakeLadder:
        def __init__(
            self, first: object, then: object, first_attempts: int = 2
        ) -> None:
            built.append((first, then))

        @property
        def summarizer_name(self) -> str:
            return "ladder"

        def release(self) -> None:
            return None

        def summarise(self, *args: object, **kwargs: object) -> str | None:
            return None

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "hosted.db"))
    monkeypatch.setenv("EVIDENCE_PATH", str(tmp_path / "evidence"))
    monkeypatch.setattr(main, "OpenRouterSummarizer", FakeHosted)
    monkeypatch.setattr(main, "OllamaSummarizer", FakeLocal)
    monkeypatch.setattr(main, "EscalatingSummarizer", FakeLadder)
    monkeypatch.setattr(
        main,
        "fetch_news",
        lambda feeds: ([_fresh("Doncic drops 40 on the Clippers")], []),
    )

    assert main.main(["--dry-run"]) == 0
    capsys.readouterr()

    # The outermost ladder is built last, and it is the one that decides what happens when
    # the hosted call fails.
    outer_first, outer_then = built[-1]
    assert isinstance(outer_first, FakeHosted), "the hosted model should be tried first"
    assert not isinstance(outer_then, FakeHosted), (
        "the fallback must be something other than the hosted model that just failed"
    )


def test_the_poll_store_forgets_what_nothing_reads(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[VERIFIED]` 2026-08-28: `fetched_articles` had no purge at all and grew forever.

    `seen_articles` got one the day it existed. The poll store, added later by ADR-014, never
    did, so it held the full title and description of every article ever fetched.

    Backdated directly, because `fetched_at` is set by the store rather than passed in: it
    records when *this process* saw the item, which is the whole point of the column.
    """
    store.record_fetched([make_article("An article polled long ago")])
    store._connection.execute(
        "UPDATE fetched_articles SET fetched_at = ?", ("2020-01-01T00:00:00+00:00",)
    )
    store._connection.commit()

    assert store.purge_fetched_before(168) == 1
    assert store.fetched_since(hours=24 * 365 * 100) == []


def test_the_purge_keeps_what_the_window_still_covers(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The half that matters: a purge cutting inside a reader's window loses live news.

    `[INFERRED]` `fetched_since` is called with the dedup window and `arrivals_per_hour`
    defaults to 168 hours, so a row inside those has to survive. This is the same failure
    `purge_delivered_before` warns about, where too short a window made delivered stories look
    new again on every run.
    """
    store.record_fetched([make_article("An article polled just now")])

    assert store.purge_fetched_before(168) == 0
    assert len(store.fetched_since(hours=1)) == 1


# --- the story memory behind P68 ----------------------------------------------------------


def test_a_delivered_story_is_remembered_by_its_names(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[VERIFIED]` 2026-09-04 (P68): nothing held a story identity across runs, so the NBA's
    ruling against the Clippers was delivered in four consecutive briefs.

    Names rather than a hash, because the rule that decides "same story" counts how many names
    two articles share, and a hash cannot answer that.
    """
    article = make_article("Clippers docked five first-round picks over Kawhi Leonard")

    store.record_story_names([article])
    remembered = store.story_names_since(24)

    assert len(remembered) == 1
    assert "Clippers" in remembered[0]


def test_one_league_cannot_suppress_another(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """`[INFERRED]` The briefs are split by league (ADR-015) and the story memory has to be
    too, or a basketball story silences a football one that happens to share a city name."""
    store.record_story_names(
        [make_article("Clippers docked five picks over Kawhi Leonard", league="NBA")]
    )

    assert store.story_names_since(24, league="NBA") != []
    assert store.story_names_since(24, league="NFL") == []


def test_a_story_outside_the_window_is_not_returned(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """The window is the whole trade-off: too long and a story that genuinely returns with
    news is silenced. Asked for zero hours, nothing delivered a moment ago can qualify."""
    store.record_story_names([make_article("Clippers docked five first-round picks")])

    assert store.story_names_since(0) == []


def test_names_are_grouped_per_story_not_pooled(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """Two stories must come back as two sets.

    `[INFERRED]` Pooled into one, any article sharing one name with each of two unrelated
    stories would look like a retelling of a story nobody ever published.
    """
    store.record_story_names(
        [
            make_article("Clippers docked five picks over Kawhi Leonard"),
            make_article("Rockets extend Amen Thompson through 2032"),
        ]
    )

    remembered = store.story_names_since(24)

    assert len(remembered) == 2, remembered


def test_the_story_memory_is_purged(
    store: SeenStore, make_article: ArticleFactory
) -> None:
    """Same reason as P65: nothing reads a row past the window, and a table that only grows
    is awkward once someone has a real database."""
    store.record_story_names([make_article("Clippers docked five first-round picks")])

    removed = store.purge_story_names_before(0)

    assert removed > 0
    assert store.story_names_since(24) == []
