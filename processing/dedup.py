"""Removes items already delivered, and near-identical items within a single run.

Two passes, deliberately not three:

  Pass 1 — exact match on the item's stable id against what previous runs already sent.
           This is the one that matters most: without it every run re-sends the entire
           feed, because ESPN's RSS still lists the same fifteen items four hours later.

  Pass 2 — near-identical titles inside one batch, catching the same story carried by two
           outlets under slightly different headlines.

  Pass 3 — the same *story* told again by a later article, added 2026-09-04 for P68. Passes 1
           and 2 both miss it: a new report of yesterday's news has a new id, and yesterday's
           article is not in today's batch. See `drop_repeated_stories`.

  Pass 4 — semantic similarity. **Not built, and declined on evidence rather than deferred
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
from processing.cluster import MIN_SHARED_NAMES, story_names

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


# How far back a story is remembered when deciding whether it is being told again.
#
# `[VERIFIED]` 2026-09-04, measured over the 371 articles delivered since 08-28. The window is
# the whole trade-off, so it was chosen from the numbers rather than from taste:
#
#     8h    3 drops (0.8%)      12h   11 (3.0%)      24h   13 (3.5%)
#     48h  19 drops (5.1%)     168h   31 (8.4%)
#
# `[INFERRED]` 24 hours is where the operator's actual complaint lives. He reported the NBA's
# Clippers ruling arriving in four consecutive briefs, which is a same-day repetition, and a
# week-long window instead starts suppressing stories that genuinely return later with news.
REPEAT_WINDOW_HOURS = 24


def drop_repeated_stories(
    articles: list[NewsArticle],
    delivered_story_names: list[frozenset[str]],
    min_shared_names: int = MIN_SHARED_NAMES,
) -> list[NewsArticle]:
    """Drop an article retelling a story already delivered, unless it names someone new.

    `[VERIFIED]` 2026-09-04, reported by the operator from reading real briefs: *"clippers news
    keep getting repeated (I'm not talking about Gillian Zucker that part is new)"*. Four
    consecutive basketball briefs carried the NBA's ruling against the Clippers.

    **The exception is the whole design, and the operator drew it.** Suppressing everything
    about a story already sent would have deleted the Gillian Zucker revelation, which was the
    genuine next chapter. So an article survives when it carries **a name that has not been
    delivered with that story**, and is dropped only when it says the same thing about the same
    people.

    Sameness is `processing/cluster.py`'s rule, reused rather than reinvented: two articles are
    one story when their titles share `MIN_SHARED_NAMES` distinctive names. `[INFERRED]` A
    second definition of "the same story" in a second module is how two modules come to
    disagree, which is what `canonical_team` was moved to `names.py` to prevent.

    `[VERIFIED]` Measured over the 371 articles delivered since 2026-08-28: **13 dropped, 3.5%**
    at the 24-hour window. It catches what was reported — the Clippers ruling repeating, the
    Tacko Fall signing arriving twice, the Duren standoff restated as "still" — and it keeps the
    Zucker article.

    `[UNKNOWN]` **Three or four of those 13 are wrong and this is not hidden.** A genuine next
    step that introduces no new name reads as a repeat: *"Joey Porter Jr may request trade from
    Steelers"* after a story about his contract dispute, *"Cowboys to re-sign QB Joe Milton"*
    after he cleared waivers. Telling "the same event reported twice" from "the next event in
    the same story" needs meaning, not names. **Every drop is logged for that reason** — this
    module's failures are otherwise invisible, which is the class of bug this project keeps
    paying for.
    """
    if not delivered_story_names:
        return list(articles)

    kept: list[NewsArticle] = []
    for article in articles:
        names = story_names(article)
        if len(names) < min_shared_names:
            kept.append(article)
            continue

        same_story = [
            delivered
            for delivered in delivered_story_names
            if len(names & delivered) >= min_shared_names
        ]
        if not same_story:
            kept.append(article)
            continue

        already_known: set[str] = set().union(*same_story)
        new_names = names - already_known
        if new_names:
            logger.info(
                "keeping %r: retells a delivered story but names %s",
                article.title,
                ", ".join(sorted(new_names)),
            )
            kept.append(article)
            continue

        logger.info(
            "dropping %r: the same story was delivered, and it names nobody new",
            article.title,
        )

    return kept
