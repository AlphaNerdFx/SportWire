"""Drops feed items that are not news at all.

**This is the one place articles are removed rather than reordered**, and the distinction
from `processing/priority.py` is deliberate. Priority *sorts*: an off-court story still
reaches the brief, just last. This module *rejects*: a highlight clip from 2017 is not a
low-priority news item, it is not a news item.

`[VERIFIED]` 2026-08-08 — the need appeared once r/nba was added. Of 25 posts in one live
capture, roughly ten were highlight clips, retrospectives or discussion threads, including
"[Highlight] 54-year-old Warriors legend Chris Mullin beats Kevin Durant" (2017) and
"[Highlight] Russell Westbrook put up 16 points..." (a 2025 playoff game). Both are recent
*posts* about old *events* — the feed's timestamp says nothing about when the thing happened.

Editorial feeds do not trip these rules; ESPN and CBS syndicate finished articles rather than
community submissions. In practice this only filters Reddit, but it is written against
article shape rather than source name so a future community feed gets the same treatment.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

# Bracket tags naming a **content type**. These are clips, images and discussion prompts —
# never reporting.
#
# The tag is a genuinely good signal because r/nba's convention distinguishes two kinds of
# bracket: a content type like [Highlight], and a **reporter or outlet** like [Charania],
# [TMZ] or [PTFO]. `[VERIFIED]` The second kind marks real news and is deliberately kept.
REJECTED_TAGS = frozenset(
    {
        "highlight",
        "highlights",
        "oc",
        "original content",
        "image",
        "video",
        "gif",
        "meme",
        "humor",
        "discussion",
        "serious",
        "question",
        "poll",
        "misc",
        "off topic",
        "throwback",
        "retrospective",
    }
)

_LEADING_TAG = re.compile(r"^\s*\[([^\]]{1,32})\]")

# Zero-width and invisible characters. `[VERIFIED]` 2026-08-08: a real post began with
# U+2060 WORD JOINER before "[Highlight]", which defeated the tag match entirely. Reddit
# titles are user-typed and carry whatever was pasted in.
# Written as escapes rather than the characters themselves: ruff rejects literal invisibles
# in source, and rightly — nobody reviewing a diff can see them.
_INVISIBLE_CODEPOINTS = frozenset(
    {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF}
)

# Any four-digit year that could name a past season.
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")

# How far into a title a past year must appear to be treated as the *subject* rather than
# context. `[VERIFIED]` 2026-08-08: this rule wrongly dropped "Pablo Torre on Ballmer's cap
# circumvention: 'This is not a first-time offense. In 2015, Ballmer & the Clippers get
# fined $250k...'" — current reporting that cites a past incident. A post genuinely *about*
# an old event says so up front ("From 1987-1998, every team that won the finals..."), while
# a current story reaches its historical aside mid-sentence.
_YEAR_SUBJECT_WINDOW = 30

# Oldest an item may be and still count as news.
#
# `[VERIFIED]` 2026-08-09 this is not hypothetical. The Athletic's NBA feed carries 100
# items whose oldest is **17 days** and of which exactly one is under 48 hours old — an
# archive wearing a news feed's clothes. It was rejected as a source, but a feed can start
# behaving that way at any time and the failure is invisible: old articles simply appear in
# the brief looking current.
#
# Seven days rather than two, because the dedup window is 168 hours: anything older than
# that could be re-delivered as if new, and anything newer has either already been sent or
# is legitimately recent. Tying the two together means an item can never be both "too old
# to report" and "forgotten enough to resend".
MAX_ARTICLE_AGE_HOURS = 168

# Phrases that announce a piece is about the past, whatever its publication date.
#
# `[VERIFIED]` 2026-08-10: "On this day in Bucks history: Milwaukee signs Bobby Simmons"
# reached a brief from Yahoo Sports. It carries no content tag and no year in its opening,
# so neither existing rule saw it — but it is a retrospective published today.
#
# Deliberately short and unambiguous. Phrases like "all-time" were considered and left out:
# "passes Jordan for third all-time" is current news, and a rule that drops it would remove
# exactly the kind of story worth reporting.
RETROSPECTIVE_PHRASES = (
    "on this day",
    "years ago",
    "throwback",
    "flashback",
    "remember when",
    "this day in",
)


def _strip_invisible(text: str) -> str:
    """Remove zero-width and directional marks that break prefix matching."""
    return "".join(ch for ch in text if ord(ch) not in _INVISIBLE_CODEPOINTS)


def _current_season_year(now: datetime | None = None) -> int:
    """The starting year of the season in progress.

    An NBA season spans two calendar years and is named by the first, so anything before
    October belongs to the previous year's season.
    """
    now = now or datetime.now(timezone.utc)
    return now.year - 1 if now.month < 10 else now.year


def is_newsworthy(article: NewsArticle, now: datetime | None = None) -> bool:
    """Whether an item is reporting rather than community content.

    Three rules, all deliberately narrow. Anything ambiguous is kept — `[INFERRED]` a
    borderline item in the brief costs a line, while a wrongly rejected one is invisible, and
    invisible failures are the class this project keeps being bitten by.
    """
    now = now or datetime.now(timezone.utc)

    # Rule 0 — too old to be news, whatever it says. This one is about the *item*, not its
    # wording, so it catches a feed that has quietly turned into an archive.
    age_hours = (now - article.published_at).total_seconds() / 3600
    if age_hours > MAX_ARTICLE_AGE_HOURS:
        return False

    # Invisible characters are stripped first, or a leading zero-width space defeats the
    # tag match entirely.
    title = _strip_invisible(article.title).strip()

    # Rule 1 — a content-type tag.
    match = _LEADING_TAG.match(title)
    if match and match.group(1).strip().lower() in REJECTED_TAGS:
        return False

    # Rule 1b — a phrase announcing the piece is about the past. Checked anywhere in the
    # title, since "on this day" is unambiguous wherever it appears.
    lowered = title.lower()
    if any(phrase in lowered for phrase in RETROSPECTIVE_PHRASES):
        return False

    # Rule 2 — the title *opens* by naming a season that has already finished, which marks
    # the post as being about that season. Only the title is searched, and only its first
    # characters: a current story citing an old incident mid-sentence is still current.
    season = _current_season_year(now)
    opening = title[:_YEAR_SUBJECT_WINDOW]
    is_about_a_past_season = any(int(year) < season for year in _YEAR.findall(opening))

    return not is_about_a_past_season


def drop_non_news(
    articles: list[NewsArticle], now: datetime | None = None
) -> list[NewsArticle]:
    """Return only the items that are reporting, logging what was removed and why.

    Logging every drop is not decoration. A filter that silently discards is exactly how a
    brief starts missing things nobody can explain, and this is the only component in the
    pipeline permitted to remove an article.
    """
    kept: list[NewsArticle] = []

    for article in articles:
        if is_newsworthy(article, now):
            kept.append(article)
        else:
            logger.info("dropping non-news item: %r", article.title[:80])

    return kept
