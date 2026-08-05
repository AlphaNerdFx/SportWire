"""Telegram Bot API delivery. See ADR-002 for why Telegram rather than WhatsApp.

`[VERIFIED]` A message reaches the operator's phone with a single HTTP POST, no SDK and no
approval process — confirmed by hand in tasks C5 and C5b before this module existed.
"""

from __future__ import annotations

import requests

from delivery.base import DeliveryChannel

# Telegram rejects messages above 4096 characters with HTTP 400. Long briefs are split
# rather than truncated, because silently dropping the tail of a brief is worse than
# sending two messages.
MAX_MESSAGE_LENGTH = 4096


class TelegramChannel(DeliveryChannel):
    """Sends messages to one Telegram chat via the Bot API."""

    API_BASE = "https://api.telegram.org"

    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 15) -> None:
        """Credentials are injected, never read from the environment here.

        Same reasoning as the ingestion adapters: this class should not know `.env` exists.
        The caller decides where the token came from, which keeps configuration in one
        place and lets tests construct one without touching the network.
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout_seconds = timeout_seconds

    @property
    def channel_name(self) -> str:
        return "Telegram"

    def _send(self, text: str, silent: bool) -> None:
        """POST each chunk to sendMessage. Exceptions are handled by `send`."""
        for chunk in split_for_telegram(text):
            response = requests.post(
                f"{self.API_BASE}/bot{self._bot_token}/sendMessage",
                data={
                    "chat_id": self._chat_id,
                    "text": chunk,
                    "disable_notification": silent,
                    # Long URLs would otherwise generate a link preview card that dwarfs
                    # the message. The brief carries no links, but a headline can contain
                    # one, so this stays off.
                    "disable_web_page_preview": True,
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()


def split_for_telegram(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks within Telegram's length limit, breaking on blank lines.

    Splitting on blank lines keeps each story or game intact rather than severing one
    mid-sentence. A single item longer than the limit is hard-split as a last resort, since
    the alternative is an API error that loses the whole message.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block

        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        # The block alone may still exceed the limit; hard-split it.
        while len(block) > limit:
            chunks.append(block[:limit])
            block = block[limit:]
        current = block

    if current:
        chunks.append(current)

    return chunks
