"""Turns a batch of articles into one written narrative, replacing the headline list.

Third use of the same boundary as `ingestion/base.py` and `delivery/base.py`: an abstract
interface, concrete implementations, and callers that depend only on the abstraction. Local
inference is the default (`SESSION.md` §9 Q4 — "local always, open-source first"), and a
hosted implementation can be added later without touching anything that calls this.

`[UNKNOWN]` No live inference has been run. Ollama is not installed on this machine, so
`OllamaSummarizer._summarise` is **unverified against a real model**. Everything that does
not require a model — prompt construction, article rendering, truncation, failure handling —
is tested. Do not claim this works end to end until it has.

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


class Summarizer(ABC):
    """Turns articles into one paragraph of prose."""

    @property
    @abstractmethod
    def summarizer_name(self) -> str:
        """Human-readable label, e.g. "Ollama (llama3.2)". Used in logs."""

    @abstractmethod
    def _summarise(self, prompt: str) -> str:
        """Send the prompt to a model and return its text. Allowed to raise."""

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
            text = self._summarise(build_prompt(articles, max_chars))
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
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def summarizer_name(self) -> str:
        return f"Ollama ({self._model})"

    def _summarise(self, prompt: str) -> str:
        """POST to Ollama's generate endpoint. Exceptions handled by `summarise`."""
        response = requests.post(
            f"{self._host}/api/generate",
            json={
                "model": self._model,
                "system": SYSTEM_PROMPT,
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
