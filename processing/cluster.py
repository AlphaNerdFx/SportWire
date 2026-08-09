"""Groups articles that are covering the same story, so a brief reports it once.

Different from `processing/dedup.py`, which catches the same *document* twice, and from
near-identical titles, which outlets never produce because each writes its own headline.
This catches many outlets and many users covering **one event** in completely different
words.

`[VERIFIED]` 2026-08-08 — the need appeared with r/nba. One live capture of 25 posts included
**seven** about the same Kawhi Leonard sponsorship story and three about one Jaylen Brown
interview. Title similarity cannot pair them: "BREAKING: Kawhi Leonard had a hidden
sponsorship" and "Per Pablo Torre, Kawhi Leonard also had a deal with Daktronics" share
almost no text.

**The grouping signal is rarity, not overlap.** `[VERIFIED]` Across 73 live articles the name
"James" appeared in 21 of them, spread over unrelated stories — grouping on a shared name
would have merged most of the brief into one cluster. Meanwhile "Daktronics" (3), "Ballmer"
(3) and "Pablo Torre" (3) each appear only within the Kawhi story. A name that appears
everywhere identifies a topic; a name that appears rarely identifies an event.

That is the intuition behind inverse document frequency, applied to one batch rather than a
corpus — no library, no model, and inspectable: anyone can print the name counts and predict
the clusters.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

# A name appearing in more than this fraction of the batch is treated as a recurring subject
# rather than a story marker. `[VERIFIED]` "James" reached 29% and "Warriors" 8%; the Kawhi
# story's distinctive names sat at 4%.
MAX_NAME_FREQUENCY = 0.08

# How many distinctive names two articles must share to count as one story. One is too
# weak — two unrelated Warriors items would merge — and the real clusters comfortably share
# several, since a story about Kawhi and Daktronics tends to name both.
MIN_SHARED_NAMES = 2

# Capitalised words and sequences of them: people, teams, companies.
_NAME = re.compile(r"\b[A-Z][a-zà-ÿ']+(?:\s+[A-Z][a-zà-ÿ']+)*")

# Capitalised because they start a sentence or are common vocabulary, not because they name
# anything. Left in, they would attach to every article.
_NOT_NAMES = frozenset(
    {
        "the",
        "a",
        "an",
        "in",
        "on",
        "of",
        "for",
        "and",
        "but",
        "per",
        "why",
        "how",
        "what",
        "when",
        "who",
        "nba",
        "breaking",
        "sources",
        "report",
        "reportedly",
        "source",
        "new",
        "his",
        "her",
        "this",
        "that",
        "it",
        "is",
        "was",
        "after",
        "before",
        "with",
        "from",
        "says",
        "said",
        "first",
        "last",
        "next",
        "one",
        "two",
    }
)


def _names(article: NewsArticle) -> set[str]:
    """Distinctive-looking proper nouns in a title.

    Only the title. `[INFERRED]` Descriptions name far more entities in passing — a match on
    something mentioned once mid-paragraph is usually coincidence, not a shared subject.
    """
    found: set[str] = set()

    for match in _NAME.findall(article.title):
        words = [w for w in match.split() if w.lower() not in _NOT_NAMES]
        if not words:
            continue
        name = " ".join(words)
        # Two characters is an initial or an abbreviation, not an identifier.
        if len(name) > 3:
            found.add(name)

    return found


# How many stories a single source may *lead* in one brief. Only community feeds are
# capped, and only because their volume is unrelated to how much news there is.
#
# `[VERIFIED]` 2026-08-09 title-pattern filtering hit its limit on r/nba. A blacklist misses
# untagged chatter ("announcers thank Russell Westbrook for bricking the game"); a whitelist
# requiring a news marker kept a HoopsHype listicle and a Dirk Nowitzki highlight while
# dropping the Pablo Torre/Ballmer reporting, which was the biggest story in the feed. The
# distinguishing information is not in the title, so the fix is structural rather than
# smarter rules: bound the volume instead of trying to classify it.
#
# `[INFERRED]` Three is judged, not measured. It is enough for the case that justifies the
# source — breaking news that reaches Reddit before the outlets write it up — while leaving
# the brief editorial.
SOURCE_LIMITS: dict[str, int] = {"r/nba": 3}

# Ceiling applied to every other source, so no feed can take the whole brief simply by
# publishing more.
#
# `[VERIFIED]` 2026-08-10: this is not only a community-feed problem. Yahoo Sports publishes
# 50 items a day, all under 48 hours old, while ESPN and CBS produce one or two NBA stories.
# After deduplication strips what has already been sent, nearly every *remaining* item is
# Yahoo — a run fetching 99 articles left 51 new ones, dominated by the fastest publisher.
# Ranking cannot fix that: the items are individually fine, there are just far more of them.
#
# `[INFERRED]` Four leaves room for every source to appear within a twelve-story brief while
# guaranteeing none can fill it.
DEFAULT_SOURCE_LIMIT = 4


def limit_per_source(
    groups: list[list[NewsArticle]],
    limits: dict[str, int] | None = None,
    default_limit: int = DEFAULT_SOURCE_LIMIT,
) -> list[list[NewsArticle]]:
    """Cap how many stories each source may lead, keeping the highest-ranked.

    Applied to **groups**, so it counts stories rather than articles — and it counts only
    the source that *leads* each group. An article already merged with another outlet's
    coverage does not count against the cap, because the merge is what corroborates it and
    the story is being reported by whoever leads.

    Every source is capped: `limits` overrides the ceiling for named ones, `default_limit`
    applies to the rest. Passing `default_limit=0` disables the general ceiling.

    Expects input ordered most-important-first, so the surviving stories are the best ones
    rather than the earliest.
    """
    limits = SOURCE_LIMITS if limits is None else limits

    used: Counter[str] = Counter()
    kept: list[list[NewsArticle]] = []
    dropped: Counter[str] = Counter()
    applied: dict[str, int] = {}

    for group in groups:
        source = group[0].source
        cap = limits.get(source, default_limit)

        if cap and used[source] >= cap:
            dropped[source] += 1
            applied[source] = cap
            continue

        used[source] += 1
        kept.append(group)

    for source, count in dropped.items():
        logger.info(
            "capped %s at %d stories; %d further stories not shown",
            source,
            applied[source],
            count,
        )

    return kept


def group_related(
    articles: list[NewsArticle],
    max_name_frequency: float = MAX_NAME_FREQUENCY,
    min_shared_names: int = MIN_SHARED_NAMES,
) -> list[list[NewsArticle]]:
    """Cluster articles covering one story. Input order is preserved within and between groups.

    Every article appears in exactly one group, so `sum(len(g) for g in groups) == len(articles)`
    always holds. This does not drop anything — the caller decides what to show, which keeps
    the "only one module removes articles" rule intact (`processing/newsworthy.py`).

    The first article in each group is the highest-ranked one, provided the input was sorted
    by `processing/priority.py`.
    """
    if len(articles) < 2:
        return [[article] for article in articles]

    names_by_index = [_names(article) for article in articles]

    # How many articles each name appears in — the document frequency.
    frequency: Counter[str] = Counter()
    for names in names_by_index:
        frequency.update(names)

    ceiling = max(1, int(len(articles) * max_name_frequency))
    distinctive = [
        {name for name in names if frequency[name] <= ceiling}
        for names in names_by_index
    ]

    groups: list[list[NewsArticle]] = []
    group_names: list[set[str]] = []

    for index, article in enumerate(articles):
        marks = distinctive[index]
        joined = None

        if marks:
            for position, existing in enumerate(group_names):
                if len(marks & existing) >= min_shared_names:
                    joined = position
                    break

        if joined is None:
            groups.append([article])
            group_names.append(set(marks))
        else:
            groups[joined].append(article)
            # Widen the group's fingerprint so a third article matching either of the first
            # two still lands here.
            group_names[joined] |= marks

    multi = [g for g in groups if len(g) > 1]
    if multi:
        logger.info(
            "grouped %d articles into %d stories (%d multi-source)",
            len(articles),
            len(groups),
            len(multi),
        )

    return groups
