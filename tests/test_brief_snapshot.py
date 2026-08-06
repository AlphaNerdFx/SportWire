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
from pathlib import Path

import pytest

from delivery.brief import build_messages
from models.schemas import GameData, NewsArticle
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
        games, find_notable_games(games), sort_by_priority(articles)
    )
    assert len(messages) == 3, "expected scores, notable and news sections"

    rendered = "\n\n=== MESSAGE BREAK ===\n\n".join(messages)
    assert_matches_snapshot("full_brief", rendered, snapshot_update)


def test_offseason_brief_matches_snapshot(
    articles: list[NewsArticle], snapshot_update: bool
) -> None:
    """With no games — the normal case outside the season — only news is sent."""
    messages = build_messages([], [], sort_by_priority(articles))
    assert len(messages) == 1, "no games should mean no scores and no notable sections"

    assert_matches_snapshot("offseason_brief", messages[0], snapshot_update)


def test_nothing_to_report_sends_nothing() -> None:
    """An empty pipeline produces no messages at all, rather than an empty brief."""
    assert build_messages([], [], []) == []
