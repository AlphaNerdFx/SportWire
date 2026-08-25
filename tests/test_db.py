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
from datetime import timedelta
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
