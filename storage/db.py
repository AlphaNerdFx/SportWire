"""Remembers what has already been delivered, so dedup survives the process exiting.

`sqlite3` from the standard library — no ORM, no migrations, no server (ADR-004). The
database is a single file that appears on first run; nothing to install, which is what
keeps the repo clonable by anyone.

Only identifiers are stored, never article text or scores. The store answers exactly one
question — "have I sent this already?" — and storing more than that would invite this
module to grow into a second source of truth about content.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.schemas import GameData, NewsArticle

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_articles (
    article_id TEXT PRIMARY KEY,
    seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_games (
    state_hash TEXT PRIMARY KEY,
    game_id    INTEGER NOT NULL,
    seen_at    TEXT NOT NULL
);

-- Final results, one row per game, for deriving head-to-head records locally.
--
-- This is the one place the store keeps content rather than identifiers, and the exception
-- is deliberate. `[VERIFIED]` 2026-08-08: asking balldontlie for a season series costs one
-- request per fixture and its free tier returns 429 from about the sixth, so a nine-game
-- slate got context for four. Every result needed is already passing through this process;
-- writing it down turns a rate-limited network call into a local query.
--
-- Keyed by game_id rather than state_hash: a game has many states but one final result, and
-- INSERT OR REPLACE lets a later state correct an earlier one.
CREATE TABLE IF NOT EXISTS game_results (
    game_id    INTEGER PRIMARY KEY,
    played_on  TEXT    NOT NULL,
    home_team  TEXT    NOT NULL,
    away_team  TEXT    NOT NULL,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    status     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_results_teams ON game_results (home_team, away_team);
"""


class SeenStore:
    """Tracks which articles and game states have already been delivered.

    Rows are kept indefinitely rather than pruned to a rolling window. `[INFERRED]` A few
    hundred short identifiers a day is nothing to SQLite, and a window would silently
    re-send an item that reappears after it expires — ESPN's feed reaches back roughly
    three days, so a 48-hour window would do exactly that.
    """

    def __init__(self, database_path: str | Path = "sportwire.db") -> None:
        self._path = Path(database_path)
        self._connection = sqlite3.connect(self._path)
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        self._connection.close()

    # `typing.Self` would be the idiomatic return type, but it landed in Python 3.11 and
    # this project targets 3.10 (constraint C1). The string annotation is equivalent here.
    def __enter__(self) -> SeenStore:  # noqa: PYI034
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def seen_article_ids(self) -> set[str]:
        """Every article id delivered in a previous run."""
        rows = self._connection.execute("SELECT article_id FROM seen_articles")
        return {row[0] for row in rows}

    def seen_game_hashes(self) -> set[str]:
        """Every game state hash delivered in a previous run."""
        rows = self._connection.execute("SELECT state_hash FROM seen_games")
        return {row[0] for row in rows}

    def record_articles(self, articles: Iterable[NewsArticle]) -> int:
        """Mark articles as delivered. Returns how many were newly recorded.

        `INSERT OR IGNORE` makes this safe to call twice with overlapping input — re-running
        after a partial failure must not raise.
        """
        now = _utc_now()
        cursor = self._connection.executemany(
            "INSERT OR IGNORE INTO seen_articles (article_id, seen_at) VALUES (?, ?)",
            [(article.article_id, now) for article in articles],
        )
        self._connection.commit()
        return cursor.rowcount

    def record_games(self, games: Iterable[GameData]) -> int:
        """Mark game states as delivered, and record final results for series history.

        Returns how many game *states* were newly recorded. Results are written separately
        and idempotently, so the count reflects deduplication rather than storage.
        """
        games = list(games)
        now = _utc_now()

        cursor = self._connection.executemany(
            "INSERT OR IGNORE INTO seen_games (state_hash, game_id, seen_at) VALUES (?, ?, ?)",
            [(game.state_hash, game.game_id, now) for game in games],
        )

        # Only completed games. `[INFERRED]` A game in progress has a score that will change,
        # and a head-to-head record built from half-time scores would be wrong in a way
        # nobody would think to check.
        finished = [game for game in games if _is_final(game)]
        self._connection.executemany(
            """
            INSERT OR REPLACE INTO game_results
                (game_id, played_on, home_team, away_team, home_score, away_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    game.game_id,
                    game.start_time.date().isoformat(),
                    game.home_team,
                    game.away_team,
                    game.home_score,
                    game.away_score,
                    game.status,
                )
                for game in finished
            ],
        )

        self._connection.commit()
        return cursor.rowcount

    def purge_delivered_before(self, hours: int) -> int:
        """Forget articles delivered more than `hours` ago. Returns how many rows went.

        **The caller decides the window, and getting it wrong re-sends stories**, so read
        `main.py` before changing anything here. `[VERIFIED]` GitHub issue #10: feeds list
        items for days, so a window shorter than an item's stay in the feed makes it look
        new again on every run. An 8-hour window left 3 of 17 ESPN items older than the
        window but still being published, re-delivered every cycle.

        Only `seen_articles` is purged. `[INFERRED]` `seen_games` is nine rows and bounded by
        the fixture list, and `game_results` is the series history that `head_to_head` reads,
        which is meant to accumulate — deleting it would make the brief worse over time
        rather than better.
        """
        cursor = self._connection.execute(
            "DELETE FROM seen_articles WHERE seen_at < ?",
            ((datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(),),
        )
        self._connection.commit()
        return cursor.rowcount

    def head_to_head(self, game: GameData) -> tuple[int, int, int]:
        """Prior meetings between this game's teams: `(home_wins, away_wins, meetings)`.

        Counts only games recorded **before** this one, so the result describes how the
        series stood beforehand rather than including tonight.

        `[INFERRED]` Wins are attributed by team name, matched in either home/away
        arrangement — the same fixture at the other venue is still the same rivalry. Names
        are the pipeline's vocabulary; team ids belong to whichever provider issued them.

        Returns zeros when nothing is known, which is the honest answer for a season this
        instance has not been running through. Unlike the API-based version this cannot be
        rate-limited, and it improves the longer SportWire runs.
        """
        rows = self._connection.execute(
            """
            SELECT home_team, away_team, home_score, away_score
            FROM game_results
            WHERE game_id != ?
              AND played_on < ?
              AND ((home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?))
            """,
            (
                game.game_id,
                game.start_time.date().isoformat(),
                game.home_team,
                game.away_team,
                game.away_team,
                game.home_team,
            ),
        ).fetchall()

        home_wins = away_wins = 0
        for row_home, _row_away, row_home_score, row_away_score in rows:
            winner = (
                row_home if row_home_score > row_away_score else _other(row_home, game)
            )
            if winner == game.home_team:
                home_wins += 1
            else:
                away_wins += 1

        return home_wins, away_wins, len(rows)


def _is_final(game: GameData) -> bool:
    """Whether a game has finished, so its score will not change again.

    `[VERIFIED]` balldontlie reports "Final" for completed games. `[UNKNOWN]` what an
    in-progress game reports — the offseason has meant none was ever observed — so this
    matches on the one value that has been seen rather than trying to exclude the ones that
    have not.
    """
    return game.status.strip().lower().startswith("final")


def _other(team: str, game: GameData) -> str:
    """Given one team in a fixture, the other one."""
    return game.away_team if team == game.home_team else game.home_team


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string. SQLite has no native datetime type."""
    return datetime.now(timezone.utc).isoformat()
