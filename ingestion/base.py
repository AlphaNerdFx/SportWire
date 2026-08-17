"""Abstract source interfaces. The pipeline depends on these, never on a concrete source.

This is the boundary that keeps source-specific ugliness contained. ESPN speaks RSS/XML;
balldontlie speaks JSON. Neither vocabulary is allowed past an adapter — everything above
this line sees only `NewsArticle` and `GameData` from `models.schemas`.

Two separate interfaces rather than one, because news and games return genuinely different
types. A single `fetch()` returning "either kind of list" would push a type check back into
the pipeline, which is exactly the knowledge this boundary exists to remove.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from models.schemas import GameData, NewsArticle

logger = logging.getLogger(__name__)


class NewsSourceAdapter(ABC):
    """One news source. Converts that source's payload into `list[NewsArticle]`."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable source label, e.g. "ESPN". Stamped onto every article produced."""

    @abstractmethod
    def _fetch(self) -> list[NewsArticle]:
        """Do the real work: request, parse, convert. Subclasses implement only this.

        Deliberately allowed to raise. Error handling lives in `fetch()` so that an adapter
        author cannot forget it.
        """

    # Why the last fetch returned nothing, or None if it did not fail.
    #
    # `[VERIFIED]` 2026-08-18: Reddit answered HTTP 500 for the whole 00:00 run and again five
    # minutes later, costing 25 of 87 articles. The brief carried on and said nothing, because
    # returning [] on failure makes a dead source indistinguishable from a quiet one. That is
    # the second observed case, after CBS timed out on 2026-08-15 and contributed 0 stories.
    #
    # A **class attribute**, deliberately. Subclasses write their own `__init__` and this must
    # not depend on any of them remembering to call up, which is the same reasoning that puts
    # the try/except in `fetch` rather than in each adapter.
    last_error: str | None = None

    def fetch(self) -> list[NewsArticle]:
        """Fetch articles, returning [] if anything at all goes wrong.

        `CLAUDE.md` §5 rule 6: a dead source must degrade the brief, never crash the run.
        That rule is enforced *here*, structurally, rather than restated in every adapter —
        an adapter cannot opt out of it, because it never implements this method.

        The empty list stays the contract. `last_error` is set alongside it so a caller that
        wants to *report* the failure can, without any caller being forced to handle it.
        """
        self.last_error = None
        try:
            return self._fetch()
        except Exception as error:
            logger.exception(
                "news source %s failed; returning no articles", self.source_name
            )
            self.last_error = type(error).__name__
            return []


class GameSourceAdapter(ABC):
    """One game-data source. Converts that source's payload into `list[GameData]`."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable source label, e.g. "balldontlie"."""

    @abstractmethod
    def _fetch(self) -> list[GameData]:
        """Do the real work. Allowed to raise; `fetch()` contains the failure policy."""

    def fetch(self) -> list[GameData]:
        """Fetch games, returning [] if anything at all goes wrong.

        Note that an empty list is **not** an error condition here: `[VERIFIED]` the NBA
        offseason legitimately returns zero games, so callers must treat [] as "nothing to
        report" rather than "something broke".
        """
        try:
            return self._fetch()
        except Exception:
            logger.exception(
                "game source %s failed; returning no games", self.source_name
            )
            return []
