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
from pathlib import Path
from typing import Any

import pytest

from ingestion.espn_news import ESPNNewsAdapter
from ingestion.nba_games import BallDontLieGamesAdapter
from models.schemas import GameData, NewsArticle

FIXTURES = Path(__file__).parent / "fixtures"


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
def balldontlie_json() -> dict[str, Any]:
    """Raw balldontlie response for 2026-01-15: 9 completed games."""
    return json.loads((FIXTURES / "nba_games.json").read_text(encoding="utf-8"))


@pytest.fixture
def articles(espn_rss_xml: str) -> list[NewsArticle]:
    """The 15 articles as the pipeline sees them, parsed by the real adapter."""
    return ESPNNewsAdapter().parse(espn_rss_xml)


@pytest.fixture
def games(balldontlie_json: dict[str, Any]) -> list[GameData]:
    """The 9 games as the pipeline sees them, parsed by the real adapter."""
    return BallDontLieGamesAdapter(api_key="test-key-never-used").parse(
        balldontlie_json
    )
