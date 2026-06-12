import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import time as time_lib

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
import bot
import engine
import main

class TestWorldCupBot(unittest.TestCase):
    
    def setUp(self):
        # Clear files before each test
        for f in [main.SCHEDULE_FILE, main.SENT_ALERTS_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def tearDown(self):
        # Clean up files after each test
        for f in [main.SCHEDULE_FILE, main.SENT_ALERTS_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    @patch('bot.requests.post')
    def test_send_telegram_alert_success(self, mock_post):
        # Configure mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Override config credentials
        Config.TELEGRAM_BOT_TOKEN = "mock_token"
        Config.FREE_CHANNEL_ID = "mock_free_id"
        Config.PREMIUM_CHANNEL_ID = "mock_premium_id"
        
        result = bot.send_telegram_alert("Hello world", is_premium=False)
        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("botmock_token/sendMessage", args[0])
        self.assertEqual(kwargs['json']['chat_id'], "mock_free_id")

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_pressure(self, mock_stats):
        # Set up mock statistics for pressure anomaly
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 65, "awayValue": 35},
                            {"key": "shotsOnGoal", "homeValue": 5, "awayValue": 1},
                            {"key": "cornerKicks", "homeValue": 2, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 35 * 60, # 35 minutes ago
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "PRESSURE_ANOMALY")
        self.assertIn("ANOMALY DETECTED", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_corners(self, mock_stats):
        # Set up mock statistics for corner anomaly
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 50, "awayValue": 50},
                            {"key": "shotsOnGoal", "homeValue": 2, "awayValue": 2},
                            {"key": "cornerKicks", "homeValue": 4, "awayValue": 4}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 40 * 60, # 40 minutes ago
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "CORNER_ANOMALY")
        self.assertIn("CORNER BLITZ", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_red_card(self, mock_stats):
        # Set up mock statistics for red card anomaly (1 red card for Team B)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "yellowCards", "homeValue": 1, "awayValue": 2},
                            {"key": "redCards", "homeValue": 0, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "2nd half"},
            "time": {"currentPeriodStartTimestamp": current_ts - 15 * 60}, # 60th minute total
            "referee": {"name": "Ivan Barton"},
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 1},
            "awayScore": {"current": 1}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "RED_CARD_ANOMALY")
        self.assertIn("RED CARD ALERT", anomaly['message'])
        self.assertIn("Team B", anomaly['message'])
        self.assertIn("Ivan Barton", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_card_blitz(self, mock_stats):
        # Set up mock statistics for card blitz (4 yellow cards total at min 30)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "yellowCards", "homeValue": 2, "awayValue": 2},
                            {"key": "redCards", "homeValue": 0, "awayValue": 0}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 30 * 60, # 30 minutes ago
            "referee": {"name": "Slavko Vincic"},
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "CARD_BLITZ")
        self.assertIn("CARD BLITZ WARNING", anomaly['message'])
        self.assertIn("Slavko Vincic", anomaly['message'])

    @patch('main.load_schedule')
    @patch('main.fetch_live_world_cup_matches')
    def test_main_no_games_today(self, mock_live, mock_schedule):
        # Mock schedule with only games in the distant past/future (not today)
        mock_schedule.return_value = [
            {
                "id": 999,
                "tournament": {
                    "name": "World Cup",
                    "uniqueTournament": {"name": "World Cup"}
                },
                "startTimestamp": 1000000000 # 2001-09-09 UTC
            }
        ]
        
        with patch('main.logging.info') as mock_log:
            main.main()
            mock_log.assert_any_call("API Guardrail: No World Cup matches scheduled for today. Exiting.")
            mock_live.assert_not_called()

if __name__ == '__main__':
    unittest.main()
