"""One scanner for proper names, with the policy left to the caller.

**Not yet wired into anything.** `validate.py` and `cluster.py` still carry their own
extractors; this module exists so the difference between them can be measured before either
is changed. See `TASKS.md` P17.

Two modules in this pipeline pull names out of text, and it is tempting to call that a
`CLAUDE.md` §5 duplication and merge them. `[VERIFIED]` Measuring says that would break
clustering: across 101 fixture and live articles the two extractors disagree on 52 titles,
and the disagreement is not a bug in either one. They ask different questions.

- `validate.py` asks **"is this string backed by the sources?"** A greedy run is safe there,
  because the run is then checked as a whole and by subset. It wants `Cavs Celtics` from
  "Cavs, Celtics" — worst case the check is stricter than needed.
- `cluster.py` asks **"which entity does this title name?"** A greedy run is useless there,
  because `Cavs Celtics` is not an entity and will never match another article's fingerprint.
  It needs the comma to end the name, and it needs single words: `Clippers` and `Ballmer`
  are exactly the markers that pair two reports of one story.

So the duplication is real but it is in the **scanner** — what counts as an uppercase letter,
in any alphabet — and not in the **policy**. This module holds the scanner. The policy is two
flags, and both callers keep their own.

`[VERIFIED]` The scanner is `validate.py`'s, character for character, because that one has
survived six mutations and two live bugs (P13). `GROUNDING` below is asserted in the test
suite to be output-identical to it, which is what makes swapping `validate.py` over to this
module a no-op rather than a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass

# Punctuation that belongs inside a name — "De'Aaron", "Karl-Anthony", "Jr." — as opposed to
# punctuation that merely follows one.
_INSIDE_A_NAME = "'’.-"
_TRAILING_PUNCTUATION = ',;:!?()[]{}"“”«»…'


def is_name_word(word: str) -> bool:
    """Whether a word could be part of a name: a capital, then letters.

    **This asks Python, and enumerates nothing.** `str.isupper` and `str.isalpha` read the
    Unicode character database, so every alphabet is covered without this module holding a
    table that goes stale.

    `[VERIFIED]` 2026-08-14 that matters, and a character range cannot substitute for it. The
    range this replaces produced `Luka Don` for "Luka Dončić", `Kristaps Porzi` for "Kristaps
    Porziņģis", and nothing at all for "LeBron James" or "DeMar DeRozan". Widening it to Latin
    Extended-A still failed "Alperen Şengün", because `Ş` is an uppercase letter outside `A-Z`.
    `[INFERRED]` Every enumerated range fails on the next name from the next alphabet; the NBA
    acquires those faster than this file is edited.

    `[VERIFIED]` **"76ers" and "2026-27" are excluded by the all-letters test, not by the
    capital.** Allowing a digit to start a word is a *provably equivalent* mutation — it
    changes no output, because a leading digit then fails `isalpha()` inside `all()` a
    character later. Mutation testing surfaced this on 2026-08-15; the previous wording
    credited the capital check with work the all-letters test was doing, which is the same
    shape as P6 and P7. What `isupper` actually excludes is a **lowercase** word, and that is
    what stops "the", "signed" and "with" from joining a name.
    """
    return (
        bool(word)
        and word[0].isupper()
        and all(
            character.isalpha() or character in _INSIDE_A_NAME for character in word
        )
    )


@dataclass(frozen=True)
class NameScanner:
    """Pulls runs of capitalised words out of text, under one caller's policy.

    `min_words` — how many capitalised words in a row make a name. Two is right for
    grounding: a lone capitalised word is usually a sentence opener or a common noun, and
    treating it as a name produces false accusations. One is right for clustering, where
    `Beal` and `Daktronics` are the whole point.

    `break_run_on_punctuation` — whether punctuation *after* a word ends the name. False lets
    "Cavs, Celtics" become one name; True makes it two. `[INFERRED]` The right answer depends
    entirely on what the caller does with the result, which is why it is a flag and not a
    decision made here.
    """

    min_words: int = 2
    break_run_on_punctuation: bool = False
    # Characters that end a run even when `break_run_on_punctuation` is False, because they
    # separate two names rather than trailing one. `[VERIFIED]` 2026-08-15: without this,
    # "Cavaliers, Heat, Warriers and Wolves" scans as the single name `Cavaliers Heat
    # Warriors`, which then refuted the real "Golden State Warriors" through the refutation
    # rule and cost a live brief its prose.
    separators: str = ""

    def findall(self, text: str) -> list[str]:
        """Every name-shaped run in `text`, in the order it appears."""
        names: list[str] = []
        run: list[str] = []

        def flush() -> None:
            if len(run) >= self.min_words:
                names.append(" ".join(run))
            run.clear()

        for token in text.split():
            # `[VERIFIED]` 2026-08-14 **trailing only, never leading**, and both bugs that
            # proved it came from one line. Stripping a leading quote turned
            # `a Sixer: "I'm still processing it"` into the name `Sixer I'm` — a false
            # accusation on a real fixture title — because the quote is the only thing
            # separating the two words. The same erased boundary welded longer runs together
            # elsewhere, and one of those runs was large enough to acquit the invented
            # "LeBron Tatum" by superset. Opening punctuation *is* the boundary.
            word = token.rstrip(_TRAILING_PUNCTUATION)
            if not is_name_word(word):
                flush()
                continue

            run.append(word)

            # The word still counts; what the punctuation ends is the *run* after it.
            trailing = token[len(word) :]
            ends_the_run = (self.break_run_on_punctuation and trailing) or any(
                ch in self.separators for ch in trailing
            )
            if ends_the_run:
                flush()

        flush()
        return names


# Runs of two or more, welded across punctuation except the separators. `[VERIFIED]` Asserted
# output-identical to `validate._PROPER_NAME` over every fixture, so adopting it there changes
# no verdict — and `separators` is part of that equivalence rather than an improvement on it:
# the comma rule landed in `validate.py` first, as a live bug fix, and this preset tracks it.
GROUNDING = NameScanner(min_words=2, break_run_on_punctuation=False, separators=",;")

# Single words count and punctuation ends a name — the shape `cluster.py` needs.
#
# **Measured, and NOT ready to adopt.** `[VERIFIED]` Against `cluster._names` over the 76
# fixture articles it gains 25 names (`LeBron`, `LeBron James`, `Luka Dončić’s`, `LA
# Clippers`) and loses 28, including bare `Clippers`, `Ballmer`, `Warriors` and
# `Russell Westbrook`. Losing those would be a worse regression than the camelCase blindness
# it fixes, because they are exactly the markers that pair two reports of one story.
#
# `[VERIFIED]` Three causes were identified and closing them is a losing game: `cluster.py`
# additionally rejects ALL-CAPS tokens (`MVP` breaks a run there, welds one here), excludes
# the curly apostrophe from a name (`Clippers’` → `Clippers`), and excludes the hyphen
# (`Ballmer-linked` → `Ballmer`). Fixing all three narrows the gap to 9 gained / 16 lost —
# and introduces new mismatches of its own (`NBA's` starts matching, `Ballmer-linked` welds).
#
# `[INFERRED]` The conclusion is that cluster's tokenizer is an accumulated pile of specifics
# rather than a policy, so converging on it by adding flags here trades one silent grouping
# change for another. **The scanner is shareable; this policy is not, yet.** Adopting it needs
# the before/after grouping measurement P17 asks for — today's baseline is 76 articles → 68
# stories, 6 multi-article — and that is a decision, not a refactor.
CLUSTERING = NameScanner(min_words=1, break_run_on_punctuation=True)
