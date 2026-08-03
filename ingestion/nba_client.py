import datetime
from typing import List
from nba_api.live.nba.endpoints import scoreboard
from schemas.normalized import GameStatus, GameDataSchema

class NBAIngestionClient:
    def fetch_live_games(self) -> List[GameDataSchema]:
        try:
            sb = scoreboard.ScoreBoard()
            games_dict = sb.get_dict()
            games_list = games_dict.get("scoreboard", {}).get("games", [])
        except Exception as e:
            import traceback
            traceback.print_exc() # This will print the exact line and key that failed to your terminal
            return []

        normalized_games = []
        for g in games_list:
            status_text = g.get("gameStatusText", "").lower()
            if "final" in status_text:
                status = GameStatus.FINAL
            elif "q" in status_text or "ot" in status_text or g.get("gameStatus") == 2:
                status = GameStatus.LIVE
            else:
                status = GameStatus.SCHEDULED

            game_data = GameDataSchema(
                game_id=f"nba_{g.get('gameId')}",
                sport="NBA",
                home_team=g.get("homeTeam", {}).get("teamName", "Unknown"),
                away_team=g.get("awayTeam", {}).get("teamName", "Unknown"),
                home_score=g.get("homeTeam", {}).get("score", 0),
                away_score=g.get("awayTeam", {}).get("score", 0),
                status=status,
                game_datetime=g.get("gameTimeUTC", datetime.datetime.utcnow().isoformat())
            )
            normalized_games.append(game_data)
        return normalized_games