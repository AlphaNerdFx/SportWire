"""One RSS news adapter, configured per feed. Adding a feed adds no code.

Replaces the ESPN-specific adapter. `[VERIFIED]` 2026-08-06: CBS Sports' feed uses byte-
identical structure to ESPN's — the same `./channel/item` path, the same `title`, `link`,
`description`, `pubDate` and `guid` elements, and the same Dublin Core `creator`. The ESPN
parser ran on the CBS payload unchanged.

That is what a shared specification buys: a per-source class would have been two copies of
one parser differing only in a URL and a label. Sources are therefore **configuration**, not
subclasses — see `FEEDS` below.

`[VERIFIED]` 2026-08-07 that claim has a limit, found by adding r/nba. **Atom is a different
specification, not a dialect of RSS.** Reddit publishes `<feed><entry>` with `<id>`,
`<link href="">` and a nested `<author><name>`, where RSS 2.0 publishes `<channel><item>` with
`<guid>`, `<link>text</link>` and `<dc:creator>`. This adapter now reads both, so adding a
feed is still one entry — but "it is a feed" was not sufficient, and assuming so produced an
adapter that silently returned nothing.

Consuming a published feed is using the interface as intended, which is what keeps this repo
publishable (C3) — unlike scraping the same outlets' HTML. See ADR-009.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree

import requests

from ingestion.base import NewsSourceAdapter
from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

# RSS puts the author in the Dublin Core namespace rather than in RSS itself, so the tag is
# addressed by its full namespaced name.
DC_NAMESPACE = "{http://purl.org/dc/elements/1.1/}"

# Atom is a different specification from RSS 2.0, not a dialect of it. Reddit publishes Atom.
ATOM_NAMESPACE = "{http://www.w3.org/2005/Atom}"

# Known feeds, keyed by the label stamped onto every article they produce.
# `[VERIFIED]` 2026-08-06 both return HTTP 200 with parseable items: ESPN 17, CBS 36.
FEEDS: dict[str, str] = {
    "ESPN": "https://www.espn.com/espn/rss/nba/news",
    "CBS Sports": "https://www.cbssports.com/rss/headlines/nba/",
    # Community feed. Far noisier than an editorial outlet, and included on that basis:
    # `processing/priority.py` promotes anything naming a team that played tonight, which
    # turns the volume into coverage rather than noise. It is also where individual
    # performances surface ("Jokic drops 50"), which no free structured source provides.
    # `[VERIFIED]` Reddit rate-limits aggressively -- three requests in ~2s returned two
    # HTTP 429s. One fetch per run is fine; never retry in a loop.
    "r/nba": "https://www.reddit.com/r/nba/.rss",
}


class RssNewsAdapter(NewsSourceAdapter):
    """Fetches NBA headlines from one RSS feed."""

    def __init__(
        self,
        source_name: str,
        feed_url: str | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        """`feed_url` may be omitted for any source listed in `FEEDS`."""
        resolved = feed_url or FEEDS.get(source_name)
        if not resolved:
            raise ValueError(
                f"unknown feed {source_name!r}; pass feed_url or add it to FEEDS"
            )

        self._source_name = source_name
        self._feed_url = resolved
        self._timeout_seconds = timeout_seconds

    @property
    def source_name(self) -> str:
        return self._source_name

    def _fetch(self) -> list[NewsArticle]:
        """Request the live feed and convert it. Exceptions are handled by `fetch()`."""
        response = requests.get(
            self._feed_url,
            timeout=self._timeout_seconds,
            headers={
                "User-Agent": "SportWire/0.1 (+https://github.com/AlphaNerdFx/SportWire)"
            },
        )
        response.raise_for_status()
        return self.parse(response.text)

    def parse(self, feed_xml: str) -> list[NewsArticle]:
        """Convert a feed into articles, accepting both RSS 2.0 and Atom.

        Public and network-free on purpose: tests drive this with the captured fixtures in
        `tests/fixtures/` rather than hitting the live feeds (`CLAUDE.md` §8).

        `[VERIFIED]` 2026-08-07 both formats are needed. ESPN and CBS publish RSS 2.0
        (`<channel><item>`); Reddit publishes Atom (`<feed><entry>`), with `<id>` instead of
        `<guid>`, `<link href="">` as an attribute rather than text, and the author nested in
        `<author><name>`. An RSS-only parser found zero matches and returned an empty list —
        **silently**, because an empty feed is indistinguishable from a quiet one.
        """
        root = ElementTree.fromstring(feed_xml)

        items = list(root.iterfind("./channel/item"))
        if items:
            parsed = [self._parse_item(item) for item in items]
        else:
            entries = list(root.iterfind(f"./{ATOM_NAMESPACE}entry"))
            parsed = [self._parse_atom_entry(entry) for entry in entries]

        articles = [article for article in parsed if article is not None]

        if not articles:
            # A feed yielding nothing is far more often a parsing mismatch than a genuinely
            # empty feed. Saying so turns a silent failure into a visible one.
            logger.warning(
                "%s produced no articles — check whether the feed format changed",
                self._source_name,
            )

        return articles

    def _parse_atom_entry(self, entry: ElementTree.Element) -> NewsArticle | None:
        """Convert one Atom <entry>. Same contract as `_parse_item`: None if unusable."""
        article_id = self._text(entry, f"{ATOM_NAMESPACE}id")
        title = self._text(entry, f"{ATOM_NAMESPACE}title")
        published_at = self._text(entry, f"{ATOM_NAMESPACE}updated") or self._text(
            entry, f"{ATOM_NAMESPACE}published"
        )

        # Atom carries the URL as an attribute, not element text.
        link_element = entry.find(f"{ATOM_NAMESPACE}link")
        url = link_element.get("href") if link_element is not None else None

        if not (article_id and title and url and published_at):
            logger.warning(
                "skipping %s entry missing required fields: %r",
                self._source_name,
                title or url,
            )
            return None

        author_element = entry.find(f"{ATOM_NAMESPACE}author")
        author = (
            self._text(author_element, f"{ATOM_NAMESPACE}name")
            if author_element is not None
            else None
        )

        return NewsArticle(
            article_id=f"{self._source_name}:{article_id}",
            title=title,
            url=url,
            # Atom's <content> is full HTML for Reddit — the whole rendered post. Excluded
            # deliberately: the brief shows a short description, and stripping markup from
            # user-submitted HTML is a parsing problem with no upside here. The title alone
            # carries the substance for this source.
            summary="",
            published_at=published_at,
            author=author,
            source=self._source_name,
        )

    def _parse_item(self, item: ElementTree.Element) -> NewsArticle | None:
        """Convert one <item>, or return None if it lacks the fields we require.

        Skipping a malformed item is deliberate: one bad entry must not discard the good
        ones alongside it.
        """
        article_id = self._text(item, "guid")
        title = self._text(item, "title")
        url = self._text(item, "link")
        published_at = self._text(item, "pubDate")

        if not (article_id and title and url and published_at):
            logger.warning(
                "skipping %s item missing required fields: %r",
                self._source_name,
                title or url,
            )
            return None

        return NewsArticle(
            # Feeds assign ids in their own namespace — ESPN uses "US-EN-49531647", CBS a
            # UUID — so the source is prefixed to keep them unique across feeds. Without
            # this, two outlets could in principle collide and one story would vanish.
            article_id=f"{self._source_name}:{article_id}",
            title=title,
            url=url,
            # Not identity-bearing, so an empty string is an acceptable default rather than
            # a reason to discard the article.
            summary=self._text(item, "description") or "",
            published_at=published_at,
            # `[VERIFIED]` Absent on 2 of 15 ESPN items, present on all 36 CBS items — hence
            # optional in the schema, and hence no error here.
            author=self._text(item, f"{DC_NAMESPACE}creator"),
            source=self._source_name,
        )

    @staticmethod
    def _text(element: ElementTree.Element, tag: str) -> str | None:
        """Return a child tag's stripped text, or None if the tag is absent or empty."""
        child = element.find(tag)
        if child is None or child.text is None:
            return None
        stripped = child.text.strip()
        return stripped or None
