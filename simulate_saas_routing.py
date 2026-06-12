import os
import sys
import time as time_lib
from dotenv import load_dotenv
from unittest.mock import patch

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
import main

def run_saas_routing_simulation():
    print("=== SAAS MULTI-CHANNEL ROUTING SIMULATOR ===")
    
    # 1. Setup Mock Live Match Data (SofaScore event format)
    # Match 1: USA vs Paraguay - 75th minute, USA leading 2-0 (Triggers WHALE_VAULT Premium)
    current_ts = int(time_lib.time())
    mock_live_matches = [
        {
            "id": 15186873,
            "homeTeam": {"name": "USA"},
            "awayTeam": {"name": "Paraguay"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 0},
            "status": {"description": "2nd half"},
            "time": {"currentPeriodStartTimestamp": current_ts - 30 * 60}, # 75th minute
            "startTimestamp": current_ts - 75 * 60,
            "referee": {"name": "Wilmar Roldán"}
        }
    ]
    
    # Mock statistics matching the Whale Vault scenario
    mock_stats = [
        {
            "period": "ALL",
            "groups": [
                {
                    "groupName": "Match overview",
                    "statisticsItems": [
                        {"key": "ballPossession", "homeValue": 70, "awayValue": 30},
                        {"key": "shotsOnGoal", "homeValue": 10, "awayValue": 1}
                    ]
                }
            ]
        }
    ]
    
    # Mock main.py's dependencies to run a complete simulation of main()
    # - Mock load_schedule to return our test fixture
    # - Mock check_active_windows to say this USA match is active
    # - Mock fetch_live_world_cup_matches to return our mock live event
    # - Mock fetch_match_statistics to return our mock stats
    
    mock_schedule = [
        {
            "id": 15186873,
            "tournament": {
                "name": "World Cup",
                "uniqueTournament": {"name": "World Cup"}
            },
            "startTimestamp": current_ts - 75 * 60
        }
    ]
    
    print("\nSimulating live execution of main.py...")
    with patch('main.load_schedule', return_value=mock_schedule), \
         patch('main.check_active_windows', return_value=(mock_schedule, mock_schedule)), \
         patch('main.fetch_live_world_cup_matches', return_value=mock_live_matches), \
         patch('engine.fetch_match_statistics', return_value=mock_stats):
        
        main.main()
        
    print("\nSimulation complete. Check your Telegram Free Channel for the TEASER and VIP Channel for the FULL SIGNAL!")

if __name__ == "__main__":
    run_saas_routing_simulation()
