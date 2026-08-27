"""Ranks articles high / medium / low so the most important news is written about first.

**This sorts. It never filters.** Every article that goes in comes out — the operator was
explicit that nothing should be dropped. Order is the only thing that changes.

Why this exists rather than asking the model to prioritise:

`[VERIFIED]` 2026-08-06 — `llama3.2:3b` was given all 15 fixture articles with a prompt
stating "lead with roster and on-court news; mention off-court items only in passing". It
opened with a child-support filing and closed with LeBron James changing teams. Two prompt
revisions did not move it. `[INFERRED]` A 3B model will not reliably rank sports news by
editorial importance, and fine-tuning one to do so would require hand-written training data,
a GPU, and a model *larger* on disk than the one it replaces.

The model puts the biggest story last because it is handed to it last. So hand it over
first. Sorting is deterministic, free, testable against the fixture, and — unlike a
fine-tuned ranking — inspectable: anyone can read the word lists below and predict the
output.

A stable sort is used deliberately, so within a tier the source's own ordering survives.
ESPN orders its feed editorially, and that is a better tiebreaker than anything invented here.
"""

from __future__ import annotations

import re

from models.schemas import GameData, NewsArticle

# Roster and on-court operations — what the brief exists to report.
HIGH_SIGNALS = frozenset(
    {
        "sign",
        "signs",
        "signed",
        "signing",
        "re-up",
        "re-ups",
        "extension",
        "extends",
        "trade",
        "trades",
        "traded",
        "waive",
        "waived",
        "release",
        "released",
        "acquire",
        "acquired",
        "joins",
        "landed",
        "leaving",
        "departure",
        "exits",
        "hired",
        "fired",
        "injury",
        "injured",
        "surgery",
        "sidelined",
        "returns",
        "cleared",
        "suspended",
        "suspension",
        "retires",
        "retirement",
        "agency",
        "agent",
        "contract",
        "deal",
        "pursuit",
    }
)

# Off-court and personal-life items. Still delivered — just last.
LOW_SIGNALS = frozenset(
    {
        "wedding",
        "married",
        "marries",
        "knot",
        "engaged",
        "fiancee",
        "fiancée",
        "divorce",
        "girlfriend",
        "boyfriend",
        "instagram",
        "tiktok",
        "podcast",
        "restaurant",
        "fashion",
        "album",
        "romance",
        # Births, which the list covered for every other family occasion but not this one.
        # `[VERIFIED]` 2026-08-27: "Luka signs a baby, the lakers visit the maternity ward of
        # the hospital" was classified **high**, the same tier as a max contract, because it
        # contains "signs". It then competed for one of the twelve story slots against actual
        # roster news. This is the exact shape the docstring below already describes: an
        # article about a player's private life that happens to use a transaction word.
        #
        # `[VERIFIED]` Only "baby" and "maternity" occur in the 109 captured articles, both in
        # that one post; the rest are `[INFERRED]` siblings. "born" was measured too and
        # **left out** on judgement rather than evidence: it happens to be safe in this corpus
        # and a bio saying "born in Athens" would be a false low.
        "baby",
        "babies",
        "newborn",
        "maternity",
        "pregnant",
        "pregnancy",
    }
)

_TIER_ORDER = {"high": 0, "medium": 1, "low": 2}

# Word-boundary matching. ~~Substring matching would classify "signs of improvement" as a
# signing and "designated" as containing "sign".~~
#
# **Corrected 2026-08-13 (TASKS.md P7).** Only the second example holds. `[VERIFIED]`
# `classify()` on the three real shapes: "Coach praises the designated starter" → medium, so
# word matching does fix that one; "Jokic signs a max extension" → high, correct; but
# **"Curry shows signs of improvement in return" → high**, which the original comment claimed
# this pattern prevents. It cannot: `signs` *is* a standalone word there, so no
# boundary-matching scheme can tell it apart from a transaction.
#
# `[INFERRED]` Left as-is deliberately. The cost is one story ranked high that should be
# medium, in a list nothing is dropped from, and this project's record (P3, twice) is that
# narrowing a keyword rule produces invisible false negatives — a worse error than a visible
# false positive.
_WORD_PATTERN = re.compile(r"[a-zà-ÿ'-]+")


def _words(text: str) -> set[str]:
    """Tokenise, emitting hyphenated and possessive words in every useful form.

    Three forms are needed, and each was added because a real headline failed without it:

    - **Whole, hyphen intact** — `[VERIFIED]` required for "re-ups".
    - **Hyphen split** — `[VERIFIED]` required for "ex-fiancée", which otherwise never
      matches "fiancée" and left a child-support story classified medium instead of low.
    - **Apostrophe stripped** — `[VERIFIED]` required for possessives. "Why the Warriors'
      pursuit of LeBron never got serious" tokenised as `warriors'` and failed to match the
      team keyword `warriors`, so an article about a team that played was not recognised
      as relevant.
    """
    tokens: set[str] = set()
    for token in _WORD_PATTERN.findall(text.lower()):
        tokens.add(token)
        if "-" in token:
            tokens.update(part for part in token.split("-") if part)
        if "'" in token or "’" in token:
            # Possessives and contractions: "warriors'" -> "warriors", "mavs'" -> "mavs".
            tokens.add(token.replace("'", "").replace("’", ""))
            tokens.add(token.split("'")[0].split("’")[0])
    return {token for token in tokens if token}


def team_keywords(games: list[GameData]) -> set[str]:
    """Distinctive one-word names of every team that played, lowercased.

    `[VERIFIED]` Every NBA team's `full_name` ends in a unique nickname — "Los Angeles
    Lakers" → "lakers", "Portland Trail Blazers" → "blazers", "Oklahoma City Thunder" →
    "thunder". Matching on that last word avoids both the city (shared by several teams) and
    the full string (which articles rarely spell out).
    """
    keywords: set[str] = set()
    for game in games:
        for name in (game.home_team, game.away_team):
            parts = name.lower().split()
            if parts:
                keywords.add(parts[-1])
    return keywords


def classify(article: NewsArticle) -> str:
    """Return "high", "medium" or "low" for one article, on subject matter alone.

    Low beats high when both appear: an article about a player's wedding that happens to use
    the word "deal" is still a wedding story. `[INFERRED]` Misfiling an off-court item as
    important is more visible in a brief than the reverse.
    """
    words = _words(f"{article.title} {article.summary}")

    if words & LOW_SIGNALS:
        return "low"
    if words & HIGH_SIGNALS:
        return "high"
    return "medium"


def mentions_team_in_play(article: NewsArticle, tonight: set[str]) -> bool:
    """Whether the article names a team that played in this run's games."""
    if not tonight:
        return False
    return bool(_words(f"{article.title} {article.summary}") & tonight)


def sort_by_priority(
    articles: list[NewsArticle], games: list[GameData] | None = None
) -> list[NewsArticle]:
    """Return every article, reordered by subject, then by tonight's relevance.

    `len(output) == len(input)` always holds; this is a permutation, not a filter.

    Passing `games` promotes articles naming a team that played — but **only within their
    tier**, never across one. `[VERIFIED]` 2026-08-07 an earlier version made "tonight" a
    top-level tier and put "Doncic's ex-fiancée pulls child support petition" first, because
    its summary mentions the Lakers. Relevance to tonight does not turn an off-court story
    into roster news; it only breaks ties among stories of equal kind.

    `[INFERRED]` This is what makes a high-volume community feed usable. r/nba carries far
    more than an editorial outlet and most of it is unrelated to any given night, but "does
    this name a team that played?" is an exact filter the pipeline already has for free. It
    also lifts individual-performance posts ("Jokić drops 50 in the win over the Nets") which
    carry no roster vocabulary and would otherwise sit in the middle of the pack.
    """
    tonight = team_keywords(games) if games else set()

    return sorted(
        articles,
        key=lambda article: (
            _TIER_ORDER[classify(article)],
            not mentions_team_in_play(article, tonight),
        ),
    )
