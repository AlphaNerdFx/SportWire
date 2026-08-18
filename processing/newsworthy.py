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
from processing.validate import normalise_word, ordinary_words

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
    # `[VERIFIED]` 2026-08-10: "During his NBA career, Bill Russell led the five best
    # defenses ever..." reached a brief. It names no year in the title at all — the 1980
    # reference sits in the body — so only the framing gives it away.
    "during his career",
    "during his nba career",
    "in his career",
    "career retrospective",
)


def _strip_invisible(text: str) -> str:
    """Remove zero-width and directional marks that break prefix matching."""
    return "".join(ch for ch in text if ord(ch) not in _INVISIBLE_CODEPOINTS)


def rejection_reason(article: NewsArticle, now: datetime | None = None) -> str | None:
    """Why an item is not reporting, or None if it is. The reason names the rule that fired.

    `is_newsworthy` is this function asked as a yes/no question. They are one implementation
    because two would drift, and a filter whose log disagreed with its behaviour would be
    worse than one that logged nothing.

    Three rules, all deliberately narrow. Anything ambiguous is kept — `[INFERRED]` a
    borderline item in the brief costs a line, while a wrongly rejected one is invisible, and
    invisible failures are the class this project keeps being bitten by.

    **There was a fourth.** Rule 2 rejected a title naming a finished season outside any
    quotation. `[VERIFIED]` It produced two live false positives and no recorded true
    positive: a current Ballmer story citing 2015, after which it was narrowed rather than
    reconsidered, and then r/nba's `[Charania] After 18 NBA seasons, Russell Westbrook has
    retired…`, dropped for citing his 2017 MVP. `[INFERRED]` The class is not fixable by
    narrowing, because the rule reads a *number* while the other three read a *phrase*: a
    year is evidence of what a piece mentions, never of what it is about, and retirement,
    contract, draft and anniversary reporting all cite years as a matter of course. Removed
    2026-08-13 under TASKS.md P3 option (a); recover it from git history if the drop log
    shows retrospectives returning.
    """
    now = now or datetime.now(timezone.utc)

    # Rule 0 — too old to be news, whatever it says. This one is about the *item*, not its
    # wording, so it catches a feed that has quietly turned into an archive.
    age_hours = (now - article.published_at).total_seconds() / 3600
    if age_hours > MAX_ARTICLE_AGE_HOURS:
        return f"older than {MAX_ARTICLE_AGE_HOURS}h ({age_hours:.0f}h)"

    # Invisible characters are stripped first, or a leading zero-width space defeats the
    # tag match entirely.
    title = _strip_invisible(article.title).strip()

    # Rule 1 — a content-type tag.
    match = _LEADING_TAG.match(title)
    if match and match.group(1).strip().lower() in REJECTED_TAGS:
        return f"content-type tag [{match.group(1).strip()}]"

    # Rule 1b — a phrase announcing the piece is about the past. Checked anywhere in the
    # title, since "on this day" is unambiguous wherever it appears.
    lowered = title.lower()
    for phrase in RETROSPECTIVE_PHRASES:
        if phrase in lowered:
            return f"retrospective phrase {phrase!r}"

    # Rule 3 — posted by the subreddit itself rather than by a reader.
    if _posted_by_a_moderator(article.author):
        return f"subreddit business, posted by {article.author}"

    # Rule 4 — an untagged question on the community feed, which is a discussion prompt.
    if _is_community_discussion(article, title):
        return "community discussion, an untagged question"

    # Rule 5 — a short untagged community post that does not open with a name. Needs the
    # whole batch to know what an ordinary word looks like, so it is applied in
    # `drop_non_news` rather than here, where only one article is in scope.

    return None


# Feeds where readers post, not reporters. `[VERIFIED]` `processing/cluster.py` names the
# same feed in `SOURCE_LIMITS`, for the same underlying reason: its volume and its shape are
# unrelated to how much news there is.
COMMUNITY_SOURCES = frozenset({"r/nba"})


def _is_community_discussion(article: NewsArticle, title: str) -> bool:
    """Whether a community item is a reader asking a question rather than reporting.

    `[VERIFIED]` 2026-08-18 the operator's brief carried *"speculation swirls around Nikola
    Jokic's potential contract, suggesting he cannot sign for the veteran minimum while still
    receiving an additional $300M"*. The source is one r/nba post: *"Can Nikola Jokic now sign
    for veteran minimum and get 300 million on the side for planting few trees?"*, which is a
    reader being sarcastic. Nothing downstream could have saved it. `processing/validate.py`
    grounded `$300M` correctly, because the thread really does say "300 million".

    **This is title-based classification of r/nba, which has failed twice**, and the warnings
    are recorded in `_posted_by_a_moderator` and in `cluster.SOURCE_LIMITS`: a blacklist
    missed untagged chatter, and a whitelist dropped the biggest story of the day. So this is
    deliberately not a keyword rule. It is one structural signal, scoped three ways.

    `[VERIFIED]` Measured across 64 r/nba titles and 175 editorial ones captured 2026-08-17
    and 2026-08-18: **exactly one r/nba title ends in a question mark, and it is this one.**
    Editorial outlets write 18, all of them real analysis pieces, which is why the rule cannot
    be applied to them: "Grades for Schroder trade to Hornets: Which team gets a B-?" and "The
    Spurs have a lot of wings. How will they play them all?" are reporting.

    A reporter tag exempts the item, so `[Charania] Will X sign?` survives. `[INFERRED]` The
    tag means a named journalist is being quoted, and that is the same evidence the existing
    rules already trust in the opposite direction when they reject `[Highlight]`.
    """
    if article.source not in COMMUNITY_SOURCES:
        return False
    if _LEADING_TAG.match(title):
        return False
    return title.rstrip().endswith("?")


def _posted_by_a_moderator(author: str | None) -> bool:
    """Whether an item was posted by the subreddit rather than by a reader.

    `[VERIFIED]` 2026-08-15, from a live fetch of `reddit.com/r/nba/.rss`: the operator's
    brief carried *"the r/nba community thread for content creators to share NBA-related
    work continues every Friday"*, which is `Weekly Friday Self-Promotion and Fan Art
    Thread`, posted by `/u/NBA_MOD`. It is housekeeping for the subreddit, not reporting.

    **This matches on identity, not on language, and that distinction is the whole point.**
    `[VERIFIED]` `SESSION.md` §11 records title-based classification of r/nba failing twice
    — a blacklist missed untagged chatter and a whitelist dropped the biggest story of the
    day. A moderator account is not a pattern to be outwitted: it is a small, stable,
    observable set, and the accounts in it never post news, so this rule cannot cost a story
    the way a keyword can.

    Suffix-matched rather than compared exactly, because the convention is a `_MOD` or
    `Moderator` suffix on the subreddit's name and every league this project might add later
    brings its own. `[UNKNOWN]` Whether any other moderator account posts to a feed this
    project reads — resolve by watching the drop log for this reason.

    Reddit's `/u/` prefix is deliberately **not** stripped. `[VERIFIED]` It cannot affect a
    suffix test — removing characters from the front never changes the end of a string — and
    a normalising version was measured verdict-identical across 149 author shapes (36 real,
    the rest adversarial: doubled slashes, `u/` without the slash, padding, mixed case). It
    was written, it survived mutation because nothing could kill it, and it was removed. That
    is P6 exactly: code that implies a protection it does not provide. **Anything stricter
    than a suffix test — an exact match, an allowlist — has to strip the prefix again.**
    """
    if not author:
        return False
    # `.strip()` and `.lower()` are load-bearing: a padded or upper-case handle fails the
    # match without them, and feed authors are whatever the source chose to write.
    return author.strip().lower().endswith(("_mod", "moderator"))


# A community post this short that does not open with a name is a reader's opinion.
#
# `[VERIFIED]` 2026-08-18 the operator's brief carried *"Fire Adam Silver"*, whose body opens
# "Adam Silver is either a coward, corrupt, or both". That is a rant. It also did real damage
# beyond taking a slot: indexed as the name `{adam, fire, silver}`, it refused the actual
# commissioner (P32).
#
# **Two weak signals, because neither works alone.** `[VERIFIED]` Dropping untagged posts that
# do not open with a name catches all three rants in the sample and also drops **11 real
# items**, including the breaking "Lakers controlling owner Jeanie Buss opposes sale of
# family's stake to Bob Iger, Joshua Kushner". Length alone is no better: real news appears at
# 11 words. Together they are clean.
#
# `[VERIFIED]` Measured across 36 untagged r/nba posts from five captures, the pair drops
# exactly two, both rants — "Fire Adam Silver" (3 words) and "Take away their picks or stop
# pretending the cap exists" (10) — and no real item. The shortest real post that does not
# open with a name is 15 words, so this sits in the gap rather than on an edge.
#
# `[UNKNOWN]` Two positives in 36 is a small sample. Re-measure on a wider capture before
# trusting the threshold, and watch the drop log.
MAX_COMMUNITY_OPINION_WORDS = 12


def _is_community_opinion(article: NewsArticle, ordinary: frozenset[str]) -> bool:
    """Whether a community post is short, untagged, and does not open with a name.

    "Opens with a name" is decided by the corpus, not by a list of verbs. `[INFERRED]` That
    matters because `SESSION.md` §11 records keyword classification of r/nba failing twice,
    and a verb blacklist would be a third attempt at the same thing. Asking whether the batch
    also writes the first word in lower case is P20's mechanism, which this project already
    chose over a hand-written list once.
    """
    if article.source not in COMMUNITY_SOURCES:
        return False

    title = _strip_invisible(article.title).strip()
    if _LEADING_TAG.match(title):
        return False

    words = title.split()
    if not words or len(words) > MAX_COMMUNITY_OPINION_WORDS:
        return False

    first = normalise_word(words[0])
    return bool(first) and first in ordinary


def is_newsworthy(article: NewsArticle, now: datetime | None = None) -> bool:
    """Whether an item is reporting rather than community content."""
    return rejection_reason(article, now) is None


def drop_non_news(
    articles: list[NewsArticle], now: datetime | None = None
) -> list[NewsArticle]:
    """Return only the items that are reporting, logging what was removed and why.

    Logging every drop is not decoration. A filter that silently discards is exactly how a
    brief starts missing things nobody can explain, and this is the only component in the
    pipeline permitted to remove an article.
    """
    kept: list[NewsArticle] = []

    # Learned from the whole batch, because one article cannot say what an ordinary word is.
    ordinary = ordinary_words(articles)

    for article in articles:
        reason = rejection_reason(article, now)
        if reason is None and _is_community_opinion(article, ordinary):
            reason = "community opinion, short and not led by a name"
        if reason is None:
            kept.append(article)
        else:
            # The full title, not a truncated one. `[VERIFIED]` 2026-08-13: an r/nba post
            # reporting Russell Westbrook's retirement was dropped here, and neither the
            # rule nor the offending text could be recovered from the log because the title
            # was cut at 80 characters and no reason was recorded.
            logger.info("dropping non-news item (%s): %r", reason, article.title)

    return kept
