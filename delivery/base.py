"""Abstract delivery interface. `main.py` depends on this, never on Telegram directly.

The mirror image of `ingestion/base.py`: adapters keep source shapes out of the pipeline,
channels keep destination shapes out of it. Between them, the pipeline knows only its own
schemas and this interface.

This is what makes ADR-002 cheap. Telegram is v1; WhatsApp may follow if the operator ever
accepts its per-message cost. When that happens, nothing above this line changes — a new
class implements `send`, and `main.py` is handed a different object.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DeliveryChannel(ABC):
    """Somewhere a brief can be sent."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Human-readable channel label, e.g. "Telegram". Used in logs."""

    @abstractmethod
    def _send(self, text: str, silent: bool) -> None:
        """Deliver one message. Subclasses implement only this.

        Deliberately allowed to raise; the failure policy lives in `send`.
        """

    def send(self, text: str, silent: bool = False) -> bool:
        """Send one message, returning whether it succeeded.

        `silent` suppresses the recipient's notification. A brief is several messages, and
        buzzing a phone once per message is worse than not sending it at all — so the
        caller marks all but the first as silent.

        Never raises. A failed send returns False and is logged, because a delivery failure
        must not lose the rest of the brief.
        """
        try:
            self._send(text, silent)
            return True
        except Exception:
            logger.exception("%s delivery failed", self.channel_name)
            return False
