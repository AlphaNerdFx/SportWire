import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, List
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import NewsArticle, ArticleChunk, GameData
from storage.embedding_engine import embedding_engine

logger = logging.getLogger("Repository")

class SportsPersistenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _generate_hash(self, provider: str, source_id: str) -> str:
        raw_string = f"{provider.strip().lower()}:{source_id.strip().lower()}"
        return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    async def get_articles_since(self, time_cutoff: datetime) -> List[NewsArticle]:
        """
        Fetches articles published since the cutoff window for the 
        deduplicator's fast lexical/Jaccard pass.
        """
        stmt = select(NewsArticle).where(NewsArticle.published_at >= time_cutoff)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_semantic_duplicate(self, incoming_embedding: List[float], time_cutoff: datetime, threshold: float) -> Optional[int]:
        """
        Leverages pgvector directly in PostgreSQL to scan chunks within the 
        time window. Returns the article_id if a highly similar chunk is found.
        """
        # pgvector cosine_distance = 1 - cosine_similarity
        # Therefore, similarity >= threshold maps to distance <= (1 - threshold)
        distance_threshold = 1.0 - threshold

        stmt = (
            select(ArticleChunk.article_id)
            .join(NewsArticle)
            .where(NewsArticle.published_at >= time_cutoff)
            .where(ArticleChunk.embedding.cosine_distance(incoming_embedding) <= distance_threshold)
            .order_by(ArticleChunk.embedding.cosine_distance(incoming_embedding))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_news_article(self, article_data: dict, deduplicator: Any = None) -> bool:
        """
        Saves parsed metrics, splits content, builds embeddings, and handles upsert constraints.
        Integrates cascading deduplication checks to guard against duplicate data.
        """
        computed_hash = self._generate_hash(
            article_data["source_provider"], 
            article_data["source_id"]
        )

        # ---------------------------------------------------------------------
        # PASS 1: Fast Exact Natural Hash Check
        # ---------------------------------------------------------------------
        check_stmt = select(NewsArticle.id).where(NewsArticle.unique_hash == computed_hash)
        result = await self.session.execute(check_stmt)
        if result.scalar_one_or_none():
            logger.info(f"Exact duplicate detected via hash for source_id: {article_data['source_id']}")
            return False

        # ---------------------------------------------------------------------
        # PASS 2 & 3: Fuzzy Deduplication Gateway (Lexical & Semantic)
        # ---------------------------------------------------------------------
        if deduplicator:
            # Set a standard 48-hour window matching your requirements
            time_cutoff = datetime.utcnow() - timedelta(hours=48)
            recent_articles = await self.get_articles_since(time_cutoff)

            # Pass 2: Fast Lexical Title Match across recent headlines
            for existing in recent_articles:
                jaccard_score = deduplicator._calculate_jaccard(article_data["title"], existing.title)
                if jaccard_score >= deduplicator.title_threshold:
                    # Pass 3: Title matched, proceed to deep semantic verification in DB
                    # Generate a single vector representing the incoming article's context
                    incoming_vector_resp = deduplicator.embedding_client.get_embedding(
                        f"{article_data['title']} {article_data['content']}"
                    )
                    # Support async/await or immediate responses from embedding client safely
                    incoming_vector = await incoming_vector_resp if hasattr(incoming_vector_resp, "__await__") else incoming_vector_resp
                    
                    # Direct pgvector distance scan in Postgres
                    duplicate_article_id = await self.find_semantic_duplicate(
                        incoming_embedding=incoming_vector,
                        time_cutoff=time_cutoff,
                        threshold=deduplicator.semantic_threshold
                    )
                    
                    if duplicate_article_id:
                        logger.info(f"Fuzzy semantic duplicate detected against article ID {duplicate_article_id}. Skipping ingestion.")
                        return False

        # ---------------------------------------------------------------------
        # Proceed with Saving Verified Unique Article
        # ---------------------------------------------------------------------
        new_article = NewsArticle(
            source_provider=article_data["source_provider"],
            source_id=article_data["source_id"],
            title=article_data["title"],
            content=article_data["content"],
            url=article_data.get("url"),
            published_at=article_data.get("published_at"),
            unique_hash=computed_hash
        )
        
        self.session.add(new_article)
        await self.session.flush()  # Populates new_article.id safely before committing

        # Generate chunk vectors via your background embedding tier
        processed_chunks = await embedding_engine.process_document(article_data["content"])

        # Bulk stage matching vectorized chunks
        for chunk in processed_chunks:
            db_chunk = ArticleChunk(
                article_id=new_article.id,
                chunk_index=chunk["index"],
                chunk_text=chunk["text"],
                embedding=chunk["vector"]
            )
            self.session.add(db_chunk)

        await self.session.commit()
        return True

    async def save_or_update_game(self, game_dict: dict):
        """Upsert dynamic team performance data on conflict parameters."""
        stmt = insert(GameData).values(
            league=game_dict["league"],
            game_id=game_dict["game_id"],
            home_team=game_dict["home_team"],
            away_team=game_dict["away_team"],
            home_score=game_dict.get("home_score"),
            away_score=game_dict.get("away_score"),
            game_status=game_dict["game_status"],
            scheduled_at=game_dict["scheduled_at"]
        )
        
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["game_id"],
            set_={
                "home_score": stmt.excluded.home_score,
                "away_score": stmt.excluded.away_score,
                "game_status": stmt.excluded.game_status,
                "last_updated": func.now()
            }
        )
        await self.session.execute(upsert_stmt)
        await self.session.commit()