"""Turns a batch of articles into one written narrative, replacing the headline list.

Third use of the same boundary as `ingestion/base.py` and `delivery/base.py`: an abstract
interface, concrete implementations, and callers that depend only on the abstraction. Local
inference is the default (`SESSION.md` §9 Q4 — "local always, open-source first"), and a
hosted implementation can be added later without touching anything that calls this.

`[VERIFIED]` 2026-08-06 against `llama3.2:3b` on the 15-article fixture: 687 characters in
9.1 seconds, covering every story including the two the single-call version dropped.

`[VERIFIED]` Quality is not yet good, and the specific defects are recorded rather than
smoothed over:
  - **Prioritisation is wrong.** LeBron James signing with Philadelphia — the biggest item
    in the feed — closes the paragraph instead of opening it, despite the prompt.
  - **Minor factual drift.** The source says Wembanyama *"will host"* teammates; the model
    wrote *"hosted"*. The model is small enough to alter tense, which changes meaning.
  - **Preamble appears anyway** ("The NBA offseason is underway with several notable
    developments") despite an explicit instruction against it.
`[INFERRED]` These are model-capability limits rather than prompt bugs: two prompt revisions
did not fix ordering, while chunking fixed coverage completely. A larger model is the next
lever, at the cost of a bigger download and slower runs.

Input is title plus RSS description only (PRD D5). Article bodies would require fetching
article pages, which is the C3 scraping exposure ADR-009 exists to avoid. Scores are
deliberately excluded: they have their own message and are self-explanatory.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

from models.schemas import NewsArticle

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_CHARS = 1024

# The instruction is the whole "training". Steering the output — what to emphasise, what to
# skim — is editing this string, not fine-tuning a model. Recorded because the assumption
# that this needs training came up more than once.
SYSTEM_PROMPT = (
    "You write a short NBA news brief for one reader who wants to know what happened "
    "without opening a sports app.\n"
    "\n"
    "Rules:\n"
    "- Write flowing prose, not a list. No bullets, no headings, no markdown.\n"
    "- Lead with roster and on-court news: trades, signings, injuries, returns.\n"
    "- Mention off-court and celebrity items only in passing, at the end, if at all.\n"
    "- Group related items into one sentence rather than repeating a story.\n"
    "- State only what the provided items say. Never add scores, statistics, dates or "
    "outcomes that are not present in them.\n"
    "- If the items are thin or routine, say so briefly rather than inflating them.\n"
    "- No preamble. Start with the news itself."
)

# Articles per model call before chunking kicks in. `[VERIFIED]` llama3.2:3b covered 5 of 5
# articles reliably but dropped items past roughly position 8 of 15.
CHUNK_SIZE = 5

# The map step deliberately produces **notes, not prose**. Summarising prose into prose is
# what makes naive map-reduce read like stitched fragments: each chunk gets its own opening,
# its own rhythm, and the reduce step welds them together. Extracting bare facts instead
# means only the final call ever writes a sentence, so the paragraph is composed once, in
# one pass, exactly as it is for a short batch.
NOTES_PROMPT = (
    "Extract the key facts from these NBA news items as terse notes.\n"
    "\n"
    "Rules:\n"
    "- One line per item. No prose, no sentences, no introduction.\n"
    "- Format: who — what happened — any figure that matters.\n"
    "- Keep names, teams, contract values and injury details exactly as given.\n"
    "- Do not add anything the items do not state.\n"
    "- Do not omit an item, however minor it seems."
)


class Summarizer(ABC):
    """Turns articles into one paragraph of prose."""

    @property
    @abstractmethod
    def summarizer_name(self) -> str:
        """Human-readable label, e.g. "Ollama (llama3.2)". Used in logs."""

    @abstractmethod
    def _summarise(self, articles: list[NewsArticle], max_chars: int) -> str:
        """Produce the summary text. Allowed to raise.

        Takes articles rather than a finished prompt because how many model calls this
        requires is the implementation's business, not the interface's. `OllamaSummarizer`
        makes several; a hosted implementation with a larger context window may make one.
        """

    def summarise(
        self, articles: list[NewsArticle], max_chars: int = DEFAULT_SUMMARY_CHARS
    ) -> str | None:
        """Summarise articles, returning None if summarisation is unavailable.

        None means "fall back to the headline list", not "fail the run". A summarizer that is
        offline must degrade the brief exactly as a dead source does, never crash it
        (`CLAUDE.md` §5 rule 6).
        """
        if not articles:
            return None

        try:
            text = self._summarise(articles, max_chars)
        except Exception:
            logger.exception(
                "%s failed; falling back to headline list", self.summarizer_name
            )
            return None

        cleaned = " ".join(text.split())
        if not cleaned:
            logger.warning("%s returned empty text", self.summarizer_name)
            return None

        return cleaned


class OllamaSummarizer(Summarizer):
    """Local inference via an Ollama server on this machine.

    Requires Ollama installed and a model pulled:
        curl -fsSL https://ollama.com/install.sh | sh
        ollama pull llama3.2:3b

    `[INFERRED]` A small model is sufficient here. The input is roughly 2–3 KB of short
    descriptions and the task is compression, not reasoning.
    """

    def __init__(
        self,
        model: str = "llama3.2:3b",
        host: str = "http://localhost:11434",
        timeout_seconds: int = 120,
        chunk_size: int = CHUNK_SIZE,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._chunk_size = chunk_size

    @property
    def summarizer_name(self) -> str:
        return f"Ollama ({self._model})"

    def _summarise(self, articles: list[NewsArticle], max_chars: int) -> str:
        """Summarise, chunking first if the batch is long enough to lose its tail.

        `[VERIFIED]` 2026-08-06: given all 15 fixture articles in one call, this model
        omitted the two LeBron-to-Philadelphia items entirely — the biggest story in the
        feed — while including a child-support filing. Re-running with those same two items
        moved to the front of the list covered them, and led with them. The model was not
        judging badly; it was barely reading the tail.

        So short batches go straight through, and long ones are split so that every article
        sits near the front of *some* call.
        """
        if len(articles) <= self._chunk_size:
            return self._generate(SYSTEM_PROMPT, build_prompt(articles, max_chars))

        chunks = [
            articles[index : index + self._chunk_size]
            for index in range(0, len(articles), self._chunk_size)
        ]
        logger.info(
            "%s: %d articles exceeds chunk size %d; extracting notes from %d chunks",
            self.summarizer_name,
            len(articles),
            self._chunk_size,
            len(chunks),
        )

        notes = [
            self._generate(NOTES_PROMPT, build_prompt(chunk, max_chars))
            for chunk in chunks
        ]

        return self._generate(SYSTEM_PROMPT, build_reduce_prompt(notes, max_chars))

    def _generate(self, system: str, prompt: str) -> str:
        """One POST to Ollama's generate endpoint. Exceptions handled by `summarise`."""
        response = requests.post(
            f"{self._host}/api/generate",
            json={
                "model": self._model,
                "system": system,
                "prompt": prompt,
                "stream": False,
                # Low temperature: this is a factual summary, and invented trades would be
                # worse than a dull paragraph.
                "options": {"temperature": 0.3},
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json().get("response", "")


def build_prompt(
    articles: list[NewsArticle], max_chars: int = DEFAULT_SUMMARY_CHARS
) -> str:
    """Render articles into the user half of the prompt.

    A plain module-level function so it can be tested, inspected and diffed without a model
    running — which is the only part of this module that can currently be verified.
    """
    instruction = (
        f"Summarise the following {len(articles)} NBA news items in at most "
        f"{max_chars} characters."
    )
    lines = [instruction, ""]

    for article in articles:
        lines.append(f"- {article.title}")
        summary = " ".join(article.summary.split())
        if summary:
            lines.append(f"  {summary}")

    return "\n".join(lines)


def build_reduce_prompt(
    notes: list[str], max_chars: int = DEFAULT_SUMMARY_CHARS
) -> str:
    """Render extracted notes into the final prompt that writes the paragraph.

    The notes are concatenated plainly. They are already compact, so the whole set sits well
    inside the range the model actually attends to — which is the entire point of having
    extracted them.
    """
    joined = "\n".join(note.strip() for note in notes if note.strip())
    instruction = (
        f"Write the brief from these notes, in at most {max_chars} characters. "
        "The notes are facts already gathered for you; turn all of them into one "
        "continuous piece of prose."
    )
    return f"{instruction}\n\n{joined}"
