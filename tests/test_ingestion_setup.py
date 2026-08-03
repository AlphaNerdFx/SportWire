import logging
import sys
import os

# Ensure the project root is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingestion.adapters.nba_api_adapter import NbaApiAdapter

# Setup basic logging to see what's happening
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def test_nba_adapter():
    print("--- Starting NBA API Adapter Test ---")
    
    # Initialize the adapter
    adapter = NbaApiAdapter()
    
    # Run the ingestion cycle
    results = adapter.run()
    
    # Validate results
    if not results:
        print("Test FAILED: No data returned. Check your internet connection or NBA API status.")
        return

    print(f"Test PASSED: Successfully retrieved {len(results)} games.")
    
    # Print the first game object to verify schema alignment
    sample = results[0]
    print("\n--- Sample Normalized Game Data ---")
    print(f"Game ID: {sample.game_id}")
    print(f"Matchup: {sample.away_team} vs {sample.home_team}")
    print(f"Status: {sample.status}")
    print(f"Score: {sample.away_score}-{sample.home_score}")
    print("-" * 30)

if __name__ == "__main__":
    test_nba_adapter()