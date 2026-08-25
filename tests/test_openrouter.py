"""Behaviour tests for the hosted summariser, which has never run.

`[VERIFIED]` GitHub issue #15 named the untested modules, and this one stayed at zero while
the rest were covered. `config/settings.py` already defaults `OPENROUTER_MODEL`, but no key
is configured, so every line here is unexercised in production. That is precisely why it
needs tests: the day the operator adds a key is the day this runs for the first time, and
nothing about it will have been checked.

No test touches the network. `requests.post` is replaced with a stub that returns a real
response shape, because the behaviour worth pinning is how this reads a payload, not whether
OpenRouter is reachable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from models.schemas import NewsArticle
from processing.openrouter import OpenRouterSummarizer

ArticleFactory = Callable[..., NewsArticle]


class _Response:
    """The parts of `requests.Response` this adapter actually uses."""

    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


def _reply(text: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": text}}]}


def test_the_models_reply_is_returned(
    monkeypatch: pytest.MonkeyPatch, make_article: ArticleFactory
) -> None:
    """The happy path, which is the one thing that has never been observed running."""
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured.update(kwargs)
        captured["url"] = url
        return _Response(_reply("The Cavaliers traded Dennis Schroder."))

    monkeypatch.setattr("processing.openrouter.requests.post", fake_post)

    summarizer = OpenRouterSummarizer(api_key="sk-test")
    result = summarizer.summarise(
        [make_article("Cavs deal Schroder for Hornets' Mann")]
    )

    assert result == "The Cavaliers traded Dennis Schroder."


def test_the_key_is_sent_and_never_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, make_article: ArticleFactory
) -> None:
    """Injected, not fetched. `[INFERRED]` A component that reads its own configuration
    cannot be tested without setting global state, and a leaked key is the one bug here whose
    cost is not measured in briefs.
    """
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured.update(kwargs)
        return _Response(_reply("Summary."))

    monkeypatch.setattr("processing.openrouter.requests.post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-the-environment")

    OpenRouterSummarizer(api_key="sk-injected").summarise(
        [make_article("Cavs deal Schroder for Hornets' Mann")]
    )

    assert captured["headers"]["Authorization"] == "Bearer sk-injected"


def test_an_error_body_behind_a_200_is_treated_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, make_article: ArticleFactory
) -> None:
    """`[VERIFIED]` OpenRouter reports upstream provider failures as a **200 with an error
    body**, so a successful status code is not on its own evidence of a successful call.

    The failure must degrade to the headline list rather than deliver an error message as if
    it were a brief, which is what would happen if the payload were read blindly.
    """

    def fake_post(url: str, **kwargs: Any) -> _Response:
        return _Response({"error": {"message": "upstream provider is down"}})

    monkeypatch.setattr("processing.openrouter.requests.post", fake_post)

    result = OpenRouterSummarizer(api_key="sk-test", timeout_seconds=1).summarise(
        [make_article("Cavs deal Schroder for Hornets' Mann")], attempts=1
    )

    assert result is None


def test_an_empty_choices_list_is_treated_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, make_article: ArticleFactory
) -> None:
    """A 200 with nothing in it is still nothing. Returning "" would deliver a blank brief."""

    def fake_post(url: str, **kwargs: Any) -> _Response:
        return _Response({"choices": []})

    monkeypatch.setattr("processing.openrouter.requests.post", fake_post)

    result = OpenRouterSummarizer(api_key="sk-test").summarise(
        [make_article("Cavs deal Schroder for Hornets' Mann")], attempts=1
    )

    assert result is None


def test_a_network_failure_degrades_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, make_article: ArticleFactory
) -> None:
    """`CLAUDE.md` §5.6: a dead dependency shortens the brief, it never ends the run."""

    def fake_post(url: str, **kwargs: Any) -> _Response:
        raise ConnectionError("no route to host")

    monkeypatch.setattr("processing.openrouter.requests.post", fake_post)

    result = OpenRouterSummarizer(api_key="sk-test").summarise(
        [make_article("Cavs deal Schroder for Hornets' Mann")], attempts=1
    )

    assert result is None


def test_a_fabricated_summary_is_rejected_like_any_other(
    monkeypatch: pytest.MonkeyPatch, make_article: ArticleFactory
) -> None:
    """The hosted path must not bypass validation.

    `[INFERRED]` It inherits `summarise` from the base class, so this holds by construction
    rather than by care — which is exactly the kind of claim worth pinning, because a future
    override would break it silently.
    """

    def fake_post(url: str, **kwargs: Any) -> _Response:
        return _Response(_reply("Joe Dumars is leading the negotiations."))

    monkeypatch.setattr("processing.openrouter.requests.post", fake_post)

    result = OpenRouterSummarizer(api_key="sk-test").summarise(
        [make_article("Cavs deal Schroder for Hornets' Mann")], attempts=1
    )

    assert result is None, "an invented name must not reach the brief"


def test_the_name_reports_which_model_is_in_use(make_article: ArticleFactory) -> None:
    """The log line names the summariser, and "OpenRouter" alone would not say which model."""
    assert (
        "gemma"
        in OpenRouterSummarizer(
            api_key="sk", model="google/gemma-4-31b-it:free"
        ).summarizer_name
    )
