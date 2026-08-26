"""Behaviour tests for the RSS/Atom adapter's decoding.

`[VERIFIED]` 2026-08-15 the delivered brief carried `Dennis SchrÃ¶der`. The cause was not the
model and not the feed: Yahoo serves `Content-Type: application/xml` with **no charset**, so
`requests` fell back to `apparent_encoding` — chardet guessed Windows-1254, Turkish — and
`response.text` decoded UTF-8 bytes through the wrong codec. The feed's own XML declaration
says UTF-8 the whole time.

`[INFERRED]` The damage is wider than one ugly name. `processing/cluster.py` fingerprints
stories by shared rare names, and `SchrÃ¶der` can never match `Schröder`, so the mojibake
silently prevented grouping of exactly the story that then occupied four slots in one brief
(`TASKS.md` P19).

These tests use the real byte sequence from the live feed, not an invented one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from ingestion.rss_news import FEED_LEAGUES, FEEDS, RssNewsAdapter
from models.schemas import NewsArticle

# `[VERIFIED]` The exact bytes the live Yahoo feed serves for "Schröder": U+00F6 as UTF-8.
SCHRODER_UTF8 = b"Schr\xc3\xb6der"

FEED_TEMPLATE = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<rss><channel><item>"
    b"<title>Dennis " + SCHRODER_UTF8 + b" traded to the Hornets</title>"
    b"<link>https://example.invalid/schroder</link>"
    b"<guid>schroder-trade</guid>"
    b"<description>Luka Don\xc4\x8di\xc4\x87 reacts</description>"
    b"<pubDate>Fri, 15 Aug 2026 08:00:00 GMT</pubDate>"
    b"</item></channel></rss>"
)


class _FakeResponse:
    """The two attributes the adapter can read, disagreeing exactly as requests makes them.

    `.text` is what `requests` produces for a charset-less `application/xml` response: the
    bytes decoded through chardet's guess. `.content` is the bytes themselves. A test that
    only supplied `.content` would pass against the old code too, and prove nothing.
    """

    def __init__(self, payload: bytes) -> None:
        self.content = payload
        # Windows-1254 is the guess chardet actually returned for the live feed, and
        # `errors="replace"` is what `requests` passes — which is precisely why the bug was
        # silent. A strict decode would have raised on `Dončić` and made the problem
        # obvious; instead every undecodable byte became U+FFFD and the run carried on.
        self.text = payload.decode("windows-1254", errors="replace")
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def yahoo_response(monkeypatch: pytest.MonkeyPatch) -> _FakeResponse:
    """Serve the captured bytes in place of the live request. No network is touched."""
    response = _FakeResponse(FEED_TEMPLATE)

    def fake_get(*_args: Any, **_kwargs: Any) -> _FakeResponse:
        return response

    monkeypatch.setattr("ingestion.rss_news.requests.get", fake_get)
    return response


def test_the_fake_response_reproduces_the_bug(yahoo_response: _FakeResponse) -> None:
    """The mojibake is real, and this asserts the test would catch its return.

    `[VERIFIED]` Without this, a test asserting the *fixed* behaviour could pass because the
    payload was ASCII all along. `SESSION.md` §11: five tests written in one session asserted
    nothing, and only mutation caught them.
    """
    assert "SchrÃ¶der" in yahoo_response.text
    assert "Schröder" not in yahoo_response.text


def test_a_name_survives_a_feed_served_without_a_charset(
    yahoo_response: _FakeResponse,
) -> None:
    """The delivered bug, asserted end to end through the real adapter."""
    articles = RssNewsAdapter(
        "Yahoo Sports", feed_url="https://example.invalid/rss"
    ).fetch()

    assert len(articles) == 1
    assert "Schröder" in articles[0].title
    assert "SchrÃ¶der" not in articles[0].title


def test_the_body_is_decoded_too_not_only_the_title(
    yahoo_response: _FakeResponse,
) -> None:
    """`[INFERRED]` Summaries reach the model as source notes, so a mangled name there
    invents a fact for the summariser rather than merely looking wrong."""
    articles = RssNewsAdapter(
        "Yahoo Sports", feed_url="https://example.invalid/rss"
    ).fetch()

    assert "Dončić" in articles[0].summary


def test_parse_still_accepts_the_text_the_fixtures_are_read_as(
    espn_rss_xml: str,
) -> None:
    """`str` stays valid input. The fixtures are read from disk with a known encoding, which
    is not a guess, and every other test in the suite drives `parse` that way."""
    articles = RssNewsAdapter("ESPN").parse(espn_rss_xml)

    assert len(articles) == 15


def test_parse_accepts_the_bytes_the_live_path_now_passes() -> None:
    """Both input types reach the same articles, so the fixtures still prove the live path."""
    articles = RssNewsAdapter(
        "Yahoo Sports", feed_url="https://example.invalid/rss"
    ).parse(FEED_TEMPLATE)

    assert [article.title for article in articles] == [
        "Dennis Schröder traded to the Hornets"
    ]


def test_a_failed_fetch_records_why_and_still_returns_nothing() -> None:
    """`[VERIFIED]` 2026-08-18: Reddit answered HTTP 500 for a whole run.

    The empty list stays the contract (`CLAUDE.md` §5 rule 6), so nothing above the adapter is
    forced to handle a failure. `last_error` is set alongside it so a caller that wants to
    *report* the outage can, which is what stopped 25 of 87 articles vanishing silently.
    """

    class DeadFeed(RssNewsAdapter):
        def _fetch(self) -> list[NewsArticle]:
            raise requests.HTTPError("500 Server Error")

    adapter = DeadFeed("r/nba")

    assert adapter.fetch() == [], "a dead source must still degrade, never raise"
    assert adapter.last_error == "HTTPError"


def test_a_healthy_fetch_leaves_no_error_behind() -> None:
    """The complement, and it must survive a *previous* failure on the same adapter.

    `[INFERRED]` `last_error` is a class attribute so no adapter author can forget to set it
    up. That makes clearing it at the start of every `fetch` the thing that must not be
    forgotten instead, which is what this asserts.
    """

    class FlakyFeed(RssNewsAdapter):
        def __init__(self, source_name: str) -> None:
            super().__init__(source_name)
            self.calls = 0

        def _fetch(self) -> list[NewsArticle]:
            self.calls += 1
            if self.calls == 1:
                raise requests.HTTPError("500 Server Error")
            return []

    adapter = FlakyFeed("r/nba")

    adapter.fetch()
    assert adapter.last_error == "HTTPError"

    adapter.fetch()
    assert adapter.last_error is None, "a recovered source must stop being reported"


def test_the_pipeline_reports_which_feeds_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[VERIFIED]` 2026-08-18, and this test exists because a mutation demanded it.

    Deleting the failure collection from the fetch loop left all 315 tests green, because
    nothing exercised it: the brief tests call `build_messages` directly and never reach the
    loop. That is a mechanism which reads as protection and proves nothing, the shape
    `TASKS.md` P6 was opened for.

    Two feeds, one dead. The dead one must be named and must not end the run.
    """
    import main

    class Fake(RssNewsAdapter):
        def _fetch(self) -> list[NewsArticle]:
            if self.source_name == "r/nba":
                raise requests.HTTPError("500 Server Error")
            return []

    monkeypatch.setattr(main, "RssNewsAdapter", Fake)

    articles, failed = main.fetch_news(["ESPN", "r/nba"])

    assert articles == []
    assert failed == ["r/nba"], "the dead feed must be named, the healthy one must not"


def test_the_pipeline_reports_nothing_when_every_feed_is_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The complement, so the note cannot quietly become permanent."""
    import main

    class Healthy(RssNewsAdapter):
        def _fetch(self) -> list[NewsArticle]:
            return []

    monkeypatch.setattr(main, "RssNewsAdapter", Healthy)

    assert main.fetch_news(["ESPN", "r/nba"]) == ([], [])


def test_every_configured_feed_declares_its_league() -> None:
    """`FEEDS` and `FEED_LEAGUES` are separate maps, so they can drift (ADR-015).

    `[INFERRED]` A feed added to one and not the other would silently take the default league
    and file its articles under the wrong sport, which is the exact misattribution ADR-015
    chose feed-based routing to avoid.
    """
    assert set(FEEDS) == set(FEED_LEAGUES), (
        "a feed is missing its league, or the reverse"
    )


def test_both_leagues_have_feeds_of_their_own() -> None:
    """v0.5.0 is the NFL milestone, and a config-only feature can be undone by a config edit.

    `[INFERRED]` Nothing else in the suite would notice the NFL feeds being deleted or
    relabelled NBA. Every other test would still pass, the run would still deliver, and the
    product would quietly be NBA-only again with no failure to point at.
    """
    served = {FEED_LEAGUES[name] for name in FEEDS}

    assert served == {"NBA", "NFL"}, (
        f"expected both leagues to have feeds, got {served}"
    )


def test_an_article_carries_the_league_of_the_feed_it_came_from(
    espn_rss_xml: str,
) -> None:
    """Carried from the producer, never inferred downstream.

    `[VERIFIED]` Inferring was measured and rejected: across 128 live articles exactly 1 reads
    as another sport, so a content classifier would misattribute more than it caught.
    """
    articles = RssNewsAdapter("ESPN").parse(espn_rss_xml)

    assert articles, "fixture produced no articles"
    assert all(article.league == "NBA" for article in articles)


def test_a_feed_can_declare_a_league_the_map_does_not_know(
    espn_rss_xml: str,
) -> None:
    """An explicit league wins, so a new sport can be tried without editing the map first.

    `[INFERRED]` This is what makes adding NFL a configuration change rather than a code
    change, which is the property the adapter boundary exists to provide.
    """
    articles = RssNewsAdapter("ESPN", league="NFL").parse(espn_rss_xml)

    assert all(article.league == "NFL" for article in articles)


def test_the_atom_path_stamps_the_league_too(
    reddit_articles: list[NewsArticle],
) -> None:
    """`[VERIFIED]` 2026-08-26, found by a surviving mutant.

    This adapter parses two formats — RSS `<item>` and Atom `<entry>` — through two separate
    construction sites, and a mutation removing the league from only one of them left the
    suite green, because every other test here uses an RSS fixture. Two code paths need two
    tests, or one of them is decoration.
    """
    assert reddit_articles, "fixture produced no articles"
    assert all(article.league == "NBA" for article in reddit_articles)


def test_an_explicit_league_reaches_the_atom_path() -> None:
    """The same override the RSS path honours, asserted where it is separately implemented."""
    atom = (Path(__file__).parent / "fixtures" / "reddit_nba_atom.xml").read_text(
        encoding="utf-8"
    )
    articles = RssNewsAdapter("r/nba", league="NFL").parse(atom)

    assert articles
    assert all(article.league == "NFL" for article in articles)
