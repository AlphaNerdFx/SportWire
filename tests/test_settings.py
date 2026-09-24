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
    MAX_STORIES_CEILING,
    POLL_INTERVAL_CHOICES,
    PROJECT_ROOT,
    Settings,
    SettingsError,
    brief_size_for,
    repeat_window_hours_for,
    scaled_source_caps,
)
from delivery.brief import DEFAULT_MAX_ARTICLES
from ingestion.rss_news import FEED_LEAGUES
from processing.cluster import DEFAULT_SOURCE_LIMIT, SOURCE_LIMITS
from processing.summarize import DEFAULT_SUMMARY_CHARS

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
    "OLLAMA_FIRST_MODEL",
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


# --- interval choices and the brief size derived from them -----------------------------------


def test_the_reference_interval_produces_todays_brief_unchanged() -> None:
    """The property that makes this safe to add: 8 hours must change nothing.

    `[INFERRED]` A scaling rule that quietly alters the current brief would be a behaviour
    change disguised as a feature, and the operator asked for 8 hours to stay the standard.
    """
    stories, chars = brief_size_for(8)

    assert (stories, chars) == (DEFAULT_MAX_ARTICLES, DEFAULT_SUMMARY_CHARS)


def test_both_the_story_cap_and_the_length_scale_together() -> None:
    """`[VERIFIED]` TASKS.md P42: the 12-story cap binds on 8 of 22 logged runs at 8 hours.

    Raising only the character limit would leave a 24-hour brief discarding most of what it
    fetched and still writing twelve stories, so a longer interval would lose more news rather
    than deliver more.
    """
    short_stories, short_chars = brief_size_for(8)
    long_stories, long_chars = brief_size_for(24)

    assert long_stories > short_stories
    assert long_chars > short_chars


def test_the_brief_grows_more_slowly_than_the_interval() -> None:
    """`[INFERRED]` Linear scaling makes a 24-hour brief three times an 8-hour one, which nobody
    finishes, and costs proportionally more model time: the 2026-08-26 00:00 run took 10m36s
    for 12 stories in 3 chunks, and a chunk is added every 5 stories.
    """
    eight_hour, _ = brief_size_for(8)
    twenty_four_hour, _ = brief_size_for(24)

    assert twenty_four_hour < eight_hour * 3, "growth must be sublinear"


def test_the_story_count_is_capped_however_long_the_interval() -> None:
    """Past a point a brief stops being read, which is why the cap exists at all.

    100 is not an offered choice; `brief_size_for` accepts any interval internally (P42), and
    the ceiling has to hold for values the settings validation would refuse too.
    """
    assert brief_size_for(100)[0] <= MAX_STORIES_CEILING
    assert brief_size_for(2000)[0] <= MAX_STORIES_CEILING


def test_even_the_shortest_interval_yields_a_brief() -> None:
    """`[INFERRED]` Rounding must never reach zero stories, or the shortest choice would
    produce a brief that cannot contain anything.
    """
    for interval in POLL_INTERVAL_CHOICES:
        stories, chars = brief_size_for(interval)
        assert stories >= 1, interval
        assert chars > 0, interval


def test_the_choices_stay_inside_the_measured_band() -> None:
    """`[VERIFIED]` TASKS.md P42, narrowed 2026-09-24 to `(8, 12, 24)`. 2 and 4 hours sat inside
    the arrival-rate band but nothing else was proven to scale that far down; 48 is dropped
    because the per-outlet cap and the repeat window were both fixed numbers that only
    happened to be right at 8 hours, and re-deriving them for 48 was never done.
    """
    assert min(POLL_INTERVAL_CHOICES) == 8
    assert max(POLL_INTERVAL_CHOICES) == 24
    assert list(POLL_INTERVAL_CHOICES) == sorted(POLL_INTERVAL_CHOICES)


@pytest.mark.parametrize("interval", POLL_INTERVAL_CHOICES)
def test_every_offered_interval_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, interval: int
) -> None:
    """The set is the contract, so every member of it has to work."""
    monkeypatch.setenv("POLL_INTERVAL_HOURS", str(interval))

    settings = Settings.from_env(env_file=tmp_path / "absent.env")

    assert settings.poll_interval_hours == interval


@pytest.mark.parametrize("interval", ["1", "2", "4", "5", "36", "48", "168"])
def test_an_interval_outside_the_set_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, interval: str
) -> None:
    """`[INFERRED]` Refusing is the point, not the set existing.

    Most integers are wrong here in ways the operator cannot see from outside: 1 delivers
    mostly empty briefs, 168 delivers one enormous one a week, and neither fails loudly. 2, 4
    and 48 are included because they were offered before 2026-09-24 (TASKS.md P42) and must
    now be refused like any other value outside the set.
    """
    monkeypatch.setenv("POLL_INTERVAL_HOURS", interval)

    with pytest.raises(SettingsError, match="must be one of"):
        Settings.from_env(env_file=tmp_path / "absent.env")


def test_the_refusal_names_the_choices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An error that says what is wrong without saying what is allowed is a guessing game."""
    monkeypatch.setenv("POLL_INTERVAL_HOURS", "5")

    with pytest.raises(SettingsError) as raised:
        Settings.from_env(env_file=tmp_path / "absent.env")

    for choice in POLL_INTERVAL_CHOICES:
        assert str(choice) in str(raised.value)


def test_an_unset_interval_still_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fresh clone with no configuration must run, and must run at today's cadence."""
    monkeypatch.delenv("POLL_INTERVAL_HOURS", raising=False)

    settings = Settings.from_env(env_file=tmp_path / "absent.env")

    assert settings.poll_interval_hours == DEFAULT_POLL_INTERVAL_HOURS


# --- scaling the two numbers that used to be fixed (TASKS.md P42) --------------------------


def test_the_source_caps_are_unchanged_at_eight_hours() -> None:
    """The property that makes scaling safe to ship: 8 hours must reproduce today's caps
    exactly, since `processing/cluster.py` still ships `DEFAULT_SOURCE_LIMIT = 4` and
    `SOURCE_LIMITS = {"r/nba": 3}` as its own unscaled defaults.
    """
    default_cap, overrides = scaled_source_caps(8, DEFAULT_SOURCE_LIMIT, SOURCE_LIMITS)

    assert default_cap == DEFAULT_SOURCE_LIMIT
    assert overrides == SOURCE_LIMITS


def test_the_source_caps_match_the_measured_ratio() -> None:
    """`[VERIFIED]` TASKS.md P42: `round(base * sqrt(interval / 8))` gives 4/5/7 for the
    default cap and 3/4/5 for r/nba, at 8/12/24 hours.
    """
    assert scaled_source_caps(8, 4, {"r/nba": 3}) == (4, {"r/nba": 3})
    assert scaled_source_caps(12, 4, {"r/nba": 3}) == (5, {"r/nba": 4})
    assert scaled_source_caps(24, 4, {"r/nba": 3}) == (7, {"r/nba": 5})


@pytest.mark.parametrize("interval", POLL_INTERVAL_CHOICES)
def test_the_scaled_caps_cover_every_leagues_story_count(interval: int) -> None:
    """The analytic check TASKS.md P42 asks for: capacity must never fall short of demand.

    `[INFERRED]` NFL has only 3 feeds and no override, so the unscaled cap alone could never
    reach the 15 or 21 stories `brief_size_for` allows at 12h or 24h. Summing the scaled cap
    over every feed in a league is the most stories that league's brief can ever show, and it
    has to be at least what `brief_size_for` asks for, at every offered interval.
    """
    max_stories, _ = brief_size_for(interval)
    default_cap, overrides = scaled_source_caps(
        interval, DEFAULT_SOURCE_LIMIT, SOURCE_LIMITS
    )
    leagues = {league for league in FEED_LEAGUES.values()}

    for league in leagues:
        feeds = [name for name, lg in FEED_LEAGUES.items() if lg == league]
        capacity = sum(overrides.get(feed, default_cap) for feed in feeds)
        assert capacity >= max_stories, (interval, league, capacity, max_stories)


def test_the_repeat_window_is_unchanged_at_eight_hours() -> None:
    """`[VERIFIED]` `processing/dedup.py:REPEAT_WINDOW_HOURS` is 24; `2 * 8 = 16` is below
    that, so the floor, not the doubling, is what fires at the reference interval.
    """
    assert repeat_window_hours_for(8) == 24


def test_the_repeat_window_matches_the_measured_values() -> None:
    """`[VERIFIED]` TASKS.md P42: 24/24/48 at 8/12/24 hours. The floor holds through 12h
    because `2 * 12 = 24` equals it; only 24h is large enough for the doubling to win.
    """
    assert repeat_window_hours_for(12) == 24
    assert repeat_window_hours_for(24) == 48


@pytest.mark.parametrize("interval", POLL_INTERVAL_CHOICES)
def test_the_repeat_window_absorbs_cron_slack(interval: int) -> None:
    """`[INFERRED]` A scheduler does not fire the instant a brief becomes due; TASKS.md P42
    asks for the window to survive the interval plus roughly 30 minutes of that slack, so a
    late wake-up does not push the previous brief outside the window that is meant to catch it.
    """
    assert repeat_window_hours_for(interval) >= interval + 0.5


def test_escalation_is_off_when_both_models_are_the_same(clean_env: Path) -> None:
    """`[INFERRED]` A machine with room to spare should go straight to the capable model.

    Setting the two names equal is the documented off switch for the model ladder, so it has
    to actually switch it off.
    """
    clean_env.write_text("OLLAMA_MODEL=mistral:7b\nOLLAMA_FIRST_MODEL=mistral:7b\n")

    assert Settings.from_env(clean_env).escalates_model is False


def test_a_small_model_writes_first_by_default(clean_env: Path) -> None:
    """`[VERIFIED]` 2026-08-27: 7.4 GB of RAM under WSL2, 5.3 GB free, and mistral:7b is 4.4 GB.

    The default has to be the light one, because the operator's machine stalled on the heavy
    one and a fresh clone should not have to discover that.
    """
    settings = Settings.from_env(clean_env)

    assert settings.ollama_first_model == "llama3.2:3b"
    assert settings.ollama_model == "mistral:7b"
    assert settings.escalates_model is True
