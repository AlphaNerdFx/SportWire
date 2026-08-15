"""Checks generated text against its sources, so fabrication fails closed.

The premise of this module is that the model **will** invent things, and that the system must
be reliable anyway. `[VERIFIED]` ADR-012: every local model tested fabricated names and
figures on real data, and the substitutions were systematic rather than random — a less famous
name replaced by a more famous one from the same organisation, because the training prior beat
the prompt context.

That failure is detectable mechanically. A proper name in a summary that appears nowhere in
the source articles was invented, and so was a dollar figure. Neither requires understanding
the text.

This is the same principle as the clean virtual environment and the `_fetch`/`fetch` split:
**a mechanism that cannot be forgotten beats trusting something to behave.** It does not make
the model truthful. It makes untruth fail closed, so a rejected summary degrades to the
headline list rather than reaching a phone.
"""

from __future__ import annotations

import logging
import re

from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

# Punctuation that belongs inside a name — "De'Aaron", "Karl-Anthony", "Jr." — as opposed to
# punctuation that merely follows one.
_INSIDE_A_NAME = "'’.-"
_TRAILING_PUNCTUATION = ',;:!?()[]{}"“”«»…'

# Punctuation that **separates two names** rather than merely following one. Stripping it is
# not enough — the run has to end there too.
#
# `[VERIFIED]` 2026-08-15: the CBS fixture carries "Cavaliers, Heat, Warriors and Wolves, so
# how do our NBA…". Every comma was stripped as trailing punctuation and the capitalised run
# walked straight through them, producing the single "name" `Cavaliers Heat Warriors` — a
# list of four teams read as one entity.
#
# `[VERIFIED]` That junk then did real damage through the refutation rule, which asks whether
# any source name shares a last word and disagrees about the rest. Indexed under "warriors",
# `{cavaliers, heat, warriors}` disagrees with `{golden, state, warriors}`, so **"Golden State
# Warriors" was refused as invented** — and it is one of the names the 2026-08-15 16:00 run
# was rejected for. Measured across the fixtures: 3 of 17 teams mentioned by short name were
# refused when a summary expanded them to the full name, which is ordinary phrasing rather
# than fabrication.
_SEPARATES_NAMES = ",;"


def _is_name_word(word: str) -> bool:
    """Whether a word could be part of a name: a capital, then letters.

    **This asks Python, and enumerates nothing.** `str.isupper` and `str.isalpha` read the
    Unicode character database, so every alphabet is covered without this module holding a
    table that goes stale.

    `[VERIFIED]` 2026-08-14 that matters, and a character range cannot substitute for it.
    The extractor was previously `[A-Z][a-zà-ÿ'’.-]*`, which produced:

        "Luka Dončić"           -> "Luka Don"
        "Nikola Jokić"          -> "Nikola Joki"
        "Kristaps Porziņģis"    -> "Kristaps Porzi"
        "LeBron James"          -> nothing at all
        "DeMar DeRozan"         -> nothing at all

    Widening the range to Latin Extended-A fixed the first three and still failed
    "Alperen Şengün", because `Ş` is an uppercase letter outside `A-Z` and the pattern
    required `[A-Z]` to start a word. `[INFERRED]` Every enumerated range fails on the next
    name from the next alphabet; the NBA acquires those faster than this file is edited.

    Digits keep "76ers" and "2026-27" out, since neither starts with an uppercase letter.
    """
    return (
        bool(word)
        and word[0].isupper()
        and all(ch.isalpha() or ch in _INSIDE_A_NAME for ch in word)
    )


class _ProperNames:
    """Runs of two or more consecutive capitalised words: people and organisations.

    `[VERIFIED]` This is what caught "Devin Booker", "Leon Rose", "Steve Nash", "Gabe
    Vincent" and "Romeo Langford" — every fabricated name measured during the model
    evaluation. Exposes `findall` because that is the one method the rest of this module
    ever called on the compiled pattern it replaces.
    """

    def findall(self, text: str) -> list[str]:
        names: list[str] = []
        run: list[str] = []
        for token in text.split():
            # `[VERIFIED]` 2026-08-14 **trailing only, never leading**, and both bugs that
            # proved it came from one line. Stripping a leading quote turned
            # `a Sixer: "I'm still processing it"` into the name `Sixer I'm` — a false
            # accusation on a real fixture title — because the quote is the only thing
            # separating the two words. The same erased boundary welded longer runs
            # together elsewhere, and one of those runs was a set large enough to acquit
            # the invented "LeBron Tatum" by superset. Opening punctuation *is* the
            # boundary; removing it removes the evidence.
            word = token.rstrip(_TRAILING_PUNCTUATION)
            if _is_name_word(word):
                run.append(word)
                # A comma ends the name it follows. Checked on what was *stripped*, so
                # `Leonard,` and `Leonard,"` and `Leonard",` all end the run alike.
                if any(ch in _SEPARATES_NAMES for ch in token[len(word) :]):
                    if len(run) >= 2:
                        names.append(" ".join(run))
                    run = []
                continue
            if len(run) >= 2:
                names.append(" ".join(run))
            run = []
        if len(run) >= 2:
            names.append(" ".join(run))
        return names


_PROPER_NAME = _ProperNames()

# Names are matched per sentence, never across one. `[VERIFIED]` 2026-08-08: matching over
# the whole summary treated "...with the Mavericks. LeBron James chose Philadelphia" as a
# single name, "Mavericks. Le", and rejected a summary in which every fact was correct. A
# validator that rejects good output silently disables the feature it was meant to protect.
#
# The closing-punctuation class is not decoration. `[VERIFIED]` 2026-08-15 the same bug
# returned through it: the 16:00 brief fell back to the headline list, and attempt 3 was
# rejected for the invented name `Hollywood Ending. Meanwhile Charles Oakley's`. That is two
# real names welded together, because `(?<=[.!?])\s+` alone requires whitespace **immediately**
# after the terminator — and a sentence ending in a quotation reads `Ending.” Meanwhile`, where
# the next character is a quote mark. No split happened, `.` is a legal character inside a name
# (`J.R. Smith`), and the run walked straight into the following sentence.
#
# `[INFERRED]` This domain makes that shape common rather than exotic: the summariser works
# from headlines that quote players, so sentences ending in `.”` or `.")` are routine. A
# phantom name can never be grounded in any source, so a single one fails the whole summary
# and costs the brief its prose — exactly what the 2026-08-08 comment above warned about,
# recurring through the case it did not cover.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"'”’»）)\]]*\s+")

# Money and counts. `[VERIFIED]` mistral:7b invented "$3.3M" for a contract whose value the
# source never stated.
_FIGURE = re.compile(
    r"\$\s?[\d,.]+\s?(?:million|billion|[MBK])?|\b\d[\d,.]*\s?(?:million|billion)\b",
    re.IGNORECASE,
)

# Openers a model produces despite being told not to. Not grounds for rejection — the summary
# is still true — but worth counting so a persistently ignored instruction is visible.
_PREAMBLE = re.compile(
    r"^(here (is|are)|in (nba|the nba) news|the nba (offseason|season)\b)",
    re.IGNORECASE,
)


class ValidationResult:
    """Whether a summary is safe to send, and what was wrong if not."""

    def __init__(
        self,
        invented_names: list[str],
        invented_figures: list[str],
        has_preamble: bool,
    ) -> None:
        self.invented_names = invented_names
        self.invented_figures = invented_figures
        self.has_preamble = has_preamble

    @property
    def is_safe(self) -> bool:
        """True when nothing in the summary was fabricated.

        A preamble does not fail validation: it is a style problem, not a truth problem, and
        rejecting a factually correct summary over its opening sentence would trade something
        real for something cosmetic.
        """
        return not self.invented_names and not self.invented_figures

    def describe(self) -> str:
        """One line naming what was fabricated, for the log."""
        parts = []
        if self.invented_names:
            parts.append(f"invented names: {', '.join(self.invented_names)}")
        if self.invented_figures:
            parts.append(f"invented figures: {', '.join(self.invented_figures)}")
        if self.has_preamble:
            parts.append("preamble present")
        return "; ".join(parts) or "clean"


def validate_summary(summary: str, articles: list[NewsArticle]) -> ValidationResult:
    """Check every proper name and figure in `summary` against the source articles.

    Matching is deliberately generous — a claim is only reported as invented when neither the
    whole phrase nor **any** of its words appear in the sources. `[INFERRED]` A false accusation
    costs a correct summary, while a missed fabrication reaches a phone; but over-strict
    matching would reject on ordinary rephrasing ("the Suns" → "Phoenix"), making the check
    useless in practice. The measured failures are wholesale substitutions, not paraphrases,
    and those are caught either way.
    """
    source = " ".join(f"{a.title} {a.summary}" for a in articles)
    source_lower = source.lower()
    source_names = _index_source_names(articles)

    candidates: list[str] = []
    for sentence in _SENTENCE_BREAK.split(summary):
        for name in _PROPER_NAME.findall(sentence):
            candidates.append(_trim_name_for_reporting(name.strip(" .,;:")))

    invented_names = [
        name
        for name in dict.fromkeys(candidates)
        if name and not _grounded(name, source, source_lower, source_names)
    ]

    invented_figures = [
        figure
        for figure in dict.fromkeys(_FIGURE.findall(summary))
        if not _figure_grounded(figure, source_lower)
    ]

    return ValidationResult(
        invented_names=invented_names,
        invented_figures=invented_figures,
        has_preamble=bool(_PREAMBLE.match(summary.strip())),
    )


# Words that are only capitalised because a sentence started with them. `[VERIFIED]`
# 2026-08-11 a live summary was rejected for the invented name "In Detroit" — the sentence
# began "In Detroit, ...", and the pattern swept the preposition into the name.
#
# ~~Every rejection costs a correct summary, so this specific artifact is worth removing.~~
# **Corrected 2026-08-13 (TASKS.md P6).** `[VERIFIED]` by mutation: disabling the trim below
# changes **no** pass/fail outcome in the test suite. `[INFERRED]` It cannot, by construction
# — it strips only a name's *first* word, while `_grounded` decides on the *last*, so a
# grounded name stays grounded and an ungrounded one stays ungrounded either way. Commit
# `7323396` (last-word grounding, 2026-08-12) made this redundant as a correctness mechanism
# one day after `c522d8e` added it; both were fixing the same live symptom, so neither had
# reason to look at the other.
#
# It is kept for **diagnosis**: a log reading `invented names: Portland` points at the real
# problem, while `In Portland` sends the reader after a preposition. Asserted in
# `tests/test_validate.py::test_sentence_initial_preposition_is_stripped_from_the_reported_name`.
_SENTENCE_STARTERS = frozenset(
    {
        "in",
        "on",
        "at",
        "the",
        "a",
        "an",
        "and",
        "but",
        "for",
        "with",
        "after",
        "before",
        "meanwhile",
        "elsewhere",
        "also",
        "however",
        "while",
        "as",
        "by",
        "from",
        "to",
        "of",
        "this",
        "that",
        "these",
        "those",
        "his",
        "her",
        "their",
    }
)


def _trim_name_for_reporting(name: str) -> str:
    """Strip a leading sentence-starter, so "In Detroit" is *reported* as "Detroit".

    **Verdict-neutral.** `[VERIFIED]` This cannot change whether a name is judged invented —
    see the note above `_SENTENCE_STARTERS`. It exists so the log names the thing that is
    actually ungrounded.

    Only the first word, and only when something remains — "The Athletic" keeps its article
    if stripping would leave nothing meaningful.
    """
    parts = name.split()
    if len(parts) > 1 and parts[0].lower() in _SENTENCE_STARTERS:
        return " ".join(parts[1:])
    return name


def _depossess(word: str) -> str:
    """Strip a trailing possessive so "Leonard's" compares equal to "Leonard".

    `[VERIFIED]` 2026-08-08: without this the validator rejected a live summary for the
    invented name "Kawhi Leonard's" — while the sources were almost entirely about Kawhi
    Leonard. A validator that rejects grounded text disables the feature it protects, so
    false positives are the expensive kind of error here.
    """
    return re.sub(r"['’]s?$", "", word.strip(" .,;:"))


def _grounded(
    name: str,
    source: str,
    source_lower: str,
    source_names: dict[str, list[frozenset[str]]],
) -> bool:
    """Whether a proper name is traceable to the sources.

    Three ways to be grounded, in increasing generosity: the whole phrase appears, every
    word appears, or the **last** word appears.

    `[VERIFIED]` 2026-08-11 the last-word rule is what makes this usable. Requiring every
    word rejected three live summaries for names that were entirely correct — "New York
    Knicks" where the source said "Knicks", "Oklahoma City Thunder" where it said "Thunder",
    and "Anthony Towns" where it said "Karl-Anthony Towns". Expanding a team's city or
    shortening a hyphenated first name is good writing, not invention.

    ~~`[INFERRED]` The failure mode it *would* miss is a wrong first name beside a right
    surname, which is a smaller error than inventing a person.~~ **Corrected 2026-08-14.**
    `[VERIFIED]` That failure mode shipped, and it is not a smaller error. The 16:00 brief
    reached the operator's phone saying *"January will see Giannis Antetokounmpo and Jayson
    Brown reunions"*. There is no Jayson Brown; the model fused Jayson Tatum and Jaylen
    Brown, who appear in the same feed because they were teammates. Blending two real
    players invents a person just as surely as "Joe Dumars" did, and it passed on attempt 1.

    So the two generous rules are now **refutable**. A summary name is refused when some
    name *in the sources* shares its identifying last word and disagrees with it about the
    rest — see `_contradicted`. `[INFERRED]` This separates the two classes exactly, because
    every legitimate case above is one source name expanded or contracted, while a blend is
    by construction drawn from two and is a subset of neither.

    The verbatim rule stays unconditional and must come first: sources containing both
    "Bronny James" and "LeBron James" would otherwise refute each other.
    """
    if name.lower() in source_lower:
        return True

    words = _name_words(name)
    if not words:
        return False

    if _contradicted(words, source_names):
        return False

    normalised_source = _depossess_text(source_lower)
    if all(word in normalised_source for word in words):
        return True

    return words[-1] in normalised_source


def _name_words(name: str) -> list[str]:
    """A name's comparable words: lowercased, de-possessed.

    ~~Hyphens are split too, so "Anthony Towns" stays recognisable as a contraction of
    "Karl-Anthony Towns".~~ **Removed 2026-08-14 before it ever shipped.** `[VERIFIED]`
    Splitting on hyphens changed **0 of 5,530** verdicts measured across the committed
    fixtures, and it cannot: `_PROPER_NAME`'s character class does not cross an internal
    capital, so "Karl-Anthony Towns" is already truncated to "Anthony Towns" by the time
    this function sees it. The only hyphenated tokens the pattern really emits are trailing
    artifacts — `Way-`, `Ballmer-linked`.

    `[INFERRED]` Kept out for the reason P6 was recorded: a mechanism that cannot change a
    verdict reads as protection, survives review, and costs a mutation campaign to disprove.
    This is also a re-diagnosis of the 2026-08-11 "Anthony Towns" bug — the model was not
    shortening a hyphenated first name, the **validator** was truncating it and then failing
    to ground its own truncation.
    """
    return [cleaned for word in name.split() if (cleaned := _depossess(word.lower()))]


def _ordinary_words(articles: list[NewsArticle]) -> frozenset[str]:
    """Words the sources also write in lower case — vocabulary, not parts of a name.

    **The corpus decides this, not a list**, and that is the whole point (TASKS.md P20
    option (b)). `[VERIFIED]` 2026-08-15 the alternative was a hand-written stop-word list
    like `cluster.py`'s `_NOT_NAMES`; measured side by side it left `Miami Heat` still
    refused, while this leaves none.

    `[INFERRED]` The reasoning is that capitalisation is only evidence of a name when the
    word is not *also* used as ordinary English in the same batch. "The", "Inside" and
    "Retired" appear in lower case constantly; "Lakers" and "Westbrook" never do.

    `[VERIFIED]` The obvious objection was that NBA teams are named after common words —
    `Heat`, `Magic`, `Jazz`, `Kings`, `Thunder`, `Bucks` — so this could strip the very names
    it must keep. Measured across the committed fixtures: **none of the 28 team words appears
    in lower case**, and all seven curated real-player blends are still caught.
    `[UNKNOWN]` Whether that holds on every live batch. `[INFERRED]` The failure direction is
    the safe one: stripping a word shortens a *refuter* and can only make this rule accuse
    less, never more, so the cost of being wrong is a missed blend rather than a lost brief.
    """
    ordinary: set[str] = set()
    for article in articles:
        for field in (article.title, article.summary):
            for token in field.split():
                if not token[:1].islower():
                    continue
                if cleaned := _depossess(token.strip(_TRAILING_PUNCTUATION).lower()):
                    ordinary.add(cleaned)
    return frozenset(ordinary)


def _index_source_names(articles: list[NewsArticle]) -> dict[str, list[frozenset[str]]]:
    """The sources' own proper names, keyed by the last word that identifies them.

    Built per field rather than from the joined blob so that a title running into the next
    article's summary cannot manufacture a name that spans them.

    `[VERIFIED]` 2026-08-15: ordinary vocabulary is dropped from each name before indexing,
    because a headline's capitalisation is not evidence. `Inside Lakers mega-deal` was
    indexed as the name `{inside, lakers}`, and `_contradicted` then read it as an entity
    disagreeing with `Los Angeles Lakers` — refusing a real team on the strength of a
    headline's first word. Measured: **2 of 11** teams named by their short form were refused
    when a summary expanded them, and **0 of 11** after this.
    """
    ordinary = _ordinary_words(articles)
    index: dict[str, list[frozenset[str]]] = {}
    for article in articles:
        for field in (article.title, article.summary):
            for sentence in _SENTENCE_BREAK.split(field):
                for name in _PROPER_NAME.findall(sentence):
                    words = [
                        word
                        for word in _name_words(name.strip(" .,;:"))
                        if word not in ordinary
                    ]
                    # One word left is not a disagreement about anything: the index exists to
                    # answer "who else shares this last name", and a bare surname agrees with
                    # every expansion of it.
                    if len(words) >= 2:
                        index.setdefault(words[-1], []).append(frozenset(words))
    return index


def _contradicted(
    words: list[str], source_names: dict[str, list[frozenset[str]]]
) -> bool:
    """Whether every source name sharing this last word disagrees about the rest.

    "Every" and not "any": a feed carrying both "Jaylen Brown" and "Jayson Tatum" must still
    ground "Jaylen Brown", so one agreeing source name is enough to acquit.

    `[UNKNOWN]` How well this holds on a title-case source. The index reads a name's last
    word, and a headline styled "Jaylen Brown Details Bumpy Celtics Exit" is captured as one
    long name ending in "exit", so it contributes nothing under "brown". The captured feeds
    are sentence case, so this is a latent weakness rather than a current one.
    """
    others = source_names.get(words[-1])
    if not others:
        return False

    mine = frozenset(words)

    # A source name may only refute one at least as long as itself.
    #
    # `[VERIFIED]` 2026-08-15 (TASKS.md P20). `Los Angeles Lakers` was refused as invented
    # because the sources carried `Inside Lakers mega-deal` and the book title `the LeBron
    # Lakers`. Both are two words, both share the last word, and neither agrees about the
    # rest — so the rule convicted a real team on the strength of a headline's first word.
    #
    # `[INFERRED]` The asymmetry is the point, and it follows from what this rule is for. A
    # **longer** summary name sharing a last word with a **shorter** source name is an
    # expansion — `Lakers` written out as `Los Angeles Lakers` — which is writing, not
    # invention. An **equal-length** disagreement is a substitution, and substitution is the
    # failure ADR-012 actually measured: a less famous name replaced by a more famous one.
    # Nothing here weakens that case, because a blend is the same length as the name it
    # displaces.
    #
    # `[VERIFIED]` Measured against the alternative of requiring a refuter to occur twice,
    # which also fixes the Lakers case: this keeps all seven curated real-player blends,
    # while the occurrence rule loses `LeBron Tatum`. Fixture teams refused when expanded
    # stay at 0 of 11.
    #
    # `[UNKNOWN]` A fabrication *longer* than the name it displaces — `Jayson Marcus Brown`
    # against a source's `Jaylen Brown` — is no longer refuted. No such case has been
    # observed; the measured failures swap words rather than add them.
    eligible = [other for other in others if len(other) >= len(mine)]
    if not eligible:
        return False

    return all(not (mine <= other or other <= mine) for other in eligible)


def _depossess_text(text: str) -> str:
    """Strip possessives throughout a body of text, for comparison against names."""
    return re.sub(r"['’]s?\b", "", text)


def _figure_grounded(figure: str, source_lower: str) -> bool:
    """Whether a monetary or numeric claim appears in the sources.

    Compared on digits alone, so "$52.2 million" is grounded by a source writing "$52.2M".
    Formatting differs constantly between outlets; the number is what must be true.
    """
    digits = re.sub(r"[^\d]", "", figure)
    if not digits:
        return True

    return digits in re.sub(r"[^\d]", "", source_lower)
