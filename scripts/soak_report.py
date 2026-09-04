"""Count what the briefs actually did, from the evidence the runs left behind.

`[VERIFIED]` This exists because of a mistake the project made twice. A comment once claimed
a ~84% pass rate from a single sitting of 3 of 5, and the next two runs contradicted it
entirely (TASKS.md P4). The lesson written down at the time was "two runs is not a rate
either", and P54 and P56 are both open right now waiting on exactly this count.

Reads `evidence/` rather than the log, because a batch file records what was *delivered*
alongside the articles it was built from, survives log rotation, and is already written by
every run. `[INFERRED]` The log carries the same outcomes but as prose to be grepped, which
is a shape that invites reading what you hoped to see.

Nothing here is a check and nothing fails: it prints numbers and exits 0. A rate is evidence
to be argued with, not a gate.

    python scripts/soak_report.py                 # everything recorded
    python scripts/soak_report.py --days 7        # the last week
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Run directly, so the project root is not on the path. Same reason as
# `scripts/schedule_windows.py`: the evidence directory is decided by settings, and a second
# place deciding it is how the two come to disagree.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings


def read_batches(directory: Path) -> tuple[list[dict[str, object]], int]:
    """Every readable batch in `directory`, plus a count of the ones that were not.

    `[VERIFIED]` 2026-08-27 a run killed mid-write left a 0 byte file that stopped a reader
    dead. Writes are atomic now, but a report that dies on one bad file is the wrong shape
    for a tool whose whole job is to describe what happened when things went wrong.
    """
    batches: list[dict[str, object]] = []
    unreadable = 0
    for path in sorted(directory.glob("*.json")):
        try:
            batches.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            unreadable += 1
    return batches, unreadable


def within(
    batches: list[dict[str, object]], days: int | None
) -> list[dict[str, object]]:
    """Batches recorded in the last `days`, or all of them when `days` is None."""
    if days is None:
        return batches
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for batch in batches:
        stamp = batch.get("recorded_at")
        if not isinstance(stamp, str):
            continue
        try:
            recorded = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if recorded >= cutoff:
            kept.append(batch)
    return kept


def report(batches: list[dict[str, object]], unreadable: int) -> str:
    """The whole report, as text. Returned rather than printed so it can be tested."""
    if not batches:
        return "No batches recorded yet. Nothing to report, which is itself the answer."

    by_league: dict[str, Counter[bool]] = defaultdict(Counter)
    by_day: dict[str, Counter[bool]] = defaultdict(Counter)
    for batch in batches:
        league = str(batch.get("label") or "unlabelled")
        prose = bool(batch.get("delivered_prose"))
        by_league[league][prose] += 1
        stamp = str(batch.get("recorded_at") or "")[:10]
        by_day[stamp][prose] += 1

    lines = [f"{len(batches)} briefs recorded"]
    if unreadable:
        lines.append(f"  ({unreadable} file(s) could not be read and were skipped)")
    lines.append("")
    lines.append("Prose delivered, by league:")
    for league in sorted(by_league):
        counts = by_league[league]
        total = counts[True] + counts[False]
        share = 100.0 * counts[True] / total
        lines.append(
            f"  {league:<12} {counts[True]:>3} of {total:<3} ({share:5.1f}%)"
            f"   fell back {counts[False]}"
        )

    lines.append("")
    lines.append("By day:")
    for day in sorted(by_day):
        counts = by_day[day]
        total = counts[True] + counts[False]
        lines.append(f"  {day}   prose {counts[True]:>2} of {total:<2}")

    # The v1.0.0 gate counts days on which a brief was delivered, and a run writes one batch
    # per league. `[VERIFIED]` 2026-09-04 the gate changed from 14 *consecutive* days to 14
    # accumulated ones, because a shut-down PC reset the count and the PC being off says
    # nothing about whether the software runs unattended. That makes this line a straight
    # count rather than a longest-run calculation, which is why there is no streak here.
    days_seen = len(by_day)
    lines.append("")
    lines.append(
        f"Days with a delivered brief: {days_seen} of the 14 the v1.0.0 gate asks for "
        f"(issue #1). They accumulate and need not be consecutive."
    )
    return "\n".join(lines)


def audit(batches: list[dict[str, object]]) -> str:
    """The most recent brief for each league, beside what the checker doubted about it.

    `[VERIFIED]` 2026-08-27 the operator read a delivered brief and asked whether the football
    news was invented. Two of its seven claims were: it said Watson had *visited* Jim Brown's
    statue when someone had taped signs on it criticising him, and it merged a separate
    training-camp skirmish into a team-mate's injury story.

    The pipeline had already noticed. The entity-pair check flagged exactly that sentence, the
    only one it flagged in the whole brief, and the flag went into the log and the evidence
    file and nowhere the reader would see it, because the operator asked for the warning to be
    taken out of the brief itself. `[INFERRED]` That instruction was about the brief, not about
    the evidence, so this shows the same information on request instead of unasked.

    A flagged sentence is a prompt to check, not a verdict. It means the entities in it never
    appear together in any single source article, which is what an invented relationship looks
    like and also what a correct summary of two related items looks like.
    """
    latest: dict[str, dict[str, object]] = {}
    for batch in batches:
        if not batch.get("summary"):
            continue
        latest[str(batch.get("label") or "unlabelled")] = batch

    if not latest:
        return "No brief with prose recorded yet."

    lines: list[str] = []
    for league in sorted(latest):
        batch = latest[league]
        articles = batch.get("articles")
        count = len(articles) if isinstance(articles, list) else 0
        lines.append(
            f"=== {league} · {str(batch.get('recorded_at'))[:16]} · from {count} articles"
        )
        lines.append("")
        lines.append(str(batch.get("summary")))
        lines.append("")
        flagged = batch.get("unsupported_claims") or []
        if isinstance(flagged, list) and flagged:
            lines.append("Sentences whose names never share a source article:")
            for claim in flagged:
                lines.append(f"  ? {claim}")
        else:
            lines.append(
                "Nothing flagged: every sentence's names co-occur in some article."
            )
        lines.append("")
        lines.append("Built from:")
        if isinstance(articles, list):
            for article in articles:
                lines.append(f"  - {str(article.get('title'))[:92]}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the report. Always succeeds: this describes, it does not judge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=None, help="only count the last N days"
    )
    parser.add_argument(
        "--evidence", type=Path, default=None, help="override the evidence directory"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help=(
            "show the latest brief per league beside the sentences the checker doubted "
            "and the headlines it was built from, for reading against the sources"
        ),
    )
    args = parser.parse_args(argv)

    directory = args.evidence or Settings.from_env().evidence_path
    if not directory.exists():
        print(f"No evidence directory at {directory}.")
        return 0

    batches, unreadable = read_batches(directory)
    selected = within(batches, args.days)
    print(audit(selected) if args.audit else report(selected, unreadable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
