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
