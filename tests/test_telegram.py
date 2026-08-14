"""Behaviour tests for the last thing between a correct brief and the phone.

`delivery/telegram.py` splits a brief that exceeds Telegram's 4096-character limit. The API
rejects an oversized message with HTTP 400, so a bug here does not shorten a brief — it loses
a **whole message**. That is a larger blast radius than anything in `processing/`, where a
failure costs one line.

Splitting is on blank lines so a story or game stays intact rather than being severed
mid-sentence; a single block longer than the limit is hard-split as a last resort, because the
alternative is an API error that loses everything.

`split_for_telegram` is a pure function — string in, list of strings out — so all of this is
asserted with no network, no token and no mocking. The `TelegramChannel` class around it takes
its credentials by injection precisely so a test can construct one without touching the wire.
"""

from __future__ import annotations

from delivery.telegram import MAX_MESSAGE_LENGTH, TelegramChannel, split_for_telegram


def _blocks(count: int, size: int = 100) -> str:
    """`count` blank-line-separated blocks, each identifiable and `size` characters wide."""
    return "\n\n".join(f"Block {index} " + "x" * size for index in range(count))


# --- the invariants that matter ----------------------------------------------------------


def test_short_text_is_returned_unchanged_as_one_chunk() -> None:
    """The common case. Most briefs fit, and must not be disturbed."""
    text = "Westbrook retired.\n\nThe Suns waived a forward."

    assert split_for_telegram(text) == [text]


def test_no_chunk_ever_exceeds_the_limit() -> None:
    """The property the API actually enforces. Anything over 4096 is rejected outright."""
    chunks = split_for_telegram(_blocks(60), limit=1000)

    assert len(chunks) > 1, (
        "this input must actually be split, or the test proves nothing"
    )
    assert all(len(chunk) <= 1000 for chunk in chunks)


def test_nothing_is_lost_when_splitting_on_blank_lines() -> None:
    """Rejoining the chunks reproduces the input exactly.

    `[INFERRED]` This is the assertion that matters most: a splitter that silently drops a
    block produces a brief that looks entirely normal, which is the failure class this project
    keeps rediscovering.
    """
    text = _blocks(60)

    chunks = split_for_telegram(text, limit=1000)

    assert "\n\n".join(chunks) == text


def test_every_block_survives_intact() -> None:
    """No block is severed mid-way: each appears whole in exactly one chunk."""
    text = _blocks(40)

    chunks = split_for_telegram(text, limit=1000)

    for index in range(40):
        marker = f"Block {index} "
        holders = [chunk for chunk in chunks if marker in chunk]
        assert len(holders) == 1, f"{marker!r} appears in {len(holders)} chunks, want 1"


def test_the_real_limit_is_telegrams() -> None:
    """`[VERIFIED]` Telegram rejects above 4096 with HTTP 400, so that is the default."""
    assert MAX_MESSAGE_LENGTH == 4096

    chunks = split_for_telegram(_blocks(200))

    assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)


# --- the last resort: a single block too big to keep whole --------------------------------


def test_an_oversized_single_block_is_hard_split() -> None:
    """One block longer than the limit has no blank line to break on.

    Hard-splitting mid-word is ugly, and it is still the right call: the alternative is an
    API error that loses the entire message.
    """
    block = "y" * 2500

    chunks = split_for_telegram(block, limit=1000)

    assert [len(chunk) for chunk in chunks] == [1000, 1000, 500]
    assert "".join(chunks) == block, "a hard split must not drop characters"


def test_an_oversized_block_among_normal_ones_does_not_disturb_them() -> None:
    """The mixed case: one giant block, ordinary blocks either side, nothing lost."""
    text = "\n\n".join(["short one", "z" * 2500, "short two"])

    chunks = split_for_telegram(text, limit=1000)

    rejoined = "".join(chunks)
    assert "short one" in chunks[0]
    assert "short two" in chunks[-1]
    assert "z" * 2500 in rejoined


# --- degenerate input ----------------------------------------------------------------------


def test_empty_text_is_one_empty_chunk() -> None:
    """`[VERIFIED]` Measured, not assumed: the function returns `['']`, not `[]`.

    Asserted so a future change to `[]` — which would send nothing — is a visible decision
    rather than a silent one.
    """
    assert split_for_telegram("") == [""]


def test_text_exactly_at_the_limit_is_not_split() -> None:
    """The boundary on the early return.

    `[VERIFIED]` 2026-08-14: flipping that `<=` to `<` is an **equivalent mutant** — it cannot
    be killed, and that is correct rather than a gap. When the text is exactly at the limit the
    loop reproduces the early return's answer: every accumulating candidate is bounded by the
    total, so all of them fit and the whole text emerges as one chunk either way. Recorded so
    nobody later mistakes it for missing coverage and writes a test that cannot fail.
    """
    text = "a" * 1000

    assert split_for_telegram(text, limit=1000) == [text]


def test_text_one_over_the_limit_is_split() -> None:
    """The other side of that boundary."""
    chunks = split_for_telegram("a" * 1001, limit=1000)

    assert len(chunks) == 2
    assert "".join(chunks) == "a" * 1001


def test_a_block_that_fills_the_chunk_exactly_still_fits() -> None:
    """`[VERIFIED]` 2026-08-14 — added because mutation testing found this uncovered.

    Changing the block-fit test from `<=` to `<` survived every other assertion here. It is
    only observable when an accumulating chunk lands on **exactly** the limit *and* the text
    as a whole exceeds it, so the early return does not fire first:

        "abc\\n\\ndefgh\\n\\nzzz"   limit 10
          <=  ->  ['abc\\n\\ndefgh', 'zzz']     two messages
          <   ->  ['abc', 'defgh', 'zzz']   three

    `[INFERRED]` One extra message is a small cost, but the mutation went unnoticed by eleven
    tests including two written specifically as boundary cases — the earlier ones put the
    boundary on the *whole text*, where the early return masks it.
    """
    text = "abc\n\ndefgh\n\nzzz"
    assert len("abc\n\ndefgh") == 10, (
        "the first two blocks must land exactly on the limit"
    )

    assert split_for_telegram(text, limit=10) == ["abc\n\ndefgh", "zzz"]


# --- the channel around it ------------------------------------------------------------------


def test_credentials_are_injected_never_read_from_the_environment() -> None:
    """Same reasoning as the ingestion adapters: this class must not know `.env` exists.

    The payoff is exactly this test — a channel can be constructed with no configuration, no
    token and no network.
    """
    channel = TelegramChannel(bot_token="never-used", chat_id="12345")

    assert channel.channel_name == "Telegram"
