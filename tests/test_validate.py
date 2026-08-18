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
from processing.validate import (
    _PROPER_NAME,
    unsupported_sentences,
    validate_summary,
)

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

    `[VERIFIED]` 2026-08-13, by mutation: disabling `_trim_name_for_reporting` changes no
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


# --- the extractor: which names the checks above ever get to see ------------------------
#
# `[VERIFIED]` 2026-08-14. Everything above only works on names the extractor produces, and
# for the whole life of this module it produced nothing at all for "LeBron James". The
# pattern was `\b[A-Z][a-zà-ÿ'’.-]*`, and there is no word boundary inside "LeBron" — "e"
# and "B" are both word characters — so no match could start at the capital. `[VERIFIED]`
# The 2026-08-14 16:00 run carried 9 lines naming LeBron.
#
# The replacement enumerates no characters: `str.isupper` and `str.isalpha` read the Unicode
# database. `[VERIFIED]` A widened range was measured first and rejected — Latin Extended-A
# rescued Dončić and Porziņģis but still failed Şengün, whose "Ş" is an uppercase letter
# outside `A-Z`.


@pytest.mark.parametrize(
    "name",
    [
        "LeBron James",  # camelCase — extracted nothing at all before 2026-08-14
        "DeMar DeRozan",
        "Luka Dončić",  # was truncated to "Luka Don"
        "Nikola Jokić",  # was truncated to "Nikola Joki"
        "Alperen Şengün",  # uppercase Ş: defeats every A-Z range, including Latin Ext-A
        "Kristaps Porziņģis",
        "De'Aaron Fox",  # was truncated to "Aaron Fox"
        "Shai Gilgeous-Alexander",  # was truncated to "Shai Gilgeous-"
    ],
)
def test_a_name_is_seen_whole_whatever_alphabet_it_uses(
    name: str, make_article: ArticleFactory
) -> None:
    """A name the extractor cannot see is a name the validator never checks.

    Asserted through `validate_summary` rather than the extractor directly, because the
    behaviour that matters is the verdict: an unseen name is not "allowed", it is *unexamined*
    — the model could attach any claim to it and nothing would look.
    """
    articles = [make_article("Nets host a workout", summary="Nothing else happened.")]

    result = validate_summary(f"{name} scored 30 points.", articles)

    assert not result.is_safe, f"{name} was never examined"
    assert name in result.invented_names, (
        f"expected {name!r}, got {result.invented_names}"
    )


def test_a_camelcase_name_is_grounded_like_any_other(
    make_article: ArticleFactory,
) -> None:
    """The other direction: seeing the name must not mean flagging it."""
    articles = [
        make_article(
            "LeBron James picks the 76ers",
            summary="DeMar DeRozan and Luka Dončić were also linked.",
        )
    ]

    result = validate_summary(
        "LeBron James joined the 76ers. DeMar DeRozan and Luka Dončić were linked.",
        articles,
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_quoted_contraction_does_not_weld_itself_to_the_previous_word(
    make_article: ArticleFactory,
) -> None:
    """Opening punctuation is a boundary, so only *trailing* punctuation is stripped.

    `[VERIFIED]` 2026-08-14 this exact fixture title was flagged for the invented name
    `Sixer I'm` while the extractor stripped punctuation from both ends: the quote is the
    only thing separating `Sixer:` from `"I'm`, and removing it made them consecutive
    capitalised words. `[VERIFIED]` The same erased boundary welded longer runs together
    elsewhere, and one of those runs was large enough to acquit an invented "LeBron Tatum"
    by superset — so one character of over-eager stripping produced a false accusation and
    a missed fabrication at the same time.

    `[VERIFIED]` 2026-08-14, second time: the first version of this test put the quote in
    mid-sentence, where the lowercase "said" before it broke the run anyway — so it passed
    under both readings and the mutation survived. The colon-then-quote below is what makes
    `Sixer` and `I'm` *adjacent*, which is the only arrangement that can weld them.
    """
    headline = 'Jaylen Brown on being a Sixer: "I\'m still processing it"'
    articles = [
        make_article(headline, summary="The forward spoke at his introduction.")
    ]

    result = validate_summary(headline, articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_token_carrying_a_digit_is_not_part_of_a_name(
    make_article: ArticleFactory,
) -> None:
    """`[INFERRED]` "76ers" and "2026-27" survive only because they do not start with an
    uppercase letter — the rule that excludes them is the same one that admits Şengün.

    `NBA2K` is the case that needs the letters-only rule as well as the capital rule: it
    *does* start with a capital, and it sat next to another capitalised word in the
    2026-08-14 brief ("his NBA2K player rating of 87"). Admitting it would manufacture a
    name out of a product and a common noun, and then flag it as invented.
    """
    articles = [make_article("Sixers news", summary="Nothing else happened.")]

    result = validate_summary(
        "The 76ers open the 2026-27 season at home. Bam responded to his NBA2K Rating.",
        articles,
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


# --- blended names: the generosity above, refuted ---------------------------------------
#
# `[VERIFIED]` 2026-08-14. The three tests above bought their generosity at a price nobody
# had measured, and the bill arrived on the operator's phone: *"January will see Giannis
# Antetokounmpo and Jayson Brown reunions."* No such player. The model fused Jayson Tatum
# and Jaylen Brown — two names in the same feed because they were teammates — and the
# last-word rule grounded the result on "Brown". It passed on attempt 1.
#
# These four assert both directions at once, which is the whole difficulty: the fix must
# refuse the blend without taking the expansions and contractions back down with it.


def test_a_name_blended_from_two_real_players_is_caught(
    make_article: ArticleFactory,
) -> None:
    """The live 2026-08-14 failure. Both halves are grounded; the person is not.

    `[INFERRED]` This is the hardest fabrication class to catch by counting words, because
    every word is genuinely present in the sources. What refutes it is that the sources'
    own "... Brown" is a *different* Brown.
    """
    articles = [
        make_article(
            "Jaylen Brown details bumpy Celtics exit in 76ers introduction",
            summary="Jaylen Brown spoke about his relationship with Jayson Tatum.",
        ),
        make_article(
            "NBA releases 2026-27 schedule",
            summary="January features a Jayson Tatum reunion game in Boston.",
        ),
    ]

    result = validate_summary(
        "January will see Giannis Antetokounmpo and Jayson Brown reunions.", articles
    )

    assert not result.is_safe
    assert "Jayson Brown" in result.invented_names


def test_an_unrelated_first_name_on_a_real_surname_is_caught(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` Before the refutation rule, "Marcus Brown" passed as readily as the
    blend did — the last-word rule accepted *any* first name bolted to a grounded surname,
    which is inventing a person, not misspelling one."""
    articles = [
        make_article(
            "Jaylen Brown details bumpy Celtics exit",
            summary="Brown spoke at his introduction.",
        )
    ]

    result = validate_summary("Marcus Brown will play in January.", articles)

    assert not result.is_safe
    assert "Marcus Brown" in result.invented_names


def test_one_agreeing_source_name_acquits_despite_a_disagreeing_one(
    make_article: ArticleFactory,
) -> None:
    """`_contradicted` requires *every* same-surname source name to disagree, not any one.

    `[VERIFIED]` 2026-08-14, measured on the committed fixtures: the two readings disagree
    on 5 of 5,530 names, and every one of the five is a case where "all" is right and "any"
    is wrong — `new knicks` and `los clippers` are fragments of "New York Knicks" and "Los
    Angeles Clippers", which the sources also carry under a second, differing name
    ("Champion Knicks"). Under "any" the second entry would convict the first.

    Contracting a team's city is the exact class this module already threw away three live
    summaries over, so the stricter reading would reintroduce that bug through a new door.
    """
    articles = [
        make_article(
            "Oklahoma City Thunder win again",
            summary="A strong night in the west.",
        ),
        make_article(
            "Reigning Champion Thunder open the season at home",
            summary="The banner goes up first.",
        ),
    ]

    result = validate_summary("Oklahoma Thunder won on Tuesday night.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_name_is_judged_against_the_sources_not_against_a_field_boundary(
    make_article: ArticleFactory,
) -> None:
    """The index is built per field, so a title running into a summary cannot invent an entry.

    `[VERIFIED]` 2026-08-14, measured on the committed fixtures: indexing the joined text
    changes **89** verdicts and manufactures 11 names that exist in neither field — among
    them `Golden State Green`, `Knicks Philly` and `Free Agency Source`, each one a title's
    tail welded to the next field's head. The shape below is that last one, taken from the
    Yahoo item verbatim in structure: joined, "Free Agency" is swallowed into "Free Agency
    Source" and nothing is left under "agency" to refuse a fabricated one.
    """
    articles = [
        make_article(
            "Hornets named a landing spot for Russell Westbrook in Free Agency",
            summary="Source: Charlotte has registered interest.",
        )
    ]

    result = validate_summary("Wasserman Agency confirmed the deal.", articles)

    assert not result.is_safe, (
        "an agency the sources never name must not ground on 'Agency'"
    )
    assert "Wasserman Agency" in result.invented_names


def test_two_real_players_sharing_a_feed_both_still_ground(
    make_article: ArticleFactory,
) -> None:
    """The false-accusation direction, and the reason `_contradicted` requires *every*
    same-surname source name to disagree rather than any one of them.

    `[INFERRED]` A feed carrying both players is the normal case, not the exception — it is
    exactly what made the blend possible. If it also rejected the true sentence, the fix
    would cost more correct summaries than the bug it closes.
    """
    articles = [
        make_article(
            "Jaylen Brown details bumpy Celtics exit",
            summary="He discussed his relationship with Jayson Tatum.",
        )
    ]

    result = validate_summary(
        "Jayson Tatum and Jaylen Brown will meet in January.", articles
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_namesake_does_not_refute_a_name_the_sources_state_in_full(
    make_article: ArticleFactory,
) -> None:
    """Why the verbatim check must stay unconditional and run first.

    Kawhi Leonard and Meyers Leonard are both real, and disagree on every word but the last,
    so one would refute the other if the refutation ran before the phrase check.

    `[VERIFIED]` 2026-08-14: the first version of this test used a source that named Kawhi
    in sentence case, which put "Kawhi Leonard" in the index as its own agreeing entry and
    acquitted him twice over — so reordering the checks changed nothing and the mutation
    survived. The title-case headline here is what makes the ordering load-bearing:
    `_PROPER_NAME` swallows a title-case headline as one long name ending in "Play", so it
    contributes **nothing** under "leonard", and the verbatim substring is the only thing
    standing between a correct name and a rejection.
    """
    articles = [
        make_article(
            "Meyers Leonard signs with a new team",
            summary="The veteran big man is back in the league.",
        ),
        make_article(
            "Clippers Star Kawhi Leonard Cleared To Play",
            summary="He is available for the opener.",
        ),
    ]

    result = validate_summary("Kawhi Leonard returned on Tuesday.", articles)

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


@pytest.mark.parametrize(
    "closing",
    ['."', ".”", ".'", ".’", ".)", '.")'],
    ids=["straight", "curly", "apostrophe", "curly-apostrophe", "paren", "quote-paren"],
)
def test_a_sentence_ending_in_a_quotation_still_ends_the_sentence(
    make_article: ArticleFactory, closing: str
) -> None:
    """`[VERIFIED]` 2026-08-15 — the 2026-08-08 fusion bug above, returning through a gap.

    The 16:00 brief fell back to the headline list, and attempt 3 was rejected for the
    invented name `Hollywood Ending. Meanwhile Charles Oakley's` — two real names welded into
    one. `(?<=[.!?])\\s+` requires whitespace **immediately** after the terminator, and a
    sentence ending in a quotation reads `Ending.” Meanwhile`, where the next character is a
    quote mark. No split happened, `.` is legal inside a name, and the run walked into the
    next sentence.

    `[INFERRED]` This shape is routine here rather than exotic: the summariser works from
    headlines that quote players, so sentences ending in `.”` are ordinary. A phantom name
    can never be grounded in any source, so one of them costs the entire brief its prose.

    Parametrized over the closing marks that actually occur, because the original fix was
    correct for the unquoted case and this is the class it missed.

    **The second sentence deliberately ends its capitalised run on an ungrounded word.**
    `[VERIFIED]` A first version of this test read "…Meanwhile, Philadelphia completed…" and
    **passed even with the bug present**, because the fused candidate ends in "Philadelphia",
    which the sources do contain, and the last-word rule acquits on that alone. That is the
    same trap the test above this one documents, and it was walked into again. Ending the run
    on "Meanwhile" is what makes the fusion detectable.
    """
    articles = [
        make_article(
            "Mavericks talks collapse",
            summary='Dallas walked away, saying "this is over for the Mavericks."',
        ),
        make_article(
            "Philadelphia lands its target",
            summary="The Sixers completed the signing on Monday.",
        ),
    ]

    result = validate_summary(
        f'Dallas said "this is over for the Mavericks{closing} '
        "Meanwhile the signing completed.",
        articles,
    )

    assert result.is_safe, (
        f"wrongly flagged across {closing!r}: {result.invented_names} — a closing quote "
        "must not stop a full stop from ending the sentence"
    )


def test_a_comma_separated_list_is_not_one_name(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-15, from the CBS fixture: "Cavaliers, Heat, Warriors and Wolves".

    Commas were stripped as trailing punctuation and the capitalised run walked straight
    through them, so four teams became the single "name" `Cavaliers Heat Warriors`. Names are
    what the refutation rule compares against, and junk in that index refuses real names.
    """
    assert (
        _PROPER_NAME.findall("Cavaliers, Heat, Warriors and Wolves play tonight") == []
    )
    assert _PROPER_NAME.findall(
        "Reports from Shams Charania, Adrian Wojnarowski follow"
    ) == [
        "Shams Charania",
        "Adrian Wojnarowski",
    ]


def test_a_comma_after_a_name_still_leaves_the_name(
    make_article: ArticleFactory,
) -> None:
    """The complement, or the fix above would delete names instead of splitting them."""
    assert _PROPER_NAME.findall("Kawhi Leonard, who signed Friday, spoke") == [
        "Kawhi Leonard"
    ]


def test_expanding_a_team_name_is_not_a_fabrication(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-15 — a false rejection that reached the operator's phone.

    The 16:00 brief fell back to the headline list, rejected in part for `Golden State
    Warriors`. Writing a team's full name where the source used the short one is ordinary
    phrasing, not invention — but `Cavaliers, Heat, Warriors` was indexed as a single name
    ending in "warriors", and the refutation rule then found it disagreed with `Golden State
    Warriors` and refused it.

    Measured across the fixtures before the fix: **3 of 17** teams mentioned by short name
    were refused when expanded.
    """
    articles = [
        make_article(
            "Cavaliers, Heat, Warriors and Wolves all made offers",
            # Deliberately avoids a sentence opening "The Warriors": that welds a
            # capitalised "The" onto the team and is a *second*, unfixed cause of the
            # same false rejection. This test is scoped to the comma alone.
            summary="Several teams made offers before Friday's deadline.",
        )
    ]

    result = validate_summary(
        "The Golden State Warriors were among the teams involved.", articles
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_capitalised_ordinary_word_does_not_refute_a_real_name(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-15 (TASKS.md P20 option (b)) — a false accusation, measured.

    A sentence-initial "The" or a headline's "Retired" is capitalised by position, not
    because it names anything. Indexed as part of a name, `{the, warriors}` then reads as an
    entity that disagrees with `Golden State Warriors`, and the real team is refused.

    The corpus decides which words are ordinary — a word the sources also write in lower
    case is vocabulary. `[VERIFIED]` Measured against a hand-written stop-word list like
    `cluster.py`'s `_NOT_NAMES`: that left `Miami Heat` still refused, this leaves none of
    the 11 expandable fixture teams refused, and both keep all seven curated blends.

    **This case is deliberately two words against two.** `[VERIFIED]` 2026-08-15 by
    mutation, during the `/commit` audit: a first version used `Golden State Warriors`
    against `The Warriors` and **passed with the filter disabled**, because the length rule
    added later already refuses a 2-word name the right to refute a 3-word one. It asserted
    nothing about this filter. `Miami Heat` against `Retired Heat` is equal length, so the
    length rule cannot reach it and only the ordinary-word filter can — which is also the
    measured evidence that this filter is not redundant.
    """
    articles = [
        make_article(
            "Retired Heat star returns for the ceremony",
            summary=(
                "The retired guard will be honoured, and the Heat have confirmed the date."
            ),
        )
    ]

    result = validate_summary("Miami Heat confirmed the date.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


@pytest.mark.parametrize("written", ["Mike D'Antoni", "Mike D’Antoni"])
def test_an_apostrophe_shape_does_not_decide_whether_a_name_exists(
    make_article: ArticleFactory, written: str
) -> None:
    """`[VERIFIED]` 2026-08-17, from the 00:00 run — the fourth false accusation of this class.

    All three attempts were rejected for `Mike D'Antoni`, and lead 3 of that very batch was
    Yahoo's *"Honoring new Hall of Fame inductee, former Rockets coach Mike D’Antoni"*. The
    feed writes U+2019 RIGHT SINGLE QUOTATION MARK and the model writes U+0027 APOSTROPHE.
    Every comparison in this module is literal string matching, so the two could never meet
    and a name plainly present in the sources was reported as fabricated.

    `[INFERRED]` It stayed hidden because both shapes **render identically** — reading the
    rejection log beside the feed shows the same characters. This is the first bug of the
    class found by an automated check rather than by the operator noticing a degraded brief.

    Parametrized over both shapes: the summary may use either, and so may the source.
    """
    articles = [
        make_article(
            "Honoring new Hall of Fame inductee, former Rockets coach Mike D’Antoni",
            summary="The coach enters the Hall this weekend.",
        )
    ]

    result = validate_summary(f"{written} enters the Hall of Fame.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


@pytest.mark.parametrize(
    ("source_spelling", "summary_spelling"),
    [
        # `[VERIFIED]` Every pair below appears in BOTH spellings across 329 live and fixture
        # articles — the sources disagree with themselves, so neither side can be called the
        # model's error. Counts from that corpus: Schröder 9 accented against 17 plain.
        ("Luka Dončić", "Luka Doncic"),
        ("Luka Doncic", "Luka Dončić"),
        ("Nikola Jokić", "Nikola Jokic"),
        ("Nikola Jokic", "Nikola Jokić"),
        ("Dennis Schröder", "Dennis Schroder"),
        ("Dennis Schroder", "Dennis Schröder"),
        # Not yet seen in both forms, but the same mechanism and the same league.
        ("Kristaps Porziņģis", "Kristaps Porzingis"),
        ("Alperen Şengün", "Alperen Sengun"),
        ("Nikola Vučević", "Nikola Vucevic"),
        ("Bogdan Bogdanović", "Bogdan Bogdanovic"),
    ],
)
def test_a_diacritic_does_not_decide_whether_a_name_exists(
    make_article: ArticleFactory, source_spelling: str, summary_spelling: str
) -> None:
    """`[VERIFIED]` 2026-08-17 — the same defect as the apostrophe, measured across the league.

    Three of the six accented names in the corpus **also appear unaccented in it**. Yahoo
    prints `Dennis Schröder` and `Dennis Schroder` in different headlines of the *same story*,
    so this cannot be corrected at the prompt: the sources disagree with themselves, and
    whichever spelling the model copies, the other one is what it gets compared against.

    Both directions are asserted, because either side may carry either spelling.
    """
    articles = [
        make_article(
            f"{source_spelling} dominates the fourth quarter",
            summary=f"A statement night from {source_spelling}.",
        )
    ]

    result = validate_summary(f"{summary_spelling} dominated late.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_folding_a_diacritic_does_not_ground_a_different_player(
    make_article: ArticleFactory,
) -> None:
    """Folding must merge spellings of one name, never two different names.

    `[INFERRED]` The risk of any normalisation is over-merging. `Jokić` and `Jokic` are one
    person; `Jokić` and `Dončić` are not, and stripping accents must not blur them.
    """
    articles = [make_article("Nikola Jokić posts a triple-double")]

    assert validate_summary("Nikola Jokic starred.", articles).is_safe
    assert not validate_summary("Luka Doncic starred.", articles).is_safe


def test_folding_apostrophes_does_not_ground_an_absent_name(
    make_article: ArticleFactory,
) -> None:
    """The complement: folding shapes must not turn the check into a rubber stamp."""
    articles = [
        make_article(
            "Honoring new Hall of Fame inductee, former Rockets coach Mike D’Antoni",
            summary="The coach enters the Hall this weekend.",
        )
    ]

    result = validate_summary("Steve O’Malley enters the Hall of Fame.", articles)

    assert not result.is_safe, "a name absent from the sources must still be refused"


def test_a_shorter_source_name_does_not_refute_an_expansion(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-15 — the case that opened P20, from the live 16:00 batch.

    `Los Angeles Lakers` was refused as invented because the sources carried
    `Inside Lakers mega-deal` and the book title `the LeBron Lakers`. Both are two words,
    both end in "lakers", and neither agrees about the rest — so the refutation rule
    convicted a real team on the strength of a headline's first word.

    `[INFERRED]` A **longer** summary name sharing a last word with a **shorter** source name
    is an expansion, which is writing. An **equal-length** disagreement is a substitution,
    which is the failure ADR-012 measured. The next test holds that half.

    Neither `inside` nor `lebron` appears in lower case here, so the ordinary-vocabulary
    filter cannot reach them — this is the half of P20 that filter could not fix.
    """
    articles = [
        make_article(
            "Inside Lakers mega-deal: Mark Walter made a shocking decision",
            summary="The sale of the Lakers to Bob Iger comes as Mark Walter faces probes.",
        ),
        make_article(
            "Book documents the LeBron Lakers",
            summary="A Hollywood Ending covers the LeBron Lakers and James in Los Angeles.",
        ),
    ]

    result = validate_summary("Los Angeles Lakers were sold this week.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_an_equal_length_disagreement_still_refutes(
    make_article: ArticleFactory,
) -> None:
    """The other half: the length rule must not disarm blend detection.

    `[VERIFIED]` A blend is the same length as the name it displaces — "Jayson Tatum" and
    "Jaylen Brown" fusing into "Jayson Brown" — so the rule above never reaches it.
    """
    articles = [
        make_article(
            "Celtics camp opens",
            summary="Jaylen Brown spoke on Monday and Jayson Tatum was present.",
        )
    ]

    result = validate_summary("Jayson Brown led the way.", articles)

    assert not result.is_safe, "a same-length substitution must still be refused"
    assert "Jayson Brown" in result.invented_names


def test_stripping_a_word_must_not_leave_a_lone_surname_in_the_index(
    make_article: ArticleFactory,
) -> None:
    """The guard on the P20 filter: a one-word entry would acquit every blend of that name.

    `[VERIFIED]` 2026-08-15 by mutation. Dropping the two-word floor in
    `_index_source_names` to one passes the rest of the suite, so nothing else pins it — but
    it is not an equivalent mutant. `Reportedly Brown` reduces to the bare `{brown}` once
    "reportedly" is recognised as ordinary vocabulary, and `_contradicted` acquits whenever
    **any** source name agrees, treating a lone surname as agreement with every expansion of
    it. The blend `Jayson Brown` then passes and reaches the phone.

    A bare surname is not evidence about which person is meant, so it must not enter the
    index at all.
    """
    articles = [
        make_article(
            "Celtics camp opens",
            summary=(
                "Jaylen Brown spoke on Monday. Reportedly Brown will sign an extension, "
                "though reportedly the talks stalled."
            ),
        ),
        make_article("Tatum update", summary="Jayson Tatum was present."),
    ]

    result = validate_summary("Jayson Brown led the way.", articles)

    assert not result.is_safe, "a blend of two real players must still be refused"
    assert "Jayson Brown" in result.invented_names


def test_a_blended_name_is_still_refused_after_the_comma_fix(
    make_article: ArticleFactory,
) -> None:
    """The guard on the fix above: splitting on commas must not disarm the refutation rule.

    `[VERIFIED]` This is the P12 case — a model fusing two real players into one name that
    the last-word rule would otherwise wave through.
    """
    articles = [
        make_article(
            "Celtics preview",
            summary="Jayson Tatum and Jaylen Brown, the Celtics pair, both spoke.",
        )
    ]

    result = validate_summary("Jayson Brown led the way.", articles)

    assert not result.is_safe, "a blend of two real names must still be refused"
    assert "Jayson Brown" in result.invented_names


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


# --- the sport's own vocabulary is not a claim about anyone --------------------------------


def test_a_conference_the_sources_never_mention_is_not_invented(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-17 00:00 — this exact batch cost a brief its prose.

    All three attempts were rejected for `Eastern Conference` and `Western Conference`, and
    by the letter of the rule the rejections were right: the replayed batch's 8 leads contain
    neither phrase. The headlines below are four of those real leads.

    They are also not fabrications in any sense that matters. Naming the half of the league a
    team plays in is not a claim about a person, and there is no `Eastern Conference` to be
    wrong about. `TASKS.md` P23.
    """
    articles = [
        make_article("NBA HOF week: Mike D'Antoni dishes on Nash, Kobe and Linsanity"),
        make_article("Wolves to retire Garnett's 21 after Celtics game"),
        make_article("Ex-Knick Oakley's assault case vs. MSG dismissed"),
        make_article("Sources: Cavs deal Schroder for Hornets' Mann"),
    ]

    result = validate_summary(
        "The Wolves will retire Kevin Garnett's number. "
        "Elsewhere in the Eastern Conference, the Cavs moved on from Dennis Schroder.",
        articles,
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


@pytest.mark.parametrize(
    "term",
    [
        # `[VERIFIED]` Every phrase here is written by the live feeds themselves — measured
        # 2026-08-17 across 203 live and fixture articles.
        "Eastern Conference",
        "Western Conference",
        "Eastern Conference Finals",
        "NBA Finals",
        "NBA Draft",
        "WNBA All-Star Weekend",
        # `[INFERRED]` Same class, same league, not yet observed in a rejection.
        "Atlantic Division",
        "Play-In Tournament",
        "Summer League",
        "Draft Lottery",
        "All-Defensive Team",
    ],
)
def test_competition_vocabulary_needs_no_source(
    make_article: ArticleFactory, term: str
) -> None:
    """A structural term of the sport is grounded by the sport, not by today's headlines."""
    articles = [make_article("Sources: Cavs deal Schroder for Hornets' Mann")]

    result = validate_summary(f"The move reshapes the {term}.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_vocabulary_does_not_launder_the_name_standing_next_to_it(
    make_article: ArticleFactory,
) -> None:
    """The exemption needs **every** word, which is the whole of its safety.

    `[VERIFIED]` `Joe Dumars` is the fabrication that proved retry cannot beat a training
    prior. Putting a real structural term in front of it must not buy it a pass.
    """
    articles = [make_article("The Detroit Pistons are exploring a sign-and-trade")]

    result = validate_summary(
        "Eastern Conference executive Joe Dumars is leading the negotiations.", articles
    )

    assert not result.is_safe
    assert "Joe Dumars" in " ".join(result.invented_names)


@pytest.mark.parametrize(
    "team",
    [
        # Every NBA nickname that is also an ordinary English word. `[INFERRED]` These are
        # the ones a vocabulary list could plausibly swallow, so they are the ones asserted:
        # if any entry ever collides, a real team stops needing a source.
        "Miami Heat",
        "Orlando Magic",
        "Utah Jazz",
        "Sacramento Kings",
        "Brooklyn Nets",
        "Chicago Bulls",
        "Phoenix Suns",
        "Oklahoma City Thunder",
        "Milwaukee Bucks",
        "Detroit Pistons",
        "Houston Rockets",
        "Indiana Pacers",
        "Washington Wizards",
    ],
)
def test_a_team_is_never_exempt_from_grounding(
    make_article: ArticleFactory, team: str
) -> None:
    """`[VERIFIED]` 0 of 31 team names are competition vocabulary — asserted, not assumed.

    A team is an entity that can be fabricated; a conference is not. If a future entry in
    `_COMPETITION_VOCABULARY` ever makes a team exempt, this fails rather than shipping a
    hole in the one check standing between the model and the operator's phone.

    The source headline is chosen to contain **no team nickname as a substring**.
    `[VERIFIED]` 2026-08-17: written first against "Sources: Cavs deal Schroder for Hornets'
    Mann", this passed for 12 of 13 teams and let `Brooklyn Nets` through — because grounding
    asks `"nets" in source`, and "Hornets" contains it. That is a real weakness of substring
    matching and it is **not** what this test is for, so the fixture avoids it; TASKS.md P24
    holds the weakness itself.
    """
    articles = [make_article("LeBron tests new talent with YouTube golf page")]

    result = validate_summary(f"The {team} were quiet on Sunday.", articles)

    assert not result.is_safe, f"{team} was exempted from grounding"


def test_one_vocabulary_word_does_not_exempt_the_whole_name(
    make_article: ArticleFactory,
) -> None:
    """The exemption needs **every** word, and this is the test that proves it.

    `[VERIFIED]` 2026-08-17, found by mutation: changing `all` to `any` in
    `_is_competition_term` left the entire suite green. `Joe Dumars` standing *beside*
    `Eastern Conference` does not exercise the rule, because a lowercase word between them
    ends the first name and starts a second — the two never share a run.

    A model writing a title does put them in one run, and that is the case that matters:
    `Western Conference MVP Joe Dumars` is a single capitalised run whose last word is
    fabricated. Under `any`, one real structural word would have bought the whole phrase a
    pass — which is exactly the hole a hardcoded list is supposed not to open.
    """
    articles = [make_article("The Detroit Pistons are exploring a sign-and-trade")]

    result = validate_summary(
        "Western Conference MVP Joe Dumars is leading the negotiations.", articles
    )

    assert not result.is_safe, "a fabricated name rode in on a vocabulary word"
    assert "Dumars" in " ".join(result.invented_names)


# --- one team, several names ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("as_the_feed_writes_it", "as_the_brief_writes_it"),
    [
        # `[VERIFIED]` Every short form here was counted in 331 live and fixture articles.
        # The first pair is the one that cost the 2026-08-17 16:00 brief its prose.
        ("76ers", "Philadelphia Sixers"),
        ("Sixers", "Philadelphia 76ers"),
        ("Cavs", "Cleveland Cavaliers"),
        ("Wolves", "Minnesota Timberwolves"),
        ("Twolves", "Minnesota Timberwolves"),
        ("Mavs", "Dallas Mavericks"),
        ("Ex-Knick", "New York Knicks"),
        ("OKC", "Oklahoma City Thunder"),
    ],
)
def test_a_team_is_one_team_under_either_name(
    make_article: ArticleFactory,
    as_the_feed_writes_it: str,
    as_the_brief_writes_it: str,
) -> None:
    """`[VERIFIED]` 2026-08-17 16:00 fell back on `Philadelphia Sixers`, three attempts running.

    The feeds wrote `76ers` 11 times and `Sixers` once that day. `76ers` starts with a digit,
    so `_is_name_word` refuses it on purpose, and grounding therefore never sees it. A team
    that half the batch was about got reported as invented. TASKS.md P26.
    """
    articles = [
        make_article(
            f"{as_the_feed_writes_it} make a move ahead of the season",
            summary=f"A busy week for {as_the_feed_writes_it}.",
        )
    ]

    result = validate_summary(f"{as_the_brief_writes_it} made a move.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


@pytest.mark.parametrize(
    ("headline", "team"),
    [
        # `[VERIFIED]` Each of these short forms really occurs in the corpus and never means
        # the team. `king` appears 5 times: it is LeBron, and a quarterback named Haynes King.
        (
            "Rookie QBs Carson Beck, Haynes King shine in the Hall of Fame Game",
            "Sacramento Kings",
        ),
        ("Watch the best clips from last night", "Los Angeles Clippers"),
        ("The safety net under his contract is thin", "Brooklyn Nets"),
    ],
)
def test_an_ordinary_word_is_not_a_team_alias(
    make_article: ArticleFactory, headline: str, team: str
) -> None:
    """The alias table is only worth having if it stays a table of teams.

    `[VERIFIED]` These three were measured and then deliberately left out. Had `king`, `clips`
    or `net` been aliased on the strength of looking like a short form, each would ground a
    team on a word that has nothing to do with it.
    """
    articles = [make_article(headline)]

    result = validate_summary(f"{team} were busy this week.", articles)

    assert not result.is_safe, f"{team} was grounded by an ordinary word"


def test_an_alias_grounds_its_own_team_and_no_other(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` Both teams the model actually invented on 2026-08-17 stay caught.

    `Heat`, `Miami Heat`, `Mavericks` and `Mavs` appear **0** times in the 128 live articles
    captured that day, and attempt 3 asserted both. An alias must reach its own team only.
    """
    articles = [make_article("Sources: Cavs deal Schroder for Hornets' Mann")]

    assert validate_summary("Cleveland Cavaliers made a deal.", articles).is_safe
    assert not validate_summary("Miami Heat made a deal.", articles).is_safe
    assert not validate_summary("Dallas Mavericks made a deal.", articles).is_safe


# --- a player the feeds name by first name alone --------------------------------------------


@pytest.mark.parametrize(
    ("as_the_feed_writes_it", "as_the_brief_writes_it"),
    [
        # `[VERIFIED]` Counted in the 127 live articles captured 2026-08-17. The bare first
        # name is what the feeds print; the count after it is how often the full name appears.
        # `Ja` 33 times against `Ja Morant` 0. `LeBron` 26 against `LeBron James` 15.
        # `Wemby` 4 against 0. `Giannis` and `Luka` twice each, against 0.
        ("LeBron", "LeBron James"),
        ("Giannis", "Giannis Antetokounmpo"),
        ("Luka", "Luka Doncic"),
        ("Ja", "Ja Morant"),
        ("Kobe", "Kobe Bryant"),
        ("Klay", "Klay Thompson"),
        ("Kawhi", "Kawhi Leonard"),
    ],
)
def test_writing_out_a_first_name_is_not_inventing_a_player(
    make_article: ArticleFactory,
    as_the_feed_writes_it: str,
    as_the_brief_writes_it: str,
) -> None:
    """`[VERIFIED]` The 2026-08-17 08:00 run lost its prose to `LeBron James`, three attempts.

    Grounding used to end on the last word, so a name was identified by its surname. When the
    batch says only `LeBron`, the full name has no surname to match and the brief is accused
    of inventing the player it is reporting on.

    `[INFERRED]` This is the mirror of the bug the last-word rule was added to fix. P11 fixed
    `Knicks` written out as `New York Knicks`, where the last word identifies. Here the first
    word does, and one rule caused both. TASKS.md P25.
    """
    articles = [
        make_article(
            f"{as_the_feed_writes_it} was the story of the night",
            summary=f"Everyone wanted to talk about {as_the_feed_writes_it}.",
        )
    ]

    result = validate_summary(f"{as_the_brief_writes_it} was the story.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


@pytest.mark.parametrize(
    "fabricated",
    [
        # A real first name from the sources with a surname from nowhere. `[VERIFIED]` Letting
        # the first word ground a name, without also letting it refute one, missed all six of
        # these. That reading is recorded in TASKS.md P25 as rejected for this reason.
        "Anthony Edwards",
        "Anthony Simons",
        "Anthony Kowalski",
        "LeBron Smith",
        "LeBron Okoro",
        "LeBron Vanterpool",
    ],
)
def test_a_real_first_name_does_not_carry_an_invented_surname(
    make_article: ArticleFactory, fabricated: str
) -> None:
    """The cost of grounding on the first word, and the reason the index keys both ends.

    Without the matching change to `_index_source_names`, a grounded first name would launder
    any surname attached to it, which invents people. Naming a real player who is not in the
    batch is exactly what this module exists to stop.
    """
    articles = [
        make_article("Anthony Davis contract extension on hold as Wizards wait"),
        make_article("LeBron James tests new talent with YouTube golf page"),
    ]

    result = validate_summary(f"{fabricated} signed on Sunday.", articles)

    assert not result.is_safe, f"{fabricated} was accepted"


def test_indexing_both_ends_still_acquits_two_real_players(
    make_article: ArticleFactory,
) -> None:
    """The other direction: a wider index must not start refusing real people.

    `[VERIFIED]` A feed carrying both `Jaylen Brown` and `Jayson Tatum` must ground each of
    them. `_contradicted` needs *every* same-key source name to disagree, so the name's own
    entry acquits it, and that holds under either key.
    """
    articles = [
        make_article("Jaylen Brown details bumpy Celtics exit with Jayson Tatum")
    ]

    assert validate_summary("Jaylen Brown spoke about it.", articles).is_safe
    assert validate_summary("Jayson Tatum spoke about it.", articles).is_safe
    assert not validate_summary("Jayson Brown spoke about it.", articles).is_safe


def test_a_headline_label_does_not_refute_the_team_beside_it(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-17: the third time this bug shipped, and the first found by a dry run.

    With P25 and P26 both in place, a full dry run still rejected `Philadelphia Sixers` on two
    attempts. The batch carried the real headline below, which was read as the name
    `{report, sixers}`. That is two words sharing a last word with the team and disagreeing
    about the other, so the refutation rule treated a headline's label as a rival entity.

    P20 was supposed to cover this. Its fix does not reach here, because `_ordinary_words` only
    learns that a word is vocabulary when the batch writes it in lower case, and a 12-story
    batch never wrote "report". `[VERIFIED]` Confirmed by adding one article containing "per
    report" to the same batch, after which the team grounded. A colon is now a separator.
    """
    articles = [
        make_article("Report: Sixers hire Tommy Balcetis to front office"),
        make_article("Wolves to retire Garnett's 21 after Celtics game"),
    ]

    result = validate_summary("Philadelphia Sixers hired him this week.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_label_is_dropped_but_the_person_after_it_is_still_checked(
    make_article: ArticleFactory,
) -> None:
    """Ending the run at a colon must not let the name after it through unexamined."""
    articles = [make_article("Wolves to retire Garnett's 21 after Celtics game")]

    result = validate_summary("Sources: Joe Dumars is leading the talks.", articles)

    assert not result.is_safe
    assert "Joe Dumars" in " ".join(result.invented_names)


# --- claims joining entities that never met -------------------------------------------------


def _lillard_batch(make_article: ArticleFactory) -> list[NewsArticle]:
    """Four real articles from the 2026-08-18 00:00 batch, reconstructed from the database."""
    return [
        make_article(
            "Blazers offseason recap and early season preview: Lillard is back but "
            "questions remain",
            summary=(
                "With noise outside the hardwood growing in Portland, how will the Blazers "
                "respond? We're looking at the offseason and previewing the 2026-27 season."
            ),
        ),
        make_article("Sources: Watford, Pels agree to 1-yr, $2.9M deal"),
        make_article("Former LSU Forward Trendon Watford signs with the Pelicans"),
        make_article("Report: Cavaliers actively searching to move key contributor"),
    ]


def test_a_claim_joining_two_entities_that_never_met_is_flagged(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-18: this sentence reached the operator's phone and is false.

    The batch's only Lillard article says he is back with Portland. The brief moved him to New
    Orleans and invented a trade to explain it. Both `Pelicans` and `Damian Lillard` are real
    and both are in the batch, so grounding passes them; only the relationship is invented.
    TASKS.md P5.
    """
    articles = _lillard_batch(make_article)

    flagged = unsupported_sentences(
        "The Pelicans, who are welcoming back star point guard Damian Lillard following "
        "his trade from Portland, are shaping up as a team.",
        articles,
    )

    assert len(flagged) == 1, flagged
    assert "Damian Lillard" in flagged[0]


def test_flagging_a_claim_does_not_reject_the_summary(
    make_article: ArticleFactory,
) -> None:
    """The operator's choice on 2026-08-18: mark these, do not reject them.

    `[VERIFIED]` Rejecting the sentence would reject the summary, and the 00:00 run would then
    have delivered a headline list on all three attempts. So this must never touch `is_safe`.
    """
    articles = _lillard_batch(make_article)
    summary = "The Pelicans are welcoming back Damian Lillard following his trade from Portland."

    assert unsupported_sentences(summary, articles)
    assert validate_summary(summary, articles).is_safe


def test_a_true_claim_about_entities_sharing_an_article_is_not_flagged(
    make_article: ArticleFactory,
) -> None:
    """The expensive direction. `[VERIFIED]` This sentence is true and was flagged twice while
    the check was being built.

    First because source entities were read with grounding's two-word rule, so the lone
    capitalised `Pelicans` in "signs with the Pelicans" contributed nothing. Then because the
    opener "In NBA news" extracts as `In NBA`, keying on `nba`, which shares no article with
    `watford`. Both are fixed, and both were found by running the real string rather than a
    tidied one.
    """
    articles = _lillard_batch(make_article)

    flagged = unsupported_sentences(
        "In NBA news, Trendon Watford has signed a one-year, $2.9 million deal with the "
        "New Orleans Pelicans, marking his return to Louisiana.",
        articles,
    )

    assert flagged == [], f"wrongly flagged: {flagged}"


def test_a_sentence_naming_one_entity_is_never_flagged(
    make_article: ArticleFactory,
) -> None:
    """A relationship needs two parties. One entity cannot contradict anything."""
    articles = _lillard_batch(make_article)

    assert (
        unsupported_sentences(
            "The Portland Trail Blazers face uncertainty this season.", articles
        )
        == []
    )


def test_competition_vocabulary_is_not_an_entity_for_this_check(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` `nba` co-occurs with almost nothing, so treating it as an entity flags
    everything. The sport's own vocabulary cannot hold a relationship.
    """
    articles = _lillard_batch(make_article)

    assert (
        unsupported_sentences(
            "The Western Conference saw Trendon Watford join the Pelicans.", articles
        )
        == []
    )


# --- a name the sources only ever abbreviate -------------------------------------------------


@pytest.mark.parametrize(
    ("headline", "written_out"),
    [
        # `[VERIFIED]` Both cost a real brief. The KAT one is from the 2026-08-17 08:00 batch,
        # which was recorded at the time as the model inventing a player. It was not.
        ("💍 KAT, Jordyn Woods tie the knot in Malibu", "Karl-Anthony Towns"),
        ("Ex-Knick Oakley's assault case vs. MSG dismissed", "Madison Square Garden"),
    ],
)
def test_writing_out_an_abbreviation_is_not_inventing_a_name(
    make_article: ArticleFactory, headline: str, written_out: str
) -> None:
    """`[VERIFIED]` TASKS.md P21, and it has cost two briefs rather than the one it recorded.

    Nothing in "MSG" contains "Madison", "Square" or "Garden", so every grounding rule fails
    correctly and the refutation index is empty. The model expanded a well-known abbreviation
    and the brief lost its prose for it.
    """
    articles = [make_article(headline)]

    result = validate_summary(f"{written_out} was in the news.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_initials_alone_do_not_ground_a_name(make_article: ArticleFactory) -> None:
    """The reason P21 is a table and not a rule, asserted so nobody generalises it later.

    `[VERIFIED]` Taking a name's initials and looking for them in the sources acquits
    `Ayo Dosunmu`, the fabrication this module exists to catch, because its initials spell
    `AD` and the feeds print `AD`. `Anthony Davis` collides on the same two letters. A rule
    that cannot separate those is worse than no rule.
    """
    articles = [make_article("AD headlined a quiet night in the Eastern Conference")]

    assert not validate_summary("Ayo Dosunmu was central.", articles).is_safe
    assert not validate_summary("Anthony Davis signed.", articles).is_safe


def test_a_name_is_not_grounded_by_letters_inside_another_word(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-18, and this is a regression guard for a hole P25 opened.

    Grounding used to ask whether a word occurred anywhere in the source text, as a plain
    substring. While only the *last* word could ground a name, an accidental match had to land
    on a surname and never did. Once P25 let the *first* word ground a name, every short first
    name became exposed: `Ayo Dosunmu` grounds against a batch that never mentions him,
    because "ayo" sits inside **playoffs** and **layoffs**.

    Measured across 239 articles, the exposure is not marginal: `ad` occurs 181 times as a
    substring against 1 as a word, `la` 352 against 9, and `kat` 3 against 2, since "skate"
    contains it.
    """
    articles = [
        make_article(
            "Mark Walter's Lakers sale memorialized by mass layoffs, price hikes"
        ),
        make_article("Nuggets look ahead to the playoffs after a quiet week"),
    ]

    result = validate_summary("Ayo Dosunmu was central to the plan.", articles)

    assert not result.is_safe, "'ayo' inside 'playoffs' must not ground a player"
    assert "Ayo Dosunmu" in result.invented_names


def test_an_abbreviation_must_stand_alone_to_ground_a_name(
    make_article: ArticleFactory,
) -> None:
    """The same boundary rule, on the abbreviation side.

    `[VERIFIED]` "skate" contains "kat". An abbreviation buried inside a longer word says
    nothing about the name it stands for.
    """
    articles = [make_article("Watch the team skate through a light practice session")]

    assert not validate_summary("Karl-Anthony Towns married.", articles).is_safe


def test_the_leagues_own_paperwork_needs_no_source(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-18 16:00 attempt 1 was rejected for `Collective Bargaining
    Agreement`, which is a document the league has whether or not any outlet mentioned it.

    `[VERIFIED]` Measured before adding it: across 256 articles and 397 distinct names, these
    three words acquit nothing else, no team and no person.
    """
    articles = [make_article("Raptors fans confused about when Kawhi nightmare ends")]

    result = validate_summary(
        "The Collective Bargaining Agreement shapes what teams can offer.", articles
    )

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_a_wider_vocabulary_sample_stops_a_label_refuting_a_team(
    make_article: ArticleFactory,
) -> None:
    """`[VERIFIED]` 2026-08-18 16:00 fell back on all three attempts, and two of its three
    rejections were this.

    `Toronto Raptors` was refused because the batch carried "Raptors Reacts: Which player
    needs to elevate their game next to Kawhi?", which is indexed as the name
    `{raptors, reacts}` and disagrees with the real team about its other word. "Reacts" is a
    section label, not an entity, and P20's vocabulary rule missed it only because a
    twelve-story batch never happened to write the word in lower case.

    The wider sample is where the evidence lives: across 258 captured articles, "reacts" is
    ordinary. Nothing else changes, and in particular the names are still grounded against
    `articles` alone.
    """
    batch = [
        make_article(
            "Raptors Reacts: Which player needs to elevate their game next to Kawhi?"
        ),
        make_article("Raptors fans confused about when Kawhi nightmare ends"),
    ]

    assert not validate_summary("Toronto Raptors have options.", batch).is_safe

    wider = [*batch, make_article("The crowd reacts to a late three in Denver")]

    result = validate_summary("Toronto Raptors have options.", batch, wider)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


def test_the_wider_sample_never_grounds_a_name_by_itself(
    make_article: ArticleFactory,
) -> None:
    """The sample teaches vocabulary only. It must not vouch for a name.

    `[INFERRED]` This is the whole reason it is a separate argument rather than simply passing
    more articles: `articles` is what a name is grounded against, and a story the brief never
    summarised has no business supporting a claim in it.
    """
    batch = [make_article("Raptors fans confused about when Kawhi nightmare ends")]
    wider = [*batch, make_article("Joe Dumars is leading the negotiations in Detroit")]

    result = validate_summary("Joe Dumars led the talks.", batch, wider)

    assert not result.is_safe, "an article outside the batch must not ground a name"
    assert "Joe Dumars" in result.invented_names


# --- one name spelled wrongly by the source --------------------------------------------------


@pytest.mark.parametrize(
    ("headline", "written_out"),
    [
        # `[VERIFIED]` Both are real headlines, and each cost a brief.
        (
            (
                "Pablo Torre on ESPN's report regarding negotiations between "
                "Steve Balmer and the NBA"
            ),
            "Steve Ballmer",
        ),
        (
            "Anthony Edwards meets Lebwrong James and company in the Philippines",
            "LeBron James",
        ),
    ],
)
def test_a_source_spelling_a_name_wrongly_does_not_refute_it(
    make_article: ArticleFactory, headline: str, written_out: str
) -> None:
    """`[VERIFIED]` TASKS.md P33. Two briefs lost to this, on 2026-08-18 and 2026-08-19.

    The first is a typo, one L in Ballmer. The second is a reddit user's deliberate joke
    spelling. Both are indexed as names, both share a word with the correct spelling, and both
    disagree about the other word, so the refutation rule read each as a rival entity.
    """
    articles = [make_article(headline)]

    result = validate_summary(f"{written_out} was in the news.", articles)

    assert result.is_safe, f"wrongly flagged: {result.invented_names}"


@pytest.mark.parametrize(
    ("real_name", "blend"),
    [
        # `[VERIFIED]` The near-match threshold has to keep these refuted. Ratios measured:
        # jayson/jaylen 0.667, edwards/davis 0.500, durant/garnett 0.462.
        ("Jaylen Brown", "Jayson Brown"),
        ("Anthony Davis", "Anthony Edwards"),
        ("Kevin Durant", "Kevin Garnett"),
    ],
)
def test_two_different_players_are_not_near_matches(
    make_article: ArticleFactory, real_name: str, blend: str
) -> None:
    """The expensive direction: a fabricated name is built from a *different* real one.

    `[VERIFIED]` This is what bounds the exemption. All three pairs score at or below 0.667,
    while the two spellings that must merge score 0.857 and 0.923.
    """
    articles = [make_article(f"{real_name} spoke to reporters after the game")]

    assert not validate_summary(f"{blend} signed on Sunday.", articles).is_safe


def test_a_near_match_must_not_bridge_names_of_different_lengths(
    make_article: ArticleFactory,
) -> None:
    """Equal length only. A difference in how many words a name has is handled by the subset
    tests, and letting a near-match cross that boundary would blur expansion with substitution.
    """
    articles = [make_article("Karl-Anthony Towns and Julius Randle were traded")]

    assert validate_summary("Anthony Towns was traded.", articles).is_safe
