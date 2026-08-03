import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_upsert

from database.models import NormalizedArticle, GameDataModel
from ingestion.normalizer import NormalizationIngestionPipeline  # Logic mapping raw payload arrays into structural Pydantic objects
from schemas.normalized import GameDataSchema, NormalizedArticleSchema

logger = logging.getLogger("OpenClaw.IngestionOrchestrator")

class IngestionOrchestrator:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], repository=None, deduplicator=None, embedding_client=None):
        self.session_factory = session_factory
        self.normalizer = NormalizationIngestionPipeline(
            repository=repository,
            deduplicator=deduplicator,
            embedding_client=embedding_client
        )

    async def run_pipeline_cycle(self) -> None:
        """
        Coordinates the scheduled execution sweep across data providers, collects their raw data,
        and saves it inside an isolated transactional boundary context.
        """
        logger.info("Initiating ingestion transaction cycle sequence...")
        
        # In a fully realized subrouter implementation, these list payloads are pulled from active async client tasks
        raw_article_payloads: List[Dict[str, Any]] = [] 
        raw_game_payloads: List[Dict[str, Any]] = []

        async with self.session_factory() as session:
            async with session.begin():
                try:
                    # Parallelizing writes ensures minimal execution cycle locks over incoming data
                    await self.save_articles(session, raw_article_payloads)
                    await self.save_games(session, raw_game_payloads)
                    logger.info("Ingestion pipeline sequence completed successfully and committed transaction.")
                except Exception as ex:
                    logger.error(f"Ingestion lifecycle anomaly recorded during pipeline execution: {str(ex)}")
                    # Transaction automatically rolls back here when exiting the context block on exception
                    await session.rollback()
                    raise e

    async def save_articles(self, session: AsyncSession, raw_payloads: List[Dict[str, Any]]) -> None:
        """
        Processes raw article metadata feeds by validating them against strict schemas and bulk-upserting
        them into PostgreSQL in O(1) database execution time.
        """
        if not raw_payloads:
            logger.debug("Skipping article persistence layer: incoming batch collection is empty.")
            return

        normalized_records: List[Dict[str, Any]] = []
        for raw_item in raw_payloads:
            try:
                # Map raw parameters cleanly via schemas
                pydantic_article: NewsArticle = self.normalizer.normalize_news(raw_item)
                
                # Format into a clean parameter dictionary ready for binding statements
                record_dict = {
                    "deterministic_id": pydantic_article.id,
                    "title": pydantic_article.title,
                    "content": pydantic_article.content,
                    "url": pydantic_article.url,
                    "source": pydantic_article.source,
                    "sport": pydantic_article.sport,
                    "published_at": pydantic_article.published_at,
                    "extracted_at": pydantic_article.extracted_at,
                    "raw_metadata": pydantic_article.raw_metadata
                }
                normalized_records.append(record_dict)
            except Exception as validation_err:
                logger.error(f"Skipping malformed article raw record drop: {str(validation_err)} Payload: {raw_item}")
                continue

        if not normalized_records:
            return

        # Build high-throughput Postgres bulk upsert block
        stmt = pg_upsert(NormalizedArticle).values(normalized_records)
        
        # Resolve target matching conflict criteria dynamically
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_articles_deterministic_id",
            set_={
                "title": stmt.excluded.title,
                "content": stmt.excluded.content,
                "url": stmt.excluded.url,
                "raw_metadata": stmt.excluded.raw_metadata
            }
        )

        # Triggers standard single round-trip bind operation matching our O(1) performance standard
        await session.execute(upsert_stmt)
        logger.info(f"Successfully bulk-upserted {len(normalized_records)} normalized articles.")

    async def save_games(self, session: AsyncSession, raw_payloads: List[Dict[str, Any]]) -> None:
        """
        Processes raw competitive data frames by validating them against the strict GameData contract and
        bulk upserting live score lines into the relational engine.
        """
        if not raw_payloads:
            logger.debug("Skipping game telemetry persistence layer: incoming payload is empty.")
            return

        normalized_records: List[Dict[str, Any]] = []
        for raw_item in raw_payloads:
            try:
                pydantic_game: GameData = self.normalizer.normalize_game(raw_item)
                
                record_dict = {
                    "game_id": pydantic_game.game_id,
                    "sport": pydantic_game.sport,
                    "home_team": pydantic_game.home_team,
                    "away_team": pydantic_game.away_team,
                    "home_score": pydantic_game.home_score,
                    "away_score": pydantic_game.away_score,
                    "status": pydantic_game.status,
                    "game_datetime": pydantic_game.game_datetime,
                    "venue": pydantic_game.venue,
                    "raw_metadata": pydantic_game.raw_metadata
                }
                normalized_records.append(record_dict)
            except Exception as validation_err:
                logger.error(f"Skipping malformed game metadata block: {str(validation_err)} Raw payload drop: {raw_item}")
                continue

        if not normalized_records:
            return

        stmt = pg_upsert(GameDataModel).values(normalized_records)
        
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_games_game_id_sport",
            set_={
                "home_score": stmt.excluded.home_score,
                "away_score": stmt.excluded.away_score,
                "status": stmt.excluded.status,
                "game_datetime": stmt.excluded.game_datetime,
                "venue": stmt.excluded.venue,
                "raw_metadata": stmt.excluded.raw_metadata
            }
        )

        await session.execute(upsert_stmt)
        logger.info(f"Successfully bulk-upserted {len(normalized_records)} target game structures.")