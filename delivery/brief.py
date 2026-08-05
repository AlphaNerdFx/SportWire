"""Turns games and articles into the single text block that gets delivered.

This is presentation only. It receives lists that are already fetched and already
deduplicated, and it never decides *what* to include — only how it reads. Keeping that
boundary means the brief's wording can change without touching ingestion or dedup.

Output is deliberately plain text rather than Telegram MarkdownV2: that format requires
escaping roughly eighteen reserved characters, and one unescaped character in a headline
returns HTTP 400 from the API. Real headlines are full of apostrophes, quotes and emoji,
so plain text is the safe default. Rich formatting can be layered on later behind this
same function.
"""

from __future__ import annotations

from models.schemas import GameData, NewsArticle

DEFAULT_SUMMARY_LIMIT = 256


def build_brief(
    games: list[GameData],
    articles: list[NewsArticle],
    summary_limit: int = DEFAULT_SUMMARY_LIMIT,
) -> str:
    """Render the brief. Games first, then news; empty sections are omitted entirely.

    `[VERIFIED]` An empty games list is the normal case outside the season — balldontlie
    returns no Summer League or G-League games, so "offseason" and "no games" are the same
    condition and need no special handling.
    """
    sections: list[str] = []

    if games:
        sections.append(_render_games(games))

    if articles:
        sections.append(_render_news(articles, summary_limit))

    if not sections:
        return "SportWire — nothing to report."

    return "\n\n".join(sections)


def _render_games(games: list[GameData]) -> str:
    """One line per game: away team and score, at home team and score, then status."""
    lines = ["GAMES", ""]
    for game in games:
        lines.append(
            f"  {game.away_team} {game.away_score} "
            f"@ {game.home_team} {game.home_score}  ({game.status})"
        )
    return "\n".join(lines)


def _render_news(articles: list[NewsArticle], summary_limit: int) -> str:
    """Headline, truncated summary, then attribution and link."""
    lines = ["NEWS", ""]
    for index, article in enumerate(articles, start=1):
        lines.append(f"  {index}. {article.title}")

        summary = _truncate(article.summary, summary_limit)
        if summary:
            lines.append(f"     {summary}")

        # Author is genuinely optional — `[VERIFIED]` absent on 2 of 15 real ESPN items —
        # so the byline degrades to source and date rather than printing "None".
        byline = article.author or article.source
        lines.append(f"     {byline} · {article.published_at:%d %b %Y %H:%M}")
        lines.append(f"     {article.url}")
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
