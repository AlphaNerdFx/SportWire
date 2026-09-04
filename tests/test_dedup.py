"""Behaviour tests for the two dedup passes, and for the evidence ADR-005 rests on.

`processing/dedup.py` has no recorded bugs, which is exactly why it is worth testing: it is
load-bearing and quiet. Without pass 1 every run re-sends the whole feed, because ESPN's RSS
still lists the same items hours later. `[VERIFIED]` A dedup window shorter than the feed's
reach caused precisely that, which is why the window is 168h rather than the 8h cadence.

Three things are asserted here that are not "does the function work":

  1. **The functions are pure.** The seen-set is injected, never read from storage, so this
     logic is testable with no database. `[VERIFIED]` H13 Q7 asked why and the answer given
     was performance; it is testability, and the test below is what that buys.
  2. **Games are matched on `state_hash`, not `game_id`.** A game reported at half time and
     again as final is *not* a duplicate — the score moved. `[VERIFIED]` H13 Q1 and Q3 both
     missed this, so it is asserted explicitly rather than left implied.
  3. **The pass-2 threshold is justified by real data, not tuned.** ADR-005 declined semantic
     dedup on measurement, and `test_real_cross_source_pairs_*` re-measures that claim from
     the committed fixtures every run rather than trusting the number in the comment.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from difflib import SequenceMatcher

import pytest

from models.schemas import GameData, NewsArticle
from processing.cluster import story_names
from processing.dedup import (
    DEFAULT_TITLE_SIMILARITY,
    deduplicate_articles,
    deduplicate_games,
    drop_repeated_stories,
    normalise_title,
)

ArticleFactory = Callable[..., NewsArticle]
GameFactory = Callable[..., GameData]


# --- pass 1: already delivered ---------------------------------------------------------


def test_articles_already_delivered_are_dropped(make_article: ArticleFactory) -> None:
    """The pass that matters most: without it every run re-sends the entire feed."""
    kept_one = make_article("Westbrook retires")
    already_sent = make_article("Lakers sale finalised")

    result = deduplicate_articles([kept_one, already_sent], {already_sent.article_id})

    assert result == [kept_one]


def test_the_seen_set_is_injected_rather_than_read_from_storage(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` H13 Q7: the injected set is for **testability**, not performance.

    This test is the payoff — the whole dedup path is exercised with no database, no
    filesystem and no configuration. A version that reached into `storage/db.py` could not be
    tested this way, and the seam is what makes that impossible to do by accident.
    """
    article = make_article("Westbrook retires")

    assert deduplicate_articles([article], set()) == [article]
    assert deduplicate_articles([article], {article.article_id}) == []


def test_input_order_is_preserved(make_article: ArticleFactory) -> None:
    """Dedup removes; `priority.py` orders. Reordering here would silently override it."""
    first = make_article("A signing")
    second = make_article("A trade")
    third = make_article("A waiver")

    assert deduplicate_articles([first, second, third], set()) == [
        first,
        second,
        third,
    ]


# --- pass 2: near-identical titles within one batch -------------------------------------


def test_near_identical_titles_collapse_and_the_first_one_wins(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """Genuine near-identical republication — the same wire item carried twice."""
    first = make_article("Russell Westbrook announces his retirement after 18 seasons")
    near_copy = make_article(
        "Russell Westbrook announces his retirement after 18 season"
    )

    with caplog.at_level(logging.INFO, logger="processing.dedup"):
        result = deduplicate_articles([first, near_copy], set())

    assert result == [first], "the first occurrence wins"
    assert "near-duplicate" in caplog.text, "a silent drop is how stories go missing"


def test_formatting_differences_alone_do_not_prevent_a_match(
    make_article: ArticleFactory,
) -> None:
    """Case and whitespace are normalised, so trivial differences do not count as new."""
    assert normalise_title("  Westbrook   RETIRES  ") == "westbrook retires"

    first = make_article("Russell Westbrook announces his retirement after 18 seasons")
    reformatted = make_article(
        "russell   westbrook ANNOUNCES his retirement after 18 seasons"
    )

    assert deduplicate_articles([first, reformatted], set()) == [first]


def test_unrelated_stories_are_both_kept(make_article: ArticleFactory) -> None:
    """The expensive error here is a false merge, which deletes a story outright."""
    signing = make_article("Suns waive Haywood Highsmith to open a roster spot")
    unrelated = make_article("NBA Cup group stage schedule revealed")

    assert len(deduplicate_articles([signing, unrelated], set())) == 2


def test_real_cross_source_pairs_do_not_collapse(
    articles: list[NewsArticle], cbs_articles: list[NewsArticle]
) -> None:
    """Re-measures ADR-005's evidence from the committed fixtures on every run.

    `[VERIFIED]` 2026-08-13, from `tests/fixtures/`: **15 ESPN × 36 CBS = 540 pairs, highest
    similarity 0.425.** The closest pair is not a duplicate — "Jaylen Brown says Donovan
    Mitchell, Coco Jones wedding sparked desire for love" against a CBS LeBron/MLB roundup.

    `[INFERRED]` **This does not reproduce the numbers in `dedup.py`'s own comment**, which
    records 612 pairs (17 ESPN × 36 CBS) and a maximum of 0.439. The committed ESPN fixture
    holds 15 items, so that measurement was taken against a *live* fetch of 17 and cannot be
    reproduced from this repository. The conclusion is unchanged and in fact slightly
    stronger — 0.425 is further from the 0.85 threshold than 0.439 — but the figure in the
    comment is not checkable. See TASKS.md P8.

    `[INFERRED]` The structural reason no pair comes close: outlets write their own headlines
    rather than syndicating one, so lexical matching cannot pair two outlets covering one
    signing and should not try. `processing/cluster.py` solved that problem, by shared rare
    names, with no model.
    """
    ratios = [
        SequenceMatcher(
            None, normalise_title(a.title), normalise_title(b.title)
        ).ratio()
        for a in articles
        for b in cbs_articles
    ]
    highest = max(ratios)

    assert len(ratios) >= 500, "the measurement needs both fixtures actually loaded"
    assert highest < DEFAULT_TITLE_SIMILARITY, (
        f"a real cross-source pair reached {highest:.3f}, at or above the "
        f"{DEFAULT_TITLE_SIMILARITY} threshold — pass 2 would now merge two different stories"
    )
    assert highest < 0.50, (
        f"highest real cross-source similarity is {highest:.3f}; ADR-005 records that nothing "
        "reaches 0.50 and that unrelated stories begin merging below it"
    )


# --- pass 3: the same story, told again ---------------------------------------------------


def test_a_retold_story_naming_nobody_new_is_dropped(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-09-04, the operator reading real briefs: the NBA's ruling against the
    Clippers arrived in four consecutive briefs.

    Both titles are real and both were delivered. The second says the same thing about the
    same people, and passes 1 and 2 both miss it: its id is new, and the first article is in
    yesterday's batch rather than this one.
    """
    delivered = [
        story_names(
            make_article(
                "Steve Ballmer suspended one year, Clippers to lose 5 first-round "
                "picks over Kawhi Leonard deal",
                league="NBA",
            )
        )
    ]
    again = [
        make_article(
            "NBA fines Clippers $30M, penalizes Kawhi Leonard after investigation",
            league="NBA",
        )
    ]

    assert drop_repeated_stories(again, delivered) == []


def test_a_retold_story_naming_someone_new_is_kept(
    make_article: ArticleFactory,
) -> None:
    """The exception, and the operator drew it himself: *"I'm not talking about Gillian Zucker
    that part is new"*.

    `[VERIFIED]` This is the article that survived in the live replay. It is the same story by
    the shared-name rule, and it carries a name the story had not been delivered with, so it is
    the next chapter rather than a repeat. A rule without this half would have deleted it.
    """
    delivered = [
        story_names(
            make_article(
                "Steve Ballmer suspended one year, Clippers to lose 5 first-round "
                "picks over Kawhi Leonard deal",
                league="NBA",
            )
        )
    ]
    development = [
        make_article(
            "Digging into the Wachtell report: Gillian Zucker and the Clippers payments "
            "to Kawhi Leonard",
            league="NBA",
        )
    ]

    assert drop_repeated_stories(development, delivered) == development


def test_one_shared_name_with_each_of_two_stories_is_not_a_retelling(
    make_article: ArticleFactory,
) -> None:
    """`MIN_SHARED_NAMES` doing its job, and the case that proves it is doing it.

    An article about two teams that have each been in the news separately is a *new* story, not
    a retelling of either. It names nobody new, so the exception cannot save it; only the
    threshold can, by refusing to call one shared name a shared subject.

    `[VERIFIED]` Written this way on 2026-09-04 after the first version of this test survived
    the threshold being lowered to one. It survived because its article introduced a new name,
    so the exception kept it either way and the threshold was never consulted. `CLAUDE.md` §8:
    a test that passes through more than one mechanism is not measuring the one it names.
    """
    delivered = [
        story_names(
            make_article("Clippers docked five picks over Kawhi Leonard", league="NBA")
        ),
        story_names(
            make_article("Rockets extend Amen Thompson through 2032", league="NBA")
        ),
    ]
    new_story = [make_article("Clippers and Rockets discuss a deal", league="NBA")]

    assert drop_repeated_stories(new_story, delivered) == new_story


def test_nothing_delivered_yet_drops_nothing(make_article: ArticleFactory) -> None:
    """The first run of a fresh install must not be silently empty."""
    articles = [
        make_article("NBA fines Clippers $30M after investigation", league="NBA")
    ]

    assert drop_repeated_stories(articles, []) == articles


# --- games: state, not identity ---------------------------------------------------------


def test_a_game_whose_score_changed_is_not_a_duplicate(
    make_game: GameFactory,
) -> None:
    """`[VERIFIED]` H13 Q1/Q3: matching is on `state_hash`, **not** `game_id`.

    A game reported at half time and again as final shares a `game_id` but is not a
    duplicate — the score moved, so it is new information and must be delivered again.
    """
    at_half_time = make_game(
        home_score=55, away_score=51, status="In Progress", period=2
    )
    at_full_time = make_game(home_score=110, away_score=104, status="Final", period=4)

    assert at_half_time.game_id == at_full_time.game_id, "same game, by construction"

    result = deduplicate_games([at_full_time], {at_half_time.state_hash})

    assert result == [at_full_time], "a changed score must not be suppressed"


def test_an_unchanged_game_is_dropped(make_game: GameFactory) -> None:
    """The other half: a game that has not moved since it was sent is not re-sent."""
    game = make_game()

    assert deduplicate_games([game], {game.state_hash}) == []


def test_state_hash_is_stable_across_runs(make_game: GameFactory) -> None:
    """`[VERIFIED]` H13 Q1 — the question the operator had himself proposed getting wrong.

    `state_hash` deliberately excludes any timestamp. Including the current time would produce
    a new hash on every poll, nothing would ever match, and every game would be re-sent every
    run — the exact opposite of dedup. Two separately constructed but identical games must
    therefore hash the same.
    """
    assert make_game().state_hash == make_game().state_hash


# --- empty input -------------------------------------------------------------------------


def test_empty_input_is_not_an_error() -> None:
    """The offseason path, which is most of the year: no games is normal."""
    assert deduplicate_articles([], set()) == []
    assert deduplicate_games([], set()) == []
