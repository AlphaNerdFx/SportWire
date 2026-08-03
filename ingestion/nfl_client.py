from typing import List
import polars as pl
import nflreadpy as nfl
from schemas.normalized import GameStatus, GameDataSchema

class NFLIngestionClient:
    def fetch_current_week_games(self) -> List[GameDataSchema]:
        try:
            schedules: pl.DataFrame = nfl.load_schedules()
            current_season = nfl.get_current_season()
            current_week = nfl.get_current_week()
            
            filtered = schedules.filter(
                (pl.col("season") == current_season) & 
                (pl.col("week") == current_week)
            )
        except Exception:
            return []

        normalized_games = []
        for row in filtered.iter_rows(named=True):
            home_score = row.get("home_score")
            away_score = row.get("away_score")
            
            if home_score is not None and away_score is not None:
                status = GameStatus.FINAL
            else:
                status = GameStatus.SCHEDULED

            game_data = GameDataSchema(
                game_id=f"nfl_{row.get('game_id')}",
                sport="NFL",
                home_team=row.get("home_team", "Unknown"),
                away_team=row.get("away_team", "Unknown"),
                home_score=int(home_score) if home_score is not None else 0,
                away_score=int(away_score) if away_score is not None else 0,
                status=status,
                game_datetime=str(row.get("gameday", "")) + "T00:00:00Z" if row.get("gameday") else "2026-01-01T00:00:00Z"
            )
            normalized_games.append(game_data)
        return normalized_games