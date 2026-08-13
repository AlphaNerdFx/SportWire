"""Behaviour tests for the one module permitted to remove an article.

`processing/newsworthy.py` is the highest-risk module in the pipeline, because its failures
are **invisible by construction**. A bug in `priority.py` puts a story in the wrong order and
the operator sees it; a bug here deletes the story and the brief looks entirely normal.

`[VERIFIED]` Five of the eleven bugs recorded in `SESSION.md` §8 were in this module, every
one found by reading live output rather than by a test, and every one able to return silently:

  - a current Ballmer story dropped for citing "2015"          -> `test_year_in_title_*`
  - U+2060 before `[Highlight]` defeated the tag match         -> `test_invisible_*`
  - "On this day" retrospectives reached a brief               -> `test_retrospective_*`
  - Ujiri/Russell retrospectives past the year window          -> `test_retrospective_*`
  - a Westbrook retirement report dropped for citing 2017      -> `test_year_in_title_*`
  - the drop log recorded no reason and truncated at 80 chars  -> `test_drop_log_*`

Every title below is **real**, taken from `logs/sportwire.log` or from the captures recorded
in `SESSION.md`. `CLAUDE.md` §8: assert on behaviour with real-shaped data. A test built from
invented titles would prove the rules match the titles someone imagined while writing them.

Nothing here touches the network, and nothing defines an article shape — `_article` builds a
real `models.schemas.NewsArticle`, so a schema change breaks these tests rather than sliding
past them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from models.schemas import NewsArticle
from processing.newsworthy import (
    MAX_ARTICLE_AGE_HOURS,
    drop_non_news,
    is_newsworthy,
    rejection_reason,
)

# Fixed, so "is this too old" is arithmetic rather than a race against the clock.
# August is deliberate: `_current_season_year` treated pre-October as the previous season,
# and that off-by-one is exactly the kind of thing a summer-only test would never catch.
NOW = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)


def _article(title: str, *, hours_old: float = 2.0) -> NewsArticle:
    """A real NewsArticle with the given title, recent enough to pass the age rule."""
    return NewsArticle(
        article_id=f"id-{abs(hash(title))}",
        title=title,
        url="https://example.com/story",
        summary="",
        published_at=NOW - timedelta(hours=hours_old),
        source="r/nba",
    )


# --- rule 0: age ---------------------------------------------------------------------


def test_item_older_than_the_window_is_dropped() -> None:
    """A feed that has quietly become an archive must not fill the brief.

    `[VERIFIED]` The Athletic's NBA feed carries 100 items whose oldest is 17 days and of
    which exactly one is under 48 hours old. It was rejected as a source, but any feed can
    start behaving this way, and the failure looks like ordinary news.
    """
    stale = _article("Nikola Jokic wins MVP", hours_old=MAX_ARTICLE_AGE_HOURS + 1)
    reason = rejection_reason(stale, NOW)

    assert reason is not None
    assert "older than" in reason


def test_item_inside_the_window_is_kept() -> None:
    """The age rule is a boundary, and boundaries are where off-by-ones live."""
    fresh = _article("Nikola Jokic wins MVP", hours_old=MAX_ARTICLE_AGE_HOURS - 1)

    assert rejection_reason(fresh, NOW) is None


def test_age_rule_fires_regardless_of_wording() -> None:
    """Rule 0 is about the item, not its title — a stale headline is stale even if perfect."""
    stale = _article("[Charania] Trade agreed", hours_old=MAX_ARTICLE_AGE_HOURS + 50)

    assert not is_newsworthy(stale, NOW)


# --- rule 1: content-type tags -------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "[Highlight] Westbrook gets intentionally fouled but still makes the shot!",
        "[Discussion] Who is the most underrated player right now?",
        "[OC] I charted every Curry three this season",
        "[Meme] When your team drafts another centre",
    ],
)
def test_content_type_tag_is_dropped(title: str) -> None:
    """A clip, a chart or a discussion prompt is not reporting at any priority."""
    reason = rejection_reason(_article(title), NOW)

    assert reason is not None
    assert "content-type tag" in reason


@pytest.mark.parametrize(
    "title",
    [
        "[Charania] After 18 NBA seasons, Russell Westbrook has retired.",
        "[TMZ] Lakers sale finalised at record valuation",
        "[PTFO] Inside the Clippers investigation",
    ],
)
def test_reporter_tag_is_kept(title: str) -> None:
    """r/nba brackets two different things, and only one of them is noise.

    `[VERIFIED]` A bracket names either a **content type** (`[Highlight]`) or a **reporter or
    outlet** (`[Charania]`). The second kind marks the fastest news on the feed. A rule that
    rejected all bracketed titles would drop exactly the items worth having.
    """
    assert is_newsworthy(_article(title), NOW)


def test_invisible_character_before_tag_does_not_defeat_the_match() -> None:
    """`[VERIFIED]` 2026-08-08: a real post began with U+2060 WORD JOINER before `[Highlight]`.

    The tag rule anchors to the start of the title, so one invisible codepoint made the match
    fail and the clip reached the brief. Reddit titles are user-typed and carry whatever was
    pasted in. Written as an escape because ruff rejects literal invisibles in source, and
    rightly — nobody reviewing a diff can see them.
    """
    title = (
        "⁠[Highlight] Josh Hart on his friendship with Jalen Brunson⁠: "
        '"I was just changing one of my newborns..."'
    )
    reason = rejection_reason(_article(title), NOW)

    assert reason is not None
    assert "content-type tag" in reason


# --- rule 1b: retrospective phrases ---------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "On this day in Bucks history: Milwaukee signs Bobby Simmons",
        "During his NBA career, Bill Russell led the five best defenses ever",
        "Remember when the Warriors blew a 3-1 lead",
        "Throwback: the 2016 Finals in full",
    ],
)
def test_retrospective_phrase_is_dropped(title: str) -> None:
    """`[VERIFIED]` Both of the first two reached real briefs.

    A retrospective is published *today* about something long past, so neither its timestamp
    nor a content tag gives it away — only the framing does.
    """
    reason = rejection_reason(_article(title), NOW)

    assert reason is not None
    assert "retrospective phrase" in reason


def test_all_time_wording_is_kept() -> None:
    """A title reading "passes Jordan for third all-time" is news, not a retrospective.

    `[VERIFIED]` "all-time" was considered for `RETROSPECTIVE_PHRASES` and deliberately left
    out. This test exists so a future tightening of that list has to break something visible
    before it can remove this class of story.
    """
    assert is_newsworthy(
        _article("LeBron passes Jordan for third on the all-time assists list"), NOW
    )


# --- the deleted rule 2: years ---------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        # The two live false positives that ended the rule.
        (
            "[Charania] After 18 NBA seasons, Russell Westbrook has retired. A legendary "
            "career: NBA's top 75, 2017 league MVP, nine-time All-Star, nine-time "
            "All-NBA, USA Olympic Gold Medalist and the all-time record for triple-doubles."
        ),
        (
            "Pablo Torre on Ballmer's cap circumvention: \"This is not a first-time "
            'offense. In 2015, Ballmer & the Clippers get fined $250k..."'
        ),
        # The shapes that made the class unfixable by narrowing: current reporting cites
        # years as a matter of course.
        "Anthony Davis contract extension, first signed in 2019, faces a decision",
        "Jalen Duren, the 2022 lottery pick, draws sign-and-trade interest",
    ],
)
def test_year_in_title_no_longer_drops_current_reporting(title: str) -> None:
    """Regression guard for TASKS.md P3. **This is the test that must not be deleted.**

    `[VERIFIED]` Rule 2 rejected any title naming a finished season outside a quotation. It
    produced two live false positives and no recorded true positive: a current Ballmer story
    citing 2015, after which it was narrowed rather than reconsidered, and then the Westbrook
    retirement report above, dropped for citing his 2017 MVP.

    `[INFERRED]` The class cannot be fixed by narrowing, because the rule read a *number*
    while rules 0, 1 and 1b read a *phrase*: a year is evidence of what a piece mentions,
    never of what it is about. Retirement, contract, draft and anniversary reporting all cite
    years, which is why this test carries four shapes rather than one.

    Removed 2026-08-13. If it returns, this fails.
    """
    assert is_newsworthy(_article(title), NOW)


def test_removing_rule_2_did_not_weaken_the_other_rules() -> None:
    """The retrospectives Rule 2 was credited with are caught by phrase and tag rules anyway.

    `[VERIFIED]` This was checked against the real drop log before the rule was removed. The
    one item Rule 2 alone caught — an Ujiri/Leonard 2019 story — is the accepted cost, and is
    asserted below rather than hidden, so the trade stays visible in the test suite.
    """
    still_dropped = [
        "[Highlight] 54-year-old Warriors legend Chris Mullin beats Kevin Durant",
        "On this day in Bucks history: Milwaukee signs Bobby Simmons",
        "During his NBA career, Bill Russell led the five best defenses ever",
    ]
    for title in still_dropped:
        assert not is_newsworthy(_article(title), NOW), title

    # The known, accepted regression from deleting Rule 2 (TASKS.md P3 option a). It reaches
    # the brief, capped by cluster.py and ranked low by priority.py. If a future rule catches
    # it again *without* re-dropping the four titles above, flip this assertion.
    accepted_cost = (
        "After Leonard signed with the Clippers in 2019, Masai Ujiri was asked"
    )
    assert is_newsworthy(_article(accepted_cost), NOW)


# --- drop_non_news: the collection behaviour and its log ------------------------------


def test_drop_non_news_returns_only_survivors_in_order() -> None:
    """Filtering must not reorder. `priority.py` sorts; this module only removes."""
    articles = [
        _article("[Charania] Westbrook retires"),
        _article("[Highlight] a dunk"),
        _article("Lakers sale finalised"),
        _article("On this day in Bucks history"),
    ]

    kept = drop_non_news(articles, NOW)

    assert [a.title for a in kept] == [
        "[Charania] Westbrook retires",
        "Lakers sale finalised",
    ]


def test_drop_log_records_the_rule_and_the_untruncated_title(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`[VERIFIED]` 2026-08-13: the Westbrook drop could not be diagnosed from the log.

    No reason was recorded and the title was cut at 80 characters, so neither the rule that
    fired nor the offending text could be recovered. A filter that discards silently is how a
    brief starts missing things nobody can explain.
    """
    long_title = (
        "[Highlight] Josh Hart on his friendship with Jalen Brunson: I was just changing "
        "one of my newborns, and I just look at Jalen like 'Yo, my son's packing'"
    )
    assert len(long_title) > 80, (
        "this test is pointless unless the title exceeds 80 chars"
    )

    with caplog.at_level(logging.INFO, logger="processing.newsworthy"):
        drop_non_news([_article(long_title)], NOW)

    assert len(caplog.records) == 1
    logged = caplog.records[0].getMessage()

    assert "content-type tag" in logged, "the log must name the rule that fired"
    assert long_title in logged, "the log must carry the full title, not a truncation"


def test_nothing_is_dropped_from_an_empty_list() -> None:
    """The offseason case: no articles is normal, not an error."""
    assert drop_non_news([], NOW) == []
