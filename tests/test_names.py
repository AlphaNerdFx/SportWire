"""Behaviour tests for the shared name scanner.

`processing/names.py` is not wired into anything yet (`TASKS.md` P17). It exists so the two
extractors this pipeline already has can be compared, and the load-bearing test in this file
is `test_grounding_preset_matches_the_shipped_extractor_exactly`: while that passes, adopting
the scanner in `validate.py` is a no-op rather than a rewrite, and no validation verdict can
move without a test noticing.

Every name below is real — taken from the committed fixtures, from `logs/sportwire.log`, or
from the two live bugs recorded in `TASKS.md` P13. `CLAUDE.md` §8: assert on behaviour with
real-shaped data.
"""

from __future__ import annotations

import pytest

from processing.names import CLUSTERING, GROUNDING, NameScanner, is_name_word
from processing.validate import _PROPER_NAME

# --- the scanner asks Python what a capital is ------------------------------------------
#
# `[VERIFIED]` P13: every one of these was invisible or truncated under the enumerated
# character range this scanner replaces, and `Ş` is what killed the range approach — it is an
# uppercase letter outside `A-Z`, so every candidate fix that started a word with `[A-Z]`
# dropped Alperen Şengün.


@pytest.mark.parametrize(
    "text, expected",
    [
        ("LeBron James passes Kareem", ["LeBron James"]),
        ("DeMar DeRozan scored 30 points", ["DeMar DeRozan"]),
        ("Luka Dončić posted a triple-double", ["Luka Dončić"]),
        ("Kristaps Porziņģis returns", ["Kristaps Porziņģis"]),
        ("Alperen Şengün leads the Rockets", ["Alperen Şengün"]),
        ("Shai Gilgeous-Alexander wins MVP", ["Shai Gilgeous-Alexander"]),
        ("De'Aaron Fox to the Spurs", ["De'Aaron Fox"]),
    ],
)
def test_a_name_is_found_whatever_alphabet_it_is_written_in(
    text: str, expected: list[str]
) -> None:
    """The camelCase and non-ASCII names that the previous extractor could not see."""
    assert GROUNDING.findall(text) == expected


def test_a_number_is_not_a_name() -> None:
    """A word containing digits is never part of a name, wherever the digits sit.

    `[VERIFIED]` 2026-08-15 this test previously asserted the wrong mechanism — that "76ers"
    is excluded because it does not *start* with a capital. Mutation testing proved that
    claim empty: allowing a leading digit changes no output, because the digit then fails the
    all-letters test a character later. The exclusion these cases actually rely on is the one
    asserted below, so it is asserted directly.
    """
    assert is_name_word("76ers") is False
    assert is_name_word("2026-27") is False
    assert is_name_word("Sixers76") is False  # digits anywhere, not only in front
    assert GROUNDING.findall("The 76ers open 2026-27 at home") == []


def test_a_lowercase_word_is_not_a_name() -> None:
    """What the capital check is actually for, asserted on its own.

    `[INFERRED]` Without it every sentence collapses into one enormous name, and `validate.py`
    would then ground or accuse whole clauses rather than people.
    """
    assert is_name_word("signed") is False
    assert GROUNDING.findall("beal signed with the clippers") == []
    assert GROUNDING.findall("Bradley Beal signed with the Clippers") == [
        "Bradley Beal"
    ]


# --- punctuation: trailing only, never leading ------------------------------------------
#
# `[VERIFIED]` P13 records both bugs this rule came from, and they came from one line.
# Stripping a leading quote turned a real fixture title into the invented name `Sixer I'm`,
# and the same erased boundary welded a run large enough to acquit the invented "LeBron
# Tatum" by superset.


def test_opening_punctuation_separates_two_names() -> None:
    """The real fixture title that produced a false accusation when this was got wrong."""
    assert GROUNDING.findall('a Sixer: "I\'m still processing it"') == []


def test_a_name_is_not_matched_across_a_sentence_boundary_by_accident() -> None:
    """`[VERIFIED]` "Mavericks. LeBron" once matched as the single name `Mavericks. Le`.

    The scanner keeps the period inside the word — "Jr." and "L.A." need it — so callers
    still split on sentences first. What this asserts is that the *name* is recovered whole,
    not truncated mid-word the way the character range truncated `Dončić`.
    """
    assert "LeBron James" in " ".join(
        GROUNDING.findall("with the Mavericks. LeBron James chose Philadelphia")
    )


# --- the two policy flags, which is the whole reason this module is shared ---------------


def test_grounding_needs_two_words_and_clustering_accepts_one() -> None:
    """`[INFERRED]` A lone capital is usually a sentence opener; treating it as a name is how
    a validator invents an accusation. Clustering needs the opposite — `Beal` and
    `Daktronics` alone are exactly what pairs two reports of one story."""
    assert GROUNDING.findall("Beal re-signs with the Clippers") == []
    assert CLUSTERING.findall("Beal re-signs with the Clippers") == ["Beal", "Clippers"]


def test_punctuation_ends_a_name_only_when_the_caller_says_so() -> None:
    """The measured disagreement between the two callers, in one assertion.

    ~~`[VERIFIED]` Grounding wants the weld: the run is checked as a whole and by subset, so
    a stricter string costs nothing.~~ **WRONG, and corrected 2026-08-15.** The weld cost a
    live brief its prose. `Cavs Celtics` is not merely a harmless stricter string — it is
    indexed as a *source name*, and the refutation rule then treats it as an entity that
    disagrees with any real name sharing its last word. `[VERIFIED]` That is how
    `Cavaliers, Heat, Warriors` came to refuse `Golden State Warriors` in the 16:00 run.
    Both presets now end a run on a comma; see `validate._SEPARATES_NAMES`.

    `[VERIFIED]` The presets still differ, and the colon shows it: clustering ends a run on
    **any** trailing punctuation, grounding only on a separator.
    """
    assert GROUNDING.findall("Cavs, Celtics tip off") == []
    assert CLUSTERING.findall("Cavs, Celtics tip off") == ["Cavs", "Celtics"]

    assert GROUNDING.findall("Report: Kawhi Leonard signs") == ["Report Kawhi Leonard"]
    assert CLUSTERING.findall("Report: Kawhi Leonard signs") == [
        "Report",
        "Kawhi Leonard",
    ]


def test_a_word_before_punctuation_is_still_part_of_its_name() -> None:
    """Breaking the run must not discard the word that carried the punctuation.

    `[INFERRED]` The obvious off-by-one here drops `Cavs` entirely rather than ending the run
    after it, and the cost is invisible: a story simply stops grouping.
    """
    assert CLUSTERING.findall("Kawhi Leonard, Daktronics and the Clippers") == [
        "Kawhi Leonard",
        "Daktronics",
        "Clippers",
    ]


def test_a_scanner_is_configured_not_hardcoded() -> None:
    """Both presets are the same class with different policy, which is the point of P17."""
    assert isinstance(GROUNDING, NameScanner) and isinstance(CLUSTERING, NameScanner)
    assert (GROUNDING.min_words, GROUNDING.break_run_on_punctuation) == (2, False)
    assert (CLUSTERING.min_words, CLUSTERING.break_run_on_punctuation) == (1, True)


# --- the load-bearing one ----------------------------------------------------------------


def test_grounding_preset_matches_the_shipped_extractor_exactly(
    article_texts: list[str],
) -> None:
    """`GROUNDING` and `validate._PROPER_NAME` must agree on every text the repo has.

    **This is what makes adopting the scanner in `validate.py` a no-op.** `[VERIFIED]` 0
    differences across every title and summary in all three committed fixtures plus the edge
    cases below. If this test ever fails, the scanner has changed a validation verdict, and
    P12/P13 are the record of how expensive an unnoticed verdict change is here.
    """
    edge_cases = [
        'a Sixer: "I\'m still processing it"',
        "Cavs, Celtics tip off",
        "LeBron James",
        "DeMar DeRozan scored 30",
        "Luka Dončić posted",
        "Alperen Şengün leads",
        "Shai Gilgeous-Alexander wins",
        "76ers and 2026-27 season",
        "",
        "   ",
        "Mavericks. LeBron James chose",
        "De'Aaron Fox to the Spurs",
        "Karl-Anthony Towns",
    ]

    for text in article_texts + edge_cases:
        assert GROUNDING.findall(text) == _PROPER_NAME.findall(text), (
            f"scanner and shipped extractor disagree on {text!r}"
        )
