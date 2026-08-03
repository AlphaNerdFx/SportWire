import logging
from typing import List, Dict, Any
from .base import BaseScraper

logger = logging.getLogger("ESPNScraper")

class ESPNScraper(BaseScraper):
    """
    Direct client wrapper to query unauthenticated, hidden, direct mobile app API endpoints 
    powering ESPN's live application infrastructure.
    """
    NBA_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"
    NFL_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"

    def fetch_nba_news(self) -> List[Dict[str, Any]]:
        """Queries raw ESPN NBA headline wire dumps."""
        logger.info("Executing retrieval against public ESPN NBA mobile JSON wire...")
        data = self.fetch_url_json(self.NBA_NEWS_URL)
        if not data or "articles" not in data:
            logger.warning("ESPN NBA feed returned an empty dataset or unexpected format.")
            return []
        return data["articles"]

    def fetch_nfl_news(self) -> List[Dict[str, Any]]:
        """Queries raw ESPN NFL headline wire dumps."""
        logger.info("Executing retrieval against public ESPN NFL mobile JSON wire...")
        data = self.fetch_url_json(self.NFL_NEWS_URL)
        if not data or "articles" not in data:
            logger.warning("ESPN NFL feed returned an empty dataset or unexpected format.")
            return []
        return data["articles"]