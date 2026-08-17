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
import unicodedata

from models.schemas import NewsArticle
from processing.names import NameScanner

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
#
# The colon was added 2026-08-17, and it is the same bug a third time. `[VERIFIED]` A dry run
# with the P25 and P26 fixes in place still rejected `Philadelphia Sixers` on two attempts,
# because the batch carried the headline "Report: Sixers hire Tommy Balcetis to front office".
# That was read as the name `{report, sixers}`, which is two words sharing a last word with
# `Philadelphia Sixers` and disagreeing about the other, so it refuted a real team.
#
# P20 was supposed to have handled this, and its fix does not reach here: `_ordinary_words`
# only knows a word is vocabulary if the batch writes it in lower case somewhere, and a
# 12-story batch never wrote "report". `[VERIFIED]` Confirmed by adding one article containing
# "per report" to the same batch, after which the team grounded.
#
# `[VERIFIED]` This is not a rare shape. 61 of 331 live and fixture titles, 18%, open with a
# label and a colon: "Sources:", "NBA odds:", "NBA Power Rankings:", "NBA HOF week:". A colon
# separates a label from what follows, so the run has to end there.
#
# A name *followed* by a colon is still kept, because the run is recorded before it is
# cleared. "Jordan Goodwin: ..." keeps `Jordan Goodwin`, and only the one-word labels are lost.
_SEPARATES_NAMES = ",;:"


# Apostrophe shapes that mean the same thing. `[VERIFIED]` 2026-08-17: the 00:00 run
# rejected `Mike D'Antoni` as invented while lead 3 of that very batch was Yahoo's
# "Honoring new Hall of Fame inductee, former Rockets coach Mike D’Antoni". The feed writes
# U+2019 RIGHT SINGLE QUOTATION MARK; the model writes U+0027 APOSTROPHE. Every comparison
# here is literal string matching, so the two can never meet and a name plainly present in
# the sources is reported as fabricated.
#
# `[INFERRED]` This is invisible precisely because both render identically — reading the log
# beside the feed shows the same characters. It is the fourth false-accusation bug of this
# class, and the first found by an automated check rather than by the operator noticing a
# degraded brief.
_APOSTROPHE_SHAPES = str.maketrans(
    {"’": "'", "‘": "'", "ʼ": "'", "´": "'", "‑": "-", "–": "-", "—": "-"}
)


def _comparable(text: str) -> str:
    """Fold the spellings of one name onto a single form, **for comparison only**.

    Never used for display or for extraction — `_is_name_word` still reads the real Unicode,
    because P13 established that enumerating characters is how this module goes stale. This
    is the opposite operation: it decides whether two spellings *mean* the same name.

    Two classes, both measured across 329 live and fixture articles rather than imagined:

    **Apostrophe and dash shapes.** `[VERIFIED]` U+2019 appears 137 times in that corpus,
    against U+0027 from the model. The 2026-08-17 00:00 run was rejected for
    `Mike D'Antoni` while its own lead 3 read `Mike D’Antoni`.

    **Diacritics.** `[VERIFIED]` Three of the six accented names in that corpus **also appear
    unaccented in it** — `Dončić`/`Doncic`, `Jokić`/`Jokic`, and `Schröder`/`Schroder`, the
    last of those 9 accented against 17 plain. Yahoo prints both spellings of the same player
    in different headlines of one story, so this is not a model quirk to be corrected at the
    prompt: **the sources disagree with themselves.**

    `[INFERRED]` Folding cannot create a false acquittal here in any realistic case, because
    the pairs it merges are the same person by construction. It is the reverse risk that has
    cost this project four briefs: two spellings of one name failing to meet.
    """
    stripped = unicodedata.normalize("NFD", text.translate(_APOSTROPHE_SHAPES))
    return "".join(c for c in stripped if not unicodedata.combining(c))


# The competition's own vocabulary: structures, rounds and honours that exist whether or not
# any outlet mentioned them today. **This is a hardcoded list, which this repository has twice
# refused to write** — rejected for P13, avoided for P20 in favour of the corpus-derived
# `_ordinary_words`. It is written here deliberately and with the operator's approval, because
# the corpus cannot derive it: `_ordinary_words` learns from words the sources write in *lower*
# case, and "Eastern Conference" is capitalised everywhere or absent entirely.
#
# `[VERIFIED]` 2026-08-17, from `logs/sportwire.log`: of 55 distinct names ever rejected as
# invented, exactly two are of this class — `Eastern Conference` (3 rejections) and
# `Western Conference` (3). Both were **correct rejections** by the letter of the rule: the
# replayed batch's 8 leads contain neither phrase. They are not fabrications in any harmful
# sense, and each one cost a whole brief its prose.
#
# **What may enter this list**, so it does not grow by habit: a formal name of an NBA
# structure, competition or honour, which is capitalised when written and cannot be part of a
# person's or a team's name. `[VERIFIED]` Measured against the 31 NBA team names and 311
# distinct proper names in a 203-article live-plus-fixture corpus, the rule below acquits
# **0 teams, 0 people**, and 5 source names — `NBA Finals`, `NBA Draft`, `Eastern Conference`,
# `Eastern Conference Finals`, `WNBA All-Star Weekend`. Re-run
# `scratchpad/p23_vocab.py`-style measurement before adding an entry.
_COMPETITION_VOCABULARY = frozenset(
    {
        # league bodies
        "nba",
        "wnba",
        "nbpa",
        "league",
        # how the league is divided
        "conference",
        "conferences",
        "division",
        "divisions",
        "eastern",
        "western",
        "east",
        "west",
        "atlantic",
        "central",
        "southeast",
        "northwest",
        "pacific",
        "southwest",
        # the competition
        "playoff",
        "playoffs",
        "postseason",
        "finals",
        "semifinals",
        "quarterfinals",
        "play-in",
        "in-season",
        "tournament",
        "cup",
        # the calendar
        "summer",
        "draft",
        "lottery",
        "combine",
        "weekend",
        # honours
        "all-star",
        "all-nba",
        "all-defensive",
        "all-rookie",
        "mvp",
        "rookie",
        "team",
        "game",
    }
)


# Other names for the same team. `[VERIFIED]` 2026-08-17 16:00: the run fell back because all
# three attempts were rejected for `Philadelphia Sixers`, while the feeds wrote `76ers` 11
# times and `Sixers` once. `76ers` starts with a digit, so `_is_name_word` refuses it on
# purpose, which means grounding can never see it. A real team was called invented.
#
# Every group is one team under the names the feeds actually print. Each was counted across
# 331 live and fixture articles, and the counts are why some obvious candidates are absent:
#
#   sixers (4), sixer (1)     against 76ers (51)
#   cavs (13)                 against cavaliers (13)
#   wolves (4), twolves (1)   against timberwolves (11)
#   knick (4)                 against knicks (30)
#   mavs (1)                  against mavericks (2)
#   okc (1)                   against thunder (6)
#
# `[VERIFIED]` Deliberately excluded after measuring, because the short form is an ordinary
# word here rather than a team: `king` occurs 5 times and never means the Sacramento Kings
# (it is LeBron, and a quarterback named Haynes King); `clips` occurs once and means video;
# `net` occurs once and is not the Nets. Aliasing any of those would ground a team on a word
# that has nothing to do with it.
#
# Singular forms only need an entry in one direction. A source writing `Lakers` already
# grounds a summary's `Laker`, because the shorter string occurs inside the longer one. It is
# the other direction that fails, which is why `knick` is listed and `laker` is not.
_TEAM_NAME_GROUPS = (
    frozenset({"76ers", "sixers", "sixer"}),
    frozenset({"cavaliers", "cavs"}),
    frozenset({"timberwolves", "wolves", "twolves", "t-wolves"}),
    frozenset({"mavericks", "mavs"}),
    frozenset({"knicks", "knick"}),
    frozenset({"thunder", "okc"}),
    # `[INFERRED]` Not yet seen in a captured feed, but the same kind of name and unambiguous:
    # none of these is an ordinary English word, so none can ground a team by accident.
    frozenset({"nuggets", "nugs"}),
    frozenset({"grizzlies", "grizz"}),
    frozenset({"pelicans", "pels"}),
    frozenset({"warriors", "dubs"}),
)

_TEAM_ALIASES: dict[str, frozenset[str]] = {
    name: group - {name} for group in _TEAM_NAME_GROUPS for name in group
}


def _appears(word: str, source: str) -> bool:
    """Whether a word, or another name for the same team, occurs in the source text.

    Only teams get this. A player has one surname, so there is nothing to alias, and adding
    people would mean guessing at nicknames rather than reading them off the feeds.
    """
    if word in source:
        return True
    return any(alias in source for alias in _TEAM_ALIASES.get(word, ()))


def _is_competition_term(words: list[str]) -> bool:
    """Whether a name is nothing but the sport's own structural vocabulary.

    **Every** word must be in the list, and that is what bounds the damage. A single word
    from outside it — a city, a surname, a nickname — sends the name back through grounding,
    so `Eastern Conference` is acquitted while `Eastern Conference Lakers` is not. The hole
    this opens is exactly the set of names built only from the words above, and none of them
    can name a person or a team.

    `[UNKNOWN]` What it now misses. `[VERIFIED]` One case, measured 2026-08-17: where the
    sources name only the Western Conference and the model writes `Eastern Conference`, the
    refutation rule *would* have refused it, and placing this check before `_contradicted`
    gives that up. Two reasons it is placed here anyway. First, no such case appears in the
    log — the observed rejections had **neither** conference in their sources. Second, putting
    it after refutation was measured to leave a real case broken: the live corpus writes
    `Eastern Conference Finals`, which refutes a summary's `NBA Finals` under the length rule.
    `[INFERRED]` A wrong conference is also a *claim* error, and P5 already records that this
    module grounds entities rather than claims — so it was never this check's job.
    """
    return bool(words) and all(word in _COMPETITION_VOCABULARY for word in words)


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
    source = _comparable(" ".join(f"{a.title} {a.summary}" for a in articles))
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
    word appears, or ~~the **last** word appears.~~ **either end appears, since 2026-08-17.**
    A name is identified by its last word often enough that the rule worked for a week, but
    the feeds name players by first name constantly, so both ends now count. The refutation
    index keys both ends too, and that pairing is what keeps it safe: see P25 below.

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

    One name never reaches any of this: the sport's own structural vocabulary, which needs no
    source because it is not a claim about anyone. See `_is_competition_term` for what that
    covers and what it costs (TASKS.md P23).
    """
    if _comparable(name).lower() in source_lower:
        return True

    words = _name_words(name)
    if not words:
        return False

    if _is_competition_term(words):
        return True

    # Either end can be the word the sources disagree about, so both are asked.
    if _contradicted(words, source_names, words[-1]) or _contradicted(
        words, source_names, words[0]
    ):
        return False

    normalised_source = _depossess_text(source_lower)
    if all(_appears(word, normalised_source) for word in words):
        return True

    # And either end can be the word that identifies the name. `[VERIFIED]` 2026-08-17
    # (TASKS.md P25): the feeds name players by first name constantly. In the 127 articles
    # captured that day, `Ja` occurs 33 times and `Ja Morant` none, `LeBron` 26 against 15,
    # `Wemby` 4 against none, `Giannis` and `Luka` twice each against none. Grounding on the
    # last word alone means a brief writing the full name is accused of inventing the player
    # it is reporting on, which is how the 08:00 run lost its prose to `LeBron James`.
    #
    # `[INFERRED]` This is the mirror of the bug the last-word rule was added to fix. P11
    # fixed `Knicks` written out as `New York Knicks`, where the last word identifies. Here
    # the first word does, and one rule caused both.
    return _appears(words[-1], normalised_source) or _appears(
        words[0], normalised_source
    )


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
    return [
        cleaned
        for word in _comparable(name).split()
        if (cleaned := _depossess(word.lower()))
    ]


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
                        # Keyed under both ends, because either can be the word that
                        # identifies a person. `[VERIFIED]` 2026-08-17 (TASKS.md P25): keying
                        # only the last word is what let `Anthony Edwards` pass against
                        # sources naming Anthony Davis, once the first word could ground a
                        # name. Indexing both ends closed that at no measured cost, and it
                        # raised blend detection from 65.2% to 87.6% on the P20 population,
                        # because a fabricated first name now has somewhere to be caught.
                        index.setdefault(words[-1], []).append(frozenset(words))
                        index.setdefault(words[0], []).append(frozenset(words))
    return index


def _contradicted(
    words: list[str], source_names: dict[str, list[frozenset[str]]], key: str
) -> bool:
    """Whether every source name sharing `key` disagrees about the rest of this name.

    `key` is the word to look the name up under, and it is always either the first word or
    the last. Passing it in rather than assuming the last word is what lets one function serve
    both ends of a name. See `_grounded` for why both ends are needed (TASKS.md P25).

    "Every" and not "any": a feed carrying both "Jaylen Brown" and "Jayson Tatum" must still
    ground "Jaylen Brown", so one agreeing source name is enough to acquit.

    `[UNKNOWN]` How well this holds on a title-case source. The index reads a name's last
    word, and a headline styled "Jaylen Brown Details Bumpy Celtics Exit" is captured as one
    long name ending in "exit", so it contributes nothing under "brown". The captured feeds
    are sentence case, so this is a latent weakness rather than a current one.
    """
    others = source_names.get(key)
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


# Entities that share an article, used to spot a claim joining two that never met.
#
# `[VERIFIED]` 2026-08-18 (TASKS.md P5), the third delivered instance of this class and the
# first the operator reported the same night. The 00:00 brief said "The Pelicans, who are
# welcoming back star point guard Damian Lillard following his trade from Portland". There was
# no trade. The batch's only Lillard article was "Blazers offseason recap and early season
# preview: Lillard is back but questions remain", whose body reads "With noise outside the
# hardwood growing in Portland, how will the Blazers respond?". He is back with Portland.
#
# Grounding cannot see this and is not meant to. It extracted `Pelicans` and `Damian Lillard`,
# and both are real and both are in the batch. Only the relationship is invented.
#
# `[VERIFIED]` The operator chose on 2026-08-18 to **mark** these rather than reject them:
# rejecting the sentence rejects the summary, and that run would have delivered a headline list
# on all three attempts. So nothing here feeds `is_safe`, and this function is additive by
# design. A sentence it flags is still delivered, with a marker.
#
# Source entities are read with a **one-word** scanner while summary entities keep grounding's
# two-word rule, and that asymmetry is the whole mechanism. `[VERIFIED]` Measured while
# building it: with a two-word scanner on both sides, `Trendon Watford signs with the Pelicans`
# contributes no `pelicans` at all, because there it is a lone capitalised word. The true
# sentence about Watford joining the Pelicans was then flagged, and the check was worthless.
_SOURCE_ENTITIES = NameScanner(
    min_words=1, break_run_on_punctuation=False, separators=_SEPARATES_NAMES
)


def _entity_keys(text: str, scanner: NameScanner | _ProperNames) -> list[str]:
    """One key per entity in `text`: the last word of each name, which identifies it.

    `[VERIFIED]` Keying on every word instead flags true sentences, because a brief writes
    names out in full where the feeds do not. `New Orleans Pelicans` yields `new` and
    `orleans`, which co-occur with nothing since no source spells the city out, and
    `Portland Trail Blazers` yields `trail` for the same reason. Both true sentences were
    flagged before this narrowed to the identifying word.
    """
    keys: list[str] = []
    for sentence in _SENTENCE_BREAK.split(text):
        for name in scanner.findall(sentence):
            # Trimmed first, so a sentence opener cannot disguise what the name is.
            # `[VERIFIED]` 2026-08-18: "In NBA news, Trendon Watford has signed..." extracts
            # `In NBA`, whose words are `in` and `nba`. The vocabulary test below needs every
            # word to be vocabulary and `in` is not, so `nba` survived as an entity, shared no
            # article with `watford`, and flagged a true sentence twice over. Stripping the
            # opener leaves `NBA`, which the vocabulary test then removes.
            words = _name_words(_trim_name_for_reporting(name.strip(" .,;:")))
            if not words:
                continue
            # The sport's own vocabulary is not an entity and cannot hold a relationship, so
            # its co-occurrence means nothing. `[VERIFIED]` 2026-08-18: without this the
            # opener "In NBA news, Trendon Watford has signed..." keys on `nba`, which shares
            # no article with `watford`, and a plainly true sentence was flagged. This was
            # missed on the first measurement because that was run on the sentence with the
            # opener already stripped, which is a reminder to measure the real string.
            if _is_competition_term(words):
                continue
            if words[-1] not in keys:
                keys.append(words[-1])
    return keys


def _entity_pairs(articles: list[NewsArticle]) -> set[tuple[str, str]]:
    """Every pair of entities that appears together inside one article.

    Built per article rather than over the joined text, for the reason
    `_index_source_names` gives: one article's title running into the next one's summary would
    manufacture a co-occurrence that no source actually reports.
    """
    pairs: set[tuple[str, str]] = set()
    for article in articles:
        keys = _entity_keys(f"{article.title} {article.summary}", _SOURCE_ENTITIES)
        for first in keys:
            for second in keys:
                pairs.add((first, second))
    return pairs


def unsupported_sentences(summary: str, articles: list[NewsArticle]) -> list[str]:
    """Sentences naming two entities that never share a source article.

    Not a verdict. `is_safe` ignores this entirely, and a flagged sentence is still delivered
    with a marker, because the operator chose visibility over a stricter check (P5).

    `[INFERRED]` Reading a co-occurrence as permission rather than proof is what keeps this
    usable. Two entities in one article does not establish that any particular claim about
    them is true; two entities that never met establishes that the sources cannot have
    reported a relationship between them, which is the narrower and checkable thing.
    """
    pairs = _entity_pairs(articles)
    flagged: list[str] = []
    for sentence in _SENTENCE_BREAK.split(summary):
        keys = _entity_keys(sentence, _PROPER_NAME)
        if any(
            (first, second) not in pairs
            for index, first in enumerate(keys)
            for second in keys[index + 1 :]
        ):
            flagged.append(sentence.strip())
    return flagged


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
