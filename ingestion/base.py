import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Optional
from pydantic import ValidationError
from ingestion.schemas import NormalizedNews, NormalizedGame
from models.schemas import NewsArticle, GameData

logger = logging.getLogger("IngestionPipeline")

class BaseSourceAdapter(ABC):
    """
    Abstract Base Class for all data ingestion sources.
    Forces each source to implement a standard fetch/normalize interface.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Returns the unique identifier for this source (e.g., 'espn_scraper')."""
        pass

    @abstractmethod
    def fetch_raw_payload(self) -> Any:
        """
        Executes the network I/O or library calls. 
        Must return the raw data structure (list of dicts, dataframe, etc.)
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: Any) -> List[Union[NewsArticle, GameData]]:
        """
        Maps raw API/Scraper data to your standard Pydantic models.
        """
        pass

    def run(self) -> List[Union[NewsArticle, GameData]]:
        """
        The main orchestration loop. 
        This handles errors at the source level so one failing source
        doesn't crash the entire ingestion pipeline.
        """
        logger.info(f"Starting ingestion cycle for: [{self.source_name}]")
        try:
            raw_data = self.fetch_raw_payload()
            if not raw_data:
                logger.warning(f"No data returned from {self.source_name}.")
                return []
            
            return self.normalize(raw_data)
            
        except Exception as e:
            logger.error(f"Critical failure in Adapter [{self.source_name}]: {str(e)}", exc_info=True)
            return []

    def safe_parse_article(self, article_dict: Dict[str, Any]) -> Optional[NewsArticle]:
        """Utility to swallow schema errors for individual articles."""
        try:
            return NewsArticle(**article_dict)
        except ValidationError as ve:
            logger.warning(f"Skipping corrupt article in [{self.source_name}]: {ve.json()}")
            return None

    def safe_parse_game(self, game_dict: Dict[str, Any]) -> Optional[GameData]:
        """Utility to swallow schema errors for individual game records."""
        try:
            return GameData(**game_dict)
        except ValidationError as ve:
            logger.warning(f"Skipping corrupt game in [{self.source_name}]: {ve.json()}")
            return None

class BaseIngestionAdapter(ABC):
    """Abstract interface enforcing uniform data transformation behavior across all sports sources."""
    
    @abstractmethod
    def transform_news(self, raw_data: Any) -> List[NormalizedNews]:
        """Converts raw news JSON feeds into strictly-validated data models."""
        pass

    @abstractmethod
    def transform_games(self, raw_data: Any) -> List[NormalizedGame]:
        """Converts raw league score metrics into strictly-validated data models."""
        pass