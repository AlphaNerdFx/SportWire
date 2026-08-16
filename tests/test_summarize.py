"""Behaviour tests for the summariser's contract, with no model and no network.

`processing/summarize.py` is the largest module in `processing/` and the least verifiable —
what `mistral:7b` writes on a given night cannot be asserted. What *can* be asserted is
everything around it, and that is where every recorded bug in this module actually lived:

  - retry gave up on the first HTTP 500      -> `test_a_request_failure_is_retried`
  - `" ".join(...)` flattened the paragraphs -> `test_tidy_preserves_paragraph_breaks`

The `Summarizer` ABC exists precisely so this is possible. `_summarise` is the only abstract
piece; the retry-and-validate loop lives in the base class, so a stub subclass exercises the
whole contract with no Ollama running. `[VERIFIED]` H13 Q2 asked why `_fetch`/`fetch` is
split in the ingestion adapters and the answer did not land — this is the same pattern in a
second place, and these tests are what it buys.

**Fallback is a feature, not a failure.** `summarise` returning `None` means "use the
headline list", never "fail the run" (`CLAUDE.md` §5.6). A summariser that is offline must
degrade the brief exactly as a dead source does.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

import pytest

from models.schemas import NewsArticle
from processing.summarize import (
    CHUNK_SIZE,
    SYSTEM_PROMPT,
    OllamaSummarizer,
    Summarizer,
    _note_lines,
    _tidy,
    _with_exclusions,
    build_prompt,
    build_reduce_prompt,
)

ArticleFactory = Callable[..., NewsArticle]

# Grounded in the article built by `_sources` below, so it survives validation.
GROUNDED = "Russell Westbrook has retired after 18 seasons."
# "Joe Dumars" appears in no source. `[VERIFIED]` mistral:7b produced this exact name on
# three consecutive attempts from a real Pistons story.
FABRICATED = "Joe Dumars is leading the negotiations."
# A *different* invention, for asserting the correction accumulates across attempts.
# `[VERIFIED]` mistral:7b produced this name on all three attempts of the 2026-08-13
# 00:00 run.
FABRICATED_OTHER = "Ayo Dosunmu was central to the plan."


def _sources(make_article: ArticleFactory) -> list[NewsArticle]:
    return [
        make_article(
            "Russell Westbrook retires after 18 seasons",
            summary="The guard steps away having played for seven teams.",
        )
    ]


class StubSummarizer(Summarizer):
    """Returns scripted text, so the base class's retry loop can be tested on its own."""

    def __init__(self, *responses: str | Exception) -> None:
        self._responses = list(responses)
        self.calls = 0
        # What each attempt was told to avoid, so the feedback loop can be asserted on.
        self.avoided: list[list[str]] = []

    @property
    def summarizer_name(self) -> str:
        return "Stub"

    def _summarise(
        self,
        articles: list[NewsArticle],
        max_chars: int,
        avoid: Sequence[str] = (),
    ) -> str:
        self.calls += 1
        self.avoided.append(list(avoid))
        response = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


# --- the retry-and-validate loop ---------------------------------------------------------


def test_a_valid_summary_is_returned_on_the_first_attempt(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """The happy path costs exactly one model call, and says so.

    `[VERIFIED]` 2026-08-14 the acceptance log was guarded by `if attempt > 1`, so this
    path — the common one — was silent. The 16:00 run read as "summarising 12 stories"
    then "delivered" with nothing between, which is indistinguishable from a summariser
    that was never called. Every acceptance must be countable, or the pass rate cannot be
    measured at all.
    """
    summarizer = StubSummarizer(GROUNDED)

    with caplog.at_level(logging.INFO, logger="processing.summarize"):
        result = summarizer.summarise(_sources(make_article))

    assert result == GROUNDED
    assert summarizer.calls == 1
    assert "accepted on attempt 1" in caplog.text


def test_a_fabricated_summary_is_retried_then_accepted(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """Retry exists because the check is mechanical — retrying without one would just
    produce a different fabrication."""
    summarizer = StubSummarizer(FABRICATED, GROUNDED)

    with caplog.at_level(logging.INFO, logger="processing.summarize"):
        result = summarizer.summarise(_sources(make_article))

    assert result == GROUNDED
    assert summarizer.calls == 2
    assert "Joe Dumars" in caplog.text, "the log must name what was rejected"
    assert "accepted on attempt 2" in caplog.text


def test_a_retry_is_told_what_the_previous_attempt_invented(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-16 — the loop computed this and threw it away.

    Every attempt received a byte-identical prompt, so a model pattern-completing from its
    training prior had no reason to answer differently. Measured: at temperature 0
    `mistral:7b` invented "Quentin Grimes" on **all ten** trials of one batch, which makes
    three attempts one attempt tried three times.

    The first attempt is told nothing — there is nothing to tell it yet — and that is
    asserted too, so the feedback cannot degrade into a permanent exclusion list.
    """
    summarizer = StubSummarizer(FABRICATED, GROUNDED)

    summarizer.summarise(_sources(make_article))

    assert summarizer.avoided[0] == [], "the first attempt has nothing to correct"
    assert "Joe Dumars" in summarizer.avoided[1], (
        "the retry must be told which name the first attempt invented"
    )


def test_the_correction_names_every_invention_so_far(
    make_article: ArticleFactory,
) -> None:
    """Attempt 3 must avoid what attempts 1 *and* 2 produced, not only the most recent.

    `[INFERRED]` A model that invents a different name each time would otherwise be free to
    cycle back to the first one, and the loop would never converge.
    """
    summarizer = StubSummarizer(FABRICATED, FABRICATED_OTHER, GROUNDED)

    summarizer.summarise(_sources(make_article))

    assert "Joe Dumars" in summarizer.avoided[2]
    assert "Ayo Dosunmu" in summarizer.avoided[2]


def test_the_correction_reaches_the_prompt_the_model_sees(
    make_article: ArticleFactory,
) -> None:
    """The list is worthless if it never reaches the system prompt.

    `[INFERRED]` Threading a value through three call sites and forgetting to use it is the
    failure `_drop_leading_stopword` recorded (P6): a mechanism that reads as protection and
    changes nothing.
    """
    original = _with_exclusions(SYSTEM_PROMPT, ())
    corrected = _with_exclusions(SYSTEM_PROMPT, ["Joe Dumars", "Phoenix Suns"])

    assert original == SYSTEM_PROMPT, "no names means no change at all"
    assert "Joe Dumars" in corrected
    assert "Phoenix Suns" in corrected
    assert corrected.startswith(SYSTEM_PROMPT), "the original instructions must survive"


def test_a_repeated_invention_is_named_once(make_article: ArticleFactory) -> None:
    """Two attempts inventing the same name must not list it twice."""
    corrected = _with_exclusions(SYSTEM_PROMPT, ["Joe Dumars", "Joe Dumars"])

    assert corrected.count("Joe Dumars") == 1


def test_fabrication_on_every_attempt_falls_back_to_the_headline_list(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """`[VERIFIED]` The identical-repeat failure mode is real, not hypothetical.

    2026-08-13's 00:00 run invented "Ayo Dosunmu" on all three attempts; an earlier run
    invented "Joe Dumars" three times over. `[INFERRED]` Retry assumes attempts fail
    independently, and a model completing a strong training prior does not — so `None`, and
    the headline list, is the outcome that matters most here.
    """
    summarizer = StubSummarizer(FABRICATED)

    with caplog.at_level(logging.WARNING, logger="processing.summarize"):
        result = summarizer.summarise(_sources(make_article))

    assert result is None, "None means 'use the headline list', not 'fail the run'"
    assert summarizer.calls == 3
    assert "using the headline list" in caplog.text


def test_a_request_failure_is_retried_rather_than_abandoned(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """`[VERIFIED]` 2026-08-10: a production run got HTTP 500 from Ollama on the first
    attempt and gave up, delivering the headline list. An earlier version returned on the
    exception instead of continuing.

    `[INFERRED]` Request failures are the clearest case for retry — a 500 is transient, and a
    timeout has usually just finished loading the model, so the next attempt is warm.
    """
    summarizer = StubSummarizer(RuntimeError("HTTP 500"), GROUNDED)

    with caplog.at_level(logging.WARNING, logger="processing.summarize"):
        result = summarizer.summarise(_sources(make_article))

    assert result == GROUNDED
    assert summarizer.calls == 2
    assert "errored on attempt 1" in caplog.text


def test_an_exception_never_escapes(make_article: ArticleFactory) -> None:
    """A dead summariser degrades the brief; it must never crash the run (`CLAUDE.md` §5.6)."""
    summarizer = StubSummarizer(RuntimeError("connection refused"))

    assert summarizer.summarise(_sources(make_article)) is None


def test_empty_text_is_not_delivered(make_article: ArticleFactory) -> None:
    """A model that returns nothing must fall back rather than send a blank brief."""
    summarizer = StubSummarizer("   \n  ")

    assert summarizer.summarise(_sources(make_article)) is None


def test_no_articles_means_no_model_call(make_article: ArticleFactory) -> None:
    """The offseason path. Calling a 5-minute model to summarise nothing is pure waste."""
    summarizer = StubSummarizer(GROUNDED)

    assert summarizer.summarise([]) is None
    assert summarizer.calls == 0


def test_the_attempt_count_is_honoured(make_article: ArticleFactory) -> None:
    """`attempts` bounds the cost. `[VERIFIED]` A failing run spent 19 minutes on three
    attempts before falling back, so this number is wall-clock time, not just calls."""
    summarizer = StubSummarizer(FABRICATED)

    summarizer.summarise(_sources(make_article), attempts=2)

    assert summarizer.calls == 2


# --- _tidy: the bug that made a working prompt look ignored -------------------------------


def test_tidy_preserves_paragraph_breaks() -> None:
    """`[VERIFIED]` 2026-08-12: `" ".join(text.split())` collapsed every run of whitespace,
    newlines included, so a multi-paragraph summary arrived as one solid block.

    The prompt asking for paragraphs appeared to be ignored when in fact the model obeyed it
    and this step undid the work. `[VERIFIED]` The 16:00 brief on 2026-08-13 arrived as two
    correctly grouped paragraphs, which is only observable because of this fix.
    """
    text = "Westbrook retired.\n\nMeanwhile the Suns waived a forward."

    assert _tidy(text) == "Westbrook retired.\n\nMeanwhile the Suns waived a forward."


def test_tidy_collapses_whitespace_inside_a_paragraph() -> None:
    """Within a paragraph, runs of whitespace are still normalised to single spaces."""
    assert _tidy("Westbrook    retired\n  after 18 seasons.") == (
        "Westbrook retired after 18 seasons."
    )


def test_tidy_drops_empty_paragraphs() -> None:
    """Three blank lines are still one break, not two empty paragraphs."""
    assert _tidy("One.\n\n\n\nTwo.") == "One.\n\nTwo."


def test_tidy_of_nothing_is_nothing() -> None:
    assert _tidy("   \n\n  ") == ""


# --- prompt construction ------------------------------------------------------------------


def test_build_prompt_names_the_item_count(make_article: ArticleFactory) -> None:
    """`[VERIFIED]` Naming the count is load-bearing, not decoration — see
    `build_reduce_prompt`'s docstring for the measurement."""
    articles = [make_article(f"Story {index}") for index in range(4)]

    prompt = build_prompt(articles, max_chars=800)

    assert "4 NBA news items" in prompt
    assert "800 characters" in prompt


def test_build_prompt_includes_every_article(make_article: ArticleFactory) -> None:
    """ "Do not omit an item" is only honest if every item is actually in the prompt."""
    articles = [
        make_article("Westbrook retires", summary="After 18 seasons."),
        make_article("Suns waive a forward", summary="Roster spot opens."),
    ]

    prompt = build_prompt(articles)

    for article in articles:
        assert article.title in prompt
        assert article.summary in prompt


def test_build_reduce_prompt_counts_the_notes_not_the_blocks() -> None:
    """`[VERIFIED]` 2026-08-06: without a stated count the model stopped after roughly 700
    characters having covered about ten of fifteen notes — the paragraph *felt* finished.

    The number must count fact lines, so two blocks of three notes ask for six, not two.
    """
    notes = ["- one\n- two\n- three", "- four\n- five\n- six"]

    prompt = build_reduce_prompt(notes)

    assert "these 6 notes" in prompt
    assert "All 6 notes must appear" in prompt


def test_note_lines_discards_the_models_preamble() -> None:
    """`[VERIFIED]` The model prefixes notes with "Here are the summaries:" despite being
    told not to. That line is not a fact, and counting it inflates the number the reduce
    step is asked to satisfy."""
    block = "Here are the summaries:\n- Westbrook retired\n- Suns waived a forward"

    assert _note_lines([block]) == ["- Westbrook retired", "- Suns waived a forward"]


def test_note_lines_accepts_numbered_notes() -> None:
    """The model alternates between bullets and numbers between runs."""
    assert _note_lines(["1. Westbrook retired\n2. Suns waived a forward"]) == [
        "1. Westbrook retired",
        "2. Suns waived a forward",
    ]


# --- chunking: the map-reduce boundary ----------------------------------------------------


class RecordingOllama(OllamaSummarizer):
    """`OllamaSummarizer` with the HTTP call replaced, so chunking is testable offline."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.prompts: list[tuple[str, str]] = []

    def _generate(self, system: str, prompt: str) -> str:
        self.prompts.append((system, prompt))
        return "- a note"


def test_a_short_batch_is_summarised_in_one_call(
    make_article: ArticleFactory,
) -> None:
    """No chunking below the threshold: one call, no reduce step."""
    summarizer = RecordingOllama()
    articles = [make_article(f"Story {index}") for index in range(CHUNK_SIZE)]

    summarizer._summarise(articles, max_chars=1024)

    assert len(summarizer.prompts) == 1


def test_a_long_batch_is_chunked_then_reduced(
    make_article: ArticleFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """`[VERIFIED]` 2026-08-06: given all 15 fixture articles in one call the model omitted
    the two LeBron-to-Philadelphia items — the biggest story in the feed — while including a
    child-support filing. Re-running with those two at the front covered them, and led with
    them. It was not judging badly; it was barely reading the tail.

    So long batches are split, and every article sits near the front of *some* call.
    """
    summarizer = RecordingOllama()
    articles = [make_article(f"Story {index}") for index in range(CHUNK_SIZE * 2 + 1)]

    with caplog.at_level(logging.INFO, logger="processing.summarize"):
        summarizer._summarise(articles, max_chars=1024)

    # Three note-extraction calls plus one reduce.
    assert len(summarizer.prompts) == 4
    assert "extracting notes from 3 chunks" in caplog.text


def test_every_article_reaches_some_chunk(make_article: ArticleFactory) -> None:
    """The point of chunking is coverage. An article in no chunk is one the brief cannot
    mention, which is the failure chunking was introduced to fix."""
    summarizer = RecordingOllama()
    articles = [make_article(f"Story {index}") for index in range(CHUNK_SIZE * 2 + 1)]

    summarizer._summarise(articles, max_chars=1024)

    combined = " ".join(prompt for _, prompt in summarizer.prompts)
    for article in articles:
        assert article.title in combined, f"{article.title} reached no chunk"
