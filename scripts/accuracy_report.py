"""Two numbers this project had been arguing about without measuring.

`[VERIFIED]` 2026-09-05, asked for by the operator: *"establishing a reliable metric for
accuracy. A metric for measuring how much the model hallucinates along with another model that
measures how much news retrieval is relevant to actual news as compared to old meta posts or
highlights etc."*

    python scripts/accuracy_report.py              # both metrics
    python scripts/accuracy_report.py --since 2026-08-28
    python scripts/accuracy_report.py --sample 12  # draw a hand-audit sample

**Read this before quoting any number below.**

Both metrics are computed from the pipeline's own opinion of itself, and that is a real limit
rather than a caveat to wave away:

  - **Fabrication** counts what `processing/validate.py` *caught*. It cannot count what the
    validator never sees. `[VERIFIED]` 2026-09-04, reading four delivered briefs against their
    sources by hand, three errors were found that no check flagged, because each was made
    inside a single clause where there is no second entity to contradict.
  - **Relevance** counts what `processing/newsworthy.py` *dropped*. A metric built from the
    same rules that do the filtering measures consistency, not truth: if a rule is blind to a
    class of junk, both the filter and this report are blind to it in the same way.

`[INFERRED]` So these track **movement**, and a hand audit is what anchors them to reality.
`--sample` draws that audit for you. `docs/reference/METRICS.md` holds the protocol and the
calibration constants measured so far.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "sportwire.log"

_ACCEPTED = re.compile(
    r"^(\d{4}-\d\d-\d\d).*summary accepted on attempt (\d+) of (\d+)"
)
_REJECTED = re.compile(r"^(\d{4}-\d\d-\d\d).*attempt (\d+) rejected \((.*)\)$")
_EXHAUSTED = re.compile(
    r"^(\d{4}-\d\d-\d\d).*?(OpenRouter|Ollama).*no attempt passed validation after"
)
_FETCHED = re.compile(r"^(\d{4}-\d\d-\d\d).*fetched \d+ games, (\d+) articles")
_DROPPED = re.compile(r"^(\d{4}-\d\d-\d\d).*dropping non-news item \(([^)]*)\)")

# A drop reason to the class of thing it removed, for reporting. The rule names are internal;
# these are what the operator asked about.
_CLASSES = {
    "content-type tag": "clips, charts and meme posts",
    "speculation phrase": "rankings, mock drafts and predictions",
    "retrospective phrase": "pieces about the past",
    "community discussion": "reader questions",
    "community opinion": "reader opinion",
    "subreddit business": "subreddit housekeeping",
    "another sport": "a sport this brief does not cover",
    "older than": "stale beyond the age window",
}


def _classify(reason: str) -> str:
    for prefix, label in _CLASSES.items():
        if reason.startswith(prefix):
            return label
    if re.match(r"^\d+h$", reason.strip()) or "h (" in reason:
        return "stale beyond the age window"
    return "other"


def read_log(path: Path, since: str | None) -> dict[str, object]:
    """Attempt outcomes and drop reasons, straight from the log."""
    accepted = rejected = 0
    hosted_errored = local_exhausted = 0
    fetched = 0
    first_try = 0
    reasons: Counter[str] = Counter()
    drops: Counter[str] = Counter()

    if not path.exists():
        return {"present": False}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for pattern, kind in (
            (_ACCEPTED, "accepted"),
            (_REJECTED, "rejected"),
            (_EXHAUSTED, "exhausted"),
            (_FETCHED, "fetched"),
            (_DROPPED, "dropped"),
        ):
            match = pattern.match(line)
            if not match:
                continue
            if since and match.group(1) < since:
                break
            if kind == "accepted":
                accepted += 1
                first_try += match.group(2) == "1"
            elif kind == "rejected":
                rejected += 1
                detail = match.group(3)
                if "invented names" in detail:
                    reasons["a name the sources never wrote"] += 1
                if "invented figures" in detail:
                    reasons["a number the sources never wrote"] += 1
                if "preamble" in detail:
                    reasons["a preamble it was told not to write"] += 1
            elif kind == "exhausted":
                # `[VERIFIED]` 2026-09-05: 48 of the 80 of these are the hosted provider
                # returning 429 before writing a word. Counting those as the model failing
                # would have overstated fabrication by more than half.
                if match.group(2) == "OpenRouter":
                    hosted_errored += 1
                else:
                    local_exhausted += 1
            elif kind == "fetched":
                fetched += int(match.group(2))
            else:
                drops[_classify(match.group(2))] += 1
            break

    return {
        "present": True,
        "accepted": accepted,
        "rejected": rejected,
        "hosted_errored": hosted_errored,
        "local_exhausted": local_exhausted,
        "fetched": fetched,
        "first_try": first_try,
        "reasons": reasons,
        "drops": drops,
    }


def read_evidence(directory: Path, since: str | None) -> dict[str, object]:
    """What actually reached the phone, from the batch files each run writes."""
    briefs = 0
    prose = 0
    flagged_sentences = 0
    delivered_articles = 0
    per_league: Counter[str] = Counter()

    for path in sorted(directory.glob("*.json")):
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stamp = str(batch.get("recorded_at") or "")[:10]
        if since and stamp < since:
            continue
        briefs += 1
        per_league[str(batch.get("label") or "unlabelled")] += 1
        if batch.get("summary"):
            prose += 1
            claims = batch.get("unsupported_claims") or []
            if isinstance(claims, list):
                flagged_sentences += len(claims)
        articles = batch.get("articles")
        if isinstance(articles, list):
            delivered_articles += len(articles)

    return {
        "briefs": briefs,
        "prose": prose,
        "flagged": flagged_sentences,
        "articles": delivered_articles,
        "per_league": per_league,
    }


def _bar(share: float, width: int = 24) -> str:
    filled = round(share * width)
    return "#" * filled + "." * (width - filled)


def fabrication(log: dict[str, object], evidence: dict[str, object]) -> list[str]:
    """Metric 1: how often the model writes something the sources do not support."""
    lines = [
        "FABRICATION — how often the model invents, as far as anything can tell",
        "",
    ]
    if not log.get("present"):
        return lines + ["  No log found, so nothing here can be computed."]

    accepted = int(log["accepted"])
    rejected = int(log["rejected"])
    attempts = accepted + rejected
    if not attempts:
        return lines + ["  No summarisation attempts recorded yet."]

    caught = rejected / attempts
    lines.append(f"  attempts               {attempts}")
    lines.append(
        f"  rejected as invented   {rejected}  ({caught:6.1%})  {_bar(caught)}"
    )
    lines.append(
        f"  accepted first try     {int(log['first_try'])}"
        f"  ({int(log['first_try']) / attempts:6.1%})"
    )
    lines.append(
        f"  briefs that never passed  {int(log['local_exhausted'])}"
        "   (fell back to a headline list)"
    )
    lines.append(
        f"  hosted provider errored   {int(log['hosted_errored'])}"
        "   (429 before writing a word, not a fabrication)"
    )
    reasons = log["reasons"]
    if isinstance(reasons, Counter) and reasons:
        lines.append("")
        lines.append("  what was rejected for:")
        for reason, count in reasons.most_common():
            lines.append(f"    {count:>4}  {reason}")

    prose = int(evidence["prose"])
    if prose:
        per_brief = int(evidence["flagged"]) / prose
        lines.append("")
        lines.append(
            f"  doubted sentences in delivered briefs   {int(evidence['flagged'])}"
            f" across {prose}  ({per_brief:.2f} per brief)"
        )
        lines.append(
            f"  of those, roughly {per_brief * 0.67:.2f} per brief are real errors,"
            " using the 6-of-9 hand audit"
        )
        lines.append("  and at least 0.75 per brief are errors nothing flagged at all")
    lines.append("")
    lines.append(
        "  `[UNKNOWN]` The true rate. This counts what the checks catch, and the 2026-09-04"
    )
    lines.append(
        "  audit found more errors that nothing flagged than flags that were wrong."
    )
    return lines


def relevance(log: dict[str, object], evidence: dict[str, object]) -> list[str]:
    """Metric 2: how much of what the feeds hand over is actually news."""
    lines = ["RELEVANCE — how much of what the feeds give us is news at all", ""]
    drops = log.get("drops")
    if not isinstance(drops, Counter) or not drops:
        return lines + ["  No drops recorded yet."]

    dropped = sum(drops.values())
    delivered = int(evidence["articles"])
    fetched = int(log.get("fetched") or 0)
    # The denominator is what the feeds handed over, taken from the fetch lines. `[VERIFIED]`
    # 2026-09-05 an earlier version of this used dropped + delivered, which is wrong: what
    # reaches a brief is also cut by deduplication, grouping and the story cap, none of which
    # is a judgement about relevance. That version read 26.1% and meant nothing.
    if not fetched:
        return lines + [
            "  No fetch lines in the log, so there is no honest denominator."
        ]

    news = 1 - dropped / fetched

    lines.append(f"  articles the feeds handed over  {fetched}")
    lines.append(
        f"  survived the news filter        {fetched - dropped}  ({news:6.1%})  {_bar(news)}"
    )
    lines.append(
        f"  removed as not news             {dropped}  ({dropped / fetched:6.1%})"
    )
    lines.append(
        f"  reached a brief                 {delivered}"
        "   (also cut by dedup, grouping and the story cap)"
    )
    lines.append("")
    lines.append("  what was removed, and as what:")
    for label, count in drops.most_common():
        lines.append(f"    {count:>5}  ({count / dropped:5.1%})  {label}")
    lines.append("")
    lines.append(
        "  `[INFERRED]` A high removal share is not a problem on its own. Two of these feeds"
    )
    lines.append(
        "  are community boards, where most posts were never reporting to begin with."
    )
    lines.append(
        "  `[UNKNOWN]` What share of what *reached* a brief is genuinely news. No rule can"
    )
    lines.append("  answer that about itself; use --sample and read them.")
    return lines


def sample(directory: Path, since: str | None, count: int, seed: int) -> list[str]:
    """Draw delivered headlines at random, for the hand audit the metrics cannot replace."""
    titles: list[tuple[str, str, str]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stamp = str(batch.get("recorded_at") or "")[:10]
        if since and stamp < since:
            continue
        for article in batch.get("articles") or []:
            titles.append(
                (stamp, str(batch.get("label") or "?"), str(article.get("title"))[:96])
            )

    if not titles:
        return ["Nothing delivered in that window to sample."]

    chosen = random.Random(seed).sample(titles, min(count, len(titles)))
    lines = [
        f"HAND AUDIT SAMPLE — {len(chosen)} of {len(titles)} delivered articles, seed {seed}",
        "",
        "  Mark each: news / not news. The share marked news is the relevance number that",
        "  counts, because it is the only one not produced by the filter judging itself.",
        "",
    ]
    for index, (stamp, league, title) in enumerate(chosen, start=1):
        lines.append(f"  {index:>2}. [ ] {stamp}  {league:<4} {title}")
    return lines


def main(argv: list[str] | None = None) -> int:
    """Print both metrics. Nothing here fails: a rate is evidence, not a gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since", default=None, help="only count from this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--log", type=Path, default=LOG_PATH, help="override the log path"
    )
    parser.add_argument(
        "--evidence", type=Path, default=None, help="override the evidence directory"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="draw N delivered headlines to audit by hand",
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="sample seed, for a repeatable draw"
    )
    args = parser.parse_args(argv)

    directory = args.evidence or Settings.from_env().evidence_path
    if not directory.exists():
        print(f"No evidence directory at {directory}.")
        return 0

    if args.sample:
        print("\n".join(sample(directory, args.since, args.sample, args.seed)))
        return 0

    log = read_log(args.log, args.since)
    evidence = read_evidence(directory, args.since)

    window = f" since {args.since}" if args.since else ""
    print(f"SportWire accuracy{window}\n")
    print("\n".join(fabrication(log, evidence)))
    print()
    print("\n".join(relevance(log, evidence)))
    print()
    print(
        "Both numbers are the pipeline judging itself. docs/reference/METRICS.md says what"
    )
    print("that is worth and how to calibrate it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
