import logging
import xml.etree.ElementTree as ET
import re
from typing import List, Dict, Any
from .base import BaseScraper

logger = logging.getLogger("HoopsHypeScraper")

class HoopsHypeScraper(BaseScraper):
    """
    Scrapes and breaks down raw narrative strings from HoopsHype's syndication index, 
    backed up by an atomic recovery parser in case of payload validation errors.
    """
    RUMORS_FEED_URL = "https://hoopshype.com/feed/"

    def fetch_rumors(self) -> List[Dict[str, Any]]:
        """Fetches and isolates raw text strings from recent basketball rumors."""
        logger.info("Accessing live syndication stream for HoopsHype text extractions...")
        raw_xml = self.fetch_url_text(self.RUMORS_FEED_URL)
        if not raw_xml:
            logger.warning("Aborting extraction sequence: HoopsHype raw string source is unavailable.")
            return []

        extracted_items = []
        try:
            # Clean string encoding layout to avoid XML parser breaking on bad characters
            clean_bytes = raw_xml.encode('utf-8', errors='ignore')
            root = ET.fromstring(clean_bytes)
            
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                description = item.find("description")
                
                extracted_items.append({
                    "title": title.text if title is not None else "",
                    "link": link.text if link is not None else "",
                    "published": pub_date.text if pub_date is not None else "",
                    "raw_text": description.text if description is not None else ""
                })
        except ET.ParseError as parse_err:
            logger.error(f"XML data error parsing HoopsHype stream ({parse_err}). Shifting to structural text extraction...")
            
            # Atomic structural extraction fallback utilizing string segment regex mapping
            titles = re.findall(r"<title><\!\[CDATA\[(.*?)\]\]></title>", raw_xml)
            if not titles:
                titles = re.findall(r"<title>(.*?)</title>", raw_xml)
            links = re.findall(r"<link>(.*?)</link>", raw_xml)
            
            for t, l in zip(titles, links):
                if "HoopsHype" in t and len(t) < 15:
                    continue  # Filter out global index header titles
                extracted_items.append({
                    "title": t,
                    "link": l,
                    "published": "Unknown",
                    "raw_text": t
                })
                
        logger.info(f"Successfully processed {len(extracted_items)} raw articles/rumors from HoopsHype.")
        return extracted_items