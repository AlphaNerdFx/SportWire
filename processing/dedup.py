"""Removes items already delivered, and near-identical items within a single run.

Two passes, deliberately not three:

  Pass 1 — exact match on the item's stable id against what previous runs already sent.
           This is the one that matters most: without it every run re-sends the entire
           feed, because ESPN's RSS still lists the same fifteen items four hours later.

  Pass 2 — near-identical titles inside one batch, catching the same story carried by two
           outlets under slightly different headlines.

  Pass 3 — semantic similarity. **Not built, and declined on evidence rather than deferred
           on principle.** ADR-005 says to build it once a real near-duplicate pair is
           captured that `SequenceMatcher` missed. Measured against the captured ESPN
           fixture, the closest pair scores 0.550 ("Mitchell and Coco Jones tie knot" vs
           "Jaylen Brown says ... wedding sparked desire for love") while two genuinely
           unrelated stories score 0.438 — an 0.11 margin, tuned on one example. And that
           pair is not a duplicate: the second carries Jaylen Brown's own comments, so
           suppressing it deletes information rather than removing redundancy. Related
           coverage is also precisely what the planned summarization step (M7) merges
           naturally.

Every function here is pure: the set of already-seen items is passed in, never read from a
database. That keeps this logic testable with no storage layer and lets the caller decide
where "seen" comes from.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from models.schemas import GameData, NewsArticle

logger = logging.getLogger(__name__)

# `[VERIFIED]` 2026-08-06, measured once CBS Sports was added as a second feed — this value
# was previously `[UNKNOWN]` pending exactly that. ~~Across **612 real cross-source pairs**
# (17 ESPN × 36 CBS), the highest similarity was **0.439**.~~ Zero pairs would collapse at any
# threshold down to 0.50, and below that genuinely unrelated stories begin merging: "Sources:
# Knicks executive Rosas leaving team" and "Why the 76ers have the Celtics and Knicks to
# thank for landing LeBron" score 0.420.
#
# **Corrected 2026-08-13 (TASKS.md P8).** `[VERIFIED]` Re-measured from the committed
# fixtures: **540 pairs (15 ESPN × 36 CBS), highest similarity 0.425.** The struck figures
# came from a *live* ESPN fetch of 17 items; the saved fixture holds 15, so nothing in this
# repository reproduces them. The conclusion is unchanged and slightly stronger — 0.425 is
# further from 0.85 than 0.439 — but a load-bearing number was recorded from data that was
# never committed, which is the failure `OPERATING_RULES.md` §2 exists to prevent, benign
# this time.
#
# `tests/test_dedup.py::test_real_cross_source_pairs_do_not_collapse` now recomputes this on
# every run, so the threshold is guarded by arithmetic over real headlines rather than by
# this comment.
#
# `[INFERRED]` The assumption behind pass 2 was wrong in a structural way: outlets write
# their own headlines rather than syndicating one. Two outlets covering the same signing
# produce completely different strings, so lexical matching cannot pair them and should not
# try. The threshold stays at 0.85 not because it was tuned to be right, but because nothing
# in real data reaches it — lowering it can only cause false merges.
#
# Pass 2 therefore earns its place only for genuine near-identical republication (the same
# outlet reposting, or a wire item carried verbatim), which has not yet been observed.
DEFAULT_TITLE_SIMILARITY = 0.85


def normalise_title(title: str) -> str:
    """Lowercase and collapse whitespace, so trivial formatting differences do not count."""
    return " ".join(title.lower().split())


def deduplicate_articles(
    articles: list[NewsArticle],
    seen_article_ids: set[str],
    similarity_threshold: float = DEFAULT_TITLE_SIMILARITY,
) -> list[NewsArticle]:
    """Drop articles already delivered, then collapse near-identical titles in this batch.

    Input order is preserved and the first occurrence of a near-duplicate group wins.
    """
    kept: list[NewsArticle] = []

    for article in articles:
        # Pass 1 — already delivered in an earlier run.
        if article.article_id in seen_article_ids:
            continue

        # Pass 2 — near-identical to something already kept from this same batch.
        normalised = normalise_title(article.title)
        duplicate_of = _find_similar(normalised, kept, similarity_threshold)
        if duplicate_of is not None:
            logger.info(
                "dropping %r as a near-duplicate of %r",
                article.title,
                duplicate_of.title,
            )
            continue

        kept.append(article)

    return kept


def deduplicate_games(
    games: list[GameData],
    seen_state_hashes: set[str],
) -> list[GameData]:
    """Drop games whose state has not changed since they were last delivered.

    Matching is on `state_hash`, not `game_id`: a game reported at half time and again as
    final is *not* a duplicate, because the score moved. Only an unchanged game is dropped.
    """
    return [game for game in games if game.state_hash not in seen_state_hashes]


def _find_similar(
    normalised_title: str,
    kept: list[NewsArticle],
    threshold: float,
) -> NewsArticle | None:
    """Return the first kept article whose title is at least `threshold` similar."""
    for existing in kept:
        ratio = SequenceMatcher(
            None, normalised_title, normalise_title(existing.title)
        ).ratio()
        if ratio >= threshold:
            return existing
    return None
