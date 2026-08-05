"""NBA game data from balldontlie.io. See ADR-009's predecessor, ADR-003, for why this source.

`cdn.nba.com` was the original choice and is dead (HTTP 403 from Akamai, verified from two
independent networks on 2026-08-04). balldontlie is a documented API intended for third-party
use, which is what C2 and C3 actually require.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import requests

from ingestion.base import GameSourceAdapter
from models.schemas import GameData

logger = logging.getLogger(__name__)


class BallDontLieGamesAdapter(GameSourceAdapter):
    """Fetches NBA games for a single date from balldontlie.io."""

    BASE_URL = "https://api.balldontlie.io/v1/games"

    def __init__(
        self,
        api_key: str,
        target_date: date | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        """The key is injected rather than read from the environment here.

        This adapter should not know that `.env` exists. Whoever constructs it decides
        where the key came from, which keeps configuration in one place (`config/settings.py`,
        task M2) and lets tests build one with a dummy key and never touch the network.
        """
        self._api_key = api_key
        self._target_date = target_date
        self._timeout_seconds = timeout_seconds

    @property
    def source_name(self) -> str:
        return "balldontlie"

    def _fetch(self) -> list[GameData]:
        """Request one day of games and convert them. Exceptions handled by `fetch()`."""
        target = self._target_date or datetime.now(timezone.utc).date()
        response = requests.get(
            self.BASE_URL,
            params={"dates[]": target.isoformat()},
            headers={"Authorization": self._api_key},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return self.parse(response.json())

    def parse(self, payload: dict[str, Any]) -> list[GameData]:
        """Convert a balldontlie games response into `GameData`.

        Public and network-free on purpose: tests drive this with
        `tests/fixtures/nba_games.json` rather than the live API (`CLAUDE.md` §8).
        """
        games: list[GameData] = []

        for raw_game in payload.get("data", []):
            game = self._parse_game(raw_game)
            if game is not None:
                games.append(game)

        return games

    def _parse_game(self, raw: dict[str, Any]) -> GameData | None:
        """Convert one game, or return None if it is unusable.

        One malformed game must not discard the rest of the night's slate.
        """
        game_id = raw.get("id")
        home = raw.get("home_team") or {}
        away = raw.get("visitor_team") or {}

        if game_id is None or not home or not away:
            logger.warning("skipping game with missing id or teams: %r", game_id)
            return None

        # `datetime` is the scheduled tip-off in UTC and is the more precise field, but
        # `date` is always present, so it is the fallback.
        start_time = raw.get("datetime") or raw.get("date")
        if not start_time:
            logger.warning("skipping game %s with no date", game_id)
            return None

        return GameData(
            game_id=game_id,
            start_time=start_time,
            # `[VERIFIED]` "Final" for completed games in the captured fixture.
            # `[UNKNOWN]` what this holds for a live or scheduled game — the fixture is a
            # past date and it is currently the offseason, so no live game has been observed.
            # Resolve once the season starts (2026-09-30) and capture a second fixture.
            status=raw.get("status") or "Unknown",
            # The source says "visitor"; the pipeline says "away". Translating vocabulary
            # is precisely what an adapter is for — the source's naming stops here.
            home_team=home.get("full_name") or "Unknown",
            away_team=away.get("full_name") or "Unknown",
            home_score=raw.get("home_team_score") or 0,
            away_score=raw.get("visitor_team_score") or 0,
            # 4 in regulation; >4 means overtime. `[VERIFIED]` every completed game in the
            # captured fixture reports 4.
            period=raw.get("period") or 0,
            home_periods=_period_scores(raw, "home"),
            away_periods=_period_scores(raw, "visitor"),
        )


def _period_scores(raw: dict[str, Any], side: str) -> list[int]:
    """Collect a side's per-period scores in order: Q1–Q4, then any overtimes.

    `[VERIFIED]` The payload uses `home_q1`…`home_q4` and `home_ot1`…`ot3` (and `visitor_`
    for the away side), with unplayed overtimes present but null. Collection stops at the
    first missing period so a game in progress yields only the periods actually played.
    """
    scores: list[int] = []
    for key in ("q1", "q2", "q3", "q4", "ot1", "ot2", "ot3"):
        value = raw.get(f"{side}_{key}")
        if value is None:
            # Quarters are contiguous, so the first gap marks the end of what was played.
            if key.startswith("ot"):
                break
            continue
        scores.append(int(value))
    return scores
