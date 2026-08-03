# test_backend.py
import asyncio
from storage.database import init_db, AsyncSessionLocal
from storage.repository import SportsPersistenceRepository

async def test():
    print("Bootstrapping Database Tables...")
    await init_db()
    
    async with AsyncSessionLocal() as session:
        repo = SportsPersistenceRepository(session)
        
        mock_article = {
            "source_provider": "ESPN",
            "source_id": "nba_1029384",
            "title": "LeBron James Hits Game Winner against Celtics",
            "content": "In an exciting overtime match-up, LeBron James hit a deep step-back fading jumper as time expired to secure victory...",
            "url": "https://espn.com/nba/story/1",
            "published_at": None
        }
        
        print("Testing Ingestion Pathway...")
        saved = await repo.save_news_article(mock_article)
        print(f"Article Ingested Safely: {saved}")
        
        print("Testing Idempotency / Deduplication Guardrail...")
        duplicate_saved = await repo.save_news_article(mock_article)
        print(f"Duplicate Article Blocked (Should be False): {duplicate_saved}")

if __name__ == "__main__":
    asyncio.run(test())