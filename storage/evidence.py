"""Keeps each run's batch on disk, so a failure can still be reproduced next week.

Every diagnosis in this project has needed the same thing: **the articles that were actually
summarised**, not the feeds they came from. `[VERIFIED]` Reconstructing that took two steps
all week — read the delivered article ids out of `seen_articles`, then match them against a
capture of the whole feed — and both halves proved fragile:

- `[VERIFIED]` 2026-08-25 the captures lived in `/tmp` and the machine was shut down, so six
  days of live batches went with it (TASKS.md P38). Numbers measured against 288 live
  articles are no longer reproducible.
- `[VERIFIED]` The same day, a purge bug deleted the delivery record those ids came from
  (P39). Behaviour was never at risk; the evidence was.

So this stores the batch itself. `[INFERRED]` It is both smaller and more useful than the
feeds: about 5 KB per run against roughly 400 KB of XML, and it is exactly the input needed
to replay validation offline. A year of three runs a day is under 6 MB.

**Not committed.** `evidence/` is git-ignored. Feed text is the C3 exposure ADR-009 exists to
avoid, and a directory that grows forever does not belong in a repository meant to be
published. Promote a specific batch into `tests/fixtures/` when a task cites it as evidence,
which is the same thing the three fixtures already there did.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

DEFAULT_EVIDENCE_DIR = Path("evidence")

# How many runs to keep. `[INFERRED]` Three runs a day makes this about six weeks, which
# comfortably covers the fourteen-run soak in GitHub #1 and the week-long lag between a brief
# arriving and somebody reading it closely enough to complain.
DEFAULT_KEEP = 120


def _slug(label: str) -> str:
    """Make a label safe to put in a filename."""
    return "".join(c if c.isalnum() else "-" for c in label).strip("-").lower()


def record_batch(
    articles: list[NewsArticle],
    *,
    summary: str | None,
    unsupported_claims: list[str] | None = None,
    failed_sources: list[str] | None = None,
    directory: Path = DEFAULT_EVIDENCE_DIR,
    keep: int = DEFAULT_KEEP,
    label: str | None = None,
) -> Path | None:
    """Write one run's batch and outcome. Returns the file, or None if nothing was written.

    `summary` is the accepted prose, or None when the run fell back to the headline list.
    Storing both together is the point: a rejection is only diagnosable beside the articles it
    was judged against.

    **Never raises.** `CLAUDE.md` §5 rule 6 is about sources, but the reasoning applies with
    more force here: losing a brief because the evidence directory is read-only would be an
    absurd trade. A failure to record is logged and swallowed.
    """
    if not articles:
        return None

    try:
        directory.mkdir(parents=True, exist_ok=True)
        recorded_at = datetime.now(timezone.utc)
        # `label` keeps two batches recorded in the same second apart. `[VERIFIED]` One
        # run now writes one batch per league (ADR-015), and both finish well inside a
        # second, so without it the second league silently overwrites the first and the
        # evidence for the run is half missing.
        stamp = recorded_at.strftime("%Y-%m-%dT%H-%M-%S")
        suffix = "" if label is None else f"-{_slug(label)}"
        path = directory / f"{stamp}{suffix}.json"

        # Written beside the target and renamed into place. `[VERIFIED]` 2026-08-27 a run
        # interrupted mid-write left a **0 byte** `.json` behind, and every reader of the
        # evidence directory then died on it rather than skipping it. A rename is atomic on
        # the same filesystem, so a reader sees either the previous state or the finished
        # file and never a half-written one.
        #
        # `[INFERRED]` This matters more here than the size of the fix suggests. The whole
        # point of this directory is to be trustworthy after something went wrong, and a run
        # that was killed is exactly the kind of thing it exists to record.
        temporary = path.with_suffix(".json.partial")
        temporary.write_text(
            json.dumps(
                {
                    "recorded_at": recorded_at.isoformat(),
                    "label": label,
                    "delivered_prose": summary is not None,
                    "summary": summary,
                    "unsupported_claims": unsupported_claims or [],
                    "failed_sources": failed_sources or [],
                    "articles": [
                        {
                            "article_id": article.article_id,
                            "title": article.title,
                            "summary": article.summary,
                            "source": article.source,
                            "url": article.url,
                            "published_at": article.published_at.isoformat(),
                            "league": article.league,
                        }
                        for article in articles
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
        _prune(directory, keep)
        return path
    except Exception:
        logger.exception("could not record the batch; the run is unaffected")
        return None


def load_batch(path: Path) -> list[NewsArticle]:
    """Read a recorded batch back into real articles, for replaying a failure offline.

    Returns `NewsArticle` rather than dictionaries so a replay exercises the same schema the
    pipeline does. `[VERIFIED]` The legacy repository defined its article shape in four places
    and they drifted; anything that reconstructs one has to go through `models.schemas`.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [NewsArticle(**article) for article in payload["articles"]]


def _prune(directory: Path, keep: int) -> None:
    """Delete all but the newest `keep` records.

    Sorted by name, which is why the filename is an ISO timestamp: it sorts chronologically as
    a string, so this needs no filesystem timestamps and cannot be confused by a copy.
    """
    records = sorted(directory.glob("*.json"))
    for stale in records[: max(0, len(records) - keep)]:
        stale.unlink(missing_ok=True)
