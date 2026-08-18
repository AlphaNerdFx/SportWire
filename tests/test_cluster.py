"""Behaviour tests for story grouping and the per-source caps.

`processing/cluster.py` is what actually solved the problem semantic dedup was proposed for
(ADR-005): many outlets covering **one event** in completely different words. The signal is
**rarity, not overlap** — a name appearing everywhere identifies a topic, a name appearing
rarely identifies an event. That is inverse document frequency applied to one batch, with no
model.

Two properties are asserted that are easy to lose by accident:

  - **Grouping partitions.** `sum(len(g) for g in groups) == len(articles)` always holds.
    This module must not drop anything; `newsworthy.py` is the only one permitted to.
  - **Capping counts stories, not articles**, and only the source that *leads* each group.
    An article merged into another outlet's coverage does not count against the cap, because
    the merge is what corroborates it.

A threshold artefact found while writing these tests (TASKS.md P9) was recorded here for two
days as `test_grouping_does_nothing_below_a_batch_of_25`: below 25 articles the rarity ceiling
dropped to 1 and no two articles could be grouped at all. That test asserted the defect, on
the reasoning that raising the ceiling risked a false merge. `[VERIFIED]` 2026-08-15 the
reasoning was measured and did not hold (P19), the floor `MIN_RARITY_CEILING` was added, and
the test is replaced by `test_a_small_batch_still_groups_a_widely_covered_story` and
`test_the_floor_is_inert_once_the_batch_is_large`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from models.schemas import NewsArticle
from processing.cluster import (
    DEFAULT_SOURCE_LIMIT,
    SOURCE_LIMITS,
    group_related,
    limit_per_source,
    order_by_relatedness,
)

ArticleFactory = Callable[..., NewsArticle]

# The two real r/nba titles from the module's own docstring. Title similarity cannot pair
# them -- they share almost no text -- but they share two rare names.
KAWHI_ONE = "BREAKING Kawhi Leonard had a hidden sponsorship with Daktronics"
KAWHI_TWO = "Per Pablo Torre, Kawhi Leonard also had a deal with Daktronics"


def _filler(make_article: ArticleFactory, count: int) -> list[NewsArticle]:
    """Unrelated articles sharing no names, to make a batch a realistic size."""
    return [
        make_article(f"Quiet roster note number {index} from a different club")
        for index in range(count)
    ]


# --- grouping: rarity is the signal ------------------------------------------------------


def test_articles_sharing_rare_names_are_grouped(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` The real case: one live capture had seven posts on one Kawhi story.

    "Kawhi Leonard" and "Daktronics" are shared, and neither appears elsewhere in the batch.
    """
    batch = [make_article(KAWHI_ONE), make_article(KAWHI_TWO)] + _filler(
        make_article, 30
    )

    groups = group_related(batch)
    merged = [g for g in groups if len(g) > 1]

    assert len(merged) == 1
    assert {a.title for a in merged[0]} == {KAWHI_ONE, KAWHI_TWO}


def test_a_name_appearing_everywhere_does_not_group(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` "James" appeared in 21 of 73 live articles across unrelated stories.

    Grouping on a shared common name would have merged most of the brief into one cluster.
    The frequency ceiling is what prevents it, and this is the test that holds it there.
    """
    # Two shared names, deliberately. `[VERIFIED]` 2026-08-13: an earlier version of this
    # test shared only one, so it passed because of `MIN_SHARED_NAMES` and would have passed
    # with the frequency ceiling removed entirely — it did not test what its name claims.
    # Mutation testing is what exposed that.
    common = [
        make_article(
            f"LeBron James was linked to the Los Angeles Lakers in note {index}"
        )
        for index in range(12)
    ]
    batch = common + _filler(make_article, 20)

    groups = group_related(batch)

    assert all(len(g) == 1 for g in groups), (
        "a name common across the batch identifies a topic, not an event"
    )


def test_one_shared_name_is_not_enough(make_article: ArticleFactory) -> None:
    """`MIN_SHARED_NAMES` is 2: one is too weak, and would merge unrelated team items."""
    batch = [
        make_article("Daktronics announces a quarterly result"),
        make_article("Daktronics installs a new scoreboard in Miami"),
    ] + _filler(make_article, 30)

    groups = group_related(batch)

    assert all(len(g) == 1 for g in groups)


def test_a_group_widens_its_fingerprint_as_articles_join(
    make_article: ArticleFactory,
) -> None:
    """A third article matching *either* of the first two still lands in the same group.

    Without widening, every candidate is compared only against the names of the article that
    opened the group, so a story that develops vocabulary — the first post names Kawhi and
    Daktronics, a later one names Ballmer and Torre — fragments into two clusters covering
    one event.

    `[VERIFIED]` 2026-08-13: this behaviour was uncovered until mutation testing showed that
    deleting the widening line broke nothing in this suite.
    """
    opener = make_article("Kawhi Leonard had a deal with Daktronics")
    bridge = make_article(
        "Kawhi Leonard and Daktronics were named by Ballmer and also Torre"
    )
    later = make_article("Ballmer met with Torre in a separate report")

    groups = group_related([opener, bridge, later] + _filler(make_article, 29))
    merged = [g for g in groups if len(g) > 1]

    assert len(merged) == 1, "one story, not two"
    assert len(merged[0]) == 3
    assert merged[0][2] is later, (
        "the third article shares no name with the first, only with the second"
    )


def test_grouping_partitions_every_article_exactly_once(
    articles: list[NewsArticle],
) -> None:
    """Against the real 15-article ESPN fixture: nothing is dropped and nothing duplicated."""
    groups = group_related(articles)

    flattened = [article for group in groups for article in group]
    assert sum(len(g) for g in groups) == len(articles)
    assert {a.article_id for a in flattened} == {a.article_id for a in articles}


def test_order_is_preserved_within_and_between_groups(
    make_article: ArticleFactory,
) -> None:
    """The first article of each group is the highest-ranked, if the input was sorted."""
    first = make_article(KAWHI_ONE)
    second = make_article(KAWHI_TWO)
    batch = [first, second] + _filler(make_article, 30)

    groups = group_related(batch)

    assert groups[0][0] is first
    assert groups[0][1] is second


def test_a_single_article_is_its_own_group(make_article: ArticleFactory) -> None:
    """The degenerate case must still satisfy the partition invariant."""
    article = make_article("Westbrook retires")

    assert group_related([article]) == [[article]]
    assert group_related([]) == []


def test_a_small_batch_still_groups_a_widely_covered_story(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-15 (TASKS.md P19) — this **reverses** the P9 behaviour.

    A previous test here, `test_grouping_does_nothing_below_a_batch_of_25`, asserted the
    opposite and was right about the code: `ceiling = max(1, int(n * 0.08))` is 1 below 25
    articles, so no name survives as distinctive and nothing can merge. P9 chose to log that
    rather than fix it, reasoning that raising the ceiling might cause a false merge.

    **That reasoning was never measured, and when it was, it did not hold.** Sweeping the
    ceiling over a live capture of 109 articles: a floor of 5 is inert at 80 articles and
    above, and every merge it newly creates at smaller sizes was read by hand — all of them
    the same Dennis Schröder trade, no false merges at any size. The cost of the old
    behaviour was real and had reached a phone: that story took four slots in one brief.

    So the old test asserted a defect rather than a decision, and is replaced rather than
    weakened. `MIN_RARITY_CEILING` carries the measurement.
    """
    pair = [make_article(KAWHI_ONE), make_article(KAWHI_TWO)]

    for filler_count in (10, 22, 30):
        groups = group_related(pair + _filler(make_article, filler_count))
        assert any(len(group) == 2 for group in groups), (
            f"the Kawhi pair must merge in a batch of {filler_count + 2}; "
            "the floor exists so batch size cannot hide a story"
        )


def test_the_floor_admits_a_name_carried_by_five_outlets(
    make_article: ArticleFactory,
) -> None:
    """Why the floor is 5 and not 4, pinned with the real cluster that motivated it.

    `[VERIFIED]` These are the five live titles for the Dennis Schröder trade, lightly
    shortened. `Dennis Schroder` has a document frequency of exactly **5** across them, so
    the two candidate floors fall either side of it: at 4 the story's own name is discarded
    as non-distinctive and only two articles merge; at 5 it survives and four do.

    Without this test a floor of 4 passes the whole suite — `[VERIFIED]` it did, as a
    surviving mutation — because every other grouping test uses a two-article story, and any
    ceiling of 2 or more admits those equally.

    `[VERIFIED]` The fifth article does **not** join, and that is a separate known defect
    rather than a tolerance here: `_NAME` greedily takes `Cleveland Cavaliers` and
    `Charlotte Hornets` as single names, so it shares only `Dennis Schroder` with the rest.
    That is TASKS.md P17, and this test will show it as a group of 5 when P17 lands.
    """
    trade = [
        make_article("Dennis Schroder traded to Hornets as Cavaliers continue retool"),
        make_article("Cavs trade Dennis Schroder to Hornets for Tre Mann"),
        make_article("Cleveland to trade Dennis Schroder to Charlotte for Tre Mann"),
        make_article("Dennis Schroder traded for ninth time as Cavaliers send guard"),
        make_article("The Cleveland Cavaliers are trading Dennis Schroder and cash"),
    ]
    batch = trade + _filler(make_article, 20)

    largest = max(len(group) for group in group_related(batch))

    assert largest >= 4, (
        "a name carried by five outlets must stay distinctive; at a ceiling of 4 it is "
        "discarded and the story fragments, which is the four-slot brief of 2026-08-15"
    )


def test_the_floor_is_inert_once_the_batch_is_large(
    articles: list[NewsArticle],
    cbs_articles: list[NewsArticle],
    reddit_articles: list[NewsArticle],
) -> None:
    """The floor must not quietly loosen grouping on the batches the pipeline usually sees.

    `[VERIFIED]` Across all 76 captured articles the proportional ceiling is already
    `int(76 * 0.08) = 6`, so `max(5, 6)` is 6 and the floor changes nothing.

    **Real captured articles, not synthetic filler**, and that is what makes this assert
    anything. `[VERIFIED]` 2026-08-15 by mutation during the `/commit` audit: a first version
    built the batch from `_filler`, whose articles deliberately share no names, so grouping
    was identical at *every* ceiling and the test **survived raising the floor to 99**. On
    these real articles the ceiling matters — floors 1 and 5 both give 68 groups, while a
    floor of 99 gives 62 — so the same mutation now fails here.
    """
    batch = [*articles, *cbs_articles, *reddit_articles]
    assert len(batch) == 76, (
        "the fixtures are the batch; the ceiling here is 6, above 5"
    )

    with_floor = group_related(batch)
    without_floor = group_related(batch, min_rarity_ceiling=1)

    assert [len(g) for g in with_floor] == [len(g) for g in without_floor]


def test_a_batch_too_small_to_group_says_so(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """The P9 remedy, still guarding the parameters it can still reach.

    `[VERIFIED]` 2026-08-15: at *default* settings this warning can no longer fire, because
    the P19 floor puts the ceiling at 5 and `min_shared_names` is 2. The guard is kept for
    callers that tune either value, and this test now reaches it the only way left — by
    asking for more shared names than the ceiling can supply.

    `[INFERRED]` Without the line the failure is undetectable from the log: duplicate coverage
    reaches the brief, `limit_per_source` spends the source cap on the duplicates, and the
    "grouped N into M" line never fires because nothing merged. An absent success message is
    not a diagnosis.
    """
    batch = [make_article(KAWHI_ONE), make_article(KAWHI_TWO)] + _filler(
        make_article, 22
    )

    with caplog.at_level(logging.WARNING, logger="processing.cluster"):
        group_related(batch, min_shared_names=6)

    assert "grouping skipped" in caplog.text
    assert "24 articles" in caplog.text, "the log must say how small the batch was"


def test_a_batch_large_enough_to_group_stays_quiet(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """The complement: a warning that fires on every normal run is one nobody reads."""
    batch = [make_article(KAWHI_ONE), make_article(KAWHI_TWO)] + _filler(
        make_article, 30
    )

    with caplog.at_level(logging.WARNING, logger="processing.cluster"):
        group_related(batch)

    assert "grouping skipped" not in caplog.text


# --- capping: stories, not articles ------------------------------------------------------


def test_community_feed_is_capped_lower_than_the_default(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """`[VERIFIED]` r/nba is capped at 3 because its volume is unrelated to how much news
    there is. Title-pattern filtering was tried first and provably could not separate its
    chatter from its reporting, so the fix bounds volume instead of classifying it."""
    groups = [[make_article(f"r/nba story {i}", source="r/nba")] for i in range(6)]

    with caplog.at_level(logging.INFO, logger="processing.cluster"):
        kept = limit_per_source(groups)

    assert len(kept) == SOURCE_LIMITS["r/nba"] == 3
    assert "capped r/nba at 3 stories" in caplog.text, (
        "a silent cap hides missing stories"
    )
    assert "3 further stories not shown" in caplog.text


def test_every_other_source_gets_the_default_ceiling(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` Not only a community-feed problem: Yahoo publishes ~50 NBA items a day
    against ESPN's one or two, so after dedup nearly every remaining item was Yahoo."""
    groups = [
        [make_article(f"Yahoo story {i}", source="Yahoo Sports")] for i in range(9)
    ]

    kept = limit_per_source(groups)

    assert len(kept) == DEFAULT_SOURCE_LIMIT == 4


def test_the_cap_keeps_the_highest_ranked_stories(
    make_article: ArticleFactory,
) -> None:
    """Input is expected most-important-first, so survivors are the best, not the earliest."""
    groups = [[make_article(f"story {i}", source="Yahoo Sports")] for i in range(9)]

    kept = limit_per_source(groups)

    assert [g[0].title for g in kept] == ["story 0", "story 1", "story 2", "story 3"]


def test_only_the_leading_source_counts_against_the_cap(
    make_article: ArticleFactory,
) -> None:
    """A merged article does not count — the merge is what corroborates the story.

    Four Yahoo-led groups exhaust the default cap. A fifth group led by ESPN survives even
    though it *contains* a Yahoo article, because capping counts leaders, not members.
    """
    yahoo_led = [
        [make_article(f"Yahoo lead {i}", source="Yahoo Sports")] for i in range(4)
    ]
    espn_led = [
        make_article("ESPN lead", source="ESPN"),
        make_article("Yahoo follow-up", source="Yahoo Sports"),
    ]

    kept = limit_per_source([*yahoo_led, espn_led])

    assert len(kept) == 5
    assert kept[-1][0].source == "ESPN"


def test_a_zero_default_disables_the_general_ceiling(
    make_article: ArticleFactory,
) -> None:
    """Named limits still apply; everything else becomes uncapped."""
    groups = [
        [make_article(f"Yahoo story {i}", source="Yahoo Sports")] for i in range(9)
    ]

    assert len(limit_per_source(groups, default_limit=0)) == 9


def test_capping_nothing_returns_nothing(make_article: ArticleFactory) -> None:
    """The nothing-to-report path."""
    assert limit_per_source([]) == []


def test_reports_of_one_story_from_four_feeds_end_up_adjacent(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` The defect the operator reported twice, from a real 15-story brief.

    That brief carried the same Schröder trade at positions 1, 5, 9 and 14, once per feed,
    with unrelated stories between them. P18 measured why: every story classifies to the same
    priority tier in the offseason, so `sort_by_priority` degenerates to the identity and the
    surviving order is fetch order, which is ESPN, then CBS, then Yahoo, then r/nba.

    Note the spellings. Two of these say `Schröder` and two say `Schroder`, which is how the
    feeds really print them, so the key has to fold accents or they never meet.
    """
    groups = [
        [make_article("Cavs deal Schroder for Hornets' Mann", source="ESPN")],
        [make_article("Beal stays with Clippers", source="ESPN")],
        [
            make_article(
                "Dennis Schröder trade grades: Cavaliers eye a bigger move",
                source="CBS Sports",
            )
        ],
        [
            make_article(
                "Kawhi Leonard investigation drags on for the Clippers",
                source="CBS Sports",
            )
        ],
        [
            make_article(
                "Dennis Schröder has now been traded nine times", source="Yahoo Sports"
            )
        ],
        [
            make_article(
                "Schroder is one team away from tying Ish Smith", source="r/nba"
            )
        ],
    ]

    ordered = order_by_relatedness(groups)
    titles = [group[0].title for group in ordered]
    positions = [index for index, title in enumerate(titles) if "chr" in title]

    assert positions == list(range(positions[0], positions[0] + 4)), (
        f"the four Schroder reports are not adjacent: {titles}"
    )


def test_the_best_ranked_story_still_leads(make_article: ArticleFactory) -> None:
    """Ordering must not promote a story over the one the caller ranked first."""
    groups = [
        [make_article("Beal stays with Clippers", source="ESPN")],
        [make_article("Cavs deal Schroder for Hornets' Mann", source="ESPN")],
        [make_article("Dennis Schröder trade grades", source="CBS Sports")],
    ]

    assert order_by_relatedness(groups)[0][0].title == "Beal stays with Clippers"


def test_unrelated_stories_keep_the_order_they_arrived_in(
    make_article: ArticleFactory,
) -> None:
    """A batch where nothing is related must come back untouched.

    `[INFERRED]` This is what makes the change safe to add to the pipeline: it can only move
    a story when there is a shared name to justify it.
    """
    titles = [
        "Wolves retire Garnett's 21",
        "Jeanie Buss opposes the sale",
        "San Antonio council votes on arena funding",
        "Haliburton returns from injury",
    ]
    groups = [[make_article(title, source="ESPN")] for title in titles]

    assert [g[0].title for g in order_by_relatedness(groups)] == titles


def test_ordering_never_adds_or_loses_a_story(make_article: ArticleFactory) -> None:
    """A permutation, never a filter. The same guarantee `sort_by_priority` gives."""
    groups = [
        [make_article("Cavs deal Schroder for Hornets' Mann", source="ESPN")],
        [make_article("Beal stays with Clippers", source="ESPN")],
        [make_article("Dennis Schröder trade grades", source="CBS Sports")],
        [make_article("Kawhi Leonard and the Clippers", source="CBS Sports")],
    ]

    ordered = order_by_relatedness(groups)

    assert len(ordered) == len(groups)
    assert {g[0].article_id for g in ordered} == {g[0].article_id for g in groups}
