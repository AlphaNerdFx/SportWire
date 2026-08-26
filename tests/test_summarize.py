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
from collections.abc import Callable
from datetime import datetime

import pytest

from models.schemas import NewsArticle
from processing.summarize import (
    CHUNK_SIZE,
    NOTES_PROMPT,
    OllamaSummarizer,
    Summarizer,
    _note_lines,
    _tidy,
    build_prompt,
    build_reduce_prompt,
    league_of,
    notes_prompt,
    system_prompt,
)

ArticleFactory = Callable[..., NewsArticle]

# Grounded in the article built by `_sources` below, so it survives validation.
GROUNDED = "Russell Westbrook has retired after 18 seasons."
# "Joe Dumars" appears in no source. `[VERIFIED]` mistral:7b produced this exact name on
# three consecutive attempts from a real Pistons story.
FABRICATED = "Joe Dumars is leading the negotiations."


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

    @property
    def summarizer_name(self) -> str:
        return "Stub"

    def _summarise(self, articles: list[NewsArticle], max_chars: int) -> str:
        self.calls += 1
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


def test_the_vocabulary_sample_reaches_the_validator(
    make_article: Callable[..., NewsArticle],
) -> None:
    """`[VERIFIED]` 2026-08-18, and this test exists because a mutation demanded it.

    Deleting the pass-through left all 331 tests green: nothing checked that `summarise`
    forwards the sample, so the widening could have been silently inert in production while
    every unit test of the validator still passed.

    The batch below refuses `Commissioner Adam Silver`, because the post "Fire Adam Silver" is
    indexed as a rival entity. One extra article writing "fire" in lower case is enough to
    teach the validator that it is an ordinary word, and it can only do so if the sample
    actually arrives. TASKS.md P32.

    `[VERIFIED]` This used the Raptors case until 2026-08-26, when `_split_at_teams` began
    ending a scanned name at a team nickname, so "Raptors Reacts" stopped being one name and
    the example stopped demonstrating anything. The commissioner is the other rejection from
    the same run and no team rule can reach it.
    """
    batch = [
        make_article("Fire Adam Silver: the case against the commissioner"),
        make_article("Adam Silver defends the new schedule"),
    ]
    claim = "Commissioner Adam Silver spoke."

    assert StubSummarizer(claim).summarise(batch) is None, (
        "without the wider sample this batch must still refuse the team"
    )

    wider = [*batch, make_article("Sources say the Lakers fire their head coach")]

    assert StubSummarizer(claim).summarise(batch, vocabulary_sample=wider) == claim


def test_each_item_is_marked_with_its_age(
    make_article: Callable[..., NewsArticle], now: datetime
) -> None:
    """`[VERIFIED]` TASKS.md P40: the prompt carried **no time information at all**.

    A brief said Klay Thompson *"is expected to clear waivers soon"* when he had already
    cleared them, because the batch held both stages of that story and nothing told the model
    which report was later. The two were three days apart.
    """
    articles = [
        make_article("Thompson expected to sign with Heat", hours_old=72),
        make_article("Thompson clears waivers, joins Heat", hours_old=0.33),
    ]

    prompt = build_prompt(articles, now=now)

    assert "[3d ago] Thompson expected to sign with Heat" in prompt
    assert "[just now] Thompson clears waivers, joins Heat" in prompt


@pytest.mark.parametrize(
    ("hours_old", "expected"),
    [
        (0.08, "just now"),
        (0.98, "just now"),
        (1.0, "1h ago"),
        (47.0, "47h ago"),
        (48.0, "2d ago"),
        (144.0, "6d ago"),
    ],
)
def test_age_reads_in_the_coarsest_unit_that_still_separates_two_reports(
    make_article: Callable[..., NewsArticle],
    now: datetime,
    hours_old: float,
    expected: str,
) -> None:
    """`[INFERRED]` Hours rather than timestamps, because the question is "which is later" and
    a relative age asks it directly. An ISO timestamp turns that into a subtraction, which is
    the kind of work a 7B model does badly.

    Under an hour reads as "just now" so a flurry of reports on one story does not all collapse
    to "0h" and become indistinguishable again.
    """
    prompt = build_prompt([make_article("A story", hours_old=hours_old)], now=now)

    assert f"[{expected}] A story" in prompt


def test_the_notes_prompt_tells_the_model_what_the_age_is_for() -> None:
    """Marking the age is useless if nothing says what to do with it.

    `[INFERRED]` This is information rather than instruction, which is why it is worth trying
    where a previous prompt tweak was measured to move nothing (TASKS.md P6 precedent): the
    model was not ignoring recency before, it was never given any.
    """
    assert "how old it is" in NOTES_PROMPT
    assert "newest" in NOTES_PROMPT


def test_the_clock_is_injected_so_the_prompt_can_be_diffed(
    make_article: Callable[..., NewsArticle], now: datetime
) -> None:
    """`[VERIFIED]` Four tests written on 2026-08-18 rotted within a week by reading the real
    clock (TASKS.md P37). A prompt builder that reads `datetime.now()` internally cannot be
    asserted against a fixed string at all.
    """
    article = make_article("A story", hours_old=5)

    assert build_prompt([article], now=now) == build_prompt([article], now=now)
    assert "[5h ago]" in build_prompt([article], now=now)


def test_every_prompt_names_the_league_it_is_summarising(
    make_article: Callable[..., NewsArticle],
) -> None:
    """`[VERIFIED]` 2026-08-26: all three prompts said "NBA" while the batch was football.

    ADR-015 split the briefs and left the wording behind, so the football batch was
    introduced to the model as basketball. It obliged. Three attempts in a row attached NBA
    teams to NFL players, "Ashton Jeanty of the Timberwolves" and "Houston Rockets" where the
    Texans belonged, and the brief lost its prose to the validator catching them.

    All three are asserted, not one. The note pass and the writing pass use different
    prompts, and fixing whichever is easiest to reach would leave the other lying.
    """
    football = [make_article("Mahomes signs an extension", league="NFL")]

    assert "NFL" in system_prompt(football)
    assert "NFL" in notes_prompt(football)
    assert "NFL" in build_prompt(football, 500)

    assert "NBA" not in system_prompt(football)
    assert "NBA" not in notes_prompt(football)
    assert "NBA" not in build_prompt(football, 500)


def test_a_mixed_batch_is_not_called_either_league(
    make_article: Callable[..., NewsArticle],
) -> None:
    """`[INFERRED]` Naming one league over a batch holding two is the mistake being fixed.

    No per-league run produces a mixed batch, but a caller could, and the honest answer for
    one is the general word rather than a coin toss between the two.
    """
    mixed = [
        make_article("Mahomes signs an extension", league="NFL"),
        make_article("Doncic drops 40", league="NBA"),
    ]

    assert league_of(mixed) == "sports"
    assert "NFL" not in system_prompt(mixed)
    assert "NBA" not in system_prompt(mixed)


def test_the_summarizer_sends_the_league_in_every_prompt_it_makes(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` Written because a mutation demanded it, the same day and the same way P32's
    pass-through test was.

    Swapping the call site back to the unformatted template left every other test green: the
    prompt builders were checked directly, and nothing checked that the summarizer used them.
    A batch large enough to chunk is used so the note prompt and the writing prompt are both
    exercised, since they are separate strings and fixing one would hide the other.
    """
    summarizer = RecordingOllama()
    football = [
        make_article(f"Football story {index}", league="NFL")
        for index in range(CHUNK_SIZE + 1)
    ]

    summarizer.summarise(football, max_chars=500)

    assert len(summarizer.prompts) > 1, (
        "expected a chunked run, with notes and a reduce"
    )
    # Every prompt, not any. `[VERIFIED]` Asserting "any" let all three call sites survive
    # mutation: with one left unformatted the others still carried the league, and an
    # unformatted template reads "{league}" rather than "NBA", so an absence check passed too.
    for system, prompt in summarizer.prompts:
        assert "NFL" in system, f"prompt does not name the league: {system[:80]}"
        assert "{league}" not in system, f"placeholder never filled: {system[:80]}"
        assert "NBA" not in system, f"basketball leaked in: {system[:80]}"
        assert "NBA" not in prompt, f"basketball leaked in: {prompt[:80]}"


def test_a_short_batch_also_names_its_league(
    make_article: ArticleFactory,
) -> None:
    """The single-call path, which the chunked test above never reaches.

    `[VERIFIED]` Mutation showed exactly that: leaving the one-call site unformatted survived
    the chunked test, because a batch over `CHUNK_SIZE` goes through notes and reduce instead
    and never touches it. Two paths, two tests.
    """
    summarizer = RecordingOllama()
    football = [
        make_article(f"Football story {index}", league="NFL")
        for index in range(CHUNK_SIZE)
    ]

    summarizer.summarise(football, max_chars=500)

    assert len(summarizer.prompts) == 1, "a short batch is one call"
    [(system, prompt)] = summarizer.prompts
    assert "NFL" in system, f"prompt does not name the league: {system[:80]}"
    assert "{league}" not in system, f"placeholder never filled: {system[:80]}"
    assert "NBA" not in system and "NBA" not in prompt
