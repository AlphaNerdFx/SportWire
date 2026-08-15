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

from typing import Any

import pytest

from ingestion.rss_news import RssNewsAdapter

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
