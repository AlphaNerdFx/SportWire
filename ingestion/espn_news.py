"""ESPN NBA news, via their public RSS feed. See ADR-009 for why this source.

Consuming a published RSS feed is using the interface as intended, which is what keeps
this repo publishable (constraint C3) — unlike scraping ESPN's HTML.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree

import requests

from ingestion.base import NewsSourceAdapter
from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

# RSS puts the author in the Dublin Core namespace rather than in RSS itself, so the
# tag is addressed by its full namespaced name.
DC_NAMESPACE = "{http://purl.org/dc/elements/1.1/}"


class ESPNNewsAdapter(NewsSourceAdapter):
    """Fetches NBA headlines from ESPN's public RSS feed."""

    FEED_URL = "https://www.espn.com/espn/rss/nba/news"

    def __init__(self, feed_url: str | None = None, timeout_seconds: int = 15) -> None:
        self._feed_url = feed_url or self.FEED_URL
        self._timeout_seconds = timeout_seconds

    @property
    def source_name(self) -> str:
        return "ESPN"

    def _fetch(self) -> list[NewsArticle]:
        """Request the live feed and convert it. Exceptions are handled by `fetch()`."""
        response = requests.get(
            self._feed_url,
            timeout=self._timeout_seconds,
            headers={"User-Agent": "SportWire/0.1 (+https://github.com/sportwire)"},
        )
        response.raise_for_status()
        return self.parse(response.text)

    def parse(self, feed_xml: str) -> list[NewsArticle]:
        """Convert raw RSS XML into articles.

        Public and network-free on purpose: tests drive this with the captured fixture in
        `tests/fixtures/espn_nba_rss.xml` rather than hitting ESPN (`CLAUDE.md` §8).
        """
        root = ElementTree.fromstring(feed_xml)
        articles: list[NewsArticle] = []

        for item in root.iterfind("./channel/item"):
            article = self._parse_item(item)
            if article is not None:
                articles.append(article)

        return articles

    def _parse_item(self, item: ElementTree.Element) -> NewsArticle | None:
        """Convert one <item>, or return None if it lacks the fields we require.

        Skipping a malformed item is deliberate: one bad entry must not discard the
        fourteen good ones alongside it.
        """
        article_id = self._text(item, "guid")
        title = self._text(item, "title")
        url = self._text(item, "link")
        published_at = self._text(item, "pubDate")

        if not (article_id and title and url and published_at):
            logger.warning(
                "skipping ESPN item missing required fields: %r", title or url
            )
            return None

        return NewsArticle(
            article_id=article_id,
            title=title,
            url=url,
            # `[VERIFIED]` description is present on every item in the captured fixture,
            # but it is not identity-bearing, so an empty string is an acceptable default
            # rather than a reason to discard the article.
            summary=self._text(item, "description") or "",
            published_at=published_at,
            # `[VERIFIED]` absent on 2 of 15 items in the fixture — hence Optional in the
            # schema, and hence no error here.
            author=self._text(item, f"{DC_NAMESPACE}creator"),
            source=self.source_name,
        )

    @staticmethod
    def _text(element: ElementTree.Element, tag: str) -> str | None:
        """Return a child tag's stripped text, or None if the tag is absent or empty."""
        child = element.find(tag)
        if child is None or child.text is None:
            return None
        stripped = child.text.strip()
        return stripped or None
