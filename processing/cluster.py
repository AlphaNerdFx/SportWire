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
