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
from datetime import datetime, timezone
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
        """Mark game states as delivered. Returns how many were newly recorded."""
        now = _utc_now()
        cursor = self._connection.executemany(
            "INSERT OR IGNORE INTO seen_games (state_hash, game_id, seen_at) VALUES (?, ?, ?)",
            [(game.state_hash, game.game_id, now) for game in games],
        )
        self._connection.commit()
        return cursor.rowcount


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string. SQLite has no native datetime type."""
    return datetime.now(timezone.utc).isoformat()
