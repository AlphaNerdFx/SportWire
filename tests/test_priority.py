"""Behaviour tests for the ranking that decides what the summariser writes about first.

`processing/priority.py` sorts and never filters, which makes its bugs quieter than
`newsworthy.py`'s but not harmless: the summariser is handed a *chunked* list, so an article
pushed to the back can fall outside the chunk that gets written about at all. Order decides
attention.

`SESSION.md` §8 records three bugs here, every one found by reading live output:

  - the "tonight" tier ranked a child-support story first  -> `test_tonight_is_a_tiebreaker_*`
  - `Warriors'` failed to match `warriors`                 -> `test_possessive_*`
  - `ex-fiancée` never matched `fiancée`                   -> `test_hyphenated_*`

The first is the important one. It is not a tokenising slip but a **structural** mistake —
relevance to tonight was made a tier of its own, so it outranked subject matter entirely. A
test that only checked tokenising would have missed it completely.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from models.schemas import GameData, NewsArticle
from processing.priority import (
    classify,
    mentions_team_in_play,
    sort_by_priority,
    team_keywords,
)

ArticleFactory = Callable[..., NewsArticle]
GameFactory = Callable[..., GameData]


# --- classification --------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Suns waive Haywood Highsmith to open a roster spot",
        "Russell Westbrook retires after 18 seasons",
        "Anthony Davis agrees a contract extension",
        "Jalen Duren draws sign-and-trade interest",
    ],
)
def test_roster_news_is_high(title: str, make_article: ArticleFactory) -> None:
    """Roster and on-court operations are what the brief exists to report."""
    assert classify(make_article(title)) == "high"


@pytest.mark.parametrize(
    "title",
    [
        "NBA star ties the knot in Italy",
        "Guard launches a podcast with his brother",
        "Forward opens a restaurant in Miami",
    ],
)
def test_off_court_news_is_low(title: str, make_article: ArticleFactory) -> None:
    """Still delivered — the operator was explicit that nothing is dropped — just last."""
    assert classify(make_article(title)) == "low"


def test_unrecognised_subject_is_medium(make_article: ArticleFactory) -> None:
    """The default is the middle, so an unknown subject is never silently buried."""
    assert classify(make_article("NBA Cup group stage schedule revealed")) == "medium"


def test_low_beats_high_when_both_appear(make_article: ArticleFactory) -> None:
    """A wedding story that uses the word "deal" is still a wedding story.

    `[INFERRED]` Misfiling an off-court item as important is more visible in a brief than the
    reverse, so the tie is broken towards caution.
    """
    article = make_article(
        "Star guard ties the knot",
        summary="The couple struck a deal with a magazine for the photographs.",
    )

    assert classify(article) == "low"


# --- tokenising: the two recorded matching bugs ----------------------------------------


def test_hyphenated_word_also_matches_its_parts(make_article: ArticleFactory) -> None:
    """`[VERIFIED]` "ex-fiancée" never matched "fiancée", leaving a child-support story medium.

    Classified low only if the hyphenated token is also split into its parts.
    """
    article = make_article("Doncic's ex-fiancée pulls child support petition")

    assert classify(article) == "low"


def test_hyphenated_word_keeps_its_whole_form(make_article: ArticleFactory) -> None:
    """Splitting must not replace the whole token: "re-ups" is itself a keyword."""
    assert classify(make_article("Veteran re-ups with the Heat")) == "high"


def test_possessive_team_name_matches_the_team(make_article: ArticleFactory) -> None:
    """`[VERIFIED]` "Why the Warriors' pursuit of LeBron never got serious" did not match.

    The token was `warriors'` and the team keyword is `warriors`, so an article about a team
    that played was not recognised as relevant to that night.
    """
    article = make_article("Why the Warriors' pursuit of LeBron never got serious")

    assert mentions_team_in_play(article, {"warriors"})


def test_team_keywords_take_the_last_word_of_each_name(
    make_game: GameFactory,
) -> None:
    """Every NBA `full_name` ends in a unique nickname; the city is shared and the full
    string is rarely spelled out in a headline."""
    games = [make_game("Los Angeles Lakers", "Golden State Warriors")]

    assert team_keywords(games) == {"lakers", "warriors"}


def test_no_games_means_nothing_is_promoted(make_article: ArticleFactory) -> None:
    """The offseason path: with no games there is no "tonight", and that is not an error."""
    article = make_article("Lakers sign a guard")

    assert not mentions_team_in_play(article, set())


# --- the structural bug: tonight is a tiebreaker, not a tier ---------------------------


def test_tonight_is_a_tiebreaker_within_a_tier_not_a_tier_of_its_own(
    make_article: ArticleFactory, make_game: GameFactory
) -> None:
    """`[VERIFIED]` 2026-08-07: this exact pairing put a child-support story first.

    An earlier version made "mentions a team that played" a top-level tier, so an off-court
    item about the Lakers outranked roster news about a team that did not play. Relevance to
    tonight does not turn an off-court story into roster news — it only breaks ties among
    stories of equal kind.

    **This is the test that would have caught it.** Both the tokenising tests above pass under
    the buggy ordering, because nothing about the tokens was wrong.
    """
    off_court_but_playing = make_article(
        "Doncic's ex-fiancée pulls child support petition",
        summary="The Lakers guard was named in the filing.",
    )
    roster_news_not_playing = make_article(
        "Suns waive a forward to open a roster spot",
        summary="Phoenix creates space ahead of the season.",
    )
    games = [make_game("Los Angeles Lakers", "Golden State Warriors")]

    ordered = sort_by_priority([off_court_but_playing, roster_news_not_playing], games)

    assert ordered[0] is roster_news_not_playing, (
        "roster news must outrank an off-court story even when the off-court story "
        "names a team that played"
    )
    assert ordered[1] is off_court_but_playing


def test_tonight_does_break_ties_inside_one_tier(
    make_article: ArticleFactory, make_game: GameFactory
) -> None:
    """The other half: within a tier, a team that played wins.

    Asserted separately so a fix that simply ignored `games` would fail here rather than
    quietly passing the test above.
    """
    high_not_playing = make_article("Hornets sign a guard")
    high_playing = make_article("Lakers sign a centre")
    games = [make_game("Los Angeles Lakers", "Golden State Warriors")]

    ordered = sort_by_priority([high_not_playing, high_playing], games)

    assert ordered[0] is high_playing


# --- invariants ------------------------------------------------------------------------


def test_sorting_is_a_permutation_never_a_filter(articles: list[NewsArticle]) -> None:
    """`len(output) == len(input)` always holds, against the real 15-article ESPN fixture.

    The operator was explicit that nothing is dropped here; `newsworthy.py` is the only module
    permitted to remove an article.
    """
    ordered = sort_by_priority(articles)

    assert len(ordered) == len(articles)
    assert {a.article_id for a in ordered} == {a.article_id for a in articles}


def test_order_within_a_tier_follows_the_source(make_article: ArticleFactory) -> None:
    """A stable sort preserves the feed's own ordering, which ESPN sets editorially.

    `[INFERRED]` That is a better tiebreaker than anything invented here, so it must survive.
    """
    first = make_article("Lakers sign a guard")
    second = make_article("Heat sign a forward")
    third = make_article("Bulls sign a centre")

    ordered = sort_by_priority([first, second, third])

    assert ordered == [first, second, third]


def test_an_empty_list_sorts_to_an_empty_list() -> None:
    """The nothing-to-report path."""
    assert sort_by_priority([]) == []


@pytest.mark.parametrize(
    "word", ["baby", "babies", "newborn", "maternity", "pregnant", "pregnancy"]
)
def test_a_birth_is_not_a_signing(
    make_article: Callable[..., NewsArticle], word: str
) -> None:
    """`[VERIFIED]` 2026-08-27, from a real captured post: "Luka signs a baby, the lakers visit
    the maternity ward of the hospital".

    It was classified **high**, the same tier as a max contract, because the title contains
    "signs". It then competed for one of the twelve story slots against actual roster news.

    `[INFERRED]` The list already covered weddings, engagements and divorces, and the module's
    own docstring gives the rule: an article about a player's private life that happens to use
    a transaction word is still a private-life story. A birth was missing from a family the
    rule already knew about.

    One word per case, on purpose. `[VERIFIED]` A first version used the real headline, which
    contains both "baby" and "maternity", so deleting either one from the list left the other
    doing the work and the test passed anyway. Every word here has to carry its own case or
    the list can rot a word at a time without anything failing.
    """
    article = make_article(f"Luka signs a {word} deal announcement at the arena")

    assert classify(article) == "low"


def test_the_real_headline_that_prompted_this_is_low(
    make_article: Callable[..., NewsArticle],
) -> None:
    """The captured post itself, kept because a constructed phrase is not evidence."""
    assert (
        classify(
            make_article(
                "Luka signs a baby, the lakers visit the maternity ward of the hospital"
            )
        )
        == "low"
    )


def test_an_actual_signing_is_still_high(
    make_article: Callable[..., NewsArticle],
) -> None:
    """The complement, and the reason the fix went in the low list rather than the high one.

    `[VERIFIED]` TASKS.md P7 warned that narrowing the transaction keywords produces invisible
    false negatives, and this project has done that twice already (P3). Adding to the low
    signals cannot: a real signing contains no birth word, so nothing about it changes.
    """
    assert classify(make_article("Kuminga signs with the Timberwolves")) == "high"
    assert classify(make_article("Jokic signs a max extension")) == "high"
