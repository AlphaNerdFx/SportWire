"""The one place `.env` is read. Every other module receives values, never fetches them.

`CLAUDE.md` §10 requires a single settings module, and the reason is recorded rather than
assumed: `[VERIFIED]` the legacy prototype's `config/settings.py` had no `__pycache__` entry,
meaning nothing ever imported it. Its documented "app-wide settings and thresholds" were read
by no running code, so the values in it were fiction.

Nothing here is auto-loaded at import time. `Settings.from_env()` is called once, in
`main.py`, and the resulting object is passed down. That is why adapters take an `api_key`
argument rather than reaching for the environment themselves: a component that fetches its
own configuration cannot be tested without setting global state.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Defaults live here, next to the field they belong to, rather than being repeated at each
# call site. `[VERIFIED]` The dedup window must exceed how far back the news feed reaches,
# not the poll interval — ESPN lists items up to ~4 days old, so a shorter window makes an
# already-sent story look new again (PRD D2).
# The project root, derived from this file's own location rather than the current working
# directory. `[VERIFIED]` 2026-08-06: without this, running from any directory other than the
# project root finds no `.env` at all — both the API key and the Telegram token come back
# empty and no brief is ever sent. Cron and Task Scheduler both start in a different
# directory, so the scheduled runs would have failed silently while manual runs worked.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATABASE_PATH = "sportwire.db"
DEFAULT_EVIDENCE_PATH = "evidence"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_POLL_INTERVAL_HOURS = 8
DEFAULT_DEDUP_WINDOW_HOURS = 168
DEFAULT_OLLAMA_MODEL = "mistral:7b"

# The model that writes first. `[VERIFIED]` 2026-08-27 the operator's machine has 7.4 GB of
# RAM under WSL2 with 5.3 GB free, and `mistral:7b` is 4.4 GB, which is what made the desktop
# unusable during a run. `llama3.2:3b` is 2.0 GB. It writes every brief; `OLLAMA_MODEL` above
# is loaded only when the validator refuses what it wrote.
#
# Set `OLLAMA_FIRST_MODEL` equal to `OLLAMA_MODEL` to turn the escalation off and go straight
# to the capable model, which is what a machine with room to spare should do.
DEFAULT_OLLAMA_FIRST_MODEL = "llama3.2:3b"

# Hosted summarisation, used when a key is present. Free tier, open-weight model, 262k
# context — see processing/openrouter.py and ADR-012.
DEFAULT_OPENROUTER_MODEL = "google/gemma-4-31b-it:free"


# The intervals a user may choose between, in hours (PRD D6, TASKS.md P42).
#
# **A set rather than a free number**, because most numbers are wrong in ways the operator
# cannot see. `[VERIFIED]` Measured over 13 scheduled runs at 8 hours, new articles arrived at
# about 3.9 an hour, so 30 minutes would usually deliver nothing at all and the brief becomes
# silence or noise. The floor and ceiling are the operator's, and the measurement agrees with
# both: 2 hours yields roughly 8 articles, 2 days roughly 187.
#
# `[UNKNOWN]` Those are offseason rates. `SeenStore.arrivals_per_hour` exists so this can be
# re-derived from what actually arrived rather than re-guessed, and it should be re-checked
# once the season starts.
POLL_INTERVAL_CHOICES: tuple[int, ...] = (2, 4, 8, 12, 24, 48)

# What a brief looks like at the reference interval. These are today's shipped values, so an
# 8-hour interval produces exactly the brief that ships now and nothing changes by default.
REFERENCE_INTERVAL_HOURS = 8
REFERENCE_MAX_STORIES = 12
REFERENCE_SUMMARY_CHARS = 1024

# Above this, a brief stops being something anyone reads to the end.
MAX_STORIES_CEILING = 24


def brief_size_for(interval_hours: int) -> tuple[int, int]:
    """How many stories a brief may carry and how long it may run, for a given interval.

    Returns `(max_stories, summary_chars)`.

    **Scaling both is the point.** `[VERIFIED]` TASKS.md P42: `DEFAULT_MAX_ARTICLES = 12` binds
    on 8 of 22 logged runs at 8 hours, so raising only the character limit would leave a 2-day
    brief discarding roughly 175 of 187 articles and still writing twelve stories. A longer
    interval would lose more news rather than deliver more.

    **Sublinear, by the square root of the ratio.** `[INFERRED]` Linear scaling would make a
    2-day brief six times longer than an 8-hour one, which nobody finishes reading, and it
    would cost proportionally more model time: `[VERIFIED]` the 2026-08-26 00:00 run took 10
    minutes 36 seconds for 12 stories in 3 chunks, and `processing/summarize.py` adds a chunk
    per 5 stories. Square root keeps a 2-day brief about 2.4 times an 8-hour one rather than 6.

    Clamped at `MAX_STORIES_CEILING` for the same reason the cap exists at all.
    """
    ratio = interval_hours / REFERENCE_INTERVAL_HOURS
    scale = math.sqrt(ratio)
    stories = min(MAX_STORIES_CEILING, max(1, round(REFERENCE_MAX_STORIES * scale)))
    # Characters follow the stories actually shown, not the interval, so the model is never
    # asked for a length the story count cannot fill.
    chars = round(REFERENCE_SUMMARY_CHARS * stories / REFERENCE_MAX_STORIES)
    return stories, chars


class SettingsError(RuntimeError):
    """Raised when configuration is missing or malformed.

    A distinct type so `main.py` can report a clear setup problem instead of letting a
    `KeyError` surface three layers down as though it were a bug.
    """


@dataclass(frozen=True)
class Settings:
    """Everything the pipeline needs from the environment, validated once.

    Frozen for the same reason the DTOs are: configuration read differently by two parts of
    one run is a bug that is very hard to see.
    """

    balldontlie_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    database_path: Path = PROJECT_ROOT / DEFAULT_DATABASE_PATH
    evidence_path: Path = PROJECT_ROOT / DEFAULT_EVIDENCE_PATH
    log_level: str = DEFAULT_LOG_LEVEL
    poll_interval_hours: int = DEFAULT_POLL_INTERVAL_HOURS
    dedup_window_hours: int = DEFAULT_DEDUP_WINDOW_HOURS
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    ollama_first_model: str = DEFAULT_OLLAMA_FIRST_MODEL
    openrouter_api_key: str = ""
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> Settings:
        """Load and validate settings from `.env` and the process environment.

        Missing credentials are **not** fatal here. A missing balldontlie key should drop the
        games section, not stop the run — that decision belongs to the caller, which is why
        `require_*` below is separate from loading.

        `.env` is located relative to the project, never the working directory, so a
        scheduled run starting in `$HOME` behaves identically to a manual one.
        """
        load_dotenv(env_file or PROJECT_ROOT / ".env")

        return cls(
            balldontlie_api_key=_text("BALL_DONT_LIE_API_KEY"),
            telegram_bot_token=_text("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_text("TELEGRAM_CHAT_ID"),
            database_path=_database_path(),
            evidence_path=_anchored("EVIDENCE_PATH", DEFAULT_EVIDENCE_PATH),
            log_level=(_text("LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper(),
            poll_interval_hours=_interval_choice(),
            dedup_window_hours=_positive_int(
                "DEDUP_WINDOW_HOURS", DEFAULT_DEDUP_WINDOW_HOURS
            ),
            ollama_model=_text("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL,
            ollama_first_model=(
                _text("OLLAMA_FIRST_MODEL") or DEFAULT_OLLAMA_FIRST_MODEL
            ),
            openrouter_api_key=_text("OPENROUTER_API_KEY"),
            openrouter_model=_text("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL,
        )

    @property
    def can_fetch_games(self) -> bool:
        """Whether game fetching is configured. False degrades the brief, it does not fail."""
        return bool(self.balldontlie_api_key)

    @property
    def escalates_model(self) -> bool:
        """Whether a small model writes first and a bigger one is the fallback."""
        return self.ollama_first_model != self.ollama_model

    @property
    def prefers_hosted_summariser(self) -> bool:
        """Whether a hosted summarizer is configured.

        Presence of the key is the switch. `[INFERRED]` Someone who has gone to the trouble
        of obtaining one wants it used; making them set a second flag as well would be
        configuration for its own sake.
        """
        return bool(self.openrouter_api_key)

    @property
    def can_deliver(self) -> bool:
        """Whether Telegram delivery is configured."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def require_delivery(self) -> None:
        """Raise if the brief cannot be sent, with the fix in the message.

        Sending is the one thing that has no meaningful degraded mode: a brief nobody
        receives is not a shorter brief, it is no brief.
        """
        if not self.can_deliver:
            raise SettingsError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env to send. "
                "Copy .env.example to .env and fill them in, or use --dry-run to preview "
                "without sending."
            )


def _text(name: str) -> str:
    """Read an environment variable, trimmed. Empty and unset are the same thing here."""
    return (os.getenv(name) or "").strip()


def _anchored(name: str, default: str) -> Path:
    """Resolve a configured path against the project root rather than the working directory.

    `[VERIFIED]` This is the bug class that already cost this project once: a bare
    "sportwire.db" resolved against the working directory gave a scheduled run its own
    database in `$HOME`, separate from the one manual runs used. `[VERIFIED]` 2026-08-25 the
    evidence directory shipped with the same defect and is now routed through here too, which
    is why this is a shared helper rather than a second copy of `_database_path`.

    An absolute path in `.env` is still honoured as given.
    """
    configured = _text(name)
    if not configured:
        return PROJECT_ROOT / default
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _database_path() -> Path:
    """Resolve the database location, anchoring a relative path to the project root.

    `[VERIFIED]` A bare "sportwire.db" resolved against the working directory would give a
    scheduled run its own database in `$HOME`, separate from the one manual runs use. Dedup
    state would then split in two and already-delivered stories would be sent again.
    An absolute path in `.env` is still honoured as given.
    """
    configured = _text("DATABASE_PATH")
    if not configured:
        return PROJECT_ROOT / DEFAULT_DATABASE_PATH

    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _interval_choice() -> int:
    """Read `POLL_INTERVAL_HOURS`, and refuse anything outside the offered set (PRD D6, R7).

    **A set rather than a free number, and refusing is the whole point.** `[INFERRED]` Most
    integers are wrong here in ways the operator cannot see from the outside: 1 delivers
    mostly empty briefs, 168 delivers one enormous one a week, and neither fails loudly. The
    error names the choices so the fix is obvious rather than a guess.

    `[VERIFIED]` The bounds are measured, not preferences. Over 13 scheduled runs at 8 hours
    new articles arrived at roughly 3.9 an hour, so half an hour usually yields nothing at all
    and two days already discards most of the batch against the story cap.
    """
    value = _positive_int("POLL_INTERVAL_HOURS", DEFAULT_POLL_INTERVAL_HOURS)
    if value not in POLL_INTERVAL_CHOICES:
        offered = ", ".join(str(choice) for choice in POLL_INTERVAL_CHOICES)
        raise SettingsError(
            f"POLL_INTERVAL_HOURS must be one of {offered}, got {value}. "
            "The set is bounded because news arrives at roughly 4 articles an hour: "
            "anything shorter usually delivers nothing, anything longer discards most of it."
        )
    return value


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer setting, or raise a clear error explaining what was wrong.

    Falling back to the default on a malformed value would hide a typo: someone who writes
    `POLL_INTERVAL_HOURS=eight` deserves to be told, not silently given 8.
    """
    raw = _text(name)
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        raise SettingsError(
            f"{name} must be a whole number of hours, got {raw!r}"
        ) from None

    if value <= 0:
        raise SettingsError(f"{name} must be greater than zero, got {value}")

    return value
