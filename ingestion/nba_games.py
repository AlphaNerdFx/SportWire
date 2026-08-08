"""NBA game data from balldontlie.io. See ADR-009's predecessor, ADR-003, for why this source.

`cdn.nba.com` was the original choice and is dead (HTTP 403 from Akamai, verified from two
independent networks on 2026-08-04). balldontlie is a documented API intended for third-party
use, which is what C2 and C3 actually require.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any

import requests

from ingestion.base import GameSourceAdapter
from models.schemas import GameData, SeriesContext

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
        self._last_team_ids: dict[int, tuple[int, int]] = {}

    @property
    def source_name(self) -> str:
        return "balldontlie"

    @property
    def last_team_ids(self) -> dict[int, tuple[int, int]]:
        """Team ids from the most recent fetch, for the season-series lookup.

        `[INFERRED]` Kept here rather than on `GameData` because a numeric team id is this
        provider's vocabulary, and the schema exists so no provider's vocabulary travels
        through the pipeline. Exposing it as a side channel on the adapter that produced it
        keeps that boundary intact while still making the ids reachable.

        Empty before the first fetch, and empty after one that failed.
        """
        return dict(self._last_team_ids)

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

        payload = response.json()
        self._last_team_ids = self.team_ids(payload)
        return self.parse(payload)

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

    @staticmethod
    def team_ids(payload: dict[str, Any]) -> dict[int, tuple[int, int]]:
        """Map each game id to `(home_team_id, away_team_id)` from a raw payload.

        These are balldontlie's own numeric identifiers, needed to query the season series.
        They are returned **beside** `GameData` rather than added to it: a team id is this
        provider's vocabulary, and the schema exists precisely so no provider's vocabulary
        travels through the pipeline. A second source would number teams differently, and
        everything downstream works in names.
        """
        mapping: dict[int, tuple[int, int]] = {}

        for raw in payload.get("data", []):
            game_id = raw.get("id")
            home_id = (raw.get("home_team") or {}).get("id")
            away_id = (raw.get("visitor_team") or {}).get("id")
            if game_id is not None and home_id is not None and away_id is not None:
                mapping[game_id] = (home_id, away_id)

        return mapping

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


class BallDontLieSeriesAdapter:
    """Fetches how the two teams in a game have fared against each other this season.

    Deliberately **not** a `GameSourceAdapter`. That interface promises `list[GameData]`, and
    this returns context about games rather than games. Reusing it would have meant a
    `fetch()` whose return type depended on which subclass you held — the exact ambiguity the
    two separate ingestion ABCs exist to avoid.

    `[VERIFIED]` 2026-08-08: `/v1/games` accepts `team_ids[]` and `seasons[]`, so one request
    per fixture returns every meeting between those two teams that season. Costs one call per
    game in the brief — nine on a full slate, at an eight-hour cadence.
    """

    BASE_URL = "https://api.balldontlie.io/v1/games"

    # Pause between per-game lookups. `[VERIFIED]` 2026-08-08: firing nine requests as fast
    # as possible returned `429 Too Many Requests` from the sixth onward. The free tier is
    # rate-limited and this is a background job that nothing waits on, so waiting is free —
    # nine games costs about fifteen seconds and no 429s.
    REQUEST_INTERVAL_SECONDS = 1.5

    def __init__(
        self,
        api_key: str,
        timeout_seconds: int = 15,
        request_interval_seconds: float = REQUEST_INTERVAL_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._request_interval_seconds = request_interval_seconds

    def fetch_for(
        self, games: list[GameData], team_ids: dict[int, tuple[int, int]]
    ) -> list[SeriesContext]:
        """Return series context for each game, skipping any that fail.

        `team_ids` maps `game_id` to `(home_team_id, away_team_id)` — the numeric ids the API
        needs, which `GameData` deliberately does not carry because the pipeline works in
        team names.

        A failure here degrades one line of one highlight. It must never cost the brief, so
        each game is attempted independently and errors are swallowed per game rather than
        for the batch.
        """
        contexts: list[SeriesContext] = []

        for index, game in enumerate(games):
            ids = team_ids.get(game.game_id)
            if ids is None:
                continue

            # Space the requests out. Before the first one there is nothing to wait for.
            if index and self._request_interval_seconds:
                time.sleep(self._request_interval_seconds)

            try:
                context = self._fetch_one(game, *ids)
            except requests.HTTPError as error:
                # `[VERIFIED]` 2026-08-08: the free tier returns 429 after roughly five
                # requests even spaced 1.5s apart. Once it does, every further request this
                # run will also fail — continuing would hammer an API that has just asked us
                # to stop, and produce nine tracebacks describing one problem. Stop asking.
                if error.response is not None and error.response.status_code == 429:
                    logger.warning(
                        "series lookups rate-limited after %d of %d games; "
                        "the brief continues without the rest",
                        len(contexts),
                        len(games),
                    )
                    break
                logger.exception(
                    "series lookup failed for game %s; continuing without it",
                    game.game_id,
                )
                continue
            except Exception:
                logger.exception(
                    "series lookup failed for game %s; continuing without it",
                    game.game_id,
                )
                continue
            if context is not None:
                contexts.append(context)

        return contexts

    def _fetch_one(
        self, game: GameData, home_team_id: int, away_team_id: int
    ) -> SeriesContext | None:
        """One request for one fixture's season series."""
        response = requests.get(
            self.BASE_URL,
            params={
                "team_ids[]": [home_team_id, away_team_id],
                "seasons[]": [_season_of(game.start_time)],
                "per_page": 100,
            },
            headers={"Authorization": self._api_key},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()

        pair = {home_team_id, away_team_id}
        home_wins = away_wins = 0
        earlier = 0

        for raw in response.json().get("data", []):
            raw_home = (raw.get("home_team") or {}).get("id")
            raw_away = (raw.get("visitor_team") or {}).get("id")

            # The query returns every game either team played, not only their meetings.
            if {raw_home, raw_away} != pair:
                continue
            # Only completed meetings before this one count toward the record.
            if raw.get("id") == game.game_id or (raw.get("status") or "") != "Final":
                continue
            if (raw.get("date") or "") >= game.start_time.date().isoformat():
                continue

            earlier += 1
            home_scored = raw.get("home_team_score") or 0
            away_scored = raw.get("visitor_team_score") or 0
            winner = raw_home if home_scored > away_scored else raw_away
            if winner == home_team_id:
                home_wins += 1
            else:
                away_wins += 1

        return SeriesContext(
            game_id=game.game_id,
            meeting_number=earlier + 1,
            home_team_prior_wins=home_wins,
            away_team_prior_wins=away_wins,
        )


def _season_of(start_time: datetime) -> int:
    """The NBA season a date belongs to.

    `[VERIFIED]` balldontlie labels a season by its starting year — the 2026-01-15 fixture is
    season 2025. So January to September belongs to the previous calendar year, and October
    onward starts a new one.
    """
    return start_time.year - 1 if start_time.month < 10 else start_time.year


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
