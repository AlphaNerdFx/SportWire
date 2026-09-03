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

import re
from dataclasses import dataclass

# Punctuation that belongs inside a name — "De'Aaron", "Karl-Anthony", "Jr." — as opposed to
# punctuation that merely follows one.
_INSIDE_A_NAME = "'’.-"
_POSSESSIVE = re.compile(r"['\u2019]s?$")

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
    # Whether a trailing possessive ends the run. `[VERIFIED]` 2026-08-26: ESPN writes
    # "Panthers' Canales" and "Vikings' Jeshaun Jones", and welding those into one name gave
    # the refutation rule a fake entity that refused the real team. Off by default because
    # clustering has not been shown to need it, and changing how stories group is a separate
    # question with its own evidence. See P48.
    possessive_ends_run: bool = False

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
            ends_the_run = (
                (self.break_run_on_punctuation and trailing)
                or any(ch in self.separators for ch in trailing)
                or (self.possessive_ends_run and bool(_POSSESSIVE.search(word)))
            )
            if ends_the_run:
                flush()

        flush()
        return names


# Runs of two or more, welded across punctuation except the separators. `[VERIFIED]` Asserted
# output-identical to `validate._PROPER_NAME` over every fixture, so adopting it there changes
# no verdict — and `separators` is part of that equivalence rather than an improvement on it:
# the comma rule landed in `validate.py` first, as a live bug fix, and this preset tracks it.
# `separators` gained the colon on 2026-08-17, in step with `validate._SEPARATES_NAMES`. The
# test that asserts these two agree is what caught the drift, on the real title "Sources:
# Knicks executive Rosas leaving team", which the old rule read as the name `Sources Knicks`.
GROUNDING = NameScanner(
    min_words=2,
    break_run_on_punctuation=False,
    separators=",;:",
    possessive_ends_run=True,
)

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
TEAM_NAME_GROUPS = (
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

TEAM_ALIASES: dict[str, frozenset[str]] = {
    name: group - {name} for group in TEAM_NAME_GROUPS for name in group
}


def canonical_team(word: str) -> str:
    """One agreed spelling for a team, so two modules do not disagree about the Wolves.

    `[VERIFIED]` 2026-08-27 this is why it moved out of `validate.py`. A brief said Kuminga
    signed with the Timberwolves and then said the Wolves had added him, because clustering
    treated "Wolves" and "Timberwolves" as different subjects and handed the summarizer the
    same signing five times over. The validator already knew they were one team; clustering
    could not see the table because it was private to another module.

    Returns the word unchanged when it names no team, so callers can apply it to everything.
    """
    lowered = word.lower()
    group = TEAM_ALIASES.get(lowered)
    if group is None:
        return word
    return min({lowered, *group})


# Team nicknames, split by league. `[VERIFIED]` 2026-09-03 this moved here from
# `processing/validate.py`, where it was a private flat set of 62 commented `# NBA` and
# `# NFL` but not keyed by either. The move is the same one `canonical_team` made and for the
# same reason: a table that two modules need cannot stay private to one of them.
#
# `[INFERRED]` Split rather than moved whole, because the caller that needed it needs to ask
# "is this word one of *this* league's teams", and a flat set cannot answer that. The union is
# published too, so nothing that only wanted "is this a team at all" has to change.
NBA_TEAM_NICKNAMES = frozenset(
    {
        "hawks",
        "celtics",
        "nets",
        "hornets",
        "bulls",
        "cavaliers",
        "mavericks",
        "nuggets",
        "pistons",
        "warriors",
        "rockets",
        "pacers",
        "clippers",
        "lakers",
        "grizzlies",
        "heat",
        "bucks",
        "timberwolves",
        "pelicans",
        "knicks",
        "thunder",
        "magic",
        "76ers",
        "suns",
        "blazers",
        "kings",
        "spurs",
        "raptors",
        "jazz",
        "wizards",
    }
)

NFL_TEAM_NICKNAMES = frozenset(
    {
        "cardinals",
        "falcons",
        "ravens",
        "bills",
        "panthers",
        "bears",
        "bengals",
        "browns",
        "cowboys",
        "broncos",
        "lions",
        "packers",
        "texans",
        "colts",
        "jaguars",
        "chiefs",
        "raiders",
        "chargers",
        "rams",
        "dolphins",
        "vikings",
        "patriots",
        "saints",
        "giants",
        "jets",
        "eagles",
        "steelers",
        "49ers",
        "seahawks",
        "buccaneers",
        "titans",
        "commanders",
    }
)

TEAM_NICKNAMES = NBA_TEAM_NICKNAMES | NFL_TEAM_NICKNAMES

TEAM_NICKNAMES_BY_LEAGUE: dict[str, frozenset[str]] = {
    "NBA": NBA_TEAM_NICKNAMES,
    "NFL": NFL_TEAM_NICKNAMES,
}


# Words that name a sport this project does not cover. `[VERIFIED]` 2026-09-03 this exists
# because the basketball brief delivered hockey: "Cale Makar has signed an 8-year NHL
# extension with the Colorado Avalanche" went to the phone in an NBA brief on 2026-08-28,
# alongside a Canucks item and one about the Cowboys. The feeds are league-scoped by URL and
# not by content, so `https://sports.yahoo.com/nba/rss/` carries hockey, baseball and college
# stories, and nothing downstream asked what sport an item was about.
#
# **Every word here is checked against the nickname tables above and any collision is refused,
# by the assertion below rather than by care.** `[VERIFIED]` The collisions are real and would
# each have cost a whole league: the Kings are Sacramento and Los Angeles, the Jets are New
# York and Winnipeg, the Panthers are Carolina in two different sports. A shared word cannot
# tell you which sport you are reading about, so it is not evidence of anything.
#
# Deliberately short. `[INFERRED]` This is a list of the unmistakable ones, not an attempt at
# every franchise: a word that is also ordinary English ("wild", "lightning", "capitals",
# "stars", "blues") would fire on sentences that have nothing to do with hockey, and the cost
# of a wrong drop is an article nobody can see was lost.
OTHER_SPORT_WORDS: dict[str, frozenset[str]] = {
    "NHL": frozenset(
        {
            "nhl",
            "canucks",
            "avalanche",
            "oilers",
            "bruins",
            "sabres",
            "blackhawks",
            "penguins",
            "islanders",
            "kraken",
            "canadiens",
            "flyers",
            "coyotes",
        }
    ),
    "MLB": frozenset(
        {
            "mlb",
            "yankees",
            "dodgers",
            "mets",
            "astros",
            "cubs",
            "orioles",
            "phillies",
            "padres",
            "brewers",
            "marlins",
            "pirates",
        }
    ),
    "college": frozenset({"ncaa", "marquette", "gonzaga", "villanova", "unlv"}),
    "soccer": frozenset({"uefa", "fifa", "laliga", "bundesliga"}),
    "WNBA": frozenset({"wnba"}),
}

# The same idea for names that are only unambiguous as a phrase. `[INFERRED]` "leafs" alone is
# a misspelling waiting to happen and "wings" is an ordinary word; both are safe written out.
OTHER_SPORT_PHRASES: dict[str, tuple[str, ...]] = {
    "NHL": (
        "maple leafs",
        "blue jackets",
        "golden knights",
        "red wings",
        "stanley cup",
    ),
    "college": ("big ten", "big 12", "college football", "transfer portal"),
    "soccer": ("premier league", "champions league"),
}

_shared = TEAM_NICKNAMES & frozenset().union(*OTHER_SPORT_WORDS.values())
assert not _shared, f"a word cannot name two sports at once: {sorted(_shared)}"
del _shared


# Position abbreviations, which headlines write between a team and a player and which the name
# scanner otherwise welds to the player. `[VERIFIED]` 2026-09-03 this is the same construction
# P48 and P52 fixed one word further along: `Broncos WR Mims exits` was indexed as the name
# `{wr, mims}`, and that entity then disagreed with the real `Marvin Mims Jr.` from the same
# article's body and refused him as a blend of two people.
#
# `[VERIFIED]` Common, not exotic: 35 of 448 captured titles put one of these immediately
# before a name. QB 9, RB 8, CB 4, OT 4, LB 3, WR 2, DT 2, TE 1, OL 1, DE 1.
#
# **`OG` is deliberately absent, and it is the reason this list is not generated from a
# position chart.** `[VERIFIED]` OG is offensive guard, and it is also OG Anunoby, who appears
# twice in the captures and both times as a person. Single letters are out for the same kind of
# reason: `C` is a centre and a letter, `G` is a guard and a grade, `S`, `K`, `P` and `T` are
# all ordinary. `MLB` is out because it is middle linebacker and Major League Baseball, and
# `OTHER_SPORT_WORDS` already claims it.
#
# `[INFERRED]` The entries never seen in a capture are here because they are the same shape as
# the ten that were, and none of them is an English word or a plausible name.
POSITION_ABBREVIATIONS = frozenset(
    {
        # Seen in the captures.
        "QB",
        "RB",
        "WR",
        "TE",
        "OL",
        "OT",
        "DL",
        "DE",
        "DT",
        "CB",
        "LB",
        # Not yet seen, same shape.
        "FB",
        "NT",
        "ILB",
        "OLB",
        "DB",
        "FS",
        "SS",
        "LS",
    }
)

_clash = frozenset(word.lower() for word in POSITION_ABBREVIATIONS) & (
    TEAM_NICKNAMES | frozenset().union(*OTHER_SPORT_WORDS.values())
)
assert not _clash, f"a position cannot also name a team or a sport: {sorted(_clash)}"
del _clash
