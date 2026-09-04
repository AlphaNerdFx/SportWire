"""Remembers what has already been delivered, so dedup survives the process exiting.

`sqlite3` from the standard library — no ORM, no migrations, no server (ADR-004). The
database is a single file that appears on first run; nothing to install, which is what
keeps the repo clonable by anyone.

~~Only identifiers are stored, never article text or scores. The store answers exactly one
question — "have I sent this already?" — and storing more than that would invite this
module to grow into a second source of truth about content.~~

**Amended 2026-08-26 by ADR-014, which said this sentence would be amended rather than quietly
left standing.** The store now answers two questions: *"have I sent this already?"* and *"what
has been fetched recently?"*

`[VERIFIED]` The second exists so that fetching and delivering can run at different rates. Under
the obvious design a brief triggers a fetch, so upstream requests scale with how often people
want news — and `ingestion/rss_news.py` has recorded since 2026-08-09 that Reddit returns 429 to
three requests in two seconds. Holding what was fetched turns "ask again" into a local query.

`[VERIFIED]` The precedent was already here: `game_results` keeps content for exactly this
reason, eight days earlier, because asking balldontlie for a season series costs one request per
fixture and its free tier 429s from about the sixth.

`[INFERRED]` The risk the original sentence guards against is duplication of *truth*, two
modules disagreeing about what an article is. That is contained by `CLAUDE.md` §5 rule 2:
`models/schemas.py` stays the only definition of `NewsArticle`, and this module persists and
returns **that** type rather than inventing a row shape the pipeline has to learn.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.schemas import GameData, NewsArticle
from processing.cluster import story_names

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_articles (
    article_id TEXT PRIMARY KEY,
    seen_at    TEXT NOT NULL
);

-- The names a delivered story was about, one row per name, so a later article retelling it
-- can be recognised (P68). `[VERIFIED]` 2026-09-04: dedup matched an article id and nothing
-- held a story identity across runs, so the NBA's ruling against the Clippers arrived in four
-- consecutive briefs.
--
-- Names rather than a hashed key, because the rule that decides "same story" is a *shared
-- name count* (`processing/cluster.py`), and a hash cannot answer "how many do these share".
-- The same shape also answers the question the operator's exception needs: whether the new
-- article names anyone who was not delivered with the story before.
--
-- `league` is stored so one sport's stories can never suppress another's.
CREATE TABLE IF NOT EXISTS delivered_story_names (
    article_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    league       TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    PRIMARY KEY (article_id, name)
);

CREATE INDEX IF NOT EXISTS delivered_story_names_at
    ON delivered_story_names (delivered_at);

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

-- Articles as fetched, so a brief can be assembled without going back upstream (ADR-014).
--
-- This is the second place the store keeps content, and the first was `game_results` above
-- for the same reason: a rate-limited network call becomes a local query.
--
-- `fetched_at` is when this process saw the article, which is deliberately not
-- `published_at`. A brief covers "what arrived since the last one", and an outlet backdating
-- or an item appearing late in a feed should not move it outside that window.
CREATE TABLE IF NOT EXISTS fetched_articles (
    article_id   TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    summary      TEXT NOT NULL,
    source       TEXT NOT NULL,
    author       TEXT,
    published_at TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    league       TEXT NOT NULL DEFAULT 'NBA'
);

CREATE INDEX IF NOT EXISTS idx_fetched_at ON fetched_articles (fetched_at);
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
        _add_missing_columns(self._connection)
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

    def record_story_names(self, articles: Iterable[NewsArticle]) -> int:
        """Remember what each delivered story was about. Returns rows newly written.

        Called beside `record_articles` and for the same reason: only after a send succeeds,
        so a failed delivery cannot make tomorrow's brief think the story was already told.

        `INSERT OR IGNORE` on the same key pair, so re-running after a partial failure is safe.
        """
        now = _utc_now()
        rows = [
            (article.article_id, name, article.league, now)
            for article in articles
            for name in story_names(article)
        ]
        cursor = self._connection.executemany(
            "INSERT OR IGNORE INTO delivered_story_names"
            " (article_id, name, league, delivered_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        self._connection.commit()
        return cursor.rowcount

    def story_names_since(
        self, hours: float, league: str | None = None
    ) -> list[frozenset[str]]:
        """One set of names per story delivered in the last `hours`, newest first.

        Grouped by `article_id`, because the caller compares *sets*: a story is being retold
        when the new article shares enough names with one delivered story, not when it shares
        one name each with several.
        """
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        clause = "" if league is None else " AND league = ?"
        parameters: tuple[str, ...] = (since,) if league is None else (since, league)
        rows = self._connection.execute(
            "SELECT article_id, name FROM delivered_story_names"
            f" WHERE delivered_at >= ?{clause}"
            " ORDER BY delivered_at DESC",
            parameters,
        )
        by_article: dict[str, set[str]] = {}
        for article_id, name in rows:
            by_article.setdefault(article_id, set()).add(name)
        return [frozenset(names) for names in by_article.values()]

    def purge_story_names_before(self, hours: float) -> int:
        """Forget stories older than the window. Returns rows removed.

        Same reason as the other purges (P65): nothing reads a row past the window, and a
        table that only grows is awkward once someone has a real database.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        cursor = self._connection.execute(
            "DELETE FROM delivered_story_names WHERE delivered_at < ?", (cutoff,)
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

    def record_fetched(self, articles: Iterable[NewsArticle]) -> int:
        """Keep what a poll found. Returns how many were newly stored (ADR-014).

        `INSERT OR IGNORE`, so an article seen in two consecutive polls keeps its **first**
        `fetched_at`. `[INFERRED]` That is the behaviour a window query needs: feeds list an
        item for days, and refreshing the timestamp on every poll would make a week-old story
        look new forever and never leave the window.

        Separate from `record_articles`, which marks something **delivered**. One says "this
        exists", the other says "the operator has seen it", and collapsing them would make a
        fetched-but-not-yet-sent article indistinguishable from a sent one.
        """
        now = _utc_now()
        cursor = self._connection.executemany(
            """
            INSERT OR IGNORE INTO fetched_articles
                (article_id, title, url, summary, source, author, published_at,
                 fetched_at, league)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    article.article_id,
                    article.title,
                    article.url,
                    article.summary,
                    article.source,
                    article.author,
                    article.published_at.isoformat(),
                    now,
                    article.league,
                )
                for article in articles
            ],
        )
        self._connection.commit()
        return cursor.rowcount

    def fetched_since(
        self, hours: float, league: str | None = None
    ) -> list[NewsArticle]:
        """Everything fetched in the last `hours`, newest first, as real articles.

        Pass `league` to get one league's batch. That is the whole mechanism behind ADR-015:
        a brief is built from a batch that only ever contained one sport, so nothing
        downstream has to tell the sports apart, and the summarizer cannot blend them
        because it never sees both. Leaving it `None` returns everything, which is what a
        single-league install wants and what every caller did before NFL existed.

        This is the read half of ADR-014: a brief assembles from here and sends nothing
        upstream, so how often briefs are wanted stops driving how often sources are asked.

        Returns `NewsArticle` rather than rows, so nothing above this line learns a database
        shape. `[VERIFIED]` `CLAUDE.md` §5 rule 2 and the legacy repository's four competing
        article definitions are why that matters more than the convenience.
        """
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        clause = "" if league is None else " AND league = ?"
        parameters: tuple[str, ...] = (since,) if league is None else (since, league)
        rows = self._connection.execute(
            f"""
            SELECT article_id, title, url, summary, source, author, published_at, league
            FROM fetched_articles
            WHERE fetched_at >= ?{clause}
            ORDER BY fetched_at DESC, article_id
            """,
            parameters,
        ).fetchall()
        return [
            NewsArticle(
                article_id=row[0],
                title=row[1],
                url=row[2],
                summary=row[3],
                source=row[4],
                author=row[5],
                published_at=datetime.fromisoformat(row[6]),
                league=row[7],
            )
            for row in rows
        ]

    def hours_since_last_delivery(self) -> float | None:
        """How long since anything was last recorded as delivered, or None if nothing ever was.

        `[VERIFIED]` 2026-08-27, and the operator confirmed the cause: *"pc was idle so no
        message"*. The 08:00 run never fired because WSL2 was suspended with the machine, and
        cron cannot run a job it slept through. That makes a missed run a normal condition
        here rather than an incident.

        It matters because the brief is sized from the *configured* interval. After an eleven
        hour gap the 11:02 run still showed twelve stories, the number chosen for eight hours,
        and everything past the cap is recorded as delivered whether or not it was shown. So a
        night of sleep quietly costs a handful of stories that never appear anywhere.

        Read from `seen_articles`, because that table is written only after a send succeeds.
        `[INFERRED]` A dry run therefore leaves it untouched, which is right: nothing reached
        the reader, so nothing was delivered.
        """
        row = self._connection.execute(
            "SELECT MAX(seen_at) FROM seen_articles"
        ).fetchone()
        if not row or not row[0]:
            return None
        delivered = datetime.fromisoformat(row[0])
        gap = (datetime.now(timezone.utc) - delivered).total_seconds() / 3600.0
        # A clock that has gone backwards should not shrink the brief.
        return max(0.0, gap)

    def arrivals_per_hour(self, over_hours: float = 168.0) -> float:
        """How fast news has actually been arriving, from what polling has recorded.

        This is what a bounded interval choice should be built on rather than a guess
        (PRD D6, TASKS.md P42). The operator's requirement is a set of intervals decided by
        how frequent news is, and `fetched_articles` is the only record of that which does not
        depend on anybody remembering to measure.

        Measured over the span actually observed, not over `over_hours`, so a store holding
        two days of history reports the rate for two days rather than diluting it across a
        week of zeros. Returns 0.0 when there is not enough history to say anything.

        `[INFERRED]` Arrivals rather than publications, deliberately, matching `fetched_at`
        elsewhere in this table: what matters for choosing an interval is how often something
        *new reaches this process*, which is what a brief covers. An outlet backdating an
        item does not change how often the operator has something to read.
        """
        since = (datetime.now(timezone.utc) - timedelta(hours=over_hours)).isoformat()
        row = self._connection.execute(
            """
            SELECT COUNT(*), MIN(fetched_at), MAX(fetched_at)
            FROM fetched_articles
            WHERE fetched_at >= ?
            """,
            (since,),
        ).fetchone()

        count, first, last = row
        if not count:
            return 0.0

        # ~~Also guarded on `first is None or first == last`.~~ **Removed 2026-08-26 before it
        # shipped, on the P6 rule.** `[VERIFIED]` A mutation deleting both left the whole suite
        # green, and neither can fire: `fetched_at` is `NOT NULL`, so `first` is None only when
        # the count is zero, and a single row makes `first == last`, which the `span <= 0`
        # guard two lines below already catches. Restore them if `fetched_at` ever becomes
        # nullable.
        span = (
            datetime.fromisoformat(last) - datetime.fromisoformat(first)
        ).total_seconds() / 3600
        if span <= 0:
            return 0.0
        return count / span

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

    def purge_fetched_before(self, hours: int) -> int:
        """Forget polled articles older than `hours`. Returns how many rows went.

        `[VERIFIED]` 2026-08-28: nothing purged this table. `seen_articles` had a purge from
        the day it existed and `fetched_articles`, added later by ADR-014, never got one, so
        the poll store held the full title and description of every article ever fetched and
        grew for as long as the program ran.

        `[INFERRED]` Nothing reads a row this old. Both readers take a window: `fetched_since`
        is called with the dedup window, and `arrivals_per_hour` defaults to 168 hours. A row
        older than the larger of those is dead weight that is still written, indexed and
        backed up.

        **The caller decides the window and must not cut inside a reader's.** `forget_window`
        already computes a value that is never below `MAX_ARTICLE_AGE_HOURS`, which is what
        `main` passes here, and that is comfortably outside both.

        `[INFERRED]` Kept separate from `purge_delivered_before` rather than folded into it.
        The two tables answer different questions, "have I sent this" and "what did I see",
        and a single purge would tie two windows together that have no reason to move
        together.
        """
        cursor = self._connection.execute(
            "DELETE FROM fetched_articles WHERE fetched_at < ?",
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


def _add_missing_columns(connection: sqlite3.Connection) -> None:
    """Add columns to tables that already exist. **This is a migration, small as it is.**

    `[VERIFIED]` ADR-014 claimed no migration was needed and was right about the case it
    described: `CREATE TABLE IF NOT EXISTS` creates a *new* table on the next connect and
    leaves existing rows alone. It also said the exception out loud — "a migration is only
    needed when a table that already exists has to change shape" — and adding `league` to
    `fetched_articles` is exactly that. The schema statement above cannot do it, because the
    table already exists and `IF NOT EXISTS` makes the whole statement a no-op.

    `[VERIFIED]` `TASKS.md` L4 defers Alembic until "a schema change against a table with real
    rows". That trigger has **not** fired: `fetched_articles` was created on 2026-08-26 and
    held 0 rows when this was written, because no scheduled poll had run against it yet. A
    hand-written `ALTER TABLE` is proportionate; a migration framework for one column would not
    be.

    Idempotent by inspection rather than by exception handling. `[INFERRED]` Catching the
    "duplicate column" error would work and would also swallow a genuine failure, and this runs
    on every single connect.
    """
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(fetched_articles)")
    }
    if columns and "league" not in columns:
        connection.execute(
            "ALTER TABLE fetched_articles ADD COLUMN league TEXT NOT NULL DEFAULT 'NBA'"
        )


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
