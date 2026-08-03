import logging
from datetime import datetime
from typing import List, Any
# pyrefly: ignore [missing-import]
from nba_api.live.nba.endpoints import scoreboard
from ingestion.base import BaseSourceAdapter
from ingestion.schemas import NormalizedGame
from models.schemas import GameData

logger = logging.getLogger("IngestionPipeline")

class NbaApiAdapter(BaseSourceAdapter):
    """
    Adapter for official NBA API scoreboard data.
    """
    
    @property
    def source_name(self) -> str:
        return "nba_api_scoreboard"

    def fetch_raw_payload(self) -> Any:
        """Pulls the live daily scoreboard from NBA.com."""
        try:
            board = scoreboard.ScoreBoard()
            return board.get_dict()
        except Exception as e:
            logger.error(f"Failed to fetch data from NBA API: {e}")
            return None

    def normalize(self, raw_data: Any) -> List[GameData]:
        normalized_records = []
        
        # Accessing the scoreboard structure from the NBA API dictionary
        games_list = raw_data.get("scoreboard", {}).get("games", [])
        
        for game in games_list:
            try:
                # Normalize time
                game_time_str = game.get("gameTimeUTC")
                dt_utc = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                
                # Map Game Status (1: Scheduled, 2: In Progress, 3: Final)
                status_val = game.get("gameStatus", 1)
                status_map = {1: "Scheduled", 2: "Live", 3: "Finished"}
                status = status_map.get(status_val, "Unknown")
                
                home = game.get("homeTeam", {})
                away = game.get("awayTeam", {})
                
                # Build the normalized schema
                constructed = {
                    "game_id": str(game.get("gameId")),
                    "sport": "NBA",
                    "home_team": home.get("teamName", "Unknown"),
                    "away_team": away.get("teamName", "Unknown"),
                    "home_score": home.get("score", 0),
                    "away_score": away.get("score", 0),
                    "status": status,
                    "game_clock": f"{game.get('period')}Q - {game.get('gameClock', '00:00')}" if status == "Live" else None,
                    "game_time_utc": dt_utc,
                    "metadata": {
                        "game_code": game.get("gameCode"),
                        "home_tricode": home.get("teamTricode"),
                        "away_tricode": away.get("teamTricode")
                    }
                }
                
                # Validate against schema via the base class helper
                valid_game = self.safe_parse_game(constructed)
                if valid_game:
                    normalized_records.append(valid_game)
                    
            except Exception as e:
                logger.warning(f"Error normalizing game record for {game.get('gameId')}: {e}")
                continue
                
        return normalized_records

    def transform_games(self, raw_data: Any) -> List[NormalizedGame]:
        """
        Maps raw scoreboard dictionary to NormalizedGame objects.
        Handles both integer status codes from the live NBA API and
        text-based status strings used in test mock payloads.
        """
        normalized_records = []
        games_list = raw_data.get("scoreboard", {}).get("games", [])

        for game in games_list:
            try:
                game_time_str = game.get("gameTimeUTC")
                dt_utc = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))

                # Resolve status from integer code first (live API), then fall back to text (mocks/test data)
                status_int = game.get("gameStatus")
                status_text = game.get("gameStatusText", "")
                if status_int is not None:
                    int_status_map = {1: "SCHEDULED", 2: "LIVE", 3: "FINAL"}
                    game_status = int_status_map.get(status_int, "SCHEDULED")
                else:
                    text_upper = status_text.strip().upper()
                    if "FINAL" in text_upper or "CLOSED" in text_upper:
                        game_status = "FINAL"
                    elif "PROGRESS" in text_upper or "LIVE" in text_upper or "Q" in text_upper:
                        game_status = "LIVE"
                    else:
                        game_status = "SCHEDULED"

                home = game.get("homeTeam", {})
                away = game.get("awayTeam", {})

                normalized_records.append(
                    NormalizedGame(
                        league="NBA",
                        game_id=str(game.get("gameId")),
                        home_team=home.get("teamName", "Unknown"),
                        away_team=away.get("teamName", "Unknown"),
                        home_score=home.get("score", 0),
                        away_score=away.get("score", 0),
                        game_status=game_status,
                        scheduled_at=dt_utc
                    )
                )
            except Exception as e:
                logger.warning(f"Error in transform_games for game {game.get('gameId')}: {e}")
                continue

        return normalized_records

    def transform_news(self, raw_data: Any) -> list:
        """NBA API scoreboard does not provide news articles."""
        return []