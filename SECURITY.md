# Security Policy

## Reporting a vulnerability

Report privately through
[GitHub's security advisories](https://github.com/AlphaNerdFx/SportWire/security/advisories/new).
Please do not open a public issue for anything exploitable.

This is a personal open-source project maintained by one person. There is no SLA. Expect a
first response within a week or so, and please give a reasonable window before public
disclosure.

## What this project handles

SportWire runs on one machine, for one recipient, and holds three secrets:

| Secret | Where it lives | If leaked |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `.env` | Anyone can send messages **as your bot** to anyone who has started a chat with it. Revoke via `/revoke` in [@BotFather](https://t.me/botfather) |
| `TELEGRAM_CHAT_ID` | `.env` | Not a credential — useless without the bot token. It identifies the recipient |
| `BALL_DONT_LIE_API_KEY` | `.env` | Someone can consume your free-tier quota. Rotate at balldontlie.io |

`.env` is gitignored and has never been committed. `[VERIFIED]` The live bot token and API key
appear **zero times** in the full git history.

The SQLite database stores only identifiers — article ids and game state hashes — never
article text, credentials, or personal data.

## What it does not do

- No inbound network listener. It makes outbound HTTPS requests and exits.
- No user input. Data comes from configured feeds only; there is no query interface.
- No arbitrary code execution, no `eval`, no plugin loading.
- No telemetry. Nothing is sent anywhere except your own Telegram chat.

## Known risks, stated plainly

**Third-party feed content is untrusted.** Article titles and descriptions come from external
sources and are inserted into messages. They are sent as **plain text** rather than Telegram
Markdown, which removes the injection surface that formatted messages would create. If you
add a channel that renders markup, escape the content.

**LLM summarisation ships enabled, and is the most likely way this project will tell you
something false.** ~~It ships disabled.~~ **Corrected 2026-08-14:** that described the
position before [ADR-012](docs/decisions/ADR-012-summarisation.md) reversed it on 2026-08-10.
Disable it with `--no-summary`.

`[VERIFIED]` Every local model tested fabricated player names and contract figures on real
data. What makes it shippable is that the output is **checked before it is sent**:
`processing/validate.py` rejects any proper name or figure absent from the source articles,
retries, and falls back to the plain headline list when nothing passes. It fails closed, and
no invented *name* has reached a phone.

`[VERIFIED]` **The check has a known hole, and it is not theoretical.** It grounds *entities*,
not *claims*: a sentence composed entirely of real, sourced names can assert a relationship
between them that no source states, and it will pass. One such sentence was delivered on
2026-08-13. Tracked as `TASKS.md` P5 and recorded as a failing test.

`[INFERRED]` Treat a generated paragraph as unverified. This is a correctness risk rather than
a security one, but if you forward a brief onward, that is the sentence that will embarrass
you.

**External orchestrators are your responsibility.** SportWire can print a brief to stdout for
another tool to relay. Tools that reach WhatsApp typically do so through unofficial bridges
that violate WhatsApp's terms and risk a permanent account ban. SportWire ships no such
integration and never will —
[ADR-013](docs/decisions/ADR-013-openclaw-stays-external.md) — but if you connect one, that
account and that risk are yours.

**Dependencies.** Five direct packages, pinned:
`requests`, `pydantic`, `python-dotenv`, plus `pytest` and `ruff` for development. Fewer
dependencies is itself the mitigation; the environment this replaced carried 151 packages
before proving anything worked.

## If you fork this

Before your first commit, confirm `.gitignore` covers `.env`, `*.db`, `.venv/`,
`__pycache__/`, `*.pyc`, `.pytest_cache/` and `.ruff_cache/`, and check your history:

```bash
git log --all --name-only | grep -i "\.env"
```

A leaked bot token in a public repository is found by scanners within minutes.
