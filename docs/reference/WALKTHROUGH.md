# How a story moves through the system

> Moved out of the GitHub wiki on 2026-09-03. This is the narrative version and it is
> deliberately not [`ARCHITECTURE.md`](ARCHITECTURE.md), which holds the target layout,
> the data flow and the autopsy of the prototype. That one is the specification; this one
> follows a single article from a feed to a phone.

## The whole system in one line

Fetch games and news → drop what was already sent → work out what was notable → format →
deliver.

```
balldontlie ──┐
              ├──► adapters ──► dedup ──► priority ──► highlights ──► brief ──► Telegram
ESPN RSS  ────┤         │         │                                              (or stdout)
CBS RSS   ────┘         │         └── SQLite: what has already been delivered
                        │
                        └── past this point nothing knows what XML or JSON looks like
```

## Following one article through

Take a real headline: *"Doncic's ex-fiancée pulls child support petition"*.

1. **`main.py`** loads settings and asks each configured feed for articles.
2. **`ingestion/rss_news.py`** fetches ESPN's RSS and gets XML. The `<guid>` becomes
   `article_id`, `<dc:creator>` becomes `author`, and the RFC-822 date string becomes a real
   `datetime`. **This is the boundary** — nothing downstream knows RSS exists.
3. **`processing/dedup.py`** checks the id against previous runs. First time: kept. Second
   run: dropped.
4. **`storage/db.py`** supplied that set of ids, from a SQLite file that survives the process
   exiting.
5. **`processing/priority.py`** classifies it `low` — it matches *fiancée*, an off-court
   signal — so it sorts behind roster news.
6. **`delivery/brief.py`** renders title, a truncated description, and a byline. No URL, no
   timestamp.
7. **`delivery/telegram.py`** sends it. Only then does `main.py` record it as delivered.

## The one idea worth understanding

Everything in the middle depends on **interfaces**, never on a concrete source or
destination.

```
          main.py
             │ depends on
             ▼
   NewsSourceAdapter (abstract)          DeliveryChannel (abstract)
             ▲                                    ▲
      ┌──────┴──────┐                    ┌────────┴────────┐
  RssNewsAdapter  (future)         TelegramChannel   StdoutChannel
```

Adding CBS Sports required **one dictionary entry** and no new parsing code. Swapping
Telegram for something else is one new class. That property is not decorative — it is what
lets an external tool relay briefs to WhatsApp without a single line of WhatsApp code
entering this repository ([ADR-013](../decisions/ADR-013-openclaw-stays-external.md)).

The same shape appears four times: source adapters, delivery channels, the summarizer, and
the process boundary itself.

## Two patterns that carry real weight

**Failure policy lives in the base class.** Adapters implement `_fetch()`; the abstract
`fetch()` wraps it in try/except and returns `[]`. An adapter author *cannot forget* error
handling, because they never write the method that contains it. A dead feed shortens the
brief; it never ends the run.

**Recording happens after delivery, never before.** If items were marked as sent first and
the send then failed, the next run would consider them delivered and skip them — losing them
permanently and silently.

## Deliberately absent

| Not used | Why |
|---|---|
| Docker | Runs on one machine; a virtualenv already isolates dependencies |
| Postgres, an ORM, migrations | SQLite is a file with full SQL. Workload is tens of rows |
| Embeddings / vector search | Measured: no real near-duplicate pair exists to catch |
| async | A synchronous run takes about a second |

Each of these was in the previous version of this project, and none of them ever delivered a
message.

**LLM summarisation used to appear in that table** as *built, disabled*. `[VERIFIED]` It has
shipped **enabled** since 2026-08-10 (ADR-012). Every local model tested did invent player
names, which is why it is wrapped: `processing/validate.py` checks every proper name and
figure in the generated text against the source articles, retries, and falls back to the plain
headline list when nothing passes. The model is not trusted; the check is.

## Where things live

| Path | Responsibility |
|---|---|
| `models/schemas.py` | The only place a game or article shape is defined |
| `ingestion/` | Source adapters + the abstract contract |
| `processing/` | dedup, priority, highlights, summarize |
| `storage/db.py` | What has already been delivered |
| `delivery/` | Channels + brief formatting |
| `config/settings.py` | The only place `.env` is read |
| `main.py` | The single entrypoint; the only file naming a concrete class |
