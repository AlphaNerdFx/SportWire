from typing import List, Dict, Any
from datetime import datetime
from ingestion.base import BaseIngestionAdapter
from ingestion.schemas import NormalizedNews, NormalizedGame

class WebScraperAdapter(BaseIngestionAdapter):
    def transform_news(self, raw_items: List[Dict[str, Any]]) -> List[NormalizedNews]:
        normalized_list = []
        for item in raw_items:
            try:
                provider = item.get("source", "WebScraper").upper()
                
                normalized_news = NormalizedNews(
                    source_provider=provider,
                    source_id=str(item["post_id"]),
                    title=item["headline"].strip(),
                    content=item["body_text"].strip(),
                    url=item.get("permalink"),
                    published_at=datetime.now() # Fallback for flat RSS/Scrapes missing precise headers
                )
                normalized_list.append(normalized_news)
            except (KeyError, ValueError, TypeError):
                continue
        return normalized_list

    def transform_games(self, raw_data: Any) -> List[NormalizedGame]:
        return []