import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from ingestion.scheduler import ConcurrentPollingEngine # Adjust to your scheduler class name

async def test_scheduler_fault_tolerance_and_isolation():
    """Ensures that a slow/broken scraper track does not freeze other concurrent loops."""
    
    # Worker 1 simulates a totally failed scraper endpoint throwing a severe network Timeout Error
    failed_scraper_client = AsyncMock()
    failed_scraper_client.poll.side_effect = asyncio.TimeoutError("Apify Gateway Timeout Failure")
    
    # Worker 2 operates flawlessly on another concurrent background schedule
    healthy_api_client = AsyncMock()
    healthy_api_client.poll.return_value = {"status": "success", "data": []}

    mock_pipeline = AsyncMock()
    engine = ConcurrentPollingEngine(pipeline=mock_pipeline)
    await engine.create_polling_worker(
    name="Apify_Broken_Scraper", 
    interval_seconds=1, 
    fetch_func=failed_scraper_client, 
    adapter=AsyncMock()
    )
    await engine.create_polling_worker(
    name="NBA_Healthy_API",
    interval_seconds=1, 
    fetch_func=healthy_api_client, 
    adapter=AsyncMock()
    )

    # Boot the system engine loop, but forcefully break out after 0.25 seconds using an async timeout blanket
    try:
        await asyncio.wait_for(engine.start_polling(), timeout=0.25)
    except asyncio.TimeoutError:
        pass # Expected termination of the continuous runtime harness

    # Critical Architecture Assertions:
    # 1. The broken worker was executed at least once
    assert failed_scraper_client.poll.call_count >= 1
    # 2. Even though Worker 1 crashed repeatedly, the Engine caught the error cleanly, and Worker 2 successfully polled concurrently!
    assert healthy_api_client.poll.call_count >= 1