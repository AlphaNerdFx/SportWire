"""Behaviour tests for the one place `.env` is read.

`config/settings.py` has two jobs that fail in opposite directions:

  - **Missing credentials must not be fatal.** A missing balldontlie key drops the games
    section; it does not stop the run. Only delivery has no meaningful degraded mode — a
    brief nobody receives is not a shorter brief, it is no brief.
  - **Malformed values must be fatal.** Falling back to a default on `POLL_INTERVAL_HOURS=eight`
    would silently hide a typo.

The most valuable assertions here are about **path anchoring**. `[VERIFIED]` 2026-08-06: paths
resolved against the working directory meant a scheduled run starting in `$HOME` found no
`.env` at all, and would have written its own separate database — dedup state splitting in two
and already-delivered stories being re-sent. Manual runs worked the whole time, so the failure
was invisible from the terminal. Those two behaviours are pinned below.

Every test sets the environment through `monkeypatch`, which restores it afterwards; nothing
here reads the operator's real `.env`.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from config.settings import (
    DEFAULT_DEDUP_WINDOW_HOURS,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_POLL_INTERVAL_HOURS,
    PROJECT_ROOT,
    Settings,
    SettingsError,
)

# Every variable `from_env` reads. Cleared before each test so a value in the operator's real
# environment cannot make a test pass or fail for reasons that have nothing to do with it.
_ENV_VARS = (
    "BALL_DONT_LIE_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DATABASE_PATH",
    "LOG_LEVEL",
    "POLL_INTERVAL_HOURS",
    "DEDUP_WINDOW_HOURS",
    "OLLAMA_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A pristine environment and an empty `.env`, so tests are independent of this machine."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    return env_file


# --- path anchoring: the bug that broke every scheduled run --------------------------------


def test_the_database_path_is_anchored_to_the_project_not_the_cwd(
    clean_env: Path,
) -> None:
    """`[VERIFIED]` A bare "sportwire.db" resolved against the working directory would give a
    scheduled run its own database in `$HOME`, separate from the one manual runs use. Dedup
    state splits in two and delivered stories are sent again."""
    settings = Settings.from_env(clean_env)

    assert settings.database_path.is_absolute()
    assert settings.database_path.parent == PROJECT_ROOT


def test_a_relative_database_path_is_anchored_too(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative value in `.env` gets the same treatment as the default."""
    monkeypatch.setenv("DATABASE_PATH", "data/custom.db")

    settings = Settings.from_env(clean_env)

    assert settings.database_path == PROJECT_ROOT / "data/custom.db"


def test_an_absolute_database_path_is_honoured_as_given(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Anchoring must not override someone who was explicit."""
    absolute = tmp_path / "elsewhere" / "sportwire.db"
    monkeypatch.setenv("DATABASE_PATH", str(absolute))

    assert Settings.from_env(clean_env).database_path == absolute


def test_the_project_root_is_derived_from_the_module_not_the_cwd() -> None:
    """The anchor itself. If this stops being the repository root, both tests above are moot."""
    assert (PROJECT_ROOT / "config" / "settings.py").exists()
    assert (PROJECT_ROOT / "main.py").exists()


# --- missing credentials degrade, they do not fail ------------------------------------------


def test_missing_credentials_are_not_fatal(clean_env: Path) -> None:
    """Loading must succeed with nothing configured. The caller decides what that costs."""
    settings = Settings.from_env(clean_env)

    assert settings.balldontlie_api_key == ""
    assert settings.can_fetch_games is False
    assert settings.can_deliver is False


def test_a_key_enables_its_feature(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Presence of the key is the switch — no second flag to set."""
    monkeypatch.setenv("BALL_DONT_LIE_API_KEY", "a-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "another-key")

    settings = Settings.from_env(clean_env)

    assert settings.can_fetch_games is True
    assert settings.prefers_hosted_summariser is True


def test_the_hosted_summariser_is_off_without_a_key(clean_env: Path) -> None:
    """The default path is local Ollama; hosted is dormant until a key exists."""
    assert Settings.from_env(clean_env).prefers_hosted_summariser is False


def test_whitespace_only_values_count_as_unset(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[INFERRED]` A trailing space in a hand-edited `.env` is common, and a token of " "
    would produce a confusing HTTP 401 rather than a clear "not configured"."""
    monkeypatch.setenv("BALL_DONT_LIE_API_KEY", "   ")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "\t")

    settings = Settings.from_env(clean_env)

    assert settings.can_fetch_games is False
    assert settings.can_deliver is False


# --- delivery is the one thing with no degraded mode ---------------------------------------


def test_require_delivery_raises_when_unconfigured(clean_env: Path) -> None:
    """A brief nobody receives is not a shorter brief, it is no brief."""
    settings = Settings.from_env(clean_env)

    with pytest.raises(SettingsError) as raised:
        settings.require_delivery()

    message = str(raised.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "--dry-run" in message, (
        "the error must name the way to proceed without sending"
    )


def test_require_delivery_is_silent_when_configured(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    Settings.from_env(clean_env).require_delivery()


def test_a_token_without_a_chat_id_cannot_deliver(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both halves are required. A token alone has nowhere to send."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")

    with pytest.raises(SettingsError):
        Settings.from_env(clean_env).require_delivery()


# --- malformed values are fatal, defaults are not -------------------------------------------


def test_numeric_defaults_apply_when_unset(clean_env: Path) -> None:
    settings = Settings.from_env(clean_env)

    assert settings.poll_interval_hours == DEFAULT_POLL_INTERVAL_HOURS
    assert settings.dedup_window_hours == DEFAULT_DEDUP_WINDOW_HOURS
    assert settings.ollama_model == DEFAULT_OLLAMA_MODEL


def test_the_dedup_window_exceeds_the_poll_interval_by_default() -> None:
    """`[VERIFIED]` These are different knobs and the original documents conflated them.

    The window must exceed how far back the *feed* reaches, not the poll interval: ESPN lists
    items up to ~4 days old, so a shorter window makes an already-sent story look new on every
    run. 168h against 8h is not an accident.
    """
    assert DEFAULT_DEDUP_WINDOW_HOURS > DEFAULT_POLL_INTERVAL_HOURS
    assert DEFAULT_DEDUP_WINDOW_HOURS == 168


@pytest.mark.parametrize("name", ["POLL_INTERVAL_HOURS", "DEDUP_WINDOW_HOURS"])
def test_a_non_numeric_value_raises_rather_than_falling_back(
    name: str, clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silently giving someone the default would hide their typo."""
    monkeypatch.setenv(name, "eight")

    with pytest.raises(SettingsError) as raised:
        Settings.from_env(clean_env)

    assert name in str(raised.value)
    assert "eight" in str(raised.value), (
        "the error must quote what was actually written"
    )


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_a_non_positive_interval_raises(
    bad: str, clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero hours is not a schedule, and a negative window is not a window."""
    monkeypatch.setenv("POLL_INTERVAL_HOURS", bad)

    with pytest.raises(SettingsError):
        Settings.from_env(clean_env)


def test_a_valid_override_is_taken(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The complement: rejecting bad values is only useful if good ones get through."""
    monkeypatch.setenv("POLL_INTERVAL_HOURS", "12")

    assert Settings.from_env(clean_env).poll_interval_hours == 12


def test_the_log_level_is_upper_cased(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`logging` expects upper case; a `.env` written by hand often is not."""
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert Settings.from_env(clean_env).log_level == "DEBUG"


# --- immutability ----------------------------------------------------------------------------


def test_settings_cannot_be_mutated_after_loading(clean_env: Path) -> None:
    """Frozen for the same reason the DTOs are: configuration read differently by two parts
    of one run is a bug that is very hard to see."""
    settings = Settings.from_env(clean_env)

    # `FrozenInstanceError` specifically, not a blind `Exception` — a bare `raises(Exception)`
    # would also pass if the attribute simply did not exist, which asserts nothing about
    # immutability.
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.log_level = "DEBUG"  # type: ignore[misc]


def test_the_evidence_directory_is_anchored_to_the_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`[VERIFIED]` 2026-08-25 it shipped resolved against the working directory instead.

    This is the same defect that already cost this project once with `.env` and the database:
    a scheduled run starting from a different directory would write its evidence somewhere
    else, so the batches would be split across two trees and neither would be complete.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVIDENCE_PATH", raising=False)

    settings = Settings.from_env(env_file=tmp_path / "absent.env")

    assert settings.evidence_path == PROJECT_ROOT / "evidence"
    assert settings.evidence_path.is_absolute()


def test_an_absolute_evidence_path_is_honoured_as_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Anchoring must not override someone who said exactly where they want it."""
    elsewhere = tmp_path / "somewhere-else"
    monkeypatch.setenv("EVIDENCE_PATH", str(elsewhere))

    settings = Settings.from_env(env_file=tmp_path / "absent.env")

    assert settings.evidence_path == elsewhere
