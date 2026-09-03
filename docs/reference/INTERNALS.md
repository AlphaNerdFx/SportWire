# Internals — every non-trivial function, and why it is shaped that way

This document explains **decisions**, not behaviour. What each function does is readable from
the code; why it takes the arguments it takes, returns what it returns, and lives where it
lives is not.

Read `ARCHITECTURE.md` first for the shape of the system. This is the level below that.

---

## `models/schemas.py`

Three frozen Pydantic models. Imports nothing else in the project — it is the bottom of the
dependency graph, which is what lets every other namespace depend on it without cycles.

### `GameData`

**Why `frozen=True`.** A game object crosses ingestion → dedup → priority → highlights →
formatting. If any stage could mutate it, a wrong score at delivery could have originated in
any of five places. Immutability deletes that debugging category outright rather than
mitigating it.

**Why `period: int = 0` has a default.** A game that has not tipped off has no periods. Zero
is representable and means "not started"; making it required would force adapters to invent a
value for a state that legitimately has none.

**Why `home_periods` / `away_periods` are lists, not fourteen fields.** The source provides
`home_q1`…`home_q4` plus `home_ot1`…`ot3`. Overtime is open-ended, and every use is a
*scan* (walk the periods accumulating a score) rather than a lookup of one specific quarter.
Fourteen named fields would encode a fixed maximum and make every consumer index by name.

### `GameData.largest_deficit_overcome`

Walks the cumulative score at each period boundary and returns the biggest deficit the
eventual winner faced.

**Why it lives on the model rather than in `processing/`.** It is a fact about a game,
derivable from that game's own fields. Putting it here means every consumer computes it
identically; putting it in `processing/` would invite a second, subtly different version.

**Why it documents its own limit.** `[VERIFIED]` The source gives period *totals*, not
play-by-play, so a team down 20 mid-quarter that levels by the buzzer never appears to have
trailed. The docstring says so. A function whose limits are undocumented gets trusted beyond
them.

**Why it returns 0 rather than `None` when data is missing.** Callers compare against a
threshold. `None` would force every call site to handle absence; 0 means "no comeback", which
is the correct answer when periods are unknown.

### `GameData.state_hash`

`sha256(game_id | status | home_score | away_score)`.

**Why no timestamp.** This is the single most load-bearing decision in the file. Including one
means every poll produces a new hash, so nothing ever matches the stored set, so **every game
is re-sent on every run** — dedup becomes a no-op. The hash must change only when the *game*
changes.

**Why not `game_id` alone.** A game at half time and the same game at final are genuinely
different information. Keying on identity alone would deliver the half-time score and then
suppress the final one.

**Why hash rather than store the tuple.** Fixed-width keys keep the storage layer ignorant of
what a game is. `storage/db.py` stores opaque strings and never learns the schema.

### `NewsArticle._parse_rss_date`

A `field_validator(mode="before")` that accepts RFC-822 dates.

**Why it exists.** Pydantic parses ISO-8601 natively; RSS emits RFC-822
(`Tue, 4 Aug 2026 17:12:16 EST`). Without this, every article would fail validation.

**Why it returns the original value on failure instead of raising.** Returning the unparsed
string lets Pydantic attempt ISO-8601 and then produce its own error message, which names the
field and shows the value. Raising here would replace a good error with a worse one.

**Why parse at the boundary at all.** A malformed date fails at the adapter, where the source
is obvious. Stored as a string, it would fail later during formatting, three layers from the
cause.

### `NewsArticle.author: str | None`

**Why optional.** `[VERIFIED]` Absent on 2 of 15 real ESPN items, present on all 36 CBS items.
Typing it `str` would have crashed on live data within the first run. This is the clearest
example in the codebase of a field shape decided by measurement rather than intuition.

### `NewsArticle.dedup_hash` vs `article_id`

Two identity concepts, deliberately separate. `article_id` identifies a **document** — one
outlet's copy. `dedup_hash` (normalised title) identifies a **story**, so the same event from
two outlets could collapse.

`[VERIFIED]` In practice it never fires: outlets write their own headlines, and across 612
real cross-source pairs the maximum similarity was 0.439. Kept because it is nearly free and
would catch genuine verbatim republication.

---

## `ingestion/base.py`

### The `_fetch` / `fetch` split

```python
@abstractmethod
def _fetch(self) -> list[NewsArticle]: ...   # subclasses write this

def fetch(self) -> list[NewsArticle]:        # subclasses never touch this
    try:
        return self._fetch()
    except Exception:
        logger.exception(...)
        return []
```

**Why not just tell adapter authors to handle errors.** Because they forget, and the failure
is invisible — a crashed run sends nothing, and nothing reports why. Here the policy lives in
a method they never write, so it **cannot** be skipped. This is the template method pattern,
and it is used for exactly one reason: making the correct behaviour the only available
behaviour.

**Why catch bare `Exception`.** Deliberately broad. A source can fail by timeout, malformed
XML, DNS failure, unexpected JSON shape, or a bug in the adapter. Enumerating them would
guarantee missing one, and the correct response to all of them is identical: log it, return
nothing, let the rest of the brief through.

**Why `logger.exception` rather than `logger.error`.** It includes the traceback. A degraded
brief with no diagnostic is a silent failure wearing a disguise.

### Two ABCs rather than one

`NewsSourceAdapter` returns `list[NewsArticle]`; `GameSourceAdapter` returns `list[GameData]`.

**Why not a shared base.** A combined `fetch()` would return "a list of either kind", forcing
`main.py` to check which. That check is source knowledge leaking back into the pipeline — the
exact thing this boundary removes.

### `source_name` as an abstract property

**Why abstract rather than a constructor argument on the base.** It forces every adapter to
declare its own identity, and it is available for logging before any fetch is attempted —
including in the error path, where you most need to know which source died.

---

## `ingestion/rss_news.py`

### `FEEDS` as a dict rather than one class per outlet

**Why.** `[VERIFIED]` CBS Sports' feed uses byte-identical structure to ESPN's — same
`./channel/item` path, same element names, same Dublin Core namespace. The ESPN parser ran on
the CBS payload unchanged. Two classes would have been two copies of one parser differing only
in a URL and a label.

RSS is a specification. Sources that conform to it are configuration, not code.

### `parse()` is public; `_fetch()` is private

**Why the split.** `_fetch` does the HTTP; `parse` does the conversion. Tests call `parse`
with a saved fixture and never touch the network — which is what makes the test suite fast,
deterministic, and runnable in CI with no credentials.

This is the single most reused idea in the codebase: **separate acquiring data from
interpreting it, and the interpretation becomes testable.**

### `_parse_item` returns `None` instead of raising

**Why.** One malformed `<item>` should not discard the other fourteen. Returning `None` lets
the caller skip it; raising would abort the batch.

**Why the required fields are `guid`, `title`, `link`, `pubDate`.** Each is load-bearing:
without `guid` an article cannot be deduplicated, without `title` there is nothing to show.
`description` is absent from the list on purpose — it is not identity-bearing, so an empty
string is an acceptable default rather than grounds for discarding a real story.

### `article_id = f"{source}:{guid}"`

**Why namespaced.** ESPN issues `US-EN-49531647`; CBS issues bare UUIDs. Two independent
namespaces with no coordination. Without the prefix a collision would silently suppress a
story — and a suppressed story is invisible by definition.

### `_text()` returning `None` for empty strings

**Why collapse empty and absent.** `<dc:creator></dc:creator>` and a missing tag mean the same
thing: no author. Returning `""` for one and `None` for the other would push that distinction
onto every call site for no benefit.

---

## `ingestion/nba_games.py`

### API key injected via constructor

**Why not read `os.getenv` here.** A component that fetches its own configuration cannot be
tested without setting global state. `BallDontLieGamesAdapter(api_key="dummy")` constructs
cleanly in a test with no `.env`, no environment, no mocking.

It also keeps configuration in one place (`config/settings.py`), so there is exactly one
answer to "where does this value come from".

### `_period_scores` stops at the first missing overtime

```python
for key in ("q1", "q2", "q3", "q4", "ot1", "ot2", "ot3"):
    value = raw.get(f"{side}_{key}")
    if value is None:
        if key.startswith("ot"):
            break      # overtimes are contiguous; the first gap ends the game
        continue       # a missing quarter is a gap, not an ending
```

**Why quarters `continue` but overtimes `break`.** A game in progress may have `q3` but not
`q4`; the periods played are still contiguous from the start. But a null `ot1` means the game
ended in regulation, so everything after it is null too. Treating both the same would either
truncate live games or append nulls.

### `status` defaults to `"Unknown"` rather than raising

**Why.** `[VERIFIED]` Every captured game reads `Final` — development happened entirely during
the offseason, so no live game has ever been observed. The docstring records this as
`[UNKNOWN]` rather than pretending the field is understood. A default keeps the pipeline
running against a shape nobody has seen yet.

---

## `processing/dedup.py`

### Every function is pure

`deduplicate_articles(articles, seen_article_ids, threshold)` takes the seen-set as an
argument rather than reading a database.

**Why.** This module was written and fully tested **before `storage/db.py` existed** — called
with `set()` for a first run and a populated set for a repeat run. A function handed data
needs nothing to test it; a function that opens a database needs a database, a schema, and
cleanup.

It also means the caller decides where "seen" comes from. SQLite today; anything else later,
with no change here.

### Pass 1 before pass 2

**Why order matters.** Pass 1 is an O(1) set lookup; pass 2 is `SequenceMatcher` against every
kept article. Running the cheap exact check first means the expensive fuzzy comparison only
ever runs on genuinely new items.

### `_find_similar` compares against `kept`, not `articles`

**Why.** Comparing against everything would let a near-duplicate pair delete *both* copies.
Comparing against survivors means the first occurrence wins and exactly one survives.

### `deduplicate_games` keys on `state_hash`, not `game_id`

See `GameData.state_hash` above. A game whose score moved is new information.

### Threshold 0.85, and why it is not tuned

`[VERIFIED]` Across 612 real cross-source pairs the maximum similarity was **0.439**. Nothing
collapses at any threshold down to 0.50, and below that genuinely unrelated stories begin
merging.

**The value stays at 0.85 not because it was tuned to be right, but because nothing in real
data reaches it.** Lowering it can only cause false merges. That distinction is recorded in
the module because otherwise a future reader would assume it was measured and validated.

---

## `processing/priority.py`

### It sorts and never filters

`len(sort_by_priority(articles)) == len(articles)` always. The operator was explicit that no
news should be dropped; truncation happens later, in presentation, where the brief can say how
many were omitted.

### Why classification rather than asking the model

`[VERIFIED]` Given an explicit instruction to lead with roster news and put off-court items
last, `llama3.2:3b` opened with a child-support filing and closed with LeBron James changing
teams. Two prompt revisions did not move it.

Sorting the input is deterministic, free, testable, and — unlike a learned ranking —
**inspectable**: anyone can read the word lists and predict the output. That last property
matters more than it sounds, because it is the difference between a system you can debug and
one you can only observe.

### `_words()` emits hyphenated tokens both whole and split

**Why both forms are needed.** Keeping hyphens is required for `re-ups`; splitting them is
required for `ex-fiancée`, which otherwise never matches `fiancée`. `[VERIFIED]` Before this,
a child-support story was classified `medium` instead of `low`.

### Low beats high when both match

**Why.** An article about a player's wedding that happens to contain the word "deal" is still
a wedding story. Misfiling an off-court item as important is more visible in a brief than the
reverse.

---

## `processing/highlights.py`

### Superlative **and** threshold

A category reports the single most extreme game, **and only if** it clears a bar.

**Why both.** Superlative alone would crown a six-point win "biggest blowout" on a quiet
night. Threshold alone flagged **5 of 9 games** in the first draft and labelled two different
games "largest margin" — which the real fixture made visible immediately.

### Comeback and overtime report every instance; the rest report one

**Why the asymmetry.** "Biggest" is the entire point of a superlative — reporting two is
incoherent. But overtime and comebacks are rare enough that each is independently worth
knowing, and there is no "most overtime".

### Categories are machine keys, not display text

`GameHighlight(category="comeback")`, never `"Comeback —"`. The wording lives in
`delivery/brief.py`.

**Why.** Rewording the brief must not touch the logic that decides what is notable. It also
leaves translation possible without rewriting analysis.

### A game appears once, under its highest-priority category

**Consequence, documented rather than hidden:** when one game is both the biggest blowout and
the highest-scoring, the `highest_scoring` category silently produces nothing that night. The
alternative — the same game listed twice with different labels — reads worse.

---

## `processing/summarize.py`

### `_summarise` takes articles, not a finished prompt

**Why the interface changed.** How many model calls a summariser needs is the implementation's
business. `OllamaSummarizer` makes four (three note-extractions plus one reduce); a hosted
model with a large context window would make one. An interface that handed over a single
prompt string would have forced that decision on every implementation.

### `summarise()` returns `None` rather than raising

**Why.** `None` means "fall back to the headline list", not "fail the run". A summariser that
is offline degrades the brief exactly as a dead source shortens it.

### The map step produces **notes**, not prose

**Why this specific design.** Naive map-reduce summarises prose into prose, and the result
reads like welded fragments — each chunk brings its own opening and rhythm. Extracting bare
facts means **only the final call ever writes a sentence**, so the paragraph is composed once,
in one pass, exactly as it would be for a short batch.

### Chunking at all

`[VERIFIED]` Given all 15 articles in one call, the model omitted the two LeBron-to-
Philadelphia items entirely — the biggest story in the feed — while including a child-support
filing. The same model with the same prompt covered them when they were moved to the front.
It was not judging badly; it was barely reading the tail.

### `build_reduce_prompt` states the note count

`[VERIFIED]` Without it the model stopped after ~700 characters having covered 10 of 15 notes
— not from a context limit (the prompt is ~1,100 characters) but because the paragraph *felt*
finished. Naming the number gives it a condition to satisfy rather than a sense of completion
to follow.

### `_note_lines` strips preamble

The model prefixes its notes with "Here are the summaries:" despite being told not to. That
line is not a fact, and counting it would inflate the number the reduce step is asked to
satisfy.

### Why the whole module is disabled by default

See ADR-012. Every model tested fabricates, and the substitutions are systematic: a less
famous name is replaced by a more famous one from the same organisation, because the training
prior beats the prompt context. The more newsworthy the subject, the more likely it is
corrupted.

---

## `storage/db.py`

### Stores identifiers only, never content

**Why.** The store answers one question: *have I sent this?* Storing titles would make it a
second source of truth about articles, and two sources of truth diverge. That is precisely how
the prototype ended up with four `NewsArticle` definitions.

### `INSERT OR IGNORE`

**Why not plain `INSERT`.** Re-running after a partial failure must not raise. Idempotent
writes mean the recovery path is "run it again", which requires no special handling anywhere.

### Rows are kept forever

**Why no purge.** `[VERIFIED]` ESPN lists items up to ~4 days old. A window shorter than the
feed's reach makes an already-sent story look new again on every cycle — an 8-hour window
would leave 3 of 17 items re-delivered indefinitely. `DEDUP_WINDOW_HOURS=168` records the
intent; nothing reads it yet because at tens of rows a purge solves nothing.

### `_utc_now()` returns an ISO string

SQLite has no native datetime type. ISO-8601 sorts lexicographically, so string comparison is
chronological comparison — which is what a future purge would need.

### Context-manager protocol

`__enter__`/`__exit__` so `main.py` can use `with`, guaranteeing the connection closes even
if delivery raises.

---

## `delivery/`

### `base.py` mirrors `ingestion/base.py`

Same `_send`/`send` split, same reason: the failure policy lives where a channel author cannot
skip it. `send()` returns `bool` rather than raising, so one failed message does not abandon
the rest of the brief.

### `silent` is accepted and ignored by `StdoutChannel`

**Why honour a parameter that means nothing here.** "Do not ring the recipient's phone" has no
meaning for a stream. But a channel that rejected messages it considered irrelevant would make
the caller aware of which channel it holds — and the caller holding an abstraction is the whole
point.

### `split_for_telegram` breaks on blank lines

**Why not a hard character split.** Telegram rejects messages over 4096 characters with HTTP
400. Splitting on blank lines keeps each story intact rather than severing one mid-sentence. A
single item longer than the limit is hard-split as a last resort — an API error would lose
everything, so a graceless split is the better failure.

### `StdoutChannel` flushes

**Why explicitly.** Standard output is block-buffered when piped rather than attached to a
terminal. Without the flush, a consumer reading incrementally receives nothing until the
process exits.

### `brief.py` — why plain text, not Markdown

**Telegram supports Markdown.** The problem is MarkdownV2 requires escaping ~18 reserved
characters, and **one unescaped character returns HTTP 400** — the entire message fails. Real
headlines contain apostrophes, quotes, `$52.2M` and emoji. Plain text cannot fail that way.

### `build_messages` assumes sorted input

**Why this is documented in the docstring.** The `max_articles` cap keeps the *front* of the
list. `[VERIFIED]` The snapshot test called this with raw feed order and the cap removed "How
LeBron landed in Philadelphia" — the biggest story in the feed. An undocumented precondition
that fails silently is worse than no precondition.

### `_truncate` cuts at a word boundary and reserves a character

Cutting mid-word reads like a bug. Reserving one character for the ellipsis means the result
never exceeds the limit — an off-by-one that would only appear at exactly the boundary.

### The cap prints `+ N more, ranked lower`

**Why say so.** Showing 12 of 53 silently would look like the other 41 never existed. The
dropped articles are still recorded as delivered — they were ranked lowest, not missed, and
will not reappear next run.

---

## `config/settings.py`

### `PROJECT_ROOT` derived from `__file__`

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(env_file or PROJECT_ROOT / ".env")
```

**Why not the working directory.** `[VERIFIED]` This was a real bug. Cron starts in `$HOME`,
so `.env` was not found at all — no API key, no bot token, no brief — while manual runs from
the project directory worked perfectly. The failure was invisible precisely because the
development path never exercised it.

The same applies to `DATABASE_PATH`: a bare relative path would give scheduled runs their own
database in `$HOME`, splitting dedup state and re-sending stories.

### Missing credentials are not fatal at load time

**Why `can_fetch_games` and `require_delivery` are separate.** A missing balldontlie key should
drop the games section; a missing Telegram token means the brief cannot be delivered at all.
Different severities, so the decision belongs to the caller rather than to loading.

### Malformed values raise instead of falling back

**Why not default silently.** `POLL_INTERVAL_HOURS=eight` is a typo. Falling back to 8 would
hide it forever. The error names the setting and shows the value.

### Frozen dataclass

Configuration read differently by two parts of one run is a bug that is very hard to see.

---

## `main.py`

### The only file that names concrete classes

Everything below depends on interfaces. This is the file that decides `RssNewsAdapter` and
`TelegramChannel` are the implementations in use — which is why adding CBS was one dictionary
entry, and why an external tool can relay to WhatsApp with no WhatsApp code in the repo.

### Recording happens after delivery

```python
delivered = sum(channel.send(m, silent=i > 0) for i, m in enumerate(messages))
if delivered == 0:
    return 1
store.record_games(fresh_games)
store.record_articles(fresh_articles)
```

**Why this order is not negotiable.** Reverse it and a failed send marks items delivered
forever; the next run skips them. They are lost, permanently, and nothing errors.

### `silent=index > 0`

The first message rings the phone; the rest arrive quietly. A three-part brief is one
notification, not three.

### `--dry-run` and `--channel stdout` are different

`--dry-run` prints and records **nothing** — for inspecting output. `--channel stdout` prints
**and records**, exactly as Telegram does — for an external relay. `[VERIFIED]` A relay built
on `--dry-run` would re-send every story on every run forever.

### Exit codes

`0` success or nothing to report, `1` delivery failed, `2` configuration error. A scheduler
can distinguish "nothing happened" from "something is broken" without parsing logs.
