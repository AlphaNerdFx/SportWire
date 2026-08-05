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

# Order in which categories are reported, and the order used to resolve a game that
# qualifies for more than one. A game is reported once, under its first matching category,
# so one game never occupies several slots in the brief.
_CATEGORY_ORDER = ("overtime", "closest_finish", "largest_margin", "highest_scoring")


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
    by_category: dict[str, list[GameData]] = {}

    # Every overtime game, not just one — OT is rare and each instance is notable.
    by_category["overtime"] = [game for game in games if game.went_to_overtime]

    # Superlatives: the single most extreme game, and only if it clears its threshold.
    closest = min(games, key=lambda game: game.margin)
    if closest.margin <= CLOSE_GAME_MARGIN:
        by_category["closest_finish"] = [closest]

    widest = max(games, key=lambda game: game.margin)
    if widest.margin >= BLOWOUT_MARGIN:
        by_category["largest_margin"] = [widest]

    highest = max(games, key=lambda game: game.total_points)
    if highest.total_points >= HIGH_SCORING_TOTAL:
        by_category["highest_scoring"] = [highest]

    highlights: list[GameHighlight] = []
    for category in _CATEGORY_ORDER:
        for game in by_category.get(category, []):
            if game.game_id in claimed:
                continue
            claimed.add(game.game_id)
            highlights.append(GameHighlight(category=category, game=game))

    return highlights
