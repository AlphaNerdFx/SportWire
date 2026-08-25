"""Turns games, highlights and articles into the messages that get delivered.

Presentation only. Receives lists that are already fetched, already deduplicated and
already analysed, and never decides *what* to include — only how it reads. Keeping that
boundary means the brief's wording can change without touching ingestion or dedup.

Three messages rather than one, per the operator's spec:

  1. Scoreboard — every game with its score, a quick overview.
  2. Notable events — comebacks, overtime, and the night's standout games, with the reason.
  3. News — non-statistical updates from the feed.

An empty section is omitted entirely rather than sent as a heading with nothing under it.
`[VERIFIED]` No games at all is the normal case outside the season, so most of the year
message 1 and 2 simply will not exist.

Output is plain text rather than Telegram MarkdownV2: that format requires escaping
roughly eighteen reserved characters, and one unescaped character in a headline returns
HTTP 400. Real headlines are full of apostrophes, quotes and emoji.

No timestamps are printed. Telegram already stamps every message with its send time, so
repeating it inside the body is noise. `[INFERRED]` The exception worth watching: an
article published three days ago, delivered in a message stamped "now", reads as breaking
news. That is a real risk once the feed reaches back further than the polling interval —
revisit if stale items start appearing.
"""

from __future__ import annotations

from models.schemas import GameData, GameHighlight, NewsArticle, SeriesContext

DEFAULT_SUMMARY_LIMIT = 256

# Most articles a single brief will carry. `[VERIFIED]` 2026-08-06: two feeds produced 53
# articles in one run — 11,155 characters, three Telegram messages of headlines alone. The
# PRD's real success criterion is that the brief gets read, and nobody reads that.
#
# Articles arrive already ranked by `processing/priority.py`, so the cap keeps roster and
# on-court news and drops the tail of analysis and off-court items. `[INFERRED]` 12 is a
# judgement, not a measurement: roughly a phone screen of scrolling. Raise it if briefs feel
# thin, lower it if they go unread.
DEFAULT_MAX_ARTICLES = 12

# Machine-readable category -> the wording used in the brief. Kept here, in presentation,
# so `processing/highlights.py` never has to care how a category is phrased.
#
# **The four ranked categories are deliberately not worded as superlatives.** `[VERIFIED]`
# 2026-08-13 (TASKS.md P10): a game is reported once, so when one game holds several records
# the ranked categories are reassigned to the best *unclaimed* game. On the real 2026-01-15
# slate Dallas held the widest margin (22), the biggest quarter (43) and the highest total
# (266); it is reported as the quarter, and `largest_margin` then names Houston at 20.
#
# "Biggest win — Houston by 20" would be **false** with a 22-point win on the same slate.
# "Big win" is true either way. `[INFERRED]` The alternative — leaving the category silent —
# loses two real lines from the brief, and the alternative of labelling only the true holder
# needs two labels per category and a rule the reader cannot see. A brief that overstates is
# worse than one that understates; that is the same principle as `processing/validate.py`.
_CATEGORY_LABELS = {
    "comeback": "Comeback",
    "overtime": "Overtime",
    "closest_finish": "Close finish",
    "wire_to_wire": "Wire to wire",
    "second_half_takeover": "Second-half takeover",
    "biggest_period": "Big quarter",
    "largest_margin": "Big win",
    "highest_scoring": "High scoring",
}


def build_messages(
    games: list[GameData],
    highlights: list[GameHighlight],
    article_groups: list[list[NewsArticle]],
    summary_limit: int = DEFAULT_SUMMARY_LIMIT,
    news_summary: str | None = None,
    max_articles: int = DEFAULT_MAX_ARTICLES,
    series: dict[int, SeriesContext] | None = None,
    unsupported_claims: list[str] | None = None,
    failed_sources: list[str] | None = None,
) -> list[str]:
    """Render the brief as an ordered list of message bodies, omitting empty sections.

    **`article_groups` must already be ranked most-important-first** — sort with
    `processing.priority.sort_by_priority`, then cluster with
    `processing.cluster.group_related`, which preserves that order. Each group is one story,
    its first entry the best-ranked article covering it. The `max_articles` cap keeps the front of the
    list, so unsorted input silently drops whatever happens to be last. `[VERIFIED]`
    2026-08-06: the snapshot test called this with raw feed order and the cap removed
    "How LeBron landed in Philadelphia", the biggest story in the feed.

    `news_summary` is written prose from the summarizer. When it is None — the summarizer is
    offline, or was never configured — message 3 falls back to the headline list. The
    fallback is the point: a headline list is never wrong, so losing the summary degrades
    the brief rather than breaking it.

    Returns an empty list when there is nothing at all to report, which the caller should
    treat as "send nothing" rather than sending an empty brief.
    """
    messages: list[str] = []

    if games:
        messages.append(_render_scoreboard(games, series))

    if highlights:
        messages.append(_render_highlights(highlights))

    if article_groups:
        if news_summary:
            messages.append(
                _render_news_summary(
                    news_summary, unsupported_claims or [], failed_sources or []
                )
            )
        else:
            # Truncation happens here, in presentation, not in dedup: the dropped articles
            # are still recorded as delivered, so they will not reappear next run. They were
            # ranked lowest, not missed. The cap counts *stories*, so one widely-covered
            # event no longer consumes half the brief.
            messages.append(
                _render_news(
                    article_groups[:max_articles], summary_limit, len(article_groups)
                )
            )

    return messages


def _render_scoreboard(
    games: list[GameData], series: dict[int, SeriesContext] | None = None
) -> str:
    """Message 1 — every game and its score, with season-series context where known."""
    lines = ["🏀 SCORES", ""]
    series = series or {}

    for game in games:
        lines.append(
            f"{game.away_team} {game.away_score} @ "
            f"{game.home_team} {game.home_score}  ({game.status})"
        )
        note = _series_note(game, series.get(game.game_id))
        if note:
            lines.append(f"   {note}")

    return "\n".join(lines)


def _series_note(game: GameData, context: SeriesContext | None) -> str:
    """One clause of season-series context, or "" when there is nothing worth saying.

    A first meeting produces nothing. `[INFERRED]` "First meeting this season" is true of
    every fixture in October and carries no information; the note exists to say how the
    rivalry stood, and before a rivalry has started there is nothing to report.
    """
    if context is None or context.is_first_meeting:
        return ""

    ordinal = _ordinal(context.meeting_number)
    home_wins = context.home_team_prior_wins
    away_wins = context.away_team_prior_wins

    if home_wins == away_wins:
        return f"{ordinal} meeting — series level at {home_wins}-{away_wins}"

    leader, trailing = (
        (game.home_team, away_wins)
        if home_wins > away_wins
        else (game.away_team, home_wins)
    )
    return f"{ordinal} meeting — {leader} led {max(home_wins, away_wins)}-{trailing}"


def _ordinal(number: int) -> str:
    """1 -> "1st". Small helper because "2th meeting" would be an embarrassing bug."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _render_highlights(highlights: list[GameHighlight]) -> str:
    """Message 2 — why particular games were worth noticing."""
    lines = ["📊 NOTABLE", ""]
    for highlight in highlights:
        game = highlight.game
        label = _CATEGORY_LABELS.get(highlight.category, highlight.category)
        lines.append(f"{label} — {_describe(highlight)}")
        lines.append(
            f"   {game.away_team} {game.away_score} @ "
            f"{game.home_team} {game.home_score}"
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def _describe(highlight: GameHighlight) -> str:
    """One clause explaining what made this game notable, using its own numbers."""
    game = highlight.game
    winner = game.home_team if game.home_score > game.away_score else game.away_team

    if highlight.category == "comeback":
        return f"{winner} came back from {game.largest_deficit_overcome} down"
    if highlight.category == "overtime":
        overtimes = max(game.period - 4, 1)
        suffix = "" if overtimes == 1 else f" ({overtimes} OT)"
        return f"{winner} won in overtime{suffix}"
    if highlight.category == "closest_finish":
        return f"decided by {game.margin}"
    if highlight.category == "wire_to_wire":
        return f"{winner} led at every break"
    if highlight.category == "second_half_takeover":
        return f"{winner} outscored them by {game.second_half_swing} after half time"
    if highlight.category == "biggest_period":
        return f"a {game.biggest_period}-point quarter"
    if highlight.category == "largest_margin":
        return f"{winner} by {game.margin}"
    if highlight.category == "highest_scoring":
        return f"{game.total_points} combined points"
    return ""


# ~~Appended to a sentence whose named entities never share a source article.~~
# **Removed from the brief 2026-08-26 on the operator's instruction:** *"remove the warning
# about the names. I don't want it."*
#
# The detection stays. `main.py` still computes the flagged sentences and logs them, so
# `TASKS.md` P5 remains countable over a soak and nothing about the check was weakened. What
# is gone is the mark and its legend reaching the phone.
#
# `[VERIFIED]` The marker's only production firing was a **false** one, on 2026-08-26: a true
# sentence about James Harden and the Cavaliers, flagged because `_entity_pairs` joined a
# title to its own summary. So its one real-world contribution was noise, which makes this an
# easy call rather than a reluctant one.
#
# Original note, kept because the reasoning still applies if it ever returns:
#
# `[VERIFIED]` 2026-08-18: the operator was sent "The Pelicans, who are welcoming back star
# point guard Damian Lillard following his trade from Portland". No such trade happened. Every
# name in it is real and present in the batch, so `validate.py` grounds them all; what is
# invented is the relationship, which is TASKS.md P5.
#
# `[VERIFIED]` The operator chose marking over rejecting on 2026-08-18. Rejecting the sentence
# rejects the summary, and that run would then have delivered a headline list on all three
# attempts, which is the outcome he had just asked never to see again. So the claim is
# delivered and labelled, and the reader decides.
def _render_news_summary(
    summary: str, unsupported: list[str], failed_sources: list[str] | None = None
) -> str:
    """Message 3, written form: one paragraph instead of a headline list.

    Flagged sentences keep their place in the prose and gain a mark, so the paragraph still
    reads as a paragraph. `[INFERRED]` Moving them to a footnote or dropping them would either
    break the writing the operator asked for or hide a claim he needs to see.
    """
    body = f"📰 NEWS\n\n{summary}"
    # A source that failed is named, because otherwise the brief is quietly shorter and looks
    # complete. `[VERIFIED]` 2026-08-18: Reddit returned HTTP 500 for a whole run, costing 25
    # of 87 articles, and the only trace was a log line the operator would never see.
    if failed_sources:
        missing = ", ".join(failed_sources)
        body += f"\n\nMissing this run: {missing}. Those stories are not in the brief."
    return body


def _render_story_group(group: list[NewsArticle], summary_limit: int) -> list[str]:
    """One story: its best article, plus who else covered it.

    `[VERIFIED]` 2026-08-08 one live capture had seven r/nba posts on a single Kawhi Leonard
    story. Showing all seven wastes most of a brief; showing one and silently discarding six
    hides that it was widely reported. Naming the other outlets does both jobs — corroboration
    is information, and "also on ESPN" says more about a rumour than any headline does.
    """
    best = group[0]
    lines = [best.title]

    summary = _truncate(best.summary, summary_limit)
    if summary:
        lines.append(summary)

    byline = best.author or best.source

    if len(group) > 1:
        # Other outlets, not other posts: three Reddit users on one story is noise, whereas
        # ESPN and CBS both carrying it is a signal about the story.
        others = sorted({article.source for article in group[1:]} - {best.source})
        if others:
            lines.append(f"— {byline}  (also {', '.join(others)})")
        else:
            lines.append(f"— {byline}  (+{len(group) - 1} more)")
    else:
        lines.append(f"— {byline}")

    return lines


def _render_news(
    groups: list[list[NewsArticle]], summary_limit: int, total_stories: int
) -> str:
    """Message 3 — one entry per story, not per article. No links, no dates.

    Takes **groups** rather than articles because the brief reports stories: seven posts
    about one investigation is one thing that happened. `total_stories` is the count before
    the cap, so the brief can say how many were left out — silently showing 12 of 53 would
    look like the other 41 never existed.
    """
    lines = ["📰 NEWS", ""]

    for group in groups:
        lines.extend(_render_story_group(group, summary_limit))
        lines.append("")

    omitted = total_stories - len(groups)
    if omitted > 0:
        lines.append(f"+ {omitted} more, ranked lower")

    return "\n".join(lines).rstrip()


def _truncate(text: str, limit: int) -> str:
    """Shorten to `limit` characters, cutting at a word boundary rather than mid-word."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed

    # Reserve one character for the ellipsis so the result never exceeds the limit.
    clipped = collapsed[: limit - 1]
    last_space = clipped.rfind(" ")
    if last_space > 0:
        clipped = clipped[:last_space]
    return f"{clipped}…"
