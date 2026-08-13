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

`test_grouping_does_nothing_below_a_batch_of_25` records a real threshold artefact found
while writing these tests (TASKS.md P9): below 25 articles the rarity ceiling drops to 1 and
no two articles can be grouped at all. The behaviour is deliberately unchanged — raising the
ceiling risks a false merge, and a wrongly merged story is one the brief never reports
separately. What changed is that it is no longer silent, asserted in
`test_a_batch_too_small_to_group_says_so`.
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


def test_grouping_does_nothing_below_a_batch_of_25(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-13 — a threshold artefact found by testing, open as TASKS.md P9.

    `ceiling = max(1, int(len(articles) * 0.08))` is **1** for any batch under 25 articles.
    A name shared by two articles has frequency 2, which exceeds that ceiling, so it is
    discarded as non-distinctive — and `MIN_SHARED_NAMES` of 2 then becomes unreachable.
    **Below 25 articles this module silently groups nothing at all.**

    Measured with the two real Kawhi titles above: not merged at 24, merged at 25.

    `[INFERRED]` It has not bitten in production — the two runs in `logs/sportwire.log`
    carried 27 and 64 articles past dedup — but 27 is close, and the degradation is invisible:
    a quiet day produces a brief with duplicate coverage and no log line saying why.

    **Resolved 2026-08-13 as P9 option (c): the behaviour stands, the silence does not.**
    `group_related` now logs a warning when the ceiling makes grouping impossible, asserted
    in `test_a_batch_too_small_to_group_says_so`. (c) was chosen over raising the ceiling
    because it cannot cause a false merge, and a wrongly merged story is one the brief never
    reports separately — the expensive error here.
    """
    pair = [make_article(KAWHI_ONE), make_article(KAWHI_TWO)]

    just_under = group_related(pair + _filler(make_article, 22))
    just_over = group_related(pair + _filler(make_article, 23))

    assert len(just_under) == 24, "24 articles, 24 groups — nothing merged"
    assert all(len(g) == 1 for g in just_under)
    assert any(len(g) == 2 for g in just_over), "at 25 the same pair merges"


def test_a_batch_too_small_to_group_says_so(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """The P9 remedy: a structurally impossible grouping pass must not be silent.

    `[INFERRED]` Without this line the failure is undetectable from the log — duplicate
    coverage reaches the brief, `limit_per_source` spends the source cap on the duplicates,
    and the "grouped N into M" line never fires because nothing merged. An absent success
    message is not a diagnosis.
    """
    batch = [make_article(KAWHI_ONE), make_article(KAWHI_TWO)] + _filler(
        make_article, 22
    )

    with caplog.at_level(logging.WARNING, logger="processing.cluster"):
        group_related(batch)

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
