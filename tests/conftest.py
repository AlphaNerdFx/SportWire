"""Shared test fixtures. Everything here is loaded from disk — never from the network.

`CLAUDE.md` §8: adapters are tested against saved real payloads, never live sources. A test
that depends on the network fails when ESPN is slow, passes for the wrong reasons when a
feed changes, and cannot run in CI.

`[VERIFIED]` The legacy repo defined its own `NewsArticle` *inside* `conftest.py`, meaning
its one passing test may never have exercised either real schema. Nothing here defines a
model; everything imports from `models.schemas`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ingestion.nba_games import BallDontLieGamesAdapter
from ingestion.rss_news import RssNewsAdapter
from models.schemas import GameData, NewsArticle

FIXTURES = Path(__file__).parent / "fixtures"

# A fixed "now", so "is this too old" is arithmetic rather than a race against the clock.
# August is deliberate: the deleted year rule treated pre-October as the previous season, and
# that off-by-one is exactly what a test pinned to the current date would hide half the year.
NOW = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def now() -> datetime:
    """The fixed "current time" that `make_article` measures article age against.

    Exposed as a fixture rather than imported from this module, so tests do not depend on
    `tests/` happening to be importable — that varies with pytest's rootdir and import mode.
    """
    return NOW


# Every test starts without the operator's own `.env`. `[VERIFIED]` 2026-08-27 this bit twice
# in one hour: adding a real `OPENROUTER_API_KEY` to `.env` changed which summarizer `main`
# builds, and two tests written earlier that day began failing on that machine alone. Neither
# test was wrong about the behaviour it described; both were reading configuration they never
# asked for.
#
# `[INFERRED]` Same family as P37 and P43, where tests depended on the wall clock and on the
# filesystem layout. A suite that passes or fails on what is in one developer's `.env` is not
# testing the code. Autouse so it cannot be forgotten, and cleared *before* the test body, so
# any test that wants a value still sets it with `monkeypatch.setenv` as usual.
_CONFIGURED_BY_ENV = (
    "BALL_DONT_LIE_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DATABASE_PATH",
    "EVIDENCE_PATH",
    "LOG_LEVEL",
    "POLL_INTERVAL_HOURS",
    "DEDUP_WINDOW_HOURS",
    "OLLAMA_MODEL",
    "OLLAMA_FIRST_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
)


@pytest.fixture(autouse=True)
def _without_the_operators_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank every setting `.env` can supply, so no test inherits this machine's setup."""
    for name in _CONFIGURED_BY_ENV:
        monkeypatch.setenv(name, "")


@pytest.fixture
def make_article() -> Callable[..., NewsArticle]:
    """Build a real `NewsArticle`, for tests that need a specific title or summary.

    One factory rather than one per test module. `[VERIFIED]` The legacy repo defined
    `NewsArticle` in four places, one of them inside its own `conftest.py`, and the copies
    drifted silently because Python raises no error when four modules define one class
    (`OPERATING_RULES.md` §5). Two factories with different defaults would drift the same way:
    a test asserting on "recent" articles would quietly mean something different per file.

    Nothing here defines a shape — this constructs `models.schemas.NewsArticle`, so a schema
    change breaks these tests rather than sliding past them.
    """

    def build(
        title: str,
        *,
        summary: str = "",
        hours_old: float = 2.0,
        source: str = "r/nba",
        author: str | None = None,
        league: str = "NBA",
    ) -> NewsArticle:
        return NewsArticle(
            article_id=f"id-{abs(hash((title, summary)))}",
            title=title,
            url="https://example.com/story",
            summary=summary,
            published_at=NOW - timedelta(hours=hours_old),
            source=source,
            author=author,
            league=league,
        )

    return build


@pytest.fixture
def make_game() -> Callable[..., GameData]:
    """Build a real `GameData`. Same one-factory reasoning as `make_article`.

    `start_time` is fixed rather than `now()` so `state_hash` is reproducible across runs —
    the property's whole point is that it changes only when the *game* changes.
    """

    def build(
        home: str = "Los Angeles Lakers",
        away: str = "Golden State Warriors",
        *,
        home_score: int = 110,
        away_score: int = 104,
        status: str = "Final",
        period: int = 4,
        game_id: int | None = None,
        home_periods: list[int] | None = None,
        away_periods: list[int] | None = None,
    ) -> GameData:
        return GameData(
            # Derived from the teams alone, never the score. A game reported at half time
            # and again as final is the *same game* — that is precisely what
            # `test_a_game_whose_score_changed_is_not_a_duplicate` relies on, and what
            # `state_hash` exists to distinguish. Pass `game_id` explicitly if a test needs
            # two distinct games between the same two teams.
            game_id=game_id
            if game_id is not None
            else abs(hash((home, away))) % 100_000,
            start_time=NOW,
            status=status,
            home_team=home,
            away_team=away,
            home_score=home_score,
            away_score=away_score,
            period=period,
            home_periods=home_periods or [],
            away_periods=away_periods or [],
        )

    return build


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --snapshot-update for re-approving intentionally changed output."""
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="overwrite approved snapshots with current output (review the diff first)",
    )


@pytest.fixture
def snapshot_update(request: pytest.FixtureRequest) -> bool:
    """Whether this run should re-approve snapshots rather than assert against them."""
    return bool(request.config.getoption("--snapshot-update"))


@pytest.fixture
def espn_rss_xml() -> str:
    """Raw ESPN RSS captured 2026-08-04: 15 items, 2 of them without an author."""
    return (FIXTURES / "espn_nba_rss.xml").read_text(encoding="utf-8")


@pytest.fixture
def cbs_rss_xml() -> str:
    """Raw CBS Sports RSS, the second feed added and the one that made ADR-005 measurable."""
    return (FIXTURES / "cbs_nba_rss.xml").read_text(encoding="utf-8")


@pytest.fixture
def cbs_articles(cbs_rss_xml: str) -> list[NewsArticle]:
    """CBS articles as the pipeline sees them, for cross-source duplicate measurement."""
    return RssNewsAdapter("CBS Sports").parse(cbs_rss_xml)


@pytest.fixture
def balldontlie_json() -> dict[str, Any]:
    """Raw balldontlie response for 2026-01-15: 9 completed games."""
    return json.loads((FIXTURES / "nba_games.json").read_text(encoding="utf-8"))


@pytest.fixture
def articles(espn_rss_xml: str) -> list[NewsArticle]:
    """The 15 articles as the pipeline sees them, parsed by the real adapter."""
    return RssNewsAdapter("ESPN").parse(espn_rss_xml)


@pytest.fixture
def reddit_articles() -> list[NewsArticle]:
    """The r/nba capture as the pipeline sees it, parsed by the real adapter.

    `[VERIFIED]` This is the fixture that carries camelCase names — `LeBron`, `DeMar
    DeRozan` — which is why `TASKS.md` P13 and P17 both had to be measured against it. Until
    2026-08-15 no test loaded it at all, so the only community feed in the pipeline was
    covered solely by hand-written titles.
    """
    return RssNewsAdapter("r/nba").parse(
        (FIXTURES / "reddit_nba_atom.xml").read_text(encoding="utf-8")
    )


@pytest.fixture
def article_texts(
    articles: list[NewsArticle],
    cbs_articles: list[NewsArticle],
    reddit_articles: list[NewsArticle],
) -> list[str]:
    """Every title and summary the repository has captured, as plain strings.

    For tests that assert two implementations agree over real text rather than over invented
    examples. `[INFERRED]` An extractor compared only against titles someone wrote by hand
    agrees on exactly the cases that occurred to whoever wrote them.
    """
    return [
        text
        for article in [*articles, *cbs_articles, *reddit_articles]
        for text in (article.title, article.summary)
    ]


@pytest.fixture
def games(balldontlie_json: dict[str, Any]) -> list[GameData]:
    """The 9 games as the pipeline sees them, parsed by the real adapter."""
    return BallDontLieGamesAdapter(api_key="test-key-never-used").parse(
        balldontlie_json
    )
