"""Behaviour tests for which games are called notable, and why.

`processing/highlights.py` decides *what* is notable; the formatter decides how it reads. The
two rules that make "notable" mean anything are both easy to break without noticing:

  1. **Superlative** — only the most extreme game of the night wins a ranked category, so the
     brief never says "biggest blowout" twice with two different numbers.
  2. **Threshold** — it must also clear an absolute bar, so a quiet night reports nothing
     rather than crowning a six-point win as a blowout.

Some categories are deliberately *not* superlatives. Overtime and comebacks are rare enough
that every instance is worth knowing, and "the most wire-to-wire" is meaningless.

The thresholds are `[INFERRED]` first guesses against one real night, so these tests assert
the *rules* against constructed games and assert the *numbers* only against the committed
2026-01-15 fixture — where a threshold change should show up as a visible, reviewable diff.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from models.schemas import GameData
from processing.highlights import (
    BIG_PERIOD_POINTS,
    BLOWOUT_MARGIN,
    CLOSE_GAME_MARGIN,
    COMEBACK_DEFICIT,
    HIGH_SCORING_TOTAL,
    SECOND_HALF_SWING,
    find_notable_games,
)

GameFactory = Callable[..., GameData]


def _categories(games: list[GameData]) -> list[str]:
    return [highlight.category for highlight in find_notable_games(games)]


# --- nothing to report ------------------------------------------------------------------


def test_no_games_is_not_an_error() -> None:
    """The offseason path, which is most of the year."""
    assert find_notable_games([]) == []


def test_a_quiet_night_reports_nothing(make_game: GameFactory) -> None:
    """A game clearing no threshold produces no highlight at all.

    This is the assertion that keeps "notable" meaningful. Without the absolute bars, the
    superlatives alone would always crown *something* — the closest game of the night is
    still the closest even if it was decided by 14.
    """
    # The loser leads after Q1, so this is not wire-to-wire either. `[VERIFIED]` An earlier
    # version of this test used a home team that led at every break with a 14-point margin,
    # which is exactly the wire_to_wire band — the "ordinary" game was notable after all.
    ordinary = make_game(
        home_score=104,
        away_score=90,
        home_periods=[22, 26, 28, 28],
        away_periods=[26, 22, 21, 21],
    )

    assert find_notable_games([ordinary]) == []


# --- superlative categories: most extreme, and over the bar ------------------------------


def test_a_blowout_is_reported_once_it_clears_the_margin(
    make_game: GameFactory,
) -> None:
    """`largest_margin` needs `BLOWOUT_MARGIN`, and the boundary is where off-by-ones live."""
    just_over = make_game(home_score=120, away_score=120 - BLOWOUT_MARGIN)

    assert "largest_margin" in _categories([just_over])


def test_a_win_just_under_the_line_is_not_a_blowout(make_game: GameFactory) -> None:
    """One point below the bar must produce nothing, or the threshold is decorative."""
    just_under = make_game(home_score=120, away_score=120 - BLOWOUT_MARGIN + 1)

    assert "largest_margin" not in _categories([just_under])


def test_only_the_most_extreme_game_takes_a_superlative(
    make_game: GameFactory,
) -> None:
    """Two blowouts, one `largest_margin`. The brief must not report two "biggest" wins."""
    big = make_game("Team A", "Team B", home_score=130, away_score=100)
    bigger = make_game("Team C", "Team D", home_score=140, away_score=100)

    highlights = find_notable_games([big, bigger])
    margins = [h for h in highlights if h.category == "largest_margin"]

    assert len(margins) == 1
    assert margins[0].game is bigger


def test_closest_finish_needs_to_be_close(make_game: GameFactory) -> None:
    """A superlative *and* a threshold: the closest game only counts if it was actually close."""
    close = make_game(home_score=108, away_score=108 - CLOSE_GAME_MARGIN)
    not_close = make_game("Team C", "Team D", home_score=120, away_score=100)

    assert "closest_finish" in _categories([close, not_close])
    assert "closest_finish" not in _categories([not_close])


def test_high_scoring_needs_the_combined_total(make_game: GameFactory) -> None:
    """Measured on both teams together, not on one."""
    shootout = make_game(
        home_score=HIGH_SCORING_TOTAL // 2 + 6, away_score=HIGH_SCORING_TOTAL // 2
    )

    assert "highest_scoring" in _categories([shootout])


def test_biggest_period_needs_an_unusual_quarter(make_game: GameFactory) -> None:
    """`[VERIFIED]` The highest single period in the captured 9-game slate was 42."""
    # Trails after Q1, so `wire_to_wire` cannot claim it first.
    explosive = make_game(
        home_score=120,
        away_score=110,
        home_periods=[25, 27, 28, BIG_PERIOD_POINTS],
        away_periods=[30, 28, 26, 26],
    )

    assert "biggest_period" in _categories([explosive])


# --- every-instance categories -----------------------------------------------------------


def test_every_overtime_game_is_reported(make_game: GameFactory) -> None:
    """Not a superlative: OT is rare enough that each one is independently worth knowing."""
    first = make_game("Team A", "Team B", home_score=120, away_score=118, period=5)
    second = make_game("Team C", "Team D", home_score=131, away_score=129, period=6)

    assert _categories([first, second]).count("overtime") == 2


def test_every_comeback_is_reported(make_game: GameFactory) -> None:
    """Also every-instance. A team down `COMEBACK_DEFICIT` at a break that still wins."""
    comeback = make_game(
        home_score=110,
        away_score=105,
        home_periods=[15, 25, 35, 35],
        away_periods=[35, 25, 25, 20],
    )

    assert comeback.largest_deficit_overcome >= COMEBACK_DEFICIT
    assert "comeback" in _categories([comeback])


def test_wire_to_wire_is_reported_only_inside_a_band(make_game: GameFactory) -> None:
    """`[VERIFIED]` 2026-08-08: leading at every break happened in 3 of 9 real games.

    It is common, not remarkable, and flagging all of them made this the dominant category.
    What is notable is the **combination** — led throughout *and* never pulled clear, meaning
    someone was held off all night. Above the blowout line it duplicates `largest_margin`;
    below the close-game line the finish itself is the story.
    """
    held_on = make_game(
        home_score=110,
        away_score=100,
        home_periods=[30, 25, 30, 25],
        away_periods=[25, 25, 25, 25],
    )
    ran_away = make_game(
        "Team C",
        "Team D",
        home_score=130,
        away_score=100,
        home_periods=[35, 30, 35, 30],
        away_periods=[25, 25, 25, 25],
    )

    assert held_on.led_wire_to_wire and ran_away.led_wire_to_wire
    assert "wire_to_wire" in _categories([held_on])
    assert "wire_to_wire" not in _categories([ran_away]), (
        "above the blowout line this duplicates largest_margin"
    )


def test_second_half_takeover_is_measured_after_the_break(
    make_game: GameFactory,
) -> None:
    """A game won in the third quarter reads differently from one won by half time."""
    # Down 12 at the break, not 15, so `comeback` does not claim it first.
    takeover = make_game(
        home_score=110,
        away_score=95,
        home_periods=[25, 20, 35, 30],
        away_periods=[30, 27, 20, 18],
    )

    assert takeover.second_half_swing >= SECOND_HALF_SWING
    assert "second_half_takeover" in _categories([takeover])


# --- one game, one slot -------------------------------------------------------------------


def test_a_game_is_reported_once_under_its_first_matching_category(
    make_game: GameFactory,
) -> None:
    """A game qualifying for several categories occupies one slot, not several.

    `comeback` precedes `largest_margin` in `_CATEGORY_ORDER`, so a blowout that was also a
    comeback is reported as the comeback — the more interesting fact.
    """
    both = make_game(
        home_score=130,
        away_score=100,
        home_periods=[15, 35, 40, 40],
        away_periods=[35, 25, 20, 20],
    )

    categories = _categories([both])

    assert categories == ["comeback"], f"expected one slot, got {categories}"


def test_a_superlative_can_be_emptied_by_an_earlier_category(
    make_game: GameFactory,
) -> None:
    """`[VERIFIED]` 2026-08-13 — real, user-facing, and open as TASKS.md P10.

    When one game holds both the widest margin *and* the biggest quarter, `biggest_period`
    comes first in `_CATEGORY_ORDER` and claims it. `largest_margin` then has no candidate
    left — it is not reassigned to the second-widest game — so **the brief never mentions the
    biggest win of the night at all.**

    This happens on the committed 2026-01-15 fixture: Dallas won by 22, the widest margin of
    the slate, and is reported as `biggest_period` instead.

    Asserts current behaviour with the reason stated, so P10 changes it deliberately.
    """
    dual = make_game(
        "Dallas",
        "Utah",
        home_score=144,
        away_score=122,
        home_periods=[43, 34, 34, 33],
        away_periods=[30, 31, 31, 30],
    )
    narrower_blowout = make_game(
        "Team C", "Team D", home_score=125, away_score=104, home_periods=[31] * 4
    )

    categories = _categories([dual, narrower_blowout])

    assert "biggest_period" in categories
    assert "largest_margin" not in categories, (
        "the widest-margin game was claimed by biggest_period and not reassigned"
    )


# --- the real slate -----------------------------------------------------------------------


def test_the_real_2026_01_15_slate(games: list[GameData]) -> None:
    """The nine committed real games, asserted end to end.

    `[INFERRED]` The thresholds are first guesses against exactly this night, so pinning the
    output here means retuning any of them shows up as a reviewable diff rather than a silent
    change to what the operator receives.

    `[VERIFIED]` 2026-08-13, measured: Orlando overcame 16 (comeback), Detroit won by 3
    (closest finish), San Antonio led throughout and won by 18 (wire to wire), Dallas had a
    43-point quarter (biggest period). Note that Dallas also had the night's widest margin at
    22 — see `test_a_superlative_can_be_emptied_by_an_earlier_category` and P10.
    """
    highlights = find_notable_games(games)

    assert len(games) == 9
    assert [h.category for h in highlights] == [
        "comeback",
        "closest_finish",
        "wire_to_wire",
        "biggest_period",
    ]

    by_category = {h.category: h.game for h in highlights}
    assert by_category["comeback"].largest_deficit_overcome == 16
    assert by_category["closest_finish"].margin == 3
    assert by_category["wire_to_wire"].margin == 18
    assert by_category["biggest_period"].biggest_period == 43


def test_no_game_appears_twice_in_the_real_slate(games: list[GameData]) -> None:
    """The one-slot rule, against real data rather than a constructed pair."""
    highlights = find_notable_games(games)
    game_ids = [h.game.game_id for h in highlights]

    assert len(game_ids) == len(set(game_ids))


@pytest.mark.parametrize(
    "threshold",
    [BLOWOUT_MARGIN, CLOSE_GAME_MARGIN, HIGH_SCORING_TOTAL, COMEBACK_DEFICIT],
)
def test_thresholds_are_named_constants(threshold: int) -> None:
    """They are named precisely so they can be retuned once several real briefs are read,
    rather than being buried in a comparison. This asserts they are importable and numeric,
    so a refactor cannot quietly inline them."""
    assert isinstance(threshold, int)
