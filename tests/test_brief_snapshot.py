"""Snapshot tests: the operator's approved output becomes the assertion.

The operator's stated position was that correctness can only be judged by looking at what
arrives on the phone. That is true for *usefulness* and false for *completeness* — a brief
that silently lost five stories looks exactly like a correct one. `[VERIFIED]` This happened:
a run delivered two messages instead of three, and the output gave no indication whether
that was correct, a crash, or lost data. The answer came from database timestamps.

These tests close that gap without requiring anyone to write assertions by hand:

  1. The pipeline renders the full brief from the saved fixtures.
  2. A human reads it once and approves it.
  3. The approved text is stored in `tests/snapshots/`.
  4. Any later change that alters the output fails, and prints the diff.

The value is in step 4 — a diff shows what *disappeared*, which is the failure looking at
the output can never reveal.

To approve a new or intentionally-changed snapshot:
    pytest --snapshot-update
Read the diff before doing that. Blindly updating a snapshot is the same mistake as editing
a test to make it pass (`OPERATING_RULES.md` §4).
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from pathlib import Path

import pytest

from delivery.brief import build_messages
from models.schemas import GameData, NewsArticle
from processing.cluster import group_related
from processing.highlights import find_notable_games
from processing.priority import sort_by_priority

SNAPSHOTS = Path(__file__).parent / "snapshots"


def assert_matches_snapshot(name: str, actual: str, snapshot_update: bool) -> None:
    """Compare text against its approved snapshot, or write it if approving."""
    SNAPSHOTS.mkdir(exist_ok=True)
    path = SNAPSHOTS / f"{name}.txt"

    if snapshot_update or not path.exists():
        path.write_text(actual, encoding="utf-8")
        if not snapshot_update:
            pytest.fail(
                f"No snapshot existed for {name!r}; one was written to {path}.\n"
                "Read it, confirm it is correct, then re-run. This failure is deliberate: "
                "an unreviewed snapshot asserts nothing."
            )
        return

    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=f"approved/{name}",
                tofile=f"current/{name}",
                lineterm="",
            )
        )
        pytest.fail(f"Output changed from the approved snapshot:\n\n{diff}")


def test_full_brief_matches_snapshot(
    games: list[GameData], articles: list[NewsArticle], snapshot_update: bool
) -> None:
    """The complete three-message brief, exactly as it would be delivered."""
    messages = build_messages(
        games,
        find_notable_games(games),
        group_related(sort_by_priority(articles)),
    )
    assert len(messages) == 3, "expected scores, notable and news sections"

    rendered = "\n\n=== MESSAGE BREAK ===\n\n".join(messages)
    assert_matches_snapshot("full_brief", rendered, snapshot_update)


def test_offseason_brief_matches_snapshot(
    articles: list[NewsArticle], snapshot_update: bool
) -> None:
    """With no games — the normal case outside the season — only news is sent."""
    messages = build_messages([], [], group_related(sort_by_priority(articles)))
    assert len(messages) == 1, "no games should mean no scores and no notable sections"

    assert_matches_snapshot("offseason_brief", messages[0], snapshot_update)


def test_nothing_to_report_sends_nothing() -> None:
    """An empty pipeline produces no messages at all, rather than an empty brief."""
    assert build_messages([], [], []) == []


def test_a_flagged_claim_is_delivered_without_a_marker(
    make_article: Callable[..., NewsArticle],
) -> None:
    """~~A flagged claim is marked in the brief.~~ **Requirement withdrawn 2026-08-26** by the
    operator: *"remove the warning about the names. I don't want it."*

    Rewritten rather than deleted, because the behaviour still needs pinning: the sentence must
    reach the phone **unchanged**, with no mark and no legend. The detection itself is
    untouched — `main.py` still computes and logs the flagged sentences, so TASKS.md P5 stays
    countable.

    `[VERIFIED]` The marker's only production firing was a false positive, on a true sentence
    about James Harden and the Cavaliers, so removing it costs nothing measured.
    """
    claim = "The Pelicans are welcoming back Damian Lillard following his trade from Portland."
    messages = build_messages(
        [],
        [],
        [[make_article("Blazers preview: Lillard is back but questions remain")]],
        news_summary=f"Watford signed with the Pelicans. {claim}",
        unsupported_claims=[claim],
    )

    news = "\n".join(messages)
    assert claim in news, "the sentence must still be delivered"
    assert "⚠️" not in news, "no marker"
    assert "never appear in the same source article" not in news, "no legend"


def test_a_brief_with_nothing_flagged_gains_no_marker(
    make_article: Callable[..., NewsArticle],
) -> None:
    """The quiet case. A clean brief must look exactly as it did before this existed."""
    messages = build_messages(
        [],
        [],
        [[make_article("Blazers preview: Lillard is back")]],
        news_summary="Lillard is back with the Blazers.",
    )

    news = "\n".join(messages)
    assert "⚠️" not in news
    assert "never appear in the same source article" not in news


def test_a_source_that_failed_is_named_in_the_brief(
    make_article: Callable[..., NewsArticle],
) -> None:
    """`[VERIFIED]` 2026-08-18: Reddit answered HTTP 500 for the whole 00:00 run and the brief
    lost 25 of 87 articles while saying nothing.

    A failed source and a quiet one both produce no articles, so a brief that stays silent
    looks complete when it is not. Second observed case, after CBS timed out on 2026-08-15.
    """
    messages = build_messages(
        [],
        [],
        [[make_article("Blazers preview: Lillard is back")]],
        news_summary="Lillard is back with the Blazers.",
        failed_sources=["r/nba"],
    )

    news = "\n".join(messages)
    assert "r/nba" in news
    assert "Missing this run" in news


def test_a_brief_with_every_source_healthy_says_nothing_about_sources(
    make_article: Callable[..., NewsArticle],
) -> None:
    """The complement, so the note cannot become permanent furniture."""
    messages = build_messages(
        [],
        [],
        [[make_article("Blazers preview: Lillard is back")]],
        news_summary="Lillard is back with the Blazers.",
        failed_sources=[],
    )

    assert "Missing this run" not in "\n".join(messages)


def test_each_brief_names_its_league(
    make_article: Callable[..., NewsArticle],
) -> None:
    """Two briefs land on the same phone seconds apart, so each has to say what it is.

    `[INFERRED]` Both headings reading "NEWS" is not a cosmetic problem: the reader has no
    way to tell which sport they are looking at except by recognising the team names, which
    defeats the point of splitting them (ADR-015).
    """
    story = [[make_article("Mahomes signs a contract extension")]]

    prose = build_messages([], [], story, news_summary="Mahomes signed.", league="NFL")
    listed = build_messages([], [], story, league="NFL")

    assert "NFL" in "\n".join(prose), "the written brief must name its league"
    assert "NFL" in "\n".join(listed), "the headline list must name its league too"


def test_a_single_league_brief_keeps_the_plain_heading(
    make_article: Callable[..., NewsArticle],
) -> None:
    """The complement. Passing no league is what a basketball-only install does.

    `[INFERRED]` Worth pinning because the snapshots were approved against the plain heading,
    so a default that quietly changed would rewrite output nobody asked to change.
    """
    messages = build_messages(
        [], [], [[make_article("Blazers preview: Lillard is back")]]
    )

    assert "📰 NEWS" in "\n".join(messages)
