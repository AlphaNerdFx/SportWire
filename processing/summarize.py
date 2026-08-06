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
did not fix ordering, while chunking fixed coverage completely.

**Model evaluation, 2026-08-06 — no 3B model tested is factually reliable here:**

| Model / run | Outcome |
|---|---|
| `llama3.2:3b`, run 1 | `[VERIFIED]` Fabricated a person: *"Tom Cachikis will be leaving his role with the Knicks"*. No such name appears anywhere in the source; the executive is Gersson Rosas. Also wrote "Chris Marshall" for Naji Marshall. |
| `llama3.2:3b`, run 2 | `[VERIFIED]` No invented names, 10 of 11 stories covered — but asserted DeRozan "won't be joining LeBron James in Philadelphia", which no item states, and merged Bosh's blood-clot warning with Wembanyama's France workouts into a single event that never happened. |
| `qwen2.5:3b` | `[VERIFIED]` Produced 187 characters stating *"There were no significant roster or on-court developments reported today"* — on a day a superstar changed teams. Also took 255s to load into RAM cold, though only 7.5s once warm. |

`[INFERRED]` The failures differ between runs of the *same* model at temperature 0.3, so
single-run testing cannot establish confidence at this size. Demanding fuller coverage buys
hallucination; demanding brevity buys silent omission. Both are worse than the plain headline
list, which is never wrong.

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

# `[VERIFIED]` 2026-08-06, all four models run against the same 15-article fixture with the
# same prompts, scored on stories missed and names invented:
#
#   model          size    missed  invented  time
#   llama3.2:3b    2.0 GB   1-5     0-2      10-42s
#   qwen2.5:3b     1.9 GB   11/11   0        8s     (asserted nothing newsworthy happened)
#   gemma3:4b      3.3 GB   11/11   5        234s   (ignored the input entirely, see below)
#   mistral:7b     4.4 GB   0       0        337s   <- chosen
#
# Mistral was checked line by line against the source on that fixture: correct first name for
# Naji Marshall, the exact $52.2M figure, "PLYRS UNTD Performance Center" verbatim, and
# correct agency on both the Doncic petition and Jaylen Brown's remarks — all of which the 3B
# models got wrong.
#
# **That result did not hold.** `[VERIFIED]` Run against 17 live articles rather than the
# 15-article fixture, mistral:7b fabricated three people and a figure:
#
#   summary claim                                  source
#   "Devin Booker ... $73M extension with Suns"    "Suns keeping Brooks on 3-year, $73M"
#   "Malik Monk ... 1-year, $3.3M, Nuggets"        "Walker returning to NBA with 1-year
#                                                   Nuggets deal" (no figure given)
#   "Steve Nash's right-hand man, Leon Rose"       "Knicks executive Rosas leaving team"
#   "9 different champions in the last 8 years"    "eight different champions in eight years"
#
# `[INFERRED]` The single clean run was a property of that input, not of the model. Scoring
# one run is not evidence at this scale — which is the conclusion the 3B evaluation had
# already reached and which was then ignored. **Summarisation is therefore off by default**
# and gated behind `main.py --summary`. The headline list is never wrong.
#
# `[VERIFIED]` gemma3:4b is worth remembering as a cautionary case: it ignored the supplied
# articles and produced fluent, entirely fabricated NBA news — a Gabe Vincent signing, an
# Anthony Davis injury return, a Celtics-Pacers trade, a LeBron watch endorsement. None of it
# appears in the feed. It reads perfectly. This is the same failure mode as the fabricated
# handoff document that caused this repository to be rebuilt.
#
# 337 seconds is acceptable because nothing waits on it: the pipeline runs from cron every
# eight hours.
DEFAULT_MODEL = "mistral:7b"

# Generous, because a cold model load was measured at 193s before any inference begins.
DEFAULT_TIMEOUT_SECONDS = 600

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
        model: str = DEFAULT_MODEL,
        host: str = "http://localhost:11434",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
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

    `[VERIFIED]` 2026-08-06: naming the item count is load-bearing. Without it the model
    stopped after roughly 700 characters having covered about ten of fifteen notes — not
    because the input was too long (the reduce prompt is barely 1,100 characters) but
    because the paragraph *felt* finished. Stating the number gives it a condition to
    satisfy instead of a sense of completion to follow.
    """
    lines = _note_lines(notes)
    instruction = (
        f"Write the brief from these {len(lines)} notes, in at most {max_chars} "
        f"characters. All {len(lines)} notes must appear in your answer — combine related "
        "ones into a single sentence rather than leaving any out. The notes are already in "
        "priority order; keep that order. Write one continuous piece of prose."
    )
    return "{}\n\n{}".format(instruction, "\n".join(lines))


def _note_lines(notes: list[str]) -> list[str]:
    """Flatten note blocks into individual fact lines, discarding any preamble.

    `[VERIFIED]` The model prefixes its notes with "Here are the summaries:" despite being
    instructed not to. That line is not a fact, and counting it would inflate the number the
    reduce step is asked to satisfy.
    """
    lines: list[str] = []
    for block in notes:
        for raw in block.splitlines():
            line = raw.strip()
            is_bullet = line[:1] in {"-", "*", "•"}
            is_numbered = line[:1].isdigit() and "." in line[:3]
            if is_bullet or is_numbered:
                lines.append(line)
    return lines
