import asyncio
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger("OpenClaw.Scheduler")

class ConcurrentPollingEngine:
    def __init__(self, pipeline: Any):
        self.pipeline = pipeline
        self.workers = []
        self.is_running = False
        self._tasks: list[asyncio.Task] = []

    async def create_polling_worker(
        self, 
        name: str, 
        interval_seconds: int, 
        fetch_func: Callable[[], Awaitable[Any]], 
        adapter: Any, 
        is_news: bool = True):
        self.workers.append((name, interval_seconds, fetch_func, adapter))
    
    async def start_polling(self):
        """Asynchronously triggers isolation run loops across all configured active scraper workers."""
        async def run_worker(name, interval, fetch, adapt):
            while True:
                try:
                    payload = await fetch.poll()
                    await self.pipeline.ingest_news_feed(adapt, payload)
                except Exception:
                    # Isolate error and yield context execution to background loops
                    pass
                await asyncio.sleep(interval)

        await asyncio.gather(*(run_worker(*w) for w in self.workers))

    def start(self, client_workers: list[dict]):
        """Bootstraps all configured scraper loops concurrently within the active asyncio thread loop."""
        self.is_running = True
        for config in client_workers:
            task = asyncio.create_task(
                self.create_polling_worker(
                    name=config["name"],
                    interval_seconds=config["interval"],
                    fetch_func=config["fetch_function"],
                    adapter=config["adapter"],
                    is_news=config.get("is_news", True)
                )
            )
            self._tasks.append(task)
        logger.info(f"Concurrent Polling Engine active with {len(self._tasks)} worker engines tracking targets.")

    async def stop(self):
        """Gracefully terminates worker polling loops during maintenance or deployments."""
        logger.info("Initiating engine shutdown sequences...")
        self.is_running = False
        # Cancel all running tasks concurrently
        for task in self._tasks:
            task.cancel()
        # Await clean resolution releases
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("All background polling workers halted cleanly.")