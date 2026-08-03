from abc import ABC, abstractmethod
from datetime import datetime
import hashlib
from typing import Any, Dict, List
from ingestion.models import NewsArticle, NewsSource, LeagueType

class BaseNewsClient(ABC):
    """Abstract base class ensuring all scrapers map to the unified NewsArticle schema."""
    
    @abstractmethod
    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[NewsArticle]:
        pass

    def _generate_fallback_id(self, url: str, title: str) -> str:
        """Generates a stable unique hash identifier if the scraper lacks an explicit ID."""
        unique_str = f"{url or ''}{title or ''}"
        return hashlib.md5(unique_str.encode('utf-8')).hexdigest()


class ESPNNewsClient(BaseNewsClient):
    """Parses raw items from the ESPN NBA News / Trade Tracker APIs hosted on Apify."""
    
    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[NewsArticle]:
        normalized_articles = []
        for item in raw_data:
            # ESPN Apify items usually contain an explicit ID, title, text/description, and ISO timestamp
            raw_id = item.get("id") or item.get("articleId")
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            
            # Map unique internal ID
            article_id = f"espn_{raw_id}" if raw_id else f"espn_{self._generate_fallback_id(url, title)}"
            
            # Extract content body, falling back to summary/description fields if needed
            content = item.get("text") or item.get("content") or item.get("description") or ""
            
            # Parse Datetime robustly
            pub_at_raw = item.get("publishedAt") or item.get("date")
            try:
                published_at = datetime.fromisoformat(pub_at_raw.replace("Z", "+00:00")) if pub_at_raw else datetime.utcnow()
            except (ValueError, TypeError):
                published_at = datetime.utcnow()
                
            # Check for league indicators or default to NBA based on the target API source
            league = LeagueType.NBA
            if "nfl" in url.lower() or "nfl" in title.lower():
                league = LeagueType.NFL

            normalized_articles.append(
                NewsArticle(
                    article_id=article_id,
                    title=title,
                    content=content.strip(),
                    url=url,
                    source=NewsSource.ESPN,
                    league=league,
                    published_at=published_at,
                    tags=item.get("categories", []) or item.get("tags", [])
                )
            )
        return normalized_articles


class HoopsHypeClient(BaseNewsClient):
    """Normalizes unstructured raw feeds or parsed rumors from HoopsHype."""
    
    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[NewsArticle]:
        normalized_articles = []
        for item in raw_data:
            title = item.get("title", "").strip()
            url = item.get("link") or item.get("url", "").strip()
            content = item.get("text") or item.get("description", "").strip()
            
            article_id = f"hoopshype_{self._generate_fallback_id(url, title)}"
            
            # Web scrapers for rumors often output simplified dates or ISO fields
            pub_at_raw = item.get("time") or item.get("date")
            try:
                published_at = datetime.fromisoformat(pub_at_raw) if pub_at_raw else datetime.utcnow()
            except (ValueError, TypeError):
                published_at = datetime.utcnow()

            normalized_articles.append(
                NewsArticle(
                    article_id=article_id,
                    title=title,
                    content=content,
                    url=url,
                    source=NewsSource.HOOPSHYPE,
                    league=LeagueType.NBA,  # HoopsHype exclusively covers basketball/NBA
                    published_at=published_at,
                    tags=["rumor", "nba-intel"]
                )
            )
        return normalized_articles


class SportsTrackerClient(BaseNewsClient):
    """Normalizes raw unstructured records parsed from the general SportsTracker web portal."""
    
    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[NewsArticle]:
        normalized_articles = []
        for item in raw_data:
            # SportsTracker scraper uses custom field names like article_title, source_url, body, pub_date
            title = item.get("article_title", "").strip()
            url = item.get("source_url", "").strip()
            content = item.get("body", "").strip()
            
            article_id = f"sportstracker_{self._generate_fallback_id(url, title)}"
            
            pub_at_raw = item.get("pub_date")
            try:
                # Custom handler for space-separated SQL string timestamps e.g. "2026-07-04 18:30:00"
                if pub_at_raw and " " in pub_at_raw and "T" not in pub_at_raw:
                    published_at = datetime.strptime(pub_at_raw, "%Y-%m-%d %H:%M:%S")
                elif pub_at_raw:
                    published_at = datetime.fromisoformat(pub_at_raw)
                else:
                    published_at = datetime.utcnow()
            except (ValueError, TypeError):
                published_at = datetime.utcnow()
                
            # Deduce League based on URL/Title tags
            league = LeagueType.GENERAL
            combined_text = f"{title} {url}".lower()
            if "nba" in combined_text:
                league = LeagueType.NBA
            elif "nfl" in combined_text:
                league = LeagueType.NFL

            normalized_articles.append(
                NewsArticle(
                    article_id=article_id,
                    title=title,
                    content=content,
                    url=url,
                    source=NewsSource.SPORTSTRACKER,
                    league=league,
                    published_at=published_at,
                    tags=item.get("metadata_tags", [])
                )
            )
        return normalized_articles