"""Turns games, highlights and articles into the messages that get delivered.

Presentation only. Receives lists that are already fetched, already deduplicated and
already analysed, and never decides *what* to include — only how it reads. Keeping that
boundary means the brief's wording can change without touching ingestion or dedup.

Three messages rather than one, per the operator's spec:

  1. Scoreboard — every game with its score, a quick overview.
  2. Notable events — comebacks, overtime, and the night's superlatives, with the reason.
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

from models.schemas import GameData, GameHighlight, NewsArticle

DEFAULT_SUMMARY_LIMIT = 256

# Machine-readable category -> the wording used in the brief. Kept here, in presentation,
# so `processing/highlights.py` never has to care how a category is phrased.
_CATEGORY_LABELS = {
    "comeback": "Comeback",
    "overtime": "Overtime",
    "closest_finish": "Closest finish",
    "largest_margin": "Biggest win",
    "highest_scoring": "Highest scoring",
}


def build_messages(
    games: list[GameData],
    highlights: list[GameHighlight],
    articles: list[NewsArticle],
    summary_limit: int = DEFAULT_SUMMARY_LIMIT,
    news_summary: str | None = None,
) -> list[str]:
    """Render the brief as an ordered list of message bodies, omitting empty sections.

    `news_summary` is written prose from the summarizer. When it is None — the summarizer is
    offline, or was never configured — message 3 falls back to the headline list. The
    fallback is the point: a headline list is never wrong, so losing the summary degrades
    the brief rather than breaking it.

    Returns an empty list when there is nothing at all to report, which the caller should
    treat as "send nothing" rather than sending an empty brief.
    """
    messages: list[str] = []

    if games:
        messages.append(_render_scoreboard(games))

    if highlights:
        messages.append(_render_highlights(highlights))

    if articles:
        if news_summary:
            messages.append(_render_news_summary(news_summary))
        else:
            messages.append(_render_news(articles, summary_limit))

    return messages


def _render_scoreboard(games: list[GameData]) -> str:
    """Message 1 — every game and its score."""
    lines = ["🏀 SCORES", ""]
    for game in games:
        lines.append(
            f"{game.away_team} {game.away_score} @ "
            f"{game.home_team} {game.home_score}  ({game.status})"
        )
    return "\n".join(lines)


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
    if highlight.category == "largest_margin":
        return f"{winner} by {game.margin}"
    if highlight.category == "highest_scoring":
        return f"{game.total_points} combined points"
    return ""


def _render_news_summary(summary: str) -> str:
    """Message 3, written form — one paragraph instead of a headline list."""
    return f"📰 NEWS\n\n{summary}"


def _render_news(articles: list[NewsArticle], summary_limit: int) -> str:
    """Message 3 — headline, author, and a truncated description. No links, no dates."""
    lines = ["📰 NEWS", ""]
    for article in articles:
        lines.append(article.title)

        summary = _truncate(article.summary, summary_limit)
        if summary:
            lines.append(summary)

        # Author is genuinely optional — `[VERIFIED]` absent on 2 of 15 real ESPN items —
        # so the byline falls back to the source rather than printing "None".
        lines.append(f"— {article.author or article.source}")
        lines.append("")

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
