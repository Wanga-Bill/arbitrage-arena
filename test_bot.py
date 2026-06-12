import unittest
from unittest.mock import patch, MagicMock
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
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
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
        # Set up mock statistics for pressure anomaly (possession 65%, shots 5)
        # dominance_index = (65*0.4) + (5*1.5) = 33.5 (<= 68, so doesn't trigger HIGH_YIELD)
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
        self.assertFalse(anomaly['premium'])
        self.assertIn("ANOMALY DETECTED", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_corners(self, mock_stats):
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
            "startTimestamp": current_ts - 40 * 60,
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "CORNER_ANOMALY")
        self.assertFalse(anomaly['premium'])
        self.assertIn("CORNER BLITZ", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_red_card(self, mock_stats):
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
        self.assertFalse(anomaly['premium'])
        self.assertIn("RED CARD ALERT", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_card_blitz(self, mock_stats):
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
            "startTimestamp": current_ts - 30 * 60,
            "referee": {"name": "Slavko Vincic"},
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "CARD_BLITZ")
        self.assertFalse(anomaly['premium'])
        self.assertIn("CARD BLITZ WARNING", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_whale_vault(self, mock_stats):
        # Set up mock statistics for Whale Vault (2-0 lead, elapsed 75)
        # dominance_index = (70*0.4) + (10*1.5) = 43.0
        # calculate_live_probability(75, 43, 2, 0) -> differential 2, time factor 0.83 -> prob = 0.95 (> 0.92)
        mock_stats.return_value = [
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
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "2nd half"},
            "time": {"currentPeriodStartTimestamp": current_ts - 30 * 60}, # 75th minute
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "WHALE_VAULT")
        self.assertTrue(anomaly['premium'])
        self.assertIn("WHALE VAULT: MAX STAKE SURE SIGNAL", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_high_yield(self, mock_stats):
        # Set up mock statistics for High Yield (scoreless, min 35, dominance > 68)
        # dominance_index = (70*0.4) + (28*1.5) = 28 + 42 = 70.0 (> 68)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 70, "awayValue": 30},
                            {"key": "shotsOnGoal", "homeValue": 28, "awayValue": 0}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 35 * 60, # 35th minute
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "HIGH_YIELD")
        self.assertTrue(anomaly['premium'])
        self.assertIn("HIGH-YIELD VALUE RADAR", anomaly['message'])

    @patch('main.load_schedule')
    @patch('main.fetch_live_world_cup_matches')
    def test_main_no_games_today(self, mock_live, mock_schedule):
        mock_schedule.return_value = [
            {
                "id": 999,
                "tournament": {
                    "name": "World Cup",
                    "uniqueTournament": {"name": "World Cup"}
                },
                "startTimestamp": 1000000000
            }
        ]
        
        with patch('main.logging.info') as mock_log:
            main.main()
            mock_log.assert_any_call("API Guardrail: No World Cup matches scheduled for today. Exiting.")
            mock_live.assert_not_called()

if __name__ == '__main__':
    unittest.main()
