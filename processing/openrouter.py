"""Summarisation via OpenRouter, for models too large to run locally.

Fourth implementation of the `Summarizer` interface, after Ollama. Nothing that calls a
summarizer changes — which is the point of the boundary.

**Why a hosted model at all.** ADR-012 rejected hosted summarisation on **C2** (recurring
cost), not on licensing, and said so explicitly. `[VERIFIED]` 2026-08-10 OpenRouter lists 17
models at zero prompt cost, including `google/gemma-4-31b-it:free` with a 262,144-token
context. A free tier removes the only stated objection, and the models are open-weight, so
C3 is unaffected: the code stays open and the user supplies their own key.

**Why size might fix what prompting could not.** `[VERIFIED]` Local 7B fabrication is not
random. Asked to summarise a Pistons story three times, `mistral:7b` invented "Joe Dumars"
on all three attempts — pattern-completing from training priors rather than reading the
input. Retry cannot help when the error repeats identically. Parameter count is the only
lever that addresses the cause; prompt revisions and input cleaning both plateaued.

**No chunking.** A 262k context takes every article in one call, so the map-reduce machinery
in `summarize.py` — which exists purely to work around a small window — is skipped entirely.
That also removes a class of failure: notes are never extracted, so nothing is lost between
steps.

`[UNKNOWN]` Whether Gemma 4 at 31B actually fabricates less. Its 4B sibling was the worst
model tested — it ignored the supplied articles and produced entirely fictional NBA news.
The validator applies identically here, so the answer is measurable rather than assumed.
"""

from __future__ import annotations

import logging

import requests

from models.schemas import NewsArticle
from processing.summarize import Summarizer, build_prompt, system_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "google/gemma-4-31b-it:free"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Generous but finite. A hosted call has no cold-start problem, but free tiers queue.
DEFAULT_TIMEOUT_SECONDS = 180


class OpenRouterSummarizer(Summarizer):
    """Sends every article in one request to a hosted open-weight model."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """The key is injected, never read from the environment here.

        Same reasoning as every other adapter: a component that fetches its own
        configuration cannot be tested without setting global state.
        """
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def summarizer_name(self) -> str:
        return f"OpenRouter ({self._model})"

    def _write(
        self, prepared: object, articles: list[NewsArticle], max_chars: int
    ) -> str:
        """One request, every article. Exceptions and retries are handled by `summarise`.

        Nothing is prepared, because there is nothing to reuse: a hosted model with a large
        context window reads the whole batch in one call, so `prepared` is the default the
        base class returns and is deliberately ignored.
        """
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                # OpenRouter uses these for attribution on its public leaderboards. Naming
                # the project honestly is the same courtesy extended to every feed here.
                "HTTP-Referer": "https://github.com/AlphaNerdFx/SportWire",
                "X-Title": "SportWire",
            },
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt(articles)},
                    {"role": "user", "content": build_prompt(articles, max_chars)},
                ],
                # Low, for the same reason as the local summarizer: this is a factual
                # summary, and an invented trade is worse than a dull paragraph.
                "temperature": 0.3,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()

        payload = response.json()

        # OpenRouter reports upstream provider failures as a 200 with an error body, so a
        # successful status code is not on its own evidence of a successful call.
        if "error" in payload:
            raise RuntimeError(f"OpenRouter returned an error: {payload['error']}")

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter returned no choices")

        return choices[0].get("message", {}).get("content", "")
