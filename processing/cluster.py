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
from processing.names import canonical_team
from processing.validate import comparable

logger = logging.getLogger(__name__)

# A name appearing in more than this fraction of the batch is treated as a recurring subject
# rather than a story marker. `[VERIFIED]` "James" reached 29% and "Warriors" 8%; the Kawhi
# story's distinctive names sat at 4%.
MAX_NAME_FREQUENCY = 0.08

# How many distinctive names two articles must share to count as one story. One is too
# weak — two unrelated Warriors items would merge — and the real clusters comfortably share
# several, since a story about Kawhi and Daktronics tends to name both.
MIN_SHARED_NAMES = 2

# The rarity ceiling never drops below this, however small the batch.
#
# `[VERIFIED]` 2026-08-15 (TASKS.md P19). `MAX_NAME_FREQUENCY` is a *share of the batch*, and
# that is self-defeating at the moment it matters most: the more outlets cover a story, the
# less distinctive its own name becomes. A live capture carried the Schröder trade in 10 of
# 109 articles, with `Hornets` in 6, `Cavaliers` in 4 and `Tre Mann` in 4. The 08:00 run
# grouped 48 articles after dedup, giving `int(48 * 0.08) = 3` — which discards *every one of
# those names*, including the player's own, and the story took four separate slots in one
# brief. The same story on a 109-article batch (ceiling 8) merged into a single group of 5.
# Same code, same story, different batch size.
#
# `[VERIFIED]` Five, measured rather than judged, sweeping the ceiling over that capture:
# the story reaches a group of 2 at ceiling 3 or 4 and its full group of 5 at ceiling 5.
# Across batches of 24, 36, 48, 60, 80 and 109 a floor of 5 is **inert at 80 and above** —
# the proportional ceiling is already higher — and every merge it newly creates was read by
# hand: all of them the Schröder trade, **no false merges at any size**. Floor 6 was
# identical in every row, so 5 is the cheaper of two equal answers.
#
# `[VERIFIED]` This reverses P9, which chose to log the degenerate case rather than fix it,
# on the grounds that raising the ceiling "cannot cause a false merge" was unproven. It is
# now measured. See `test_a_small_batch_still_groups_a_widely_covered_story`.
MIN_RARITY_CEILING = 5

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


def story_names(article: NewsArticle) -> set[str]:
    """Distinctive-looking proper nouns in a title: what identifies the story it tells.

    **Public since 2026-09-04, and imported by `processing/dedup.py`** to decide whether an
    article retells a story already delivered (P68). `[INFERRED]` The alternative was a second
    idea of "the same story" living in the dedup module, which is exactly how two modules come
    to disagree about one thing; `canonical_team` was made public and moved for the same reason
    after clustering and the validator disagreed about the Wolves.

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

    return _also_short_forms(found)


def _also_short_forms(names: set[str]) -> set[str]:
    """Add the forms the same subject is written in elsewhere, so headlines can meet.

    `[VERIFIED]` 2026-08-27, from a brief the operator read: it announced that Kuminga had
    signed with the Timberwolves and then, a sentence later, that the Wolves had added him.
    Five headlines covered that one signing and grouping put them in **four** groups, so the
    summarizer was handed the same event four times and wrote it twice. The names it
    extracted were:

    ```
    {Jonathan Kuminga, Timberwolves}          {Jonathan Kuminga, Wolves}
    {Jonathan Kuminga, Minnesota Timberwolves}  {Kuminga, Wolves}
    ```

    Three different ways of failing to match: a surname against a full name, a team against
    the same team with its city attached, and a nickname against its longer form. Two
    articles need two names in common, and these pairs could only ever find one.

    So a name also contributes its last word, and any team alias contributes one agreed
    spelling. `[INFERRED]` This does not weaken the rarity rule that stops "James" grouping
    unrelated stories: a word that turns up in too many articles is still ignored, and adding
    short forms feeds that rule rather than bypassing it.
    """
    expanded = set(names)
    for name in names:
        words = name.split()
        if len(words) > 1:
            # "Jonathan Kuminga" also answers to "Kuminga", "Minnesota Timberwolves" to
            # "Timberwolves". The last word is the one headlines drop to.
            expanded.add(words[-1])
    return {canonical_team(name) for name in expanded}


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
    min_rarity_ceiling: int = MIN_RARITY_CEILING,
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

    names_by_index = [story_names(article) for article in articles]

    # How many articles each name appears in — the document frequency.
    frequency: Counter[str] = Counter()
    for names in names_by_index:
        frequency.update(names)

    # The floor is what keeps a small batch from discarding the very names that identify its
    # biggest story — see `MIN_RARITY_CEILING`. Above roughly 62 articles the proportional
    # term wins and the floor does nothing.
    ceiling = max(min_rarity_ceiling, int(len(articles) * max_name_frequency))

    # `[VERIFIED]` 2026-08-13 (TASKS.md P9): below a ceiling of `min_shared_names`, grouping
    # cannot happen at all. Two articles sharing a name give that name a document frequency
    # of at least 2, so it fails `frequency[name] <= 1` and is discarded as non-distinctive —
    # which leaves `min_shared_names` of 2 unreachable by construction.
    #
    # `[VERIFIED]` 2026-08-15 the *condition* this reports is now fixed rather than merely
    # announced (P19), so at default settings this warning can no longer fire: the floor puts
    # `ceiling` at 5 and `min_shared_names` is 2. It is kept because both are parameters and
    # the guard is still correct whenever it does fire — a caller passing `min_shared_names=6`
    # or a lower floor gets told, instead of silently grouping nothing.
    #
    # `[VERIFIED]` Nine of the eleven bugs in `SESSION.md` §8 were found by reading output,
    # so making a failure visible remains this project's cheapest remedy.
    if ceiling < min_shared_names and len(articles) >= 2:
        logger.warning(
            "grouping skipped: %d articles gives a rarity ceiling of %d, below the %d "
            "shared names required, so no two articles can be grouped",
            len(articles),
            ceiling,
            min_shared_names,
        )

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


def order_by_relatedness(groups: list[list[NewsArticle]]) -> list[list[NewsArticle]]:
    """Reorder stories so that ones about the same subject sit next to each other.

    **This changes order only.** No story is merged, dropped or added, so a caller's ranking
    and per-source caps survive it, and the best-ranked story stays first.

    `[VERIFIED]` 2026-08-15 (P18) and again 2026-08-18 (P30), the second time from the
    operator reading a delivered brief: *"why is jeanie buss section separated by vote in san
    antonio and 2 clippers separated by reddit fan-thread"*. One 15-story brief carried the
    **same Schröder trade at positions 1, 5, 9 and 14**, once per feed.

    `[VERIFIED]` Grouping cannot fix that and should not try. `group_related` needs
    `MIN_SHARED_NAMES` = 2, and four reports of one trade share only the player's name, so
    they are correctly four stories. Lowering that threshold would merge any two articles that
    happen to mention one player. Relatedness is a weaker relation than sameness, and ordering
    is where it belongs.

    `[VERIFIED]` The order was previously fetch order in practice: P18 measured that every
    story classifies to the same priority tier in the offseason, so `sort_by_priority`
    degenerates to the identity and the brief reads ESPN, then CBS, then Yahoo, then r/nba.

    Greedy chaining rather than a similarity sort. `[INFERRED]` It reads in one sentence —
    after each story, take whichever remaining story shares the most names with it — and that
    matters more here than optimality (`CLAUDE.md` C5). Ties keep the caller's ranking, so a
    batch where nothing is related comes back unchanged.
    """
    if len(groups) <= 2:
        return list(groups)

    keys = [_relatedness_key(group) for group in groups]
    remaining = list(range(1, len(groups)))
    order = [0]

    while remaining:
        current = keys[order[-1]]
        # `-index` keeps the caller's order among stories that share nothing.
        nearest = max(remaining, key=lambda index: (len(current & keys[index]), -index))
        order.append(nearest)
        remaining.remove(nearest)

    return [groups[index] for index in order]


def _relatedness_key(group: list[NewsArticle]) -> frozenset[str]:
    """Every word of every name in a story, folded so two spellings meet.

    Words rather than whole names, because the feeds write `Dennis Schröder` and bare
    `Schroder` for one person and those never match as strings. Folded for the same reason
    P22 folds them in the validator: the sources disagree with themselves about accents.
    """
    words: set[str] = set()
    for article in group:
        for name in story_names(article):
            words.update(comparable(name).lower().split())
    return frozenset(words)
