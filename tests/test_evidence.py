"""Behaviour tests for the thing that keeps a failure reproducible.

`[VERIFIED]` This module exists because the evidence was destroyed twice in one week:
`/tmp` was cleared on shutdown (TASKS.md P38), and a purge bug deleted the delivery record
(P39). Both times the *behaviour* was fine and the *measurements* stopped being reproducible.

So these tests care about two things only: that a batch survives, and that failing to record
one can never cost a brief.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from models.schemas import NewsArticle
from storage.evidence import load_batch, record_batch

ArticleFactory = Callable[..., NewsArticle]


def test_a_batch_can_be_read_back_as_real_articles(
    tmp_path: Path, make_article: ArticleFactory
) -> None:
    """The whole purpose: replay a run offline weeks later.

    Round-tripping into `NewsArticle` rather than dictionaries matters, because a replay must
    exercise the same schema the pipeline does. `[VERIFIED]` The legacy repository defined its
    article shape in four places and they drifted silently.
    """
    articles = [
        make_article("Cavs deal Schroder for Hornets' Mann", source="ESPN"),
        make_article(
            "Raptors fans confused about when Kawhi nightmare ends", source="r/nba"
        ),
    ]

    path = record_batch(
        articles, summary="The Cavaliers traded Dennis Schroder.", directory=tmp_path
    )

    assert path is not None
    replayed = load_batch(path)
    assert [a.title for a in replayed] == [a.title for a in articles]
    assert [a.source for a in replayed] == ["ESPN", "r/nba"]


def test_a_fallback_is_recorded_as_such(
    tmp_path: Path, make_article: ArticleFactory
) -> None:
    """A rejection is only diagnosable beside the articles it was judged against.

    Recording the batch without the outcome would leave the same gap that made this week's
    fallbacks so expensive to investigate.
    """
    path = record_batch(
        [make_article("Cavs deal Schroder for Hornets' Mann")],
        summary=None,
        failed_sources=["r/nba"],
        directory=tmp_path,
    )

    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["delivered_prose"] is False
    assert payload["summary"] is None
    assert payload["failed_sources"] == ["r/nba"]


def test_recording_never_costs_a_brief(
    tmp_path: Path, make_article: ArticleFactory
) -> None:
    """`CLAUDE.md` §5.6 reasoning, applied harder.

    Losing a delivered brief because the evidence directory was unwritable would be an absurd
    trade. A file path pointed at an existing *file* is the simplest way to make `mkdir` fail.
    """
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("this is a file")

    assert (
        record_batch([make_article("A story")], summary=None, directory=blocked) is None
    )


def test_an_empty_batch_records_nothing(tmp_path: Path) -> None:
    """A run with nothing to report leaves no file, so the directory tracks real runs."""
    assert record_batch([], summary=None, directory=tmp_path) is None
    assert list(tmp_path.glob("*.json")) == []


def test_old_records_are_pruned_newest_first(
    tmp_path: Path, make_article: ArticleFactory
) -> None:
    """Bounded, or it becomes the problem it was built to solve.

    Sorted by filename, which is why the name is an ISO timestamp: it sorts chronologically as
    a string, so pruning needs no filesystem metadata and a copied file cannot confuse it.
    """
    for index in range(5):
        (tmp_path / f"2026-08-{10 + index:02d}T00-00-00.json").write_text("{}")

    record_batch(
        [make_article("Newest story")], summary=None, directory=tmp_path, keep=3
    )

    remaining = sorted(p.name for p in tmp_path.glob("*.json"))
    assert len(remaining) == 3
    assert "2026-08-10T00-00-00.json" not in remaining, "the oldest must go first"


def test_two_batches_in_one_second_do_not_overwrite_each_other(
    tmp_path: Path, make_article: Callable[..., NewsArticle]
) -> None:
    """`[VERIFIED]` 2026-08-26: one run records one batch per league, both within a second.

    The filename is a timestamp to the second, so without the label the football batch lands
    on the basketball one and the run's evidence is half missing. That is the same class of
    loss as P38 and P39, which is why it is worth a test rather than a comment.
    """
    basketball = record_batch(
        [make_article("Doncic drops 40")],
        summary=None,
        directory=tmp_path,
        label="NBA",
    )
    football = record_batch(
        [make_article("Mahomes signs an extension")],
        summary=None,
        directory=tmp_path,
        label="NFL",
    )

    assert basketball != football, "one label per league, so one file per league"
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert load_batch(basketball)[0].title == "Doncic drops 40"
    assert load_batch(football)[0].title == "Mahomes signs an extension"


def test_a_recorded_article_keeps_its_league(
    tmp_path: Path, make_article: Callable[..., NewsArticle]
) -> None:
    """Evidence is only reproduction evidence if it round trips.

    `[INFERRED]` The league decides which brief an article belonged to, so a batch that
    forgot it cannot be replayed against the run that produced it.
    """
    path = record_batch(
        [make_article("Mahomes signs an extension", league="NFL")],
        summary=None,
        directory=tmp_path,
    )

    assert load_batch(path)[0].league == "NFL"


def test_an_interrupted_write_leaves_no_broken_file(
    tmp_path: Path,
    make_article: Callable[..., NewsArticle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`[VERIFIED]` 2026-08-27: a run killed mid-write left a 0 byte `.json` in `evidence/`.

    Every reader of that directory then died on it rather than skipping it, which is the
    opposite of what an evidence store is for. It exists to be trustworthy after something has
    gone wrong, and a run that was killed is exactly the case it is meant to record.

    Written to a neighbouring file and renamed, so a reader sees the finished file or nothing.
    """
    original = Path.write_text

    def fail_halfway(self: Path, *args: object, **kwargs: object) -> int:
        if self.suffix == ".partial":
            original(self, "{ truncated", encoding="utf-8")
            raise OSError("killed mid-write")
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", fail_halfway)

    result = record_batch(
        [make_article("Doncic drops 40")], summary=None, directory=tmp_path
    )

    assert result is None, "a failed recording reports failure"
    assert list(tmp_path.glob("*.json")) == [], (
        "no half-written file may be left behind"
    )


def test_a_finished_recording_leaves_no_temporary_file(
    tmp_path: Path, make_article: Callable[..., NewsArticle]
) -> None:
    """The complement: the scratch file must not survive a successful write either.

    `[INFERRED]` A stray `.partial` accumulating next to every batch would quietly fill the
    directory and confuse the pruning, which counts `*.json`.
    """
    record_batch([make_article("Doncic drops 40")], summary=None, directory=tmp_path)

    assert list(tmp_path.glob("*.partial")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1
