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

from models.schemas import NewsArticle

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
    }
)

_TIER_ORDER = {"high": 0, "medium": 1, "low": 2}

# Word-boundary matching. Substring matching would classify "signs of improvement" as a
# signing and "designated" as containing "sign".
_WORD_PATTERN = re.compile(r"[a-zà-ÿ'-]+")


def _words(text: str) -> set[str]:
    """Tokenise, emitting hyphenated words both whole and split.

    `[VERIFIED]` Both forms are needed. Keeping hyphens is required for "re-ups"; splitting
    them is required for "ex-fiancée", which otherwise never matches "fiancée" and left a
    child-support story classified medium instead of low.
    """
    tokens: set[str] = set()
    for token in _WORD_PATTERN.findall(text.lower()):
        tokens.add(token)
        if "-" in token:
            tokens.update(part for part in token.split("-") if part)
    return tokens


def classify(article: NewsArticle) -> str:
    """Return "high", "medium" or "low" for one article.

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


def sort_by_priority(articles: list[NewsArticle]) -> list[NewsArticle]:
    """Return every article, reordered high → medium → low. Nothing is dropped.

    `len(output) == len(input)` always holds; this is a permutation, not a filter.
    """
    return sorted(articles, key=lambda article: _TIER_ORDER[classify(article)])
