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
import re
from html.parser import HTMLParser
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

# Reddit ends every entry with navigation rather than content.
_SUBMITTED_BY = re.compile(r"submitted by\s*/u/\S+.*$", re.IGNORECASE | re.DOTALL)

# Below this, whatever survived stripping is boilerplate rather than a description. A link
# post reduces to little more than "[link] [comments]"; a real text post does not.
MIN_SUMMARY_CHARS = 60


class _TextExtractor(HTMLParser):
    """Collects visible text from an HTML fragment, discarding tags.

    `html.parser` is standard library, so richer markup handling costs nothing here and needs
    no dependency (`CLAUDE.md` §11). Only Reddit's Atom content requires this — RSS feeds
    supply plain text already.
    """

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())


def strip_html(markup: str) -> str:
    """Return the visible text of an HTML fragment, whitespace collapsed."""
    extractor = _TextExtractor()
    extractor.feed(markup)
    return extractor.text


# Known feeds, keyed by the label stamped onto every article they produce.
# `[VERIFIED]` 2026-08-06 both return HTTP 200 with parseable items: ESPN 17, CBS 36.
# Which sport each feed carries (ADR-015). Kept beside `FEEDS` rather than folded into it, so
# adding a feed is still one line and the existing `FEEDS[name] -> url` shape is unchanged for
# every caller. `[INFERRED]` The risk is the two drifting apart, which a test asserts against.
DEFAULT_LEAGUE = "NBA"
FEED_LEAGUES: dict[str, str] = {
    "ESPN": "NBA",
    "CBS Sports": "NBA",
    "Yahoo Sports": "NBA",
    "r/nba": "NBA",
}

FEEDS: dict[str, str] = {
    "ESPN": "https://www.espn.com/espn/rss/nba/news",
    "CBS Sports": "https://www.cbssports.com/rss/headlines/nba/",
    # `[VERIFIED]` 2026-08-09: 50 items, every one published within 48 hours and the newest
    # under three. Added because editorial outlets publish slowly in the offseason — ESPN
    # and CBS produce a couple of NBA stories a day, so nearly every *new* item in a run was
    # coming from Reddit and the brief had drifted community-heavy.
    "Yahoo Sports": "https://sports.yahoo.com/nba/rss/",
    # Community feed. Far noisier than an editorial outlet, and included on that basis:
    # `processing/priority.py` promotes anything naming a team that played tonight, which
    # turns the volume into coverage rather than noise. It is also where individual
    # performances surface ("Jokic drops 50"), which no free structured source provides.
    # `[VERIFIED]` Reddit rate-limits aggressively -- three requests in ~2s returned two
    # HTTP 429s. One fetch per run is fine; never retry in a loop.
    "r/nba": "https://www.reddit.com/r/nba/.rss",
}

# Feeds evaluated and rejected, recorded so they are not re-proposed:
#
#   The Athletic (theathletic.com/nba/?rss=1)
#       `[VERIFIED]` 2026-08-09: 100 items, newest 42h old, oldest **17 days**, and only 1
#       within 48 hours. It is an archive rather than a news feed; adding it would have
#       flooded the brief with fortnight-old articles.
#   Sporting News (sportingnews.com/us/rss)
#       `[VERIFIED]` All sports, not NBA — the sample carried Phillies, WNBA and betting
#       promotions. Would need its own filtering to be usable.
#   NYT Basketball
#       `[VERIFIED]` 10 items and stale; the sample led with a Knicks title celebration
#       from the previous season.
#   NBA.com, SI, Bleacher Report, SB Nation
#       `[VERIFIED]` HTTP 404 at their documented feed paths. HoopsHype returns 406.


class RssNewsAdapter(NewsSourceAdapter):
    """Fetches NBA headlines from one RSS feed."""

    def __init__(
        self,
        source_name: str,
        feed_url: str | None = None,
        timeout_seconds: int = 15,
        league: str | None = None,
    ) -> None:
        """`feed_url` and `league` may be omitted for any source listed in `FEEDS`.

        `league` is stamped onto every article this adapter produces, the same way
        `source_name` is and for the same reason (ADR-015): the feed URL is league-scoped, so
        the producer knows, and nothing downstream has to infer it from the wording.
        """
        resolved = feed_url or FEEDS.get(source_name)
        if not resolved:
            raise ValueError(
                f"unknown feed {source_name!r}; pass feed_url or add it to FEEDS"
            )

        self._source_name = source_name
        self._feed_url = resolved
        self._timeout_seconds = timeout_seconds
        self._league = league or FEED_LEAGUES.get(source_name, DEFAULT_LEAGUE)

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
        # `.content`, never `.text`. `[VERIFIED]` 2026-08-15: Yahoo serves
        # `Content-Type: application/xml` with **no charset**, so `requests` falls back to
        # `apparent_encoding` — chardet guessed **Windows-1254 (Turkish)** — and `.text`
        # turned the bytes `Schr\xc3\xb6der` into `SchrÃ¶der`. The feed's own declaration
        # says `encoding="UTF-8"` and `.text` never looks at it. Every non-ASCII name from
        # that feed reached the brief mangled, and a mangled name can never match a clean
        # one, so this also silently prevented `cluster.py` from grouping the affected
        # stories (TASKS.md P19).
        return self.parse(response.content)

    def parse(self, feed_xml: str | bytes) -> list[NewsArticle]:
        """Convert a feed into articles, accepting both RSS 2.0 and Atom.

        Public and network-free on purpose: tests drive this with the captured fixtures in
        `tests/fixtures/` rather than hitting the live feeds (`CLAUDE.md` §8).

        Accepts **bytes** as well as `str`, and bytes are what the live path passes. An XML
        document declares its own encoding in its first line, so handing the parser the raw
        bytes lets it obey that declaration; handing it a `str` means something upstream has
        already guessed. `[INFERRED]` The fixtures are read as text and stay valid, because
        decoding a file whose encoding you already know is not a guess.

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
            summary=self._atom_summary(entry),
            published_at=published_at,
            author=author,
            source=self._source_name,
            league=self._league,
        )

    def _atom_summary(self, entry: ElementTree.Element) -> str:
        """Extract readable text from an Atom <content>, or "" if there is none worth having.

        `[VERIFIED]` Reddit's content is HTML and comes in two shapes. A **text post** carries
        the real body (`<div class="md"><p>The Los Angeles Clippers and Kawhi Leonard, who are
        currently under investigation...`), which is genuinely more detailed than the title. A
        **link post** carries only an image table and a "submitted by" trailer, which is
        boilerplate.

        So markup is stripped and the result kept only if it survives as something a reader
        would want. `[INFERRED]` An empty summary is a fine outcome — `delivery/brief.py`
        omits the line entirely rather than printing a blank.
        """
        content = entry.find(f"{ATOM_NAMESPACE}content")
        if content is None or not content.text:
            return ""

        text = strip_html(content.text)

        # Reddit appends this to every entry; it is navigation, not content.
        text = _SUBMITTED_BY.sub("", text).strip()

        return text if len(text) >= MIN_SUMMARY_CHARS else ""

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
            league=self._league,
        )

    @staticmethod
    def _text(element: ElementTree.Element, tag: str) -> str | None:
        """Return a child tag's stripped text, or None if the tag is absent or empty."""
        child = element.find(tag)
        if child is None or child.text is None:
            return None
        stripped = child.text.strip()
        return stripped or None
