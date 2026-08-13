"""Behaviour tests for the check that stands between a model and the operator's phone.

`processing/validate.py` is the only thing preventing a fabricated summary from being
delivered, and it has **two opposite failure modes that cost different amounts**:

  - a **missed fabrication** reaches the phone, which is what the module exists to stop;
  - a **false accusation** rejects a correct summary, and since the fallback is the headline
    list, this silently disables the feature. `[VERIFIED]` Three of the four bugs recorded
    against this module were of the second kind.

Both directions are asserted here. `SESSION.md` §8 records four validator bugs, every one
found by reading live output rather than by a test:

  - `In Detroit` flagged as an invented name        -> `test_sentence_initial_*`
  - every-word grounding rejected `New York Knicks` -> `test_expanded_or_shortened_*`
  - `Kawhi Leonard's` rejected over a possessive    -> `test_possessive_*`
  - `Mavericks. Le` matched across a sentence break -> `test_names_are_not_matched_across_*`

`test_false_relationship_*` is different: it is an **xfail**, marking a real gap found on
2026-08-13 that has not been fixed and is not yet decided (TASKS.md P5). It asserts what the
validator *should* do, so it flips to XPASS the moment P5 lands. Recording a known hole as a
declared expected-failure is not the same as weakening a test (`OPERATING_RULES.md` §4) —
omitting the case entirely is what would hide it.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from models.schemas import NewsArticle
from processing.validate import validate_summary

ArticleFactory = Callable[..., NewsArticle]


# --- fabrication is caught -------------------------------------------------------------


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        # `[VERIFIED]` mistral:7b produced this from a Pistons story on three consecutive
        # attempts -- the failure that proved retry cannot fix a strong training prior.
        (
            (
                "The Detroit Pistons are exploring a sign-and-trade. Joe Dumars is "
                "leading the negotiations."
            ),
            "Joe Dumars",
        ),
        # `[VERIFIED]` 2026-08-13 00:00 run, invented on all three attempts.
        (
            (
                "Chicago continued their rebuild this week. Ayo Dosunmu was central "
                "to the plan."
            ),
            "Ayo Dosunmu",
        ),
    ],
)
def test_invented_name_is_caught(
    summary: str, expected: str, make_article: ArticleFactory
) -> None:
    """A proper name traceable to nothing in the sources was invented."""
    articles = [
        make_article(
            "Pistons and Bulls explore sign-and-trade options",
            summary="Both front offices have opened talks about a rebuild.",
        )
    ]

    result = validate_summary(summary, articles)

    assert not result.is_safe
    assert expected in result.invented_names


def test_invented_figure_is_caught(make_article: ArticleFactory) -> None:
    """`[VERIFIED]` mistral:7b invented "$3.3M" for a contract whose value no source stated."""
    articles = [
        make_article(
            "Pistons re-sign guard to a multi-year deal",
            summary="Terms of the agreement were not disclosed.",
        )
    ]

    result = validate_summary("The deal is worth $3.3M over two years.", articles)

    assert not result.is_safe
    assert "$3.3M" in result.invented_figures


def test_a_clean_summary_is_safe(make_article: ArticleFactory) -> None:
    """The other half of the contract: correct text must pass, or the check is useless."""
    articles = [
        make_article(
            "Russell Westbrook retires after 18 seasons",
            summary="LeBron James paid tribute to the former MVP.",
        )
    ]

    result = validate_summary(
        "Russell Westbrook has retired after 18 seasons. LeBron James paid tribute.",
        articles,
    )

    assert result.is_safe
    assert result.describe() == "clean"


# --- false accusations: the bugs that cost correct summaries ---------------------------


def test_sentence_initial_preposition_is_stripped_from_the_reported_name(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-11: a live summary was rejected for the invented name "In Detroit".

    **This test asserts the log text, not the verdict, and that is deliberate.**

    `[VERIFIED]` 2026-08-13, by mutation: disabling `_drop_leading_stopword` changes no
    pass/fail outcome in this suite. `[INFERRED]` It cannot, by construction — stripping the
    *first* word never changes the *last* word, and `_grounded` returns True whenever the last
    word appears in the sources. If the last word is grounded both forms pass; if it is not,
    both fail. Commit `7323396` (last-word grounding, 2026-08-12) therefore made `c522d8e`
    (this strip, 2026-08-11) redundant as a correctness mechanism one day after it landed.
    Both fixed the same live symptom, so nothing revealed the overlap.

    What survives is diagnostic value: a log reading `invented names: Portland` points at the
    real problem, while `In Portland` sends the reader after a preposition. Asserted here so
    the remaining purpose is explicit rather than assumed. See TASKS.md P6.
    """
    articles = [
        make_article(
            "Blazers weigh their options",
            summary="The front office is considering a sign-and-trade.",
        )
    ]

    result = validate_summary(
        "In Portland, the front office is weighing a sign-and-trade.", articles
    )

    assert not result.is_safe, "Portland is genuinely ungrounded here"
    assert "Portland" in result.invented_names
    assert "In Portland" not in result.invented_names


@pytest.mark.parametrize(
    ("written", "as_the_source_has_it"),
    [
        # `[VERIFIED]` All three were rejected live on 2026-08-11 by the every-word rule,
        # and all three were entirely correct.
        ("New York Knicks", "Knicks"),
        ("Oklahoma City Thunder", "Thunder"),
        ("Anthony Towns", "Karl-Anthony Towns"),
    ],
)
def test_expanded_or_shortened_name_is_grounded(
    written: str, as_the_source_has_it: str, make_article: ArticleFactory
) -> None:
    """Expanding a team's city or shortening a hyphenated first name is writing, not invention.

    `[VERIFIED]` Requiring *every* word of a name to appear in the sources threw away three
    correct summaries. Grounding now accepts the **last** word — the identifying one.
    """
    articles = [
        make_article(
            f"{as_the_source_has_it} win again",
            summary=f"A strong night for {as_the_source_has_it}.",
        )
    ]

    result = validate_summary(f"{written} won on Tuesday night.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_possessive_does_not_break_grounding(make_article: ArticleFactory) -> None:
    """`[VERIFIED]` 2026-08-08: rejected for "Kawhi Leonard's" while the sources were about him."""
    articles = [
        make_article(
            "Kawhi Leonard investigation continues",
            summary="The league is still reviewing the case.",
        )
    ]

    result = validate_summary("Kawhi Leonard's situation remains unresolved.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_names_are_not_matched_across_a_sentence_boundary(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-08: "...the Mavericks. LeBron James chose..." matched as "Mavericks. Le".

    The name pattern allows a full stop inside a word, so scanning the whole summary at once
    fused the end of one sentence to the start of the next and rejected a summary in which
    every fact was correct. Names are matched per sentence for this reason.
    """
    articles = [
        make_article(
            "Mavericks talks collapse",
            summary="Dallas walked away from the negotiation.",
        ),
        make_article(
            "Philadelphia lands its target",
            summary="The Sixers completed the signing on Monday.",
        ),
    ]

    # The second sentence opens with a connective the sources never use. `[VERIFIED]` This
    # specific shape is what makes the test discriminating: an earlier version used
    # "...Mavericks. Philadelphia completed..." and passed even with sentence splitting
    # disabled, because the fused candidate's last word ("Philadelphia") was itself grounded.
    # "Meanwhile" is ungrounded, so fusion produces a name that fails, and splitting produces
    # no candidate at all -- a single capitalised word is not a name.
    result = validate_summary(
        "Talks collapsed with the Mavericks. Meanwhile, Philadelphia completed the signing.",
        articles,
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_figure_is_grounded_across_differing_formats(
    make_article: ArticleFactory,
) -> None:
    """Outlets format money differently; the number is what has to be true."""
    articles = [
        make_article(
            "Extension agreed",
            summary="The deal is reported at $52.2M over three years.",
        )
    ]

    result = validate_summary("The extension is worth $52.2 million.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_figures}"


# --- preamble: counted, never fatal ----------------------------------------------------


def test_preamble_is_reported_but_does_not_fail_validation(
    make_article: ArticleFactory,
) -> None:
    """A style problem must not reject a true summary.

    Rejecting correct output over its opening sentence trades something real for something
    cosmetic. It is still counted, so a persistently ignored instruction stays visible.
    """
    articles = [
        make_article(
            "Russell Westbrook retires",
            summary="The guard steps away after 18 seasons.",
        )
    ]

    result = validate_summary(
        "Here is your NBA brief. Russell Westbrook has retired.", articles
    )

    assert result.is_safe, "a preamble is a style problem, not a truth problem"
    assert result.has_preamble
    assert "preamble present" in result.describe()


def test_describe_names_every_problem_for_the_log(
    make_article: ArticleFactory,
) -> None:
    """The log line is the only diagnosis available after an unattended run."""
    articles = [make_article("Pistons news", summary="No terms were disclosed.")]

    result = validate_summary(
        "Here is your brief. Joe Dumars agreed a deal worth $3.3M.", articles
    )
    described = result.describe()

    assert "Joe Dumars" in described
    assert "$3.3M" in described
    assert "preamble present" in described


# --- the known gap: TASKS.md P5 --------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "TASKS.md P5, open and undecided: the validator grounds entities, not claims. "
        "Every name below appears in the sources, so a false relationship between real "
        "names passes. This is asserted as what the validator *should* do, so it flips to "
        "XPASS when P5 is fixed."
    ),
    strict=False,
)
def test_false_relationship_between_grounded_names_is_caught(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-13: this exact sentence passed validation on attempt 1 and was
    delivered to the operator's phone.

    *"His retirement marked the end of playoff runs for basketball greats like Kobe Bryant,
    Tim Duncan, Dirk Nowitzki, and Kawhi Leonard."*

    `[INFERRED]` Kawhi Leonard is active — the same run's feed carried his Raptors trade
    story. Every name is real and grounded, so the check passes it. This is a different
    failure class from an invented name, and neither grounding nor retry addresses it.
    """
    articles = [
        make_article(
            "Russell Westbrook retires after 18 seasons",
            summary=(
                "Westbrook faced Kobe Bryant, Tim Duncan and Dirk Nowitzki during his "
                "career."
            ),
        ),
        make_article(
            "As the Kawhi Leonard investigation drags on",
            summary="His trade to the Raptors may yet fall apart.",
        ),
    ]

    result = validate_summary(
        "His retirement marked the end of playoff runs for basketball greats like Kobe "
        "Bryant, Tim Duncan, Dirk Nowitzki, and Kawhi Leonard.",
        articles,
    )

    assert not result.is_safe, (
        "a sentence asserting a false relationship between grounded names was accepted"
    )
