import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from ingestion.base import BaseSourceAdapter
from ingestion.schemas import NormalizedNews
from models.schemas import NewsArticle

logger = logging.getLogger("IngestionPipeline")

class ApifyNewsAdapter(BaseSourceAdapter):
    def __init__(self, provider_tag: str = "", client_token: str = "", actor_id: str = "", sport: str = "", source_label: str = ""):
        self.provider_tag = provider_tag
        self.token = client_token
        self.actor_id = actor_id
        self._sport = sport
        self._source_label = source_label

    @property
    def source_name(self) -> str:
        return self.provider_tag or f"apify_{self._source_label}_{self._sport.lower()}"

    def fetch_raw_payload(self) -> Any:
        """Hits the Apify API client to scrape latest platform data."""
        # Simulated run or integration using standard requests/apify-client package
        # returning an array of parsed dictionary articles
        pass 

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[NewsArticle]:
        normalized_articles = []
        for item in raw_data:
            try:
                # Map raw properties cleanly to models.schemas.NewsArticle requirements
                constructed = {
                    "title": item.get("title") or item.get("headline"),
                    "body": item.get("description") or item.get("text") or item.get("story"),
                    "summary": item.get("summary"),
                    "url": item.get("url"),
                    "source": self.source_name,
                    "sport": self._sport,
                    "tags": item.get("categories", []),
                    "published_at": datetime.now(timezone.utc), # Standard fallback or parse item dynamic field
                    "metadata": {"raw_id": item.get("id")}
                }
                
                valid_article = self.safe_parse_article(constructed)
                if valid_article:
                    normalized_articles.append(valid_article)
            except Exception as e:
                logger.warning(f"Error mapping Apify item payload: {e}")
                continue
        return normalized_articles

    def transform_news(self, raw_data: List[Dict[str, Any]]) -> List[NormalizedNews]:
        """
        Maps raw Apify item payloads into NormalizedNews objects.
        Drops any item where the content body is missing or None.
        """
        results = []
        for item in raw_data:
            content = item.get("content") or item.get("text") or item.get("description")
            if not content:
                continue
            try:
                pub_raw = item.get("publishedAt") or item.get("date")
                published_at = (
                    datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                    if pub_raw else datetime.now(timezone.utc)
                )
                results.append(
                    NormalizedNews(
                        source_provider=self.provider_tag or self.source_name,
                        source_id=str(item.get("id", "")),
                        title=(item.get("title") or "").strip(),
                        content=content.strip(),
                        url=item.get("url"),
                        published_at=published_at
                    )
                )
            except Exception as e:
                logger.warning(f"Skipping malformed Apify item: {e}")
                continue
        return results

    def transform_games(self, raw_data: Any) -> list:
        """Apify news adapters do not provide game telemetry."""
        return []