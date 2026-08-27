"""Tests for the soak report, the instrument P4, P54 and P56 all wait on.

`[VERIFIED]` The report exists because this project twice quoted a rate from a single sitting
and was wrong both times. A tool for counting outcomes has to be right about the counting, so
the arithmetic is asserted rather than eyeballed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.soak_report import main, read_batches, report, within


def _batch(path: Path, *, label: str, prose: bool, days_ago: float = 0.0) -> None:
    recorded = datetime.now(timezone.utc) - timedelta(days=days_ago)
    path.write_text(
        json.dumps(
            {
                "recorded_at": recorded.isoformat(),
                "label": label,
                "delivered_prose": prose,
                "articles": [],
            }
        ),
        encoding="utf-8",
    )


def test_the_rate_is_counted_per_league(tmp_path: Path) -> None:
    """Per league, because a mixed number hides the league that is struggling.

    `[VERIFIED]` 2026-08-27 the first real reading was 8 of 9 for basketball and 5 of 8 for
    football. Averaged together that is a healthy-looking number that says nothing about
    football being the one to watch.
    """
    _batch(tmp_path / "a.json", label="NBA", prose=True)
    _batch(tmp_path / "b.json", label="NBA", prose=True)
    _batch(tmp_path / "c.json", label="NFL", prose=False)

    batches, unreadable = read_batches(tmp_path)
    text = report(batches, unreadable)

    assert "NBA            2 of 2   (100.0%)" in text
    assert "NFL            0 of 1   (  0.0%)" in text


def test_an_unreadable_batch_is_counted_not_fatal(tmp_path: Path) -> None:
    """`[VERIFIED]` 2026-08-27 a 0 byte evidence file stopped a reader dead.

    Writes are atomic now, so this should not recur, but a tool whose job is to describe what
    happened when things went wrong is the wrong place to die on a damaged file. It is
    reported rather than ignored, because a file that cannot be read is itself a finding.
    """
    _batch(tmp_path / "good.json", label="NBA", prose=True)

    # Two different kinds of unreadable, because they raise different exceptions and catching
    # only one leaves the other fatal. `[VERIFIED]` The empty file is the case that actually
    # happened; it fails to parse. A path that cannot be opened at all fails earlier, and a
    # test using only the first kind lets a narrower `except` pass unnoticed.
    (tmp_path / "empty.json").write_text("", encoding="utf-8")
    (tmp_path / "unopenable.json").mkdir()

    batches, unreadable = read_batches(tmp_path)

    assert len(batches) == 1
    assert unreadable == 2
    assert "2 file(s) could not be read" in report(batches, unreadable)


def test_the_window_excludes_older_batches(tmp_path: Path) -> None:
    """`--days` has to actually cut, or a claim about "this week" quietly covers everything."""
    _batch(tmp_path / "new.json", label="NBA", prose=True, days_ago=1)
    _batch(tmp_path / "old.json", label="NBA", prose=False, days_ago=30)

    batches, _ = read_batches(tmp_path)

    assert len(within(batches, days=7)) == 1
    assert len(within(batches, days=None)) == 2


def test_an_empty_directory_says_so_rather_than_dividing_by_zero(
    tmp_path: Path,
) -> None:
    """`[INFERRED]` The first person to run this will have no evidence yet."""
    assert "Nothing to report" in report([], 0)
    assert main(["--evidence", str(tmp_path)]) == 0


def test_a_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    """Reporting is never a gate. It describes; it does not judge."""
    assert main(["--evidence", str(tmp_path / "nope")]) == 0
