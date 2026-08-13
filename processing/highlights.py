"""Picks out which of the night's games were worth mentioning.

Uses team-level data only — margins, combined score, and whether the game went to
overtime. Player-level "notable performances" would need a box-score source, and
`[VERIFIED]` no free documented one exists: balldontlie's `/v1/stats` returns 401 on the
free tier, TheSportsDB's `eventstats` 404s, `stats.nba.com` times out from any datacenter
IP, and ESPN's internal API returns 403 to any self-identifying client. Elite individual
performances are covered by the news feed instead, editorially.

This module decides *what* is notable and why. It does not decide how that reads — the
category strings below are looked up by the formatter, so wording changes never touch
this logic.
"""

from __future__ import annotations

from collections.abc import Callable

from models.schemas import GameData, GameHighlight

# Two conditions must both hold before a game is reported, which is what keeps "notable"
# meaningful:
#
#   1. It must be the *most* extreme game of the night in its category (superlative), so
#      the brief never says "biggest blowout" twice with two different numbers.
#   2. It must still clear a threshold, so a quiet night reports nothing rather than
#      crowning a six-point win as a blowout.
#
# `[INFERRED]` These numbers are first guesses against a single night of real data
# (2026-01-15). They are named constants precisely so they can be retuned once several
# real briefs have been read, rather than being buried in a comparison.
BLOWOUT_MARGIN = 20
CLOSE_GAME_MARGIN = 5
HIGH_SCORING_TOTAL = 250
COMEBACK_DEFICIT = 15

# A quarter this big is unusual enough to be the story of the game on its own.
# `[VERIFIED]` The highest single period in the captured 9-game slate was 42.
BIG_PERIOD_POINTS = 40

# Outscoring the opponent by this much after half time is a takeover rather than a win.
SECOND_HALF_SWING = 20

# Order in which categories are reported, and the order used to resolve a game that
# qualifies for more than one. A game is reported once, under its first matching category,
# so one game never occupies several slots in the brief.
_CATEGORY_ORDER = (
    "comeback",
    "overtime",
    "closest_finish",
    "wire_to_wire",
    "second_half_takeover",
    "biggest_period",
    "largest_margin",
    "highest_scoring",
)

# Categories where **every** qualifying game is reported. These are properties of a game
# rather than rankings: overtime and comebacks are rare enough that each instance is worth
# knowing, and "the most wire-to-wire" is meaningless.
_EVERY_INSTANCE: dict[str, Callable[[GameData], bool]] = {
    "comeback": lambda game: game.largest_deficit_overcome >= COMEBACK_DEFICIT,
    "overtime": lambda game: game.went_to_overtime,
    # Reported only in a band. `[VERIFIED]` 2026-08-08: leading at every break happened in
    # 3 of 9 real games — common, not remarkable, and flagging all of them made this the
    # dominant category. What is notable is the *combination*: a team that led throughout
    # **and** never pulled clear held someone off all night, which no other category
    # expresses. Above the blowout line it is redundant with `largest_margin`; below the
    # close-game line the finish itself is the story.
    "wire_to_wire": lambda game: (
        game.led_wire_to_wire and CLOSE_GAME_MARGIN < game.margin < BLOWOUT_MARGIN
    ),
    "second_half_takeover": lambda game: game.second_half_swing >= SECOND_HALF_SWING,
}

# Categories where only the single most extreme game is reported, and only if it clears its
# threshold. Each entry is (how to measure, which extreme, does it clear the bar).
_SUPERLATIVES: dict[
    str,
    tuple[
        Callable[[GameData], int], Callable[..., GameData], Callable[[GameData], bool]
    ],
] = {
    "closest_finish": (
        lambda game: game.margin,
        min,
        lambda game: game.margin <= CLOSE_GAME_MARGIN,
    ),
    "biggest_period": (
        lambda game: game.biggest_period,
        max,
        lambda game: game.biggest_period >= BIG_PERIOD_POINTS,
    ),
    "largest_margin": (
        lambda game: game.margin,
        max,
        lambda game: game.margin >= BLOWOUT_MARGIN,
    ),
    "highest_scoring": (
        lambda game: game.total_points,
        max,
        lambda game: game.total_points >= HIGH_SCORING_TOTAL,
    ),
}


def _candidates(category: str, available: list[GameData]) -> list[GameData]:
    """Which of the still-unclaimed games qualify for this category.

    Superlatives are measured over `available` rather than over the whole slate. `[VERIFIED]`
    2026-08-13 (TASKS.md P10): measuring over the whole slate meant that when one game held
    several superlatives, the categories it did not get reported under produced **nothing** —
    they were not reassigned to the next-best game. On the real 2026-01-15 slate Dallas held
    the widest margin, the biggest quarter and the highest total, so the brief silently lost
    both "biggest win" and "highest scoring".
    """
    if category in _EVERY_INSTANCE:
        return [game for game in available if _EVERY_INSTANCE[category](game)]

    measure, extreme, clears = _SUPERLATIVES[category]
    best = extreme(available, key=measure)
    return [best] if clears(best) else []


def find_notable_games(games: list[GameData]) -> list[GameHighlight]:
    """Return at most one highlight per game, at most one game per superlative category.

    Overtime is the exception: every overtime game is reported, because OT is rare enough
    that each one is independently worth knowing about.

    Returns an empty list when nothing clears the thresholds. That is a normal outcome on
    a quiet night, not an error.
    """
    if not games:
        return []

    claimed: set[int] = set()
    highlights: list[GameHighlight] = []

    for category in _CATEGORY_ORDER:
        # Recomputed each time, so a superlative is measured over what is still free rather
        # than over the whole slate. This is what stops a category going silent when the
        # game it would have named was already claimed by an earlier one (P10).
        available = [game for game in games if game.game_id not in claimed]
        if not available:
            break

        for game in _candidates(category, available):
            if game.game_id in claimed:
                continue
            claimed.add(game.game_id)
            highlights.append(GameHighlight(category=category, game=game))

    return highlights
