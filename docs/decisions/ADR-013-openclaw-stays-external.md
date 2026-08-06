# ADR-013 — OpenClaw may orchestrate SportWire, but must never be a dependency of it

**Date:** 2026-08-06
**Status:** accepted

## Surface
OpenClaw is a local AI assistant that can send messages through WhatsApp and other chat apps.
The operator may use it to run SportWire and forward briefs to WhatsApp on his own machine.
SportWire itself will not contain any OpenClaw code, because the way OpenClaw reaches
WhatsApp breaks WhatsApp's rules, and this repository is meant to be publishable.

## Thorough

**What OpenClaw is.** `[VERIFIED]` 2026-08-06 from `openclaw.ai` and its documentation: an
open-source, locally-run personal AI assistant that connects to 29 messaging channels
including WhatsApp, Telegram, Discord, Slack, Signal and iMessage. It is a **host/runtime that
invokes external programs**, not a library that programs import. It advertises browser control
and "full system access", and is maintained by the OpenClaw Foundation.

**The decisive finding.** `[VERIFIED]` OpenClaw's WhatsApp channel is
`"production-ready via WhatsApp Web (Baileys)"` with `"Login is QR-only."`

That is the exact mechanism ADR-002 rejected by name:

> "The unofficial alternatives (Evolution API, Baileys, `whatsapp-web.js`) impersonate
> WhatsApp Web using a real personal phone number. They violate WhatsApp's terms, risk a
> permanent ban of the operator's personal account, and cannot be published (C3)."

Two further observations. `[VERIFIED]` The documentation recommends *"A separate WhatsApp
number is recommended"* — a burner is only advisable if the primary account is exposed. And
`[VERIFIED]` it carries no terms-of-service warning at all, which for a product this polished
reads as a decision rather than an omission.

**Free and open source does not resolve C3.** The operator's initial reasoning was that
routing through OpenClaw keeps everything free and open-source, and therefore compliant.
Licensing and terms of service are independent axes. Baileys is genuinely free and genuinely
open-source; it is also impersonating WhatsApp Web. A permissive licence grants nothing from
Meta. **C2 is satisfied; C3 is not.**

**Decision.**

| Arrangement | Verdict |
|---|---|
| SportWire ships an `OpenClawChannel`, or depends on OpenClaw in any way | **Prohibited.** Distributing a ToS-violating path in a public repository is exactly what C3 forbids |
| The operator runs OpenClaw himself, and it invokes `main.py` | **Permitted.** His machine, his account, his risk. SportWire needs no knowledge of it |

This works precisely *because* OpenClaw is a host rather than a library. It calls SportWire;
SportWire never calls it. The repository contains no OpenClaw code, no mention of Baileys, and
no dependency — it prints a brief, and what invokes it is not its concern.

**Supporting change: a `StdoutChannel`.** `[VERIFIED]` `--dry-run` prints without recording to
the seen-store, so an external process relaying dry-run output would re-send every story on
every run, forever. A `StdoutChannel` implementing the existing `DeliveryChannel` interface
prints the brief **and** records it as delivered. Printing to standard output violates
nobody's terms, so it ships freely, and any external orchestrator can consume it.

**Telegram is explicitly excluded from this.** SportWire already delivers to Telegram through
the official Bot API in ~140 lines with one dependency and no ban risk. Routing it through an
agent adds moving parts and a non-deterministic failure mode to a path that currently has
neither. `[INFERRED]` Non-determinism in the delivery path is worse than in the content path,
and content non-determinism was already severe enough to disable summarisation (ADR-012).

## Deep

**The principle: a boundary that lets something call you is not the same as depending on it.**

This is the fourth appearance of the same shape in this project — `SourceAdapter`,
`DeliveryChannel`, `Summarizer`, and now the process boundary itself. Each time, the value is
that the thing on the other side can be swapped, or be absent, without the core changing. Here
the boundary is the operating system's own: a process that reads no configuration from its
caller and writes its output to a stream. That is the loosest coupling available, and it is
what lets a ToS-encumbered tool sit next to a publishable repository without contaminating it.

The generalisable rule: **when a useful tool carries a licensing or compliance hazard, put a
process boundary between it and anything you intend to distribute.** The hazard stays on one
side. Vendoring it, wrapping it, or listing it as an optional dependency all move it across.

**Second principle: "open source" is not a compliance argument.** It answers cost and
inspectability. It says nothing about whether a third party permits the access being made.
`[INFERRED]` This conflation is easy precisely because C2 and C3 usually agree — free tools
are usually also permitted — and the exception is where the trouble is.

## Reversal condition

If OpenClaw adds a WhatsApp path through the official Business API (or Meta introduces a
free, sanctioned local route), the C3 objection disappears and an `OpenClawChannel` could ship
— subject to C2, since the official API bills per message. Reversal on the Telegram question
requires a concrete failure of the native channel, not convenience.
