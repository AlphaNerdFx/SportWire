import logging
import random
import time
from typing import Dict, Any, Optional
import httpx

# Configure uniform production-grade logger logging hooks
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ScraperBase")

# Production User-Agents rotation bank to prevent automated block listing
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

class BaseScraper:
    """
    Handles robust HTTP infrastructure across all sub-scrapers, 
    including exponential backoff retries and dynamic user-agent injection.
    """
    def __init__(self, timeout: float = 12.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    def get_headers(self) -> Dict[str, str]:
        """Generates dynamic browser-emulated headers."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }

    def fetch_url_json(self, url: str) -> Optional[Dict[str, Any]]:
        """Executes a GET request returning a parsed JSON dictionary with retry mechanisms."""
        headers = self.get_headers()
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP code error fetching JSON from {url} (Attempt {attempt}/{self.max_retries}): {e}")
            except Exception as e:
                logger.error(f"Unexpected connectivity error fetching JSON from {url} (Attempt {attempt}/{self.max_retries}): {e}")
            
            if attempt < self.max_retries:
                time.sleep(2 ** attempt)  # Exponential backoff delay
        return None

    def fetch_url_text(self, url: str) -> Optional[str]:
        """Executes a GET request returning raw text/strings with retry mechanisms."""
        headers = self.get_headers()
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    return response.text
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP code error fetching text from {url} (Attempt {attempt}/{self.max_retries}): {e}")
            except Exception as e:
                logger.error(f"Unexpected connectivity error fetching text from {url} (Attempt {attempt}/{self.max_retries}): {e}")
            
            if attempt < self.max_retries:
                time.sleep(2 ** attempt)  # Exponential backoff delay
        return None
    
    @abc.abstractmethod
    def parse(self, html_content: str) -> list:
        """Parses the raw HTML into a list of dicts."""
        pass

    def fetch(self, endpoint: str) -> Optional[str]:
        """Fetches the raw HTML content."""
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            # Log the error and return None
            return None