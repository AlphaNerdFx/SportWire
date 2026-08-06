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

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Defaults live here, next to the field they belong to, rather than being repeated at each
# call site. `[VERIFIED]` The dedup window must exceed how far back the news feed reaches,
# not the poll interval — ESPN lists items up to ~4 days old, so a shorter window makes an
# already-sent story look new again (PRD D2).
DEFAULT_DATABASE_PATH = "sportwire.db"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_POLL_INTERVAL_HOURS = 8
DEFAULT_DEDUP_WINDOW_HOURS = 168
DEFAULT_OLLAMA_MODEL = "mistral:7b"


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
    database_path: Path = Path(DEFAULT_DATABASE_PATH)
    log_level: str = DEFAULT_LOG_LEVEL
    poll_interval_hours: int = DEFAULT_POLL_INTERVAL_HOURS
    dedup_window_hours: int = DEFAULT_DEDUP_WINDOW_HOURS
    ollama_model: str = DEFAULT_OLLAMA_MODEL

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> Settings:
        """Load and validate settings from `.env` and the process environment.

        Missing credentials are **not** fatal here. A missing balldontlie key should drop the
        games section, not stop the run — that decision belongs to the caller, which is why
        `require_*` below is separate from loading.
        """
        load_dotenv(env_file)

        return cls(
            balldontlie_api_key=_text("BALL_DONT_LIE_API_KEY"),
            telegram_bot_token=_text("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_text("TELEGRAM_CHAT_ID"),
            database_path=Path(_text("DATABASE_PATH") or DEFAULT_DATABASE_PATH),
            log_level=(_text("LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper(),
            poll_interval_hours=_positive_int(
                "POLL_INTERVAL_HOURS", DEFAULT_POLL_INTERVAL_HOURS
            ),
            dedup_window_hours=_positive_int(
                "DEDUP_WINDOW_HOURS", DEFAULT_DEDUP_WINDOW_HOURS
            ),
            ollama_model=_text("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL,
        )

    @property
    def can_fetch_games(self) -> bool:
        """Whether game fetching is configured. False degrades the brief, it does not fail."""
        return bool(self.balldontlie_api_key)

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
