"""The one thing a unit test of `drop_repeated_stories` cannot prove: that it is called.

`[VERIFIED]` 2026-09-04 this file exists because the suppression was wired into
`assemble_brief` and then deleted again as a mutation, and **all 565 tests still passed**. That
is the fourth pipeline-wiring mutant to survive in this repository; `TASKS.md` P36 records the
first three, and `build_story_groups` was extracted from `main` for exactly this reason.

Nothing here touches the network. The store is a real `SeenStore` on a temporary database, so
the recording and the reading are the ones production uses rather than a stand-in that could
drift from them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from config.settings import Settings
from main import assemble_brief
from models.schemas import NewsArticle
from storage.db import SeenStore

ArticleFactory = Callable[..., NewsArticle]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Credentials that are never used: this assembles a brief, it does not send one."""
    return Settings(
        balldontlie_api_key="unused",
        telegram_bot_token="unused",
        telegram_chat_id="unused",
        database_path=tmp_path / "test.db",
        evidence_path=tmp_path / "evidence",
    )


def _brief(articles: list[NewsArticle], store: SeenStore, settings: Settings) -> str:
    brief = assemble_brief(
        articles,
        [],
        store=store,
        settings=settings,
        failed_sources=[],
        no_summary=True,
        covering_hours=8.0,
        league="NBA",
    )
    return "\n".join(brief.messages)


def test_a_story_already_delivered_does_not_reach_the_brief(
    tmp_path: Path, settings: Settings, make_article: ArticleFactory
) -> None:
    """The wiring, end to end: record a story, then offer a retelling of it.

    `no_summary=True` keeps the model out of this entirely, so the assertion is about which
    articles reached the brief and nothing else.
    """
    told = make_article(
        "Steve Ballmer suspended one year, Clippers to lose 5 first-round picks "
        "over Kawhi Leonard deal",
        league="NBA",
    )
    retold = make_article(
        "NBA fines Clippers $30M, penalizes Kawhi Leonard after investigation",
        league="NBA",
    )

    with SeenStore(tmp_path / "test.db") as store:
        store.record_story_names([told])
        text = _brief([retold], store, settings)

    assert "fines Clippers" not in text, text


def test_a_development_in_that_story_still_reaches_the_brief(
    tmp_path: Path, settings: Settings, make_article: ArticleFactory
) -> None:
    """The other half, and the half the operator asked for by name.

    A rule that suppressed everything about a told story would have deleted this, and he said
    so while reporting the bug: *"I'm not talking about Gillian Zucker that part is new"*.
    """
    told = make_article(
        "Steve Ballmer suspended one year, Clippers to lose 5 first-round picks "
        "over Kawhi Leonard deal",
        league="NBA",
    )
    development = make_article(
        "Digging into the Wachtell report: Gillian Zucker and the Clippers payments "
        "to Kawhi Leonard",
        league="NBA",
    )

    with SeenStore(tmp_path / "test.db") as store:
        store.record_story_names([told])
        text = _brief([development], store, settings)

    assert "Zucker" in text, text
