"""Canonical data shapes for SportWire. Every other module imports from here.

`CLAUDE.md` §5 rule 2: this is the ONE place an article or game shape is defined.
The legacy prototype defined `NewsArticle` in four separate files, which is why
nothing in it could be trusted to mean the same thing twice.

Both models are deliberately independent — they are NOT given a shared base class.
Games and news arrive from different sources with nothing meaningful in common, and
they are only ever brought together at the formatting step, immediately before
delivery. Forcing a shared parent now would invent a relationship that does not exist.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from email.utils import parsedate_to_datetime

from pydantic import BaseModel, ConfigDict, field_validator


class GameData(BaseModel):
    """One NBA game at one point in time, as reported by balldontlie.io.

    "At one point in time" is load-bearing: a game's score changes between polls,
    so two `GameData` objects with the same `game_id` are not necessarily duplicates.
    See `state_hash`.
    """

    # frozen=True makes instances immutable. A DTO flows through fetch -> dedup ->
    # format -> send; if any stage could mutate it, a bug three stages down would be
    # traceable to any of them. Immutability removes that entire class of bug.
    model_config = ConfigDict(frozen=True)

    game_id: int
    start_time: datetime
    status: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int

    # `[VERIFIED]` 4 for every completed regulation game in the captured fixture. Anything
    # above 4 is overtime, which is the only way to detect an OT game without per-quarter
    # data. Defaults to 0 so a scheduled game that has not tipped off is representable.
    period: int = 0

    # Points scored in each period, in order: Q1–Q4 then any overtimes. Stored as lists
    # rather than fourteen named fields because the number of overtimes is open-ended, and
    # because every use of them is a scan rather than a lookup of one specific quarter.
    # Empty for a game that has not started.
    home_periods: list[int] = []
    away_periods: list[int] = []

    @property
    def largest_deficit_overcome(self) -> int:
        """Biggest deficit the eventual winner faced at any period boundary.

        Returns 0 if the winner never trailed at the end of a period, or if per-period data
        is unavailable. This measures comebacks at period granularity only — a team down 20
        mid-third-quarter that levels by the buzzer never appears to have trailed, because
        balldontlie reports period totals rather than a running play-by-play.
        """
        if not self.home_periods or len(self.home_periods) != len(self.away_periods):
            return 0

        home_leads = self.home_score > self.away_score
        home_running = 0
        away_running = 0
        largest_deficit = 0

        for home_points, away_points in zip(self.home_periods, self.away_periods):
            home_running += home_points
            away_running += away_points
            deficit = (
                away_running - home_running
                if home_leads
                else home_running - away_running
            )
            largest_deficit = max(largest_deficit, deficit)

        return largest_deficit

    @property
    def led_wire_to_wire(self) -> bool:
        """True when the winner was ahead at the end of every period, never level.

        Returns False when period data is unavailable — an unknown is not a claim. A tie at
        any boundary disqualifies it: "wire to wire" means never headed, and a team that was
        level was, briefly, not ahead.
        """
        leads = self._winner_leads()
        return bool(leads) and all(lead > 0 for lead in leads)

    @property
    def largest_lead_lost(self) -> int:
        """Biggest lead the *losing* team held at a period boundary, or 0 if it never led.

        The mirror of `largest_deficit_overcome` and the same number seen from the other
        side, kept separate because a brief phrases them differently — "came back from 16
        down" is about the winner, "blew a 16-point lead" is about the loser. Which reads
        better depends on which team the reader cares about, and the formatter decides.
        """
        return self.largest_deficit_overcome

    @property
    def biggest_period(self) -> int:
        """Most points either side scored in a single period. 0 when unknown.

        `[INFERRED]` A 40-point quarter is the kind of detail that makes a scoreline memorable
        and is invisible in a final score.
        """
        return max([*self.home_periods, *self.away_periods], default=0)

    @property
    def second_half_swing(self) -> int:
        """How much the winner out- or under-scored the loser after half time.

        Positive means the winner pulled away; negative means they were outscored after the
        break and won on the strength of the first half. `[INFERRED]` Both are worth saying,
        and neither is visible in the final score.

        Returns 0 when a game has not reached the second half, or when period data is absent.
        """
        if len(self.home_periods) < 4 or len(self.away_periods) < 4:
            return 0

        home_second = sum(self.home_periods[2:])
        away_second = sum(self.away_periods[2:])
        return (
            home_second - away_second
            if self.home_score > self.away_score
            else away_second - home_second
        )

    def _winner_leads(self) -> list[int]:
        """The winner's lead at the end of each period. Empty when data is unavailable."""
        if not self.home_periods or len(self.home_periods) != len(self.away_periods):
            return []

        home_wins = self.home_score > self.away_score
        leads: list[int] = []
        home_running = away_running = 0

        for home_points, away_points in zip(self.home_periods, self.away_periods):
            home_running += home_points
            away_running += away_points
            leads.append(
                home_running - away_running
                if home_wins
                else away_running - home_running
            )

        return leads

    @property
    def margin(self) -> int:
        """Absolute points difference. Used to classify blowouts and close finishes."""
        return abs(self.home_score - self.away_score)

    @property
    def total_points(self) -> int:
        """Combined score of both teams."""
        return self.home_score + self.away_score

    @property
    def went_to_overtime(self) -> bool:
        """True when the game needed more than four periods."""
        return self.period > 4

    @property
    def state_hash(self) -> str:
        """Identity of this game *in its current state*, for cross-run deduplication.

        Deliberately excludes any timestamp. Including the current time would produce
        a new hash on every poll, so nothing would ever match and every game would be
        re-sent every run — the opposite of dedup. The hash must change only when the
        game itself changes.
        """
        payload = f"{self.game_id}|{self.status}|{self.home_score}|{self.away_score}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SeriesContext(BaseModel):
    """How the two teams in one game have fared against each other this season.

    Separate from `GameData` rather than a field on it, because it comes from a different
    request and is optional. A game is complete without it; forcing the field would make
    every construction of `GameData` depend on a second API call.
    """

    model_config = ConfigDict(frozen=True)

    game_id: int

    # Which meeting of the season this is, counting this one. 1 means first.
    meeting_number: int

    # Wins *before* this game, attributed to the teams as named in this game. Deliberately
    # excludes the current result: the brief already states tonight's score, and a record
    # that silently includes it reads as though the series stood there beforehand.
    home_team_prior_wins: int
    away_team_prior_wins: int

    @property
    def is_first_meeting(self) -> bool:
        """True when these teams have not played each other yet this season."""
        return self.meeting_number <= 1


class GameHighlight(BaseModel):
    """A game flagged as worth mentioning, plus the reason it was flagged.

    `category` is a stable machine-readable key ("overtime", "closest_finish", ...), not
    display text. The formatter maps it to wording, so the brief can be reworded without
    touching the logic that decides what counts as notable.
    """

    model_config = ConfigDict(frozen=True)

    category: str
    game: GameData


class NewsArticle(BaseModel):
    """One news item from an RSS feed, normalised across sources.

    Field choices here are driven by measurements of the real ESPN payload saved in
    `tests/fixtures/espn_nba_rss.xml`, not by what an RSS feed "should" contain.
    """

    model_config = ConfigDict(frozen=True)

    # `guid` in the feed. 15/15 unique in the captured fixture, and stable across
    # fetches, which makes it the identity key. `published_at` is NOT usable for this:
    # only 6 distinct timestamps appear across 15 items, so seven stories share one
    # second and would collapse into each other.
    article_id: str
    title: str
    url: str
    summary: str
    published_at: datetime

    # `[VERIFIED]` Absent on 2 of 15 items in the captured fixture. Typing this as a
    # required `str` would raise a ValidationError on real data within the first run.
    author: str | None = None

    # Which feed this came from ("ESPN", "CBS Sports", ...). Set by the adapter, not
    # parsed from the payload — the article does not know where it was fetched from.
    source: str

    # Which sport this belongs to ("NBA", "NFL", ...). Set by the adapter for the same reason
    # as `source`, and carried rather than inferred (ADR-015).
    #
    # `[VERIFIED]` The feed URLs are league-scoped — `espn.com/espn/rss/nba/news`,
    # `cbssports.com/rss/headlines/nba/` — so the producer already knows this and nothing
    # downstream has to guess. `[VERIFIED]` Guessing was measured: across 128 live articles,
    # exactly 1 reads as another sport, so a content classifier would misattribute more than
    # it caught.
    #
    # Defaulted rather than required, so every existing caller and fixture keeps working while
    # the other leagues are added. `[INFERRED]` A required field here would be a schema change
    # touching every construction site in the tests at once, which is the sort of edit that
    # hides a real mistake among a hundred mechanical ones.
    league: str = "NBA"

    @field_validator("published_at", mode="before")
    @classmethod
    def _parse_rss_date(cls, value: object) -> object:
        """Accept RFC-822 dates as emitted by RSS (`Tue, 4 Aug 2026 17:12:16 EST`).

        Pydantic parses ISO-8601 natively but not RFC-822, which is what RSS uses.
        Parsing here means a malformed date fails at the boundary, where the source is
        obvious, rather than surfacing as a confusing error deeper in the pipeline.
        """
        if isinstance(value, str):
            try:
                return parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return value  # let pydantic try ISO-8601, then report the error itself
        return value

    @property
    def dedup_hash(self) -> str:
        """Cross-source identity, for catching the same story reported by two outlets.

        Uses the normalised title rather than `article_id`, because two outlets covering
        one event assign different ids. `article_id` identifies a *document*; this
        identifies a *story*. Exact-match only — near-duplicate detection is a separate,
        deferred concern (ADR-005).
        """
        normalised = " ".join(self.title.lower().split())
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()
