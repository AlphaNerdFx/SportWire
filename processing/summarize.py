"""Turns a batch of articles into one written narrative, replacing the headline list.

Third use of the same boundary as `ingestion/base.py` and `delivery/base.py`: an abstract
interface, concrete implementations, and callers that depend only on the abstraction. Local
inference is the default (`SESSION.md` §9 Q4 — "local always, open-source first"), and a
hosted implementation can be added later without touching anything that calls this.

`[VERIFIED]` 2026-08-06 against `llama3.2:3b` on the 15-article fixture: 687 characters in
9.1 seconds, covering every story including the two the single-call version dropped.

`[VERIFIED]` Quality is not yet good, and the specific defects are recorded rather than
smoothed over:
  - **Prioritisation is wrong.** LeBron James signing with Philadelphia — the biggest item
    in the feed — closes the paragraph instead of opening it, despite the prompt.
  - **Minor factual drift.** The source says Wembanyama *"will host"* teammates; the model
    wrote *"hosted"*. The model is small enough to alter tense, which changes meaning.
  - **Preamble appears anyway** ("The NBA offseason is underway with several notable
    developments") despite an explicit instruction against it.
`[INFERRED]` These are model-capability limits rather than prompt bugs: two prompt revisions
did not fix ordering, while chunking fixed coverage completely.

**Model evaluation, 2026-08-06 — no 3B model tested is factually reliable here:**

| Model / run | Outcome |
|---|---|
| `llama3.2:3b`, run 1 | `[VERIFIED]` Fabricated a person: *"Tom Cachikis will be leaving his role with the Knicks"*. No such name appears anywhere in the source; the executive is Gersson Rosas. Also wrote "Chris Marshall" for Naji Marshall. |
| `llama3.2:3b`, run 2 | `[VERIFIED]` No invented names, 10 of 11 stories covered — but asserted DeRozan "won't be joining LeBron James in Philadelphia", which no item states, and merged Bosh's blood-clot warning with Wembanyama's France workouts into a single event that never happened. |
| `qwen2.5:3b` | `[VERIFIED]` Produced 187 characters stating *"There were no significant roster or on-court developments reported today"* — on a day a superstar changed teams. Also took 255s to load into RAM cold, though only 7.5s once warm. |

`[INFERRED]` The failures differ between runs of the *same* model at temperature 0.3, so
single-run testing cannot establish confidence at this size. Demanding fuller coverage buys
hallucination; demanding brevity buys silent omission. Both are worse than the plain headline
list, which is never wrong.

Input is title plus RSS description only (PRD D5). Article bodies would require fetching
article pages, which is the C3 scraping exposure ADR-009 exists to avoid. Scores are
deliberately excluded: they have their own message and are self-explanatory.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import cast

import requests

from models.schemas import NewsArticle
from processing.validate import validate_summary

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_CHARS = 1024

# How many times to ask the model before giving up and using the headline list.
#
# `[VERIFIED]` 2026-08-10: `mistral:7b` passed validation on 3 of 5 attempts over the same
# twelve articles, which suggested two attempts reach ~84% and three ~94%.
#
# `[VERIFIED]` 2026-08-13 that compounding does **not** hold. The 00:00 run failed all three
# attempts and invented the same name -- "Ayo Dosunmu" -- on every one. The arithmetic above
# assumes attempts fail independently; a model pattern-completing from a training prior fails
# the same way each time, so three attempts are not 1 - (1-p)^3, they are closer to one
# attempt repeated. `[INFERRED]` Retry rescues the *variable* failures and does nothing for
# the fixed ones, so the true benefit sits somewhere below the compounded figure and above
# the single-attempt one. Do not quote a number until the soak has counted enough runs.
#
# Three is kept anyway: `[VERIFIED]` the first call of a run pays a cold model load -- 490-668
# seconds against 16-19 for subsequent calls -- so retries are much cheaper than the first
# attempt. `[VERIFIED]` The worst case is real though, and was measured: a failing run spent
# 19 minutes before falling back to the headline list.
DEFAULT_ATTEMPTS = 3

# `[VERIFIED]` 2026-08-06, all four models run against the same 15-article fixture with the
# same prompts, scored on stories missed and names invented:
#
#   model          size    missed  invented  time
#   llama3.2:3b    2.0 GB   1-5     0-2      10-42s
#   qwen2.5:3b     1.9 GB   11/11   0        8s     (asserted nothing newsworthy happened)
#   gemma3:4b      3.3 GB   11/11   5        234s   (ignored the input entirely, see below)
#   mistral:7b     4.4 GB   0       0        337s   <- chosen
#
# Mistral was checked line by line against the source on that fixture: correct first name for
# Naji Marshall, the exact $52.2M figure, "PLYRS UNTD Performance Center" verbatim, and
# correct agency on both the Doncic petition and Jaylen Brown's remarks — all of which the 3B
# models got wrong.
#
# **That result did not hold.** `[VERIFIED]` Run against 17 live articles rather than the
# 15-article fixture, mistral:7b fabricated three people and a figure:
#
#   summary claim                                  source
#   "Devin Booker ... $73M extension with Suns"    "Suns keeping Brooks on 3-year, $73M"
#   "Malik Monk ... 1-year, $3.3M, Nuggets"        "Walker returning to NBA with 1-year
#                                                   Nuggets deal" (no figure given)
#   "Steve Nash's right-hand man, Leon Rose"       "Knicks executive Rosas leaving team"
#   "9 different champions in the last 8 years"    "eight different champions in eight years"
#
# `[INFERRED]` The single clean run was a property of that input, not of the model. Scoring
# one run is not evidence at this scale — which is the conclusion the 3B evaluation had
# already reached and which was then ignored. **Summarisation is therefore off by default**
# and gated behind `main.py --summary`. The headline list is never wrong.
#
# `[VERIFIED]` gemma3:4b is worth remembering as a cautionary case: it ignored the supplied
# articles and produced fluent, entirely fabricated NBA news — a Gabe Vincent signing, an
# Anthony Davis injury return, a Celtics-Pacers trade, a LeBron watch endorsement. None of it
# appears in the feed. It reads perfectly. This is the same failure mode as the fabricated
# handoff document that caused this repository to be rebuilt.
#
# 337 seconds is acceptable because nothing waits on it: the pipeline runs from cron every
# eight hours.
DEFAULT_MODEL = "mistral:7b"

# Generous, because a cold model load was measured at 193s before any inference begins.
DEFAULT_TIMEOUT_SECONDS = 600

# How long Ollama keeps the model resident after a request. `[VERIFIED]` 2026-08-27 the
# operator's machine has **7.4 GB of RAM total under WSL2, 5.3 GB free, with 656 MB of swap
# already in use**, and `mistral:7b` is 4.4 GB. Ollama's default is to hold the model for five
# minutes after the last request, so the machine stayed under that pressure long after the
# brief was delivered, for a program that runs once every eight hours and then has nothing to
# say. Releasing it immediately costs a reload on the next run, which is seconds, and returns
# the memory to the desktop, which is the thing the operator actually noticed.
# ~~UNLOAD_AFTER_RUN = "0s"~~ **Corrected 2026-08-27, hours after it was written.**
#
# `[VERIFIED]` Ollama's `keep_alive` says how long to hold the model after *that request*, not
# after the program finishes. Setting it to zero unloaded the model after **every call**, so a
# brief making three calls loaded the model three times. The escalation path made it obvious:
# `mistral:7b` spent over seven minutes on two chunks and a reduce, work the small model had
# just done in fifty seconds.
#
# `[INFERRED]` So the model stays resident across a run's calls and is released explicitly
# when the run is done. Two minutes rather than Ollama's default five, so a process that dies
# before releasing still gives the memory back reasonably soon.
KEEP_ALIVE_DURING_RUN = "2m"

# Hard ceiling on generated tokens. `[INFERRED]` The brief already has a character budget, so
# nothing downstream wants more than this; what it prevents is the pathological case where the
# model does not stop. `[VERIFIED]` One run on 2026-08-26 spent **600 seconds** in a single
# call and hit the read timeout, and a bounded generation cannot do that. Four characters per
# token is the usual rough ratio for English, and the margin is deliberate.
TOKEN_BUDGET_RATIO = 0.4

# The instruction is the whole "training". Steering the output — what to emphasise, what to
# skim — is editing this string, not fine-tuning a model. Recorded because the assumption
# that this needs training came up more than once.
SYSTEM_PROMPT = (
    "You write a short {league} news brief for one reader who wants to know what happened "
    "without opening a sports app.\n"
    "\n"
    "Structure:\n"
    "- Write two or three paragraphs, separated by a blank line. Never one solid block.\n"
    "- **Each paragraph covers one subject.** Every mention of a person or event belongs "
    "in the same paragraph, however the notes are ordered. If one note says a player "
    "retired and another says someone reacted to that retirement, both go together — "
    "never in separate paragraphs.\n"
    "- Order the paragraphs by importance: the biggest story first.\n"
    "\n"
    "Content:\n"
    "- Flowing prose, not a list. No bullets, no headings, no markdown.\n"
    "- Lead with roster and on-court news: trades, signings, injuries, returns.\n"
    "- Off-court and celebrity items get a clause at most, in the final paragraph.\n"
    "- State only what the notes say. Never add scores, statistics, dates or outcomes "
    "that are not present in them.\n"
    "- Never name a team the notes do not name, and never say who someone plays for "
    "unless the notes say it. If a note names a person without a team, write the person "
    "without a team.\n"
    "- If the notes are thin or routine, say so briefly rather than inflating them.\n"
    "- No preamble. Start with the news itself."
)

# Articles per model call before chunking kicks in. `[VERIFIED]` llama3.2:3b covered 5 of 5
# articles reliably but dropped items past roughly position 8 of 15.
CHUNK_SIZE = 5

# The map step deliberately produces **notes, not prose**. Summarising prose into prose is
# what makes naive map-reduce read like stitched fragments: each chunk gets its own opening,
# its own rhythm, and the reduce step welds them together. Extracting bare facts instead
# means only the final call ever writes a sentence, so the paragraph is composed once, in
# one pass, exactly as it is for a short batch.
NOTES_PROMPT = (
    "Extract the key facts from these {league} news items as terse notes.\n"
    "\n"
    "Rules:\n"
    "- One line per item. No prose, no sentences, no introduction.\n"
    "- Format: who — what happened — any figure that matters.\n"
    "- Keep names, teams, contract values and injury details exactly as given.\n"
    "- Do not add anything the items do not state. In particular, never attach a team to "
    "a person unless the item does.\n"
    "- Do not omit an item, however minor it seems.\n"
    "- Each item is marked with how old it is. When two items describe the same event,"
    " state it as the newest one does."
)


class Summarizer(ABC):
    """Turns articles into one paragraph of prose."""

    @property
    @abstractmethod
    def summarizer_name(self) -> str:
        """Human-readable label, e.g. "Ollama (llama3.2)". Used in logs."""

    def release(self) -> None:
        """Give back whatever this summarizer holds. Called when the run is finished.

        A no-op by default, which is right for a hosted model: nothing on this machine to
        release. `[VERIFIED]` It matters for local inference on the operator's machine, where
        the model is 4.4 GB against 5.3 GB of free RAM and Ollama would otherwise hold it for
        minutes after a program that runs every eight hours has stopped talking.

        Never raises. Failing to hand memory back is not a reason to lose a delivered brief.
        """

    def _prepare(self, articles: list[NewsArticle], max_chars: int) -> object:
        """Whatever the writing step needs, computed **once** for all attempts.

        `[VERIFIED]` 2026-08-27, and this seam exists entirely because of it. A long batch is
        chunked, and every chunk costs a model call to turn into notes. Those calls were
        inside the retry loop, so a three-attempt brief extracted the same notes three times:
        twelve model calls where six would do. The notes do not change between attempts, only
        the paragraph written from them does.

        The default returns the articles unchanged, which is right for any implementation
        that makes a single call: there is nothing to reuse.
        """
        return articles

    @abstractmethod
    def _write(
        self, prepared: object, articles: list[NewsArticle], max_chars: int
    ) -> str:
        """Produce the summary text from what `_prepare` returned. Allowed to raise.

        Called once per attempt. `articles` comes along because the prompts name the league
        the batch belongs to, and that is a property of the articles rather than of the notes.
        """

    def summarise(
        self,
        articles: list[NewsArticle],
        max_chars: int = DEFAULT_SUMMARY_CHARS,
        attempts: int = DEFAULT_ATTEMPTS,
        vocabulary_sample: list[NewsArticle] | None = None,
    ) -> str | None:
        """Summarise articles, retrying until the result survives validation.

        Returns None when no attempt produced something safe, which means "fall back to the
        headline list", not "fail the run". A summarizer that is offline or unreliable must
        degrade the brief exactly as a dead source does, never crash it (`CLAUDE.md` §5.6).

        **Retry only makes sense because the check is mechanical.** Retrying without a
        check would simply produce a different fabrication.

        **It also assumes attempts fail independently, and they do not always.** `[VERIFIED]`
        2026-08-13 the 00:00 run invented "Ayo Dosunmu" on all three attempts; an earlier run
        invented "Joe Dumars" three times over. `[INFERRED]` When the model is completing a
        strong training prior rather than sampling noise, every attempt lands in the same
        place and retry buys nothing but time. It still helps against the variable failures,
        which is why it stays.

        `[VERIFIED]` An earlier measurement on noisier input scored 0 of 3, and retry was
        correctly rejected then — at a zero pass rate it only burns time. What changed is the
        input, not the model: filtering retrospectives and capping per source left twelve
        coherent current stories instead of a mix including 2017 highlight clips and
        week-old articles.
        """
        if not articles:
            return None

        try:
            prepared = self._prepare(articles, max_chars)
        except Exception:
            # Preparation is one or more model calls too, so it fails the same ways. A
            # failure here means no attempt can run, which is the headline list.
            logger.warning(
                "%s failed while preparing", self.summarizer_name, exc_info=True
            )
            return None

        for attempt in range(1, max(1, attempts) + 1):
            try:
                text = self._write(prepared, articles, max_chars)
            except Exception:
                # `[VERIFIED]` 2026-08-10 a production run got HTTP 500 from Ollama on the
                # first attempt and gave up, delivering the headline list — an earlier
                # version returned here instead of continuing. Request failures are the
                # clearest case for retry: a 500 is transient, and a timeout has usually
                # just finished loading the model, so the next attempt is warm and fast.
                logger.warning(
                    "%s errored on attempt %d of %d",
                    self.summarizer_name,
                    attempt,
                    attempts,
                    exc_info=True,
                )
                continue

            cleaned = _tidy(text)
            if not cleaned:
                logger.warning("%s returned empty text", self.summarizer_name)
                continue

            # `vocabulary_sample` widens only the evidence for which capitalised words are
            # ordinary English. Names are still grounded against `articles`, the stories the
            # brief actually summarised. `[VERIFIED]` TASKS.md P32.
            result = validate_summary(cleaned, articles, vocabulary_sample)
            if result.is_safe:
                # `[VERIFIED]` 2026-08-14: this was guarded by `if attempt > 1`, so a summary
                # accepted first try logged nothing at all and the run read as
                # "summarising 12 stories" followed straight by "delivered". Success on the
                # cheapest path was the one outcome that left no trace, which makes the
                # pass rate uncountable in the direction that flatters it — P4's measured
                # floor of 2/19 could not have included a single attempt-1 acceptance.
                logger.info("summary accepted on attempt %d of %d", attempt, attempts)
                return cleaned

            logger.warning("attempt %d rejected (%s)", attempt, result.describe())

        # States what happened, not what follows from it. `[VERIFIED]` 2026-08-27 this said
        # "using the headline list", and once `EscalatingSummarizer` existed that was simply
        # untrue: the small model exhausting its attempts escalates to the big one, and the
        # log claimed a fallback that had not happened. `main` already logs the real
        # consequence when it gets None back, which is the layer that decides it.
        logger.warning(
            "%s: no attempt passed validation after %d tries",
            self.summarizer_name,
            attempts,
        )
        return None


class EscalatingSummarizer(Summarizer):
    """Try a small model first and only reach for a big one when the small one fails.

    `[VERIFIED]` 2026-08-27, the operator's machine: **7.4 GB of RAM under WSL2, 5.3 GB free,
    656 MB of swap already used**, against `mistral:7b` at 4.4 GB and `llama3.2:3b` at 2.0 GB.
    Running the big model for every brief is what made the desktop unusable, and most briefs
    do not need it: the task is compression of a few kilobytes of headlines.

    So the small model writes, the validator judges, and the big one is loaded only when the
    small one produced something that did not survive. `[INFERRED]` The escalation is worth
    having rather than simply switching models because the validator gives an honest signal to
    escalate *on*. Without it this would be a quality gamble; with it, the worst case is the
    behaviour the project already had.

    Each model prepares its own notes. `[INFERRED]` That is deliberate and it costs calls: a
    fabrication can enter at the note step as easily as at the writing step, so handing the
    big model the small one's notes would escalate the writing while keeping the mistake.

    Composition rather than a flag inside `OllamaSummarizer`, because "which model" and "what
    to do when a model fails" are two different decisions, and only one of them is about
    Ollama. `[INFERRED]` It also means a hosted model can be the second rung without this
    class learning anything new.
    """

    def __init__(
        self, first: Summarizer, then: Summarizer, first_attempts: int = 2
    ) -> None:
        self._first = first
        self._then = then
        self._first_attempts = max(1, first_attempts)

    @property
    def summarizer_name(self) -> str:
        return f"{self._first.summarizer_name} then {self._then.summarizer_name}"

    def _write(
        self, prepared: object, articles: list[NewsArticle], max_chars: int
    ) -> str:
        """Never called: `summarise` is overridden and delegates to the wrapped summarizers."""
        raise NotImplementedError

    def release(self) -> None:
        """Release both rungs. Either may hold a model, depending how far the run got."""
        self._first.release()
        self._then.release()

    def summarise(
        self,
        articles: list[NewsArticle],
        max_chars: int = DEFAULT_SUMMARY_CHARS,
        attempts: int = DEFAULT_ATTEMPTS,
        vocabulary_sample: list[NewsArticle] | None = None,
    ) -> str | None:
        """Small model first, then the capable one, splitting the attempt budget between them."""
        first_attempts = min(self._first_attempts, max(1, attempts))
        text = self._first.summarise(
            articles, max_chars, first_attempts, vocabulary_sample
        )
        if text is not None:
            return text

        # The small model goes before the big one arrives. `[VERIFIED]` 2026-08-27: 2.0 GB
        # plus 4.4 GB does not fit in 5.3 GB free, and the machine swapping is the whole
        # problem this ladder exists to avoid.
        self._first.release()

        remaining = max(1, attempts - first_attempts)
        logger.info(
            "%s did not pass in %d attempt(s); escalating to %s",
            self._first.summarizer_name,
            first_attempts,
            self._then.summarizer_name,
        )
        return self._then.summarise(articles, max_chars, remaining, vocabulary_sample)


class OllamaSummarizer(Summarizer):
    """Local inference via an Ollama server on this machine.

    Requires Ollama installed and a model pulled:
        curl -fsSL https://ollama.com/install.sh | sh
        ollama pull llama3.2:3b

    `[INFERRED]` A small model is sufficient here. The input is roughly 2–3 KB of short
    descriptions and the task is compression, not reasoning.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = "http://localhost:11434",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        chunk_size: int = CHUNK_SIZE,
        keep_alive: str = KEEP_ALIVE_DURING_RUN,
        token_budget: int = int(DEFAULT_SUMMARY_CHARS * TOKEN_BUDGET_RATIO),
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._chunk_size = chunk_size
        self._keep_alive = keep_alive
        self._token_budget = token_budget

    @property
    def summarizer_name(self) -> str:
        return f"Ollama ({self._model})"

    def _prepare(self, articles: list[NewsArticle], max_chars: int) -> object:
        """Extract the notes once, if this batch is long enough to need chunking.

        Returns None for a short batch, meaning "there is nothing to reuse, write straight
        from the articles". `[VERIFIED]` 2026-08-27: doing this inside the retry loop cost a
        three-attempt brief twelve model calls instead of six, on a machine with 5.3 GB of
        RAM free and a 4.4 GB model. The notes are identical every time; only the paragraph
        written from them differs.
        """
        if len(articles) <= self._chunk_size:
            return None

        chunks = [
            articles[index : index + self._chunk_size]
            for index in range(0, len(articles), self._chunk_size)
        ]
        logger.info(
            "%s: %d articles exceeds chunk size %d; extracting notes from %d chunks",
            self.summarizer_name,
            len(articles),
            self._chunk_size,
            len(chunks),
        )
        return [
            self._generate(notes_prompt(chunk), build_prompt(chunk, max_chars))
            for chunk in chunks
        ]

    def _write(
        self, prepared: object, articles: list[NewsArticle], max_chars: int
    ) -> str:
        """Write the paragraph, from notes when there are any and from the articles when not."""
        if prepared is None:
            return self._generate(
                system_prompt(articles), build_prompt(articles, max_chars)
            )
        notes = cast("list[str]", prepared)
        return self._generate(
            system_prompt(articles), build_reduce_prompt(notes, max_chars)
        )

    def release(self) -> None:
        """Ask Ollama to unload this model now, rather than holding it for `keep_alive`.

        A generate request carrying no prompt and `keep_alive: 0` is how Ollama is told to
        evict a model. `[VERIFIED]` 2026-08-27: 4.4 GB against 5.3 GB free is the difference
        between a usable desktop and one that swaps.

        Swallows everything. This runs after the brief is already built, so a failure costs
        some memory for two minutes and must never cost the brief.
        """
        try:
            requests.post(
                f"{self._host}/api/generate",
                json={"model": self._model, "keep_alive": 0},
                timeout=self._timeout_seconds,
            )
        except Exception:
            logger.debug("could not release %s", self._model, exc_info=True)

    def _generate(self, system: str, prompt: str) -> str:
        """One POST to Ollama's generate endpoint. Exceptions handled by `summarise`."""
        response = requests.post(
            f"{self._host}/api/generate",
            json={
                "model": self._model,
                "system": system,
                "prompt": prompt,
                "stream": False,
                # Low temperature: this is a factual summary, and invented trades would be
                # worse than a dull paragraph.
                "options": {
                    "temperature": 0.3,
                    "num_predict": self._token_budget,
                },
                # Held between this run's calls, then released. See `release`.
                "keep_alive": self._keep_alive,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json().get("response", "")


def _tidy(text: str) -> str:
    """Normalise whitespace **without** destroying paragraph breaks.

    `[VERIFIED]` 2026-08-12: the previous `" ".join(text.split())` collapsed every run of
    whitespace, newlines included, so a multi-paragraph summary arrived as one solid block.
    The prompt asking for paragraphs would have appeared to be ignored when in fact the
    model obeyed it and this step undid the work.

    Blank lines are preserved as paragraph separators; everything inside a paragraph is
    collapsed to single spaces.
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    paragraphs = [" ".join(block.split()) for block in blocks]
    return "\n\n".join(block for block in paragraphs if block)


def league_of(articles: list[NewsArticle]) -> str:
    """The league these articles belong to, for the prompts.

    `[VERIFIED]` 2026-08-26, and this is why it exists. Every prompt said "NBA news items",
    and after ADR-015 split the briefs the football batch was still being introduced as
    basketball. The model obliged: three attempts in a row attached NBA teams to NFL players,
    "Ashton Jeanty of the Timberwolves" and "Houston Rockets" where the Texans belonged, and
    the brief lost its prose to the validator catching them.

    Read from the articles rather than passed in, so it cannot disagree with the batch it
    describes. `[INFERRED]` Falls back to "sports" for a mixed batch, which no per-league run
    produces but a caller could; naming one league over a mixed batch is the exact mistake
    this function exists to stop making.
    """
    leagues = {article.league for article in articles}
    return leagues.pop() if len(leagues) == 1 else "sports"


def system_prompt(articles: list[NewsArticle]) -> str:
    """The writing instructions, naming the league this batch is actually about."""
    return SYSTEM_PROMPT.format(league=league_of(articles))


def notes_prompt(articles: list[NewsArticle]) -> str:
    """The note-extraction instructions, naming the league this batch is actually about."""
    return NOTES_PROMPT.format(league=league_of(articles))


def build_prompt(
    articles: list[NewsArticle],
    max_chars: int = DEFAULT_SUMMARY_CHARS,
    now: datetime | None = None,
) -> str:
    """Render articles into the user half of the prompt, each marked with its age.

    A plain module-level function so it can be tested, inspected and diffed without a model
    running — which is the only part of this module that can currently be verified.

    **The age is why this exists in this shape.** `[VERIFIED]` 2026-08-26 (TASKS.md P40) a
    brief said *"Thompson signed a two-year deal with the Heat and is expected to clear
    waivers soon"* when he had already cleared them. The batch held both stages of that story,
    CBS reporting it as expected and ESPN reporting it as done, and the prompt carried **no
    time information at all** — so the model could not have preferred the newer one. It was
    not ignoring recency; it was never given any.

    `now` is injectable rather than read from the clock inside, because `tests/conftest.py`
    fixes a "now" for exactly this reason and `[VERIFIED]` four tests written on 2026-08-18
    rotted within a week by reading the real clock (P37).
    """
    now = now or datetime.now(timezone.utc)
    instruction = (
        f"Summarise the following {len(articles)} {league_of(articles)} news items in at most "
        f"{max_chars} characters."
    )
    lines = [instruction, ""]

    for article in articles:
        lines.append(f"- [{_age(article.published_at, now)}] {article.title}")
        summary = " ".join(article.summary.split())
        if summary:
            lines.append(f"  {summary}")

    return "\n".join(lines)


def _age(published_at: datetime, now: datetime) -> str:
    """How old an item is, in the coarsest unit that still distinguishes two reports.

    `[INFERRED]` Hours rather than timestamps, because the question the model has to answer is
    "which of these two is later", and a relative age asks it directly. An ISO timestamp makes
    the same comparison a subtraction, which is exactly the kind of work a 7B model does
    badly. Under an hour reads as "just now" so a flurry of reports on one story does not all
    collapse to "0h".
    """
    hours = (now - published_at).total_seconds() / 3600
    if hours < 1:
        return "just now"
    if hours < 48:
        return f"{int(hours)}h ago"
    return f"{int(hours // 24)}d ago"


def build_reduce_prompt(
    notes: list[str], max_chars: int = DEFAULT_SUMMARY_CHARS
) -> str:
    """Render extracted notes into the final prompt that writes the paragraph.

    `[VERIFIED]` 2026-08-06: naming the item count is load-bearing. Without it the model
    stopped after roughly 700 characters having covered about ten of fifteen notes — not
    because the input was too long (the reduce prompt is barely 1,100 characters) but
    because the paragraph *felt* finished. Stating the number gives it a condition to
    satisfy instead of a sense of completion to follow.
    """
    lines = _note_lines(notes)
    instruction = (
        f"Write the brief from these {len(lines)} notes, in at most {max_chars} "
        f"characters. All {len(lines)} notes must appear in your answer — combine related "
        "ones into a single sentence rather than leaving any out. The notes are already in "
        "priority order; keep that order. Write one continuous piece of prose."
    )
    return "{}\n\n{}".format(instruction, "\n".join(lines))


def _note_lines(notes: list[str]) -> list[str]:
    """Flatten note blocks into individual fact lines, discarding any preamble.

    `[VERIFIED]` The model prefixes its notes with "Here are the summaries:" despite being
    instructed not to. That line is not a fact, and counting it would inflate the number the
    reduce step is asked to satisfy.
    """
    lines: list[str] = []
    for block in notes:
        for raw in block.splitlines():
            line = raw.strip()
            is_bullet = line[:1] in {"-", "*", "•"}
            is_numbered = line[:1].isdigit() and "." in line[:3]
            if is_bullet or is_numbered:
                lines.append(line)
    return lines
