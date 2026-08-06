"""Delivers the brief to standard output, for an external process to relay.

Exists so that something outside SportWire — a scheduler, a shell pipeline, or an assistant
like OpenClaw — can forward the brief to a channel SportWire does not and should not
implement itself. See ADR-013.

The distinction from `--dry-run` is the entire point and is easy to miss:

  `--dry-run`            prints the brief and records **nothing**. For inspecting output.
  `--channel stdout`     prints the brief and records it as **delivered**, exactly as
                         Telegram does.

`[VERIFIED]` Without that difference, an external relay reading dry-run output would re-send
every story on every run forever, because nothing would ever be marked as seen.

Printing to standard output violates nobody's terms of service, which is why this ships
freely while an OpenClaw or WhatsApp channel does not (ADR-013).
"""

from __future__ import annotations

import sys

from delivery.base import DeliveryChannel

# Separates messages in the stream so a consumer can split them back apart. A blank line is
# not enough — briefs contain blank lines between stories.
MESSAGE_SEPARATOR = "\n---\n"


class StdoutChannel(DeliveryChannel):
    """Writes each message to standard output, one per delivery."""

    def __init__(self, separator: str = MESSAGE_SEPARATOR) -> None:
        self._separator = separator

    @property
    def channel_name(self) -> str:
        return "stdout"

    def _send(self, text: str, silent: bool) -> None:
        """Write the message, then flush.

        `silent` is accepted and ignored: it means "do not ring the recipient's phone", which
        has no meaning for a stream. Honouring the interface matters more than the parameter
        being useful here — a channel that refused messages it considered irrelevant would
        make the caller aware of which channel it holds.

        The flush is deliberate. Standard output is block-buffered when piped rather than
        attached to a terminal, so without it a consumer reading incrementally would receive
        nothing until the process exits.
        """
        sys.stdout.write(text)
        sys.stdout.write(self._separator)
        sys.stdout.flush()
