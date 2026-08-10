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

# Sequences of capitalised words: person and organisation names. `[VERIFIED]` This is what
# would have caught "Devin Booker", "Leon Rose", "Steve Nash", "Gabe Vincent" and "Romeo
# Langford" — every fabricated name measured during the model evaluation.
_PROPER_NAME = re.compile(r"\b[A-Z][a-zà-ÿ'’.-]*(?:\s+[A-Z][a-zà-ÿ'’.-]*)+")

# Names are matched per sentence, never across one. `[VERIFIED]` 2026-08-08: matching over
# the whole summary treated "...with the Mavericks. LeBron James chose Philadelphia" as a
# single name, "Mavericks. Le", and rejected a summary in which every fact was correct. A
# validator that rejects good output silently disables the feature it was meant to protect.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")

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

    candidates: list[str] = []
    for sentence in _SENTENCE_BREAK.split(summary):
        for name in _PROPER_NAME.findall(sentence):
            candidates.append(_drop_leading_stopword(name.strip(" .,;:")))

    invented_names = [
        name
        for name in dict.fromkeys(candidates)
        if name and not _grounded(name, source, source_lower)
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
# began "In Detroit, ...", and the pattern swept the preposition into the name. Every
# rejection costs a correct summary, so this specific artifact is worth removing.
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


def _drop_leading_stopword(name: str) -> str:
    """Strip a leading sentence-starter, so "In Detroit" is checked as "Detroit".

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


def _grounded(name: str, source: str, source_lower: str) -> bool:
    """Whether a proper name is traceable to the sources.

    Accepts the full phrase, or every individual word appearing somewhere, with possessives
    normalised on both sides. "Golden State Warriors" is grounded by a source saying "the
    Warriors"; "Devin Booker" is not grounded by a source mentioning neither Devin nor Booker.
    """
    if name.lower() in source_lower:
        return True

    normalised_source = _depossess_text(source_lower)
    return all(
        _depossess(word.lower()) in normalised_source for word in name.split() if word
    )


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
